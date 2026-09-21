"""Ask the local corpus. Full text, then a quote, then one cited completion."""

from __future__ import annotations

from dataclasses import dataclass, replace

from dossier.cards import (
    STATUS_APPROVED,
    carrying_span,
    content_token_set,
    content_tokens,
    evidence_carries,
    header_values,
    sentences,
)
from dossier.llm.client import CompletionRequest, LLMClient, LLMClientError, ctx_tokens_for
from dossier.store import Corpus, Record

ASK_PROMPT = """You answer a question about someone's professional work.
Use only the records below. Return JSON only:
{"answer": "...", "citations": ["uri", ...]}
Every citation must be a URI from the records. If the records do not answer
the question, return {"answer": "", "citations": []}.
Do not invent employers, dates, or titles.
@@PRIOR@@
Question: @@QUESTION@@

Records:
@@RECORDS@@
"""

MAX_HITS = 8
COSINE_NEIGHBOR = 0.34
COSINE_QUOTE = 0.82
_RRF_K = 60
ASK_MODES = ("exact", "auto", "rich")
_TRIGGERS: dict[str, tuple[str, ...]] = {
    "delivered": ("report", "paper", "chapter", "workshop"),
    "skills": ("teaching", "editing"),
    "contributions": ("authored", "coordinated"),
    "publications": ("paper", "chapter"),
    "publication": ("paper", "chapter"),
    "roles": ("position", "title"),
    "role": ("position", "title"),
}


@dataclass(frozen=True)
class Hit:
    uri: str
    title: str
    text: str
    score: int
    cosine: float = 0.0


@dataclass(frozen=True)
class Answer:
    text: str
    citations: list[str]
    refused: bool
    reason: str
    route: str = ""


def expand_tokens(question: str, lexicon: tuple[str, ...] | None) -> list[str]:
    """Add closed lens words when the question already uses one. No model."""
    tokens = content_tokens(question)
    triggered = [token for token in tokens if token in _TRIGGERS]
    if not triggered:
        return tokens
    extras: list[str] = []
    if lexicon is None:
        for token in triggered:
            extras.extend(_TRIGGERS[token])
    else:
        extras.extend(lexicon)
    seen = set(tokens)
    out = list(tokens)
    for extra in extras:
        for token in content_tokens(extra):
            if token not in seen:
                seen.add(token)
                out.append(token)
    return out


def match_query(tokens: list[str]) -> str:
    """FTS5 query over title and text. URI and source are not searchable."""
    return _column_query(tokens, ("title", "text"))


def passage_query(tokens: list[str]) -> str:
    """FTS5 query over passage text. The parent URI is stored, not indexed."""
    return _column_query(tokens, ("text",))


def _column_query(tokens: list[str], columns: tuple[str, ...]) -> str:
    parts: list[str] = []
    for token in tokens:
        if not token.isalnum():
            continue
        quoted = f'"{token}"'
        for column in columns:
            parts.append(f"{column} : {quoted}")
    return " OR ".join(parts)


def retrieve(
    records: list[Record],
    question: str,
    *,
    limit: int = 5,
    source: str | None = None,
    lens: str | None = None,
    kind: str | None = None,
    tokens: list[str] | None = None,
    fts_rank: dict[str, float] | None = None,
) -> list[Hit]:
    """Rank records by shared whole words. FTS rank wins; overlap breaks ties."""
    used = content_tokens(question) if tokens is None else list(tokens)
    capped = min(limit, MAX_HITS)
    if not used or capped < 1:
        return []
    rows = _filter_records(records, source=source, lens=lens, kind=kind)
    scored = _score(rows, used)
    # None means full text is off or unavailable. An empty map means it ran and missed.
    if fts_rank is not None:
        preferred = [hit for hit in scored if hit.uri in fts_rank]
        preferred.sort(key=lambda hit: (fts_rank[hit.uri], -hit.score, hit.uri))
        return preferred[:capped]
    scored.sort(key=lambda hit: (-hit.score, hit.uri))
    return scored[:capped]


def collect_hits(
    corpus: Corpus,
    question: str,
    cfg: object,
    *,
    limit: int,
    source: str | None = None,
    lens: str | None = None,
    kind: str | None = None,
    tokens: list[str] | None = None,
    query_vec: list[float] | None = None,
    embed_model: str = "",
) -> list[Hit]:
    """Rank records, or their passages when that knob is on."""
    lexicon = getattr(cfg, "lexicon", None)
    used = list(tokens) if tokens is not None else expand_tokens(question, lexicon)
    records = _filter_records(corpus.records(), source=source, lens=lens, kind=kind)
    passages_on = bool(getattr(cfg, "ask_passages", True))
    fts_on = bool(getattr(cfg, "ask_fts", True))
    if not passages_on:
        lexical = retrieve(
            records,
            question,
            limit=limit,
            tokens=used,
            fts_rank=_fts_rank(corpus.search_fts, match_query(used), limit, fts_on),
        )
        return _with_vectors(
            corpus,
            lexical,
            records,
            query_vec=query_vec if getattr(cfg, "ask_embed", True) else None,
            embed_model=embed_model,
            limit=min(limit, MAX_HITS),
        )
    by_uri = {rec.uri: rec for rec in records}
    rows = [(uri, text) for uri, text in corpus.passage_rows() if uri in by_uri]
    pseudo = [
        Record(
            id=f"{uri}#{index}",
            source=by_uri[uri].source,
            uri=uri,
            title=by_uri[uri].title,
            text=text,
        )
        for index, (uri, text) in enumerate(rows)
    ]
    hits = retrieve(
        pseudo,
        question,
        limit=limit,
        tokens=used,
        fts_rank=_fts_rank(
            corpus.search_passages,
            passage_query(used),
            limit,
            fts_on,
        ),
    )
    seen: set[str] = set()
    unique: list[Hit] = []
    for hit in hits:
        if hit.uri in seen:
            continue
        seen.add(hit.uri)
        unique.append(hit)
    return _with_vectors(
        corpus,
        unique,
        records,
        query_vec=query_vec if getattr(cfg, "ask_embed", True) else None,
        embed_model=embed_model,
        limit=min(limit, MAX_HITS),
    )


def approved_answer(corpus: Corpus, question: str) -> Answer | None:
    """An approved claim that carries the question. Pending cards stay out."""
    best = None
    best_score = 0
    qtokens = content_tokens(question)
    for card in corpus.cards(STATUS_APPROVED):
        if not card.claim.strip() or not card.citations:
            continue
        if not evidence_carries(question, card.claim):
            continue
        score = sum(1 for token in qtokens if token in content_token_set(card.claim))
        if score > best_score:
            best = card
            best_score = score
    if best is None:
        return None
    evidence = corpus.evidence_by_uri()
    for uri in best.citations:
        if not (evidence.get(uri) or "").strip():
            return None
    return Answer(
        text=best.claim,
        citations=list(best.citations),
        refused=False,
        reason="",
        route="exact",
    )


def _fts_rank(
    search,
    query: str,
    limit: int,
    enabled: bool,
) -> dict[str, float] | None:
    if not enabled or not query:
        return None
    found = search(query, limit=max(limit * 5, 30))
    if found is None:
        return None
    return {uri: rank for uri, rank in found}


def respond(
    question: str,
    hits: list[Hit],
    client: LLMClient,
    model: str,
    *,
    mode: str = "auto",
    prior: list[str] | None = None,
) -> Answer:
    """exact quotes a span. auto tries that first. rich always asks the model."""
    if mode not in ASK_MODES:
        mode = "auto"
    if not question.strip():
        return Answer(text="", citations=[], refused=True, reason="empty question")
    if not hits:
        return Answer(text="", citations=[], refused=True, reason="no matching records")
    if mode == "exact":
        return replace(_exact(question, hits), route="exact")
    if mode == "auto" and not _needs_many(hits):
        exact = _exact(question, hits)
        if not exact.refused:
            return replace(exact, route="exact")
    return replace(answer_question(question, hits, client, model, prior=prior), route="rich")


def answer_question(
    question: str,
    hits: list[Hit],
    client: LLMClient,
    model: str,
    *,
    prior: list[str] | None = None,
) -> Answer:
    if not question.strip():
        return Answer(text="", citations=[], refused=True, reason="empty question")
    if not hits:
        return Answer(text="", citations=[], refused=True, reason="no matching records")
    prior_block = ""
    lines = [line.strip() for line in (prior or []) if line and line.strip()]
    if lines:
        prior_block = (
            "Earlier accepted answers, for context only. Do not cite them:\n"
            + "\n".join(f"- {line}" for line in lines)
            + "\n\n"
        )
    prompt = (
        ASK_PROMPT.replace("@@PRIOR@@", prior_block)
        .replace("@@QUESTION@@", question.strip())
        .replace("@@RECORDS@@", _format_hits(hits))
    )
    req = CompletionRequest(
        model=model,
        prompt=prompt,
        json_mode=True,
        num_ctx=ctx_tokens_for(prompt),
    )
    try:
        data = client.complete_json(req)
    except LLMClientError as exc:
        return Answer(text="", citations=[], refused=True, reason=str(exc))
    return _accept(data, hits)


def _format_hits(hits: list[Hit]) -> str:
    blocks: list[str] = []
    for hit in hits:
        body = hit.text[:4000]
        blocks.append(f"URI: {hit.uri}\nTitle: {hit.title}\nText:\n{body}")
    return "\n\n".join(blocks)


def _accept(data: object, hits: list[Hit]) -> Answer:
    allowed = {hit.uri for hit in hits}
    if not isinstance(data, dict):
        return Answer(text="", citations=[], refused=True, reason="model returned no object")
    text = str(data.get("answer") or "").strip()
    raw = data.get("citations") or []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        raw = []
    citations: list[str] = []
    seen: set[str] = set()
    for item in raw:
        uri = str(item).strip()
        if not uri or uri in seen:
            continue
        seen.add(uri)
        citations.append(uri)
    if not text or not citations:
        return Answer(text="", citations=[], refused=True, reason="no cited answer")
    unknown = [uri for uri in citations if uri not in allowed]
    if unknown:
        return Answer(
            text="",
            citations=[],
            refused=True,
            reason="citation is not in the retrieved records",
        )
    cited = "\n".join(f"{hit.title}\n{hit.text}" for hit in hits if hit.uri in seen)
    if not evidence_carries(text, cited):
        return Answer(
            text="",
            citations=[],
            refused=True,
            reason="evidence will not carry this answer",
        )
    return Answer(text=text, citations=citations, refused=False, reason="")


def _filter_records(
    records: list[Record],
    *,
    source: str | None,
    lens: str | None,
    kind: str | None,
) -> list[Record]:
    rows = records
    if source:
        rows = [rec for rec in rows if rec.source == source]
    if lens:
        want = lens.strip().lower()
        rows = [rec for rec in rows if want in header_values(rec.text, "Lens")]
    if kind:
        want = kind.strip().lower()
        rows = [rec for rec in rows if header_values(rec.text, "Kind") == [want]]
    return rows


def _score(records: list[Record], tokens: list[str]) -> list[Hit]:
    scored: list[Hit] = []
    for rec in records:
        blob = content_token_set(f"{rec.title}\n{rec.text}")
        score = sum(1 for token in tokens if token in blob)
        if score:
            scored.append(Hit(uri=rec.uri, title=rec.title, text=rec.text, score=score))
    return scored


def _needs_many(hits: list[Hit]) -> bool:
    return len(hits) >= 2 and hits[0].score > 0 and hits[1].score == hits[0].score


def _exact(question: str, hits: list[Hit]) -> Answer:
    top = hits[0]
    span = carrying_span(question, top.text)
    if not span and top.cosine >= COSINE_QUOTE:
        span = _paraphrase_span(top.text)
    if not span:
        return Answer(text="", citations=[], refused=True, reason="no direct span")
    return Answer(text=span[:240], citations=[top.uri], refused=False, reason="")


def _paraphrase_span(text: str) -> str:
    """Nearest-neighbor quote. Used only when cosine already cleared the bar."""
    for sentence in sentences(text):
        if content_tokens(sentence):
            return sentence
    return ""


def _with_vectors(
    corpus: Corpus,
    lexical: list[Hit],
    records: list[Record],
    *,
    query_vec: list[float] | None,
    embed_model: str,
    limit: int,
) -> list[Hit]:
    """Full text first. Vectors fill an empty or thin set. They do not replace a rich one."""
    if query_vec is None or not embed_model or len(lexical) >= 2 or limit < 1:
        return lexical
    if corpus.vector_count(embed_model) < 1:
        return lexical
    neighbors = _vector_hits(corpus, query_vec, embed_model, records, limit)
    if not neighbors:
        return lexical
    if not lexical:
        return neighbors[:limit]
    return _fuse(lexical, neighbors, limit)


def _vector_hits(
    corpus: Corpus,
    vector: list[float],
    model: str,
    records: list[Record],
    limit: int,
) -> list[Hit]:
    by_uri = {rec.uri: rec for rec in records}
    found = corpus.nearest_passages(vector, model, limit=max(limit * 5, 30))
    hits: list[Hit] = []
    for uri, text, score in found:
        if uri not in by_uri or score < COSINE_NEIGHBOR:
            continue
        rec = by_uri[uri]
        hits.append(
            Hit(
                uri=uri,
                title=rec.title,
                text=text,
                score=max(1, int(score * 100)),
                cosine=score,
            )
        )
    return hits


def _fuse(lexical: list[Hit], vector: list[Hit], limit: int) -> list[Hit]:
    scores: dict[str, float] = {}
    best: dict[str, Hit] = {}
    for rank, hit in enumerate(lexical):
        scores[hit.uri] = 1.0 / (_RRF_K + rank + 1)
        best[hit.uri] = hit
    for rank, hit in enumerate(vector):
        scores[hit.uri] = scores.get(hit.uri, 0.0) + 1.0 / (_RRF_K + rank + 1)
        prev = best.get(hit.uri)
        if prev is None:
            best[hit.uri] = hit
        elif hit.cosine > prev.cosine:
            best[hit.uri] = replace(prev, cosine=hit.cosine, text=hit.text)
    ordered = sorted(best, key=lambda uri: (-scores[uri], -best[uri].score, uri))
    return [best[uri] for uri in ordered[:limit]]
