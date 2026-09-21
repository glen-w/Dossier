"""Ask the local corpus. Full text, then a quote, then one cited completion."""

from __future__ import annotations

import re
from dataclasses import dataclass

from dossier.cards import content_token_set, content_tokens, evidence_carries
from dossier.llm.client import CompletionRequest, LLMClient, LLMClientError, ctx_tokens_for
from dossier.store import Record

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
ASK_MODES = ("exact", "auto", "rich")
_HEADER = re.compile(
    r"^(Lens|Kind|Org|Year|Skills|Artifacts|People|Hunt):",
    re.I,
)
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


@dataclass(frozen=True)
class Answer:
    text: str
    citations: list[str]
    refused: bool
    reason: str


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
    parts = [f'"{token}"' for token in tokens if token.isalnum()]
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
    if fts_rank:
        preferred = [hit for hit in scored if hit.uri in fts_rank]
        if preferred:
            preferred.sort(key=lambda hit: (fts_rank[hit.uri], -hit.score, hit.uri))
            return preferred[:capped]
    scored.sort(key=lambda hit: (-hit.score, hit.uri))
    return scored[:capped]


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
        return _exact(question, hits)
    if mode == "auto" and not _needs_many(hits):
        exact = _exact(question, hits)
        if not exact.refused:
            return exact
    return answer_question(question, hits, client, model, prior=prior)


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
        rows = [rec for rec in rows if want in _header_values(rec.text, "Lens")]
    if kind:
        want = kind.strip().lower()
        rows = [rec for rec in rows if _header_values(rec.text, "Kind") == [want]]
    return rows


def _header_values(text: str, key: str) -> list[str]:
    prefix = key.lower() + ":"
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith(prefix):
            raw = stripped.split(":", 1)[1]
            return [part.strip().lower() for part in raw.split(",") if part.strip()]
    return []


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
    if not evidence_carries(question, f"{top.title}\n{top.text}"):
        return Answer(text="", citations=[], refused=True, reason="no direct span")
    best = ""
    best_score = -1
    question_tokens = content_tokens(question)
    for sentence in _sentences(top.text):
        if not evidence_carries(question, sentence):
            continue
        blob = content_token_set(sentence)
        score = sum(1 for token in question_tokens if token in blob)
        if score > best_score:
            best = sentence
            best_score = score
    if not best:
        return Answer(text="", citations=[], refused=True, reason="no direct span")
    return Answer(text=best[:240], citations=[top.uri], refused=False, reason="")


def _sentences(text: str) -> list[str]:
    body: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or _HEADER.match(stripped):
            continue
        body.append(stripped)
    blob = " ".join(body) if body else text.strip()
    parts = re.split(r"(?<=[.!?])\s+", blob)
    return [part.strip() for part in parts if part.strip()]
