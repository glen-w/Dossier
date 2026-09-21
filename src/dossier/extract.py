"""Records in → proposed claims → refuse if uncited → pending cards."""

from __future__ import annotations

import json
from typing import Any

from dossier.cards import ClaimCard, ProposedClaim, adjudicate, card_id
from dossier.drafts import draft_record
from dossier.llm.client import CompletionRequest, LLMClient, LLMClientError, ctx_tokens_for
from dossier.store import Corpus, Record

EXTRACT_PROMPT = """You extract professional claim sentences for a CV locker.
Return JSON only: {"claims": [{"claim": "...", "citations": ["@@URI@@"]}]}
Each claim MUST be supported by the record text. Use only this URI in citations.
If nothing is a sellable professional claim, return {"claims": []}.
Do not invent employers, titles, or dates that are not in the text.

URI: @@URI@@
Title: @@TITLE@@
Text:
@@TEXT@@
"""

SEEKER_PROMPT_TAIL = """
This record was sought as professional work evidence, not a full inbox dump.
Optional keys per claim: "lens" (delivered|skills|contributions), "kind",
"skills" (list of strings), "org", "period". Prefer the Lens/Kind/Org/Year
header when present. Still refuse anything the text will not carry.
"""


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


def propose_with_llm(
    record: Record, client: LLMClient, model: str
) -> list[ProposedClaim]:
    prompt = (
        EXTRACT_PROMPT.replace("@@URI@@", record.uri)
        .replace("@@TITLE@@", record.title)
        .replace("@@TEXT@@", record.text[:12_000])
    )
    if record.source in {"slack", "mbox", "meetings"}:
        prompt = prompt + SEEKER_PROMPT_TAIL
    req = CompletionRequest(
        model=model,
        prompt=prompt,
        json_mode=True,
        num_ctx=ctx_tokens_for(prompt),
    )
    try:
        data = client.complete_json(req)
    except LLMClientError:
        return []
    return proposals_from_json(data, record.uri)


def extract_record(
    record: Record,
    corpus: Corpus,
    client: LLMClient,
    model: str,
) -> list[ClaimCard]:
    proposals = propose_with_llm(record, client, model)
    evidence = corpus.evidence_by_uri()
    if record.uri not in evidence:
        evidence = {**evidence, record.uri: record.text}
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
) -> list[ClaimCard]:
    records = corpus.records(source)
    if limit is not None:
        records = records[:limit]
    out: list[ClaimCard] = []
    for rec in records:
        if corpus.record_has_open_card(rec.id):
            continue
        drafted = draft_record(rec, corpus)
        if drafted:
            out.extend(drafted)
            continue
        if use_llm:
            out.extend(extract_record(rec, corpus, client, model))
    return out


def dump_proposals(proposals: list[ProposedClaim]) -> str:
    return json.dumps(
        {"claims": [{"claim": p.claim, "citations": p.citations} for p in proposals]}
    )


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
