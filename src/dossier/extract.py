"""Records in → proposed claims → refuse if uncited → pending cards."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from dossier.cards import ClaimCard, ProposedClaim, adjudicate, card_id
from dossier.drafts import draft_record
from dossier.llm.client import CompletionRequest, LLMClient, LLMClientError, ctx_tokens_for
from dossier.prompts import EXTRACT_BODY, SEEKER_TAIL, active_prompt, render
from dossier.store import Corpus, Record


@dataclass(frozen=True)
class ExtractProgress:
    """One beat of extract_corpus for UI callbacks."""

    phase: str  # start | draft | llm | llm_done | pass | done
    index: int = 0
    total: int = 0
    skipped: int = 0
    cards_added: int = 0
    source: str = ""
    title: str = ""
    use_llm: bool = False

EXTRACT_PROMPT = EXTRACT_BODY
SEEKER_PROMPT_TAIL = SEEKER_TAIL

DEFAULT_CHUNK_CHARS = 4000
DEFAULT_MAX_CHUNKS = 4
DEFAULT_TIMEOUT_SECONDS = 300.0


def lock_claims(
    record: Record,
    proposals: list[ProposedClaim],
    evidence_by_uri: dict[str, str],
) -> list[ClaimCard]:
    """Adjudicate proposals against the corpus. Uncited or unsupported → refused."""
    out: list[ClaimCard] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for prop in proposals:
        cites = [u.strip() for u in prop.citations if u and str(u).strip()]
        key = (_norm_claim(prop.claim), tuple(cites))
        if prop.claim.strip() and key in seen:
            continue
        if prop.claim.strip():
            seen.add(key)
        status, reason = adjudicate(prop.claim, cites, evidence_by_uri)
        out.append(
            ClaimCard(
                id=card_id(prop.claim, cites),
                claim=prop.claim.strip(),
                citations=cites,
                source=record.source,
                status=status,
                reason=reason,
                record_id=record.id,
                extras=dict(prop.extras),
            )
        )
    return out


def proposals_from_json(data: dict[str, Any], default_uri: str) -> list[ProposedClaim]:
    raw = data.get("claims") or []
    if not isinstance(raw, list):
        return []
    out: list[ProposedClaim] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        claim = str(item.get("claim") or "").strip()
        cites = item.get("citations") or [default_uri]
        if isinstance(cites, str):
            cites = [cites]
        if not isinstance(cites, list):
            cites = [default_uri]
        uris = [str(c).strip() or default_uri for c in cites]
        if not uris:
            uris = [default_uri]
        extras = _extras_from_item(item)
        out.append(ProposedClaim(claim=claim, citations=uris, extras=extras))
    return out


def text_chunks(
    text: str,
    *,
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
    max_chunks: int = DEFAULT_MAX_CHUNKS,
) -> list[str]:
    """Split record text into paragraph-aware windows for LLM extract."""
    raw = text.strip()
    if not raw:
        return []
    limit = max(500, int(chunk_chars))
    cap = max(1, int(max_chunks))
    if len(raw) <= limit:
        return [raw]
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", raw) if part.strip()]
    if not paragraphs:
        paragraphs = [raw]
    out: list[str] = []
    buf = ""
    for para in paragraphs:
        pieces = _hard_split(para, limit) if len(para) > limit else [para]
        for piece in pieces:
            if buf and len(buf) + 2 + len(piece) > limit:
                out.append(buf)
                if len(out) >= cap:
                    return out
                buf = piece
            else:
                buf = f"{buf}\n\n{piece}".strip() if buf else piece
    if buf and len(out) < cap:
        out.append(buf)
    return out[:cap] or [raw[:limit]]


def propose_with_llm(
    record: Record,
    client: LLMClient,
    model: str,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
    max_chunks: int = DEFAULT_MAX_CHUNKS,
    max_num_ctx: int = 32_768,
) -> list[ProposedClaim]:
    out: list[ProposedClaim] = []
    role = "extract_seeker" if record.source in {"slack", "mbox", "meetings"} else "extract"
    template = active_prompt(role)
    for piece in text_chunks(
        record.text, chunk_chars=chunk_chars, max_chunks=max_chunks
    ):
        prompt = render(
            template,
            {"URI": record.uri, "TITLE": record.title, "TEXT": piece},
        )
        req = CompletionRequest(
            model=model,
            prompt=prompt,
            json_mode=True,
            num_ctx=ctx_tokens_for(prompt, max_num_ctx=max_num_ctx),
            timeout_seconds=timeout_seconds,
            think=False,
        )
        try:
            data = client.complete_json(req)
        except LLMClientError:
            continue
        out.extend(proposals_from_json(data, record.uri))
    return out


def extract_record(
    record: Record,
    corpus: Corpus,
    client: LLMClient,
    model: str,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
    max_chunks: int = DEFAULT_MAX_CHUNKS,
    max_num_ctx: int = 32_768,
) -> list[ClaimCard]:
    proposals = propose_with_llm(
        record,
        client,
        model,
        timeout_seconds=timeout_seconds,
        chunk_chars=chunk_chars,
        max_chunks=max_chunks,
        max_num_ctx=max_num_ctx,
    )
    evidence = {record.uri: record.text}
    for prop in proposals:
        for uri in prop.citations:
            if uri in evidence:
                continue
            found = corpus.get_record(uri)
            if found is not None:
                evidence[uri] = found.text
    cards = lock_claims(record, proposals, evidence)
    for card in cards:
        corpus.put_card(card)
    return cards


def extract_corpus(
    corpus: Corpus,
    client: LLMClient,
    model: str,
    source: str | None = None,
    limit: int | None = None,
    *,
    use_llm: bool = True,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
    max_chunks: int = DEFAULT_MAX_CHUNKS,
    max_num_ctx: int = 32_768,
    on_progress: Callable[[ExtractProgress], None] | None = None,
) -> list[ClaimCard]:
    records = corpus.records(source)
    if limit is not None:
        records = records[:limit]
    open_ids = corpus.open_card_record_ids()
    work = [rec for rec in records if rec.id not in open_ids]
    skipped = len(records) - len(work)
    if on_progress is not None:
        on_progress(
            ExtractProgress(
                phase="start",
                total=len(work),
                skipped=skipped,
                use_llm=use_llm,
            )
        )
    out: list[ClaimCard] = []
    llm_on = use_llm
    for index, rec in enumerate(work, start=1):
        drafted = draft_record(rec, corpus)
        if drafted:
            out.extend(drafted)
            if on_progress is not None:
                on_progress(
                    ExtractProgress(
                        phase="draft",
                        index=index,
                        total=len(work),
                        skipped=skipped,
                        cards_added=len(drafted),
                        source=rec.source,
                        title=rec.title,
                        use_llm=use_llm,
                    )
                )
            continue
        if llm_on and _client_has_budget(client):
            if on_progress is not None:
                on_progress(
                    ExtractProgress(
                        phase="llm",
                        index=index,
                        total=len(work),
                        skipped=skipped,
                        source=rec.source,
                        title=rec.title,
                        use_llm=True,
                    )
                )
            cards = extract_record(
                rec,
                corpus,
                client,
                model,
                timeout_seconds=timeout_seconds,
                chunk_chars=chunk_chars,
                max_chunks=max_chunks,
                max_num_ctx=max_num_ctx,
            )
            if not _client_has_budget(client):
                llm_on = False
            out.extend(cards)
            if on_progress is not None:
                on_progress(
                    ExtractProgress(
                        phase="llm_done",
                        index=index,
                        total=len(work),
                        skipped=skipped,
                        cards_added=len(cards),
                        source=rec.source,
                        title=rec.title,
                        use_llm=True,
                    )
                )
            continue
        if on_progress is not None:
            on_progress(
                ExtractProgress(
                    phase="pass",
                    index=index,
                    total=len(work),
                    skipped=skipped,
                    source=rec.source,
                    title=rec.title,
                    use_llm=False,
                )
            )
    if on_progress is not None:
        on_progress(
            ExtractProgress(
                phase="done",
                index=len(work),
                total=len(work),
                skipped=skipped,
                cards_added=len(out),
                use_llm=use_llm,
            )
        )
    return out


def dump_proposals(proposals: list[ProposedClaim]) -> str:
    return json.dumps(
        {"claims": [{"claim": p.claim, "citations": p.citations} for p in proposals]}
    )


def _hard_split(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    return [text[i : i + limit] for i in range(0, len(text), limit)]


def _extras_from_item(item: dict[str, Any]) -> dict[str, str]:
    extras: dict[str, str] = {}
    for key in ("lens", "kind", "org", "period"):
        value = item.get(key)
        if value:
            extras[key] = str(value).strip()
    skills = item.get("skills")
    if isinstance(skills, list):
        joined = ", ".join(str(s).strip() for s in skills if s)
        if joined:
            extras["skills"] = joined
    elif isinstance(skills, str) and skills.strip():
        extras["skills"] = skills.strip()
    return extras


def _norm_claim(claim: str) -> str:
    return " ".join(claim.lower().split())


def _client_has_budget(client: LLMClient) -> bool:
    budget = getattr(client, "_budget", None)
    if budget is None:
        return True
    return bool(getattr(budget, "remaining", True))
