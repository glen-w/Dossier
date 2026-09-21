"""Local interview: cards, passages, one hop, then at most one completion."""

from __future__ import annotations

import re
from dataclasses import replace

from dossier.ask import (
    MAX_HITS,
    Answer,
    Hit,
    _exact,
    _needs_many,
    answer_question,
    approved_answer,
    collect_hits,
    expand_tokens,
)
from dossier.cards import content_tokens, header_values
from dossier.config import Config
from dossier.llm.client import CompletionRequest, LLMClient, LLMClientError, ctx_tokens_for
from dossier.store import Corpus

_AND = re.compile(r"\s*;\s*|\s+\band\b\s+", re.I)
_PLAN = """Split the question into at most 4 shorter questions a record search can answer.
Return JSON only: {"questions": ["...", ...]}
Do not invent employers, dates, or titles.
Question: @@QUESTION@@
"""


def conduct(
    corpus: Corpus,
    question: str,
    cfg: Config,
    client: LLMClient,
    *,
    mode: str,
    limit: int,
    source: str | None = None,
    lens: str | None = None,
    kind: str | None = None,
    prior: list[str] | None = None,
) -> Answer:
    """Answer one question. exact never calls the model."""
    if mode not in {"exact", "auto", "rich"}:
        mode = "auto"
    if not question.strip():
        return Answer(text="", citations=[], refused=True, reason="empty question", route="exact")
    if cfg.ask_cards_first:
        card = approved_answer(corpus, question)
        if card is not None:
            return card
    subs = _subquestions(question, cfg, client, mode)
    parts: list[Answer] = []
    pooled: list[Hit] = []
    for sub in subs:
        answer, hits = _without_model(
            corpus,
            sub,
            cfg,
            mode=mode,
            limit=limit,
            source=source,
            lens=lens,
            kind=kind,
        )
        parts.append(answer)
        pooled.extend(hits)
    if mode != "rich" and parts and all(not part.refused for part in parts):
        return parts[0] if len(parts) == 1 else _stitch(parts)
    if mode == "exact":
        return parts[0] if len(parts) == 1 else _partial(parts)
    merged = _dedupe(pooled)[: min(limit, MAX_HITS)]
    if not merged:
        if any(not part.refused for part in parts):
            return _partial(parts)
        reason = parts[0].reason if parts else "no matching records"
        return Answer(text="", citations=[], refused=True, reason=reason, route="exact")
    rich = answer_question(question, merged, client, cfg.llm_model, prior=prior)
    return replace(rich, route="rich")


def decompose_question(question: str, setting: str) -> list[str]:
    text = question.strip()
    if not text or setting == "off":
        return [text] if text else []
    parts = _split(text)
    if setting == "on":
        return parts[:4]
    tokens = content_tokens(text)
    if ";" in text or len(tokens) > 8 or len(parts) >= 2:
        return parts[:4]
    return [text]


def _subquestions(
    question: str,
    cfg: Config,
    client: LLMClient,
    mode: str,
) -> list[str]:
    if cfg.ask_planner == "rich" and mode != "exact":
        planned = _plan(question, client, cfg.llm_model)
        if planned:
            return planned
    return decompose_question(question, cfg.ask_decompose)


def _plan(question: str, client: LLMClient, model: str) -> list[str]:
    prompt = _PLAN.replace("@@QUESTION@@", question.strip())
    request = CompletionRequest(
        model=model,
        prompt=prompt,
        json_mode=True,
        num_ctx=ctx_tokens_for(prompt),
    )
    try:
        data = client.complete_json(request)
    except LLMClientError:
        return []
    raw = data.get("questions") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        text = str(item).strip()
        if text and content_tokens(text):
            out.append(text)
        if len(out) == 4:
            break
    return out


def _without_model(
    corpus: Corpus,
    question: str,
    cfg: Config,
    *,
    mode: str,
    limit: int,
    source: str | None,
    lens: str | None,
    kind: str | None,
) -> tuple[Answer, list[Hit]]:
    if cfg.ask_cards_first and mode != "rich":
        card = approved_answer(corpus, question)
        if card is not None:
            return card, []
    hits = collect_hits(
        corpus,
        question,
        cfg,
        limit=limit,
        source=source,
        lens=lens,
        kind=kind,
    )
    if mode == "auto" and _needs_many(hits):
        missed = Answer(
            text="",
            citations=[],
            refused=True,
            reason="needs more than one record",
            route="exact",
        )
        return missed, hits
    exact = _quote(question, hits)
    if not exact.refused:
        return exact, hits
    if cfg.ask_hops >= 1 and hits:
        extra = header_values(hits[0].text, "Lens") + header_values(hits[0].text, "Kind")
        if extra:
            base = expand_tokens(question, cfg.lexicon)
            hopped = collect_hits(
                corpus,
                question,
                cfg,
                limit=limit,
                source=source,
                lens=lens,
                kind=kind,
                tokens=_append(base, extra),
            )
            if hopped:
                again = _quote_any(question, hopped)
                if not again.refused:
                    return again, hopped
                hits = hopped
    if not hits:
        return (
            Answer(
                text="",
                citations=[],
                refused=True,
                reason="no matching records",
                route="exact",
            ),
            [],
        )
    return exact, hits


def _quote(question: str, hits: list[Hit]) -> Answer:
    if not hits:
        return Answer(
            text="",
            citations=[],
            refused=True,
            reason="no matching records",
            route="exact",
        )
    return replace(_exact(question, hits), route="exact")


def _quote_any(question: str, hits: list[Hit]) -> Answer:
    """After a hop, any retrieved span may answer. Try each hit."""
    if not hits:
        return _quote(question, hits)
    for hit in hits:
        answer = replace(_exact(question, [hit]), route="exact")
        if not answer.refused:
            return answer
    return _quote(question, hits)


def _split(text: str) -> list[str]:
    chunks = [part.strip() for part in _AND.split(text) if part.strip()]
    kept = [part for part in chunks if content_tokens(part)]
    return kept[:4] or [text.strip()]


def _append(base: list[str], extra: list[str]) -> list[str]:
    seen = set(base)
    out = list(base)
    for token in extra:
        for piece in content_tokens(token):
            if piece not in seen:
                seen.add(piece)
                out.append(piece)
    return out


def _stitch(parts: list[Answer]) -> Answer:
    texts = [part.text for part in parts if part.text]
    return Answer(
        text="\n\n".join(texts),
        citations=_citations(parts),
        refused=False,
        reason="",
        route="exact",
    )


def _partial(parts: list[Answer]) -> Answer:
    kept = [part for part in parts if part.text and not part.refused]
    reason = "incomplete" if kept else (parts[0].reason if parts else "no matching records")
    return Answer(
        text="\n\n".join(part.text for part in kept),
        citations=_citations(kept),
        refused=True,
        reason=reason,
        route="exact",
    )


def _citations(parts: list[Answer]) -> list[str]:
    out: list[str] = []
    for part in parts:
        for uri in part.citations:
            if uri not in out:
                out.append(uri)
    return out


def _dedupe(hits: list[Hit]) -> list[Hit]:
    best: dict[str, Hit] = {}
    for hit in hits:
        current = best.get(hit.uri)
        if current is None or hit.score > current.score:
            best[hit.uri] = hit
    return sorted(best.values(), key=lambda hit: (-hit.score, hit.uri))
