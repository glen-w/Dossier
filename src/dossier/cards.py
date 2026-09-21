"""Claim cards. Refuse a claim the records will not carry (CareerForge rule)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REFUSED = "refused"

_STOP = frozenset(
    {
        "that",
        "this",
        "with",
        "from",
        "have",
        "been",
        "were",
        "they",
        "their",
        "them",
        "into",
        "over",
        "under",
        "about",
        "which",
        "while",
        "where",
        "when",
        "your",
        "ours",
        "also",
        "than",
        "then",
        "some",
        "such",
        "only",
        "just",
        "very",
        "more",
        "most",
        "other",
        "into",
    }
)


@dataclass(frozen=True)
class ClaimCard:
    id: str
    claim: str
    citations: list[str]
    source: str
    status: str
    reason: str = ""
    record_id: str = ""
    extras: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ProposedClaim:
    claim: str
    citations: list[str]


def card_id(claim: str, citations: list[str]) -> str:
    key = claim.strip() + "\0" + "\0".join(citations)
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def evidence_carries(claim: str, evidence: str) -> bool:
    """True when evidence text can carry the claim without an LLM."""
    blob = evidence.lower()
    if not blob.strip():
        return False
    tokens = [
        w
        for w in re.findall(r"[a-z0-9]+", claim.lower())
        if len(w) >= 4 and w not in _STOP
    ]
    if not tokens:
        return True
    hits = sum(1 for t in tokens if t in blob)
    need = 1 if len(tokens) <= 3 else max(2, len(tokens) // 4)
    return hits >= need


def adjudicate(
    claim: str,
    citations: list[str],
    evidence_by_uri: dict[str, str],
) -> tuple[str, str]:
    """Return (status, reason). pending if the records carry the claim, else refused."""
    text = claim.strip()
    if not text:
        return STATUS_REFUSED, "empty claim"
    uris = [u.strip() for u in citations if u and str(u).strip()]
    if not uris:
        return STATUS_REFUSED, "no citations"
    chunks: list[str] = []
    for uri in uris:
        body = (evidence_by_uri.get(uri) or "").strip()
        if not body:
            return STATUS_REFUSED, f"citation missing or empty: {uri}"
        chunks.append(body)
    if not evidence_carries(text, "\n".join(chunks)):
        return STATUS_REFUSED, "evidence will not carry this claim"
    return STATUS_PENDING, ""
