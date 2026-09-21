"""Claim sentences copied from record text. No model."""

from __future__ import annotations

import re

from dossier.cards import (
    STATUS_PENDING,
    ClaimCard,
    ProposedClaim,
    adjudicate,
    card_id,
    evidence_carries,
)
from dossier.store import Corpus, Record

_PLAIN_SOURCES = frozenset({"employer", "git", "chatgpt"})
_LINKEDIN_TABLES = frozenset(
    {
        "linkedin.positions",
        "linkedin.education",
        "linkedin.skills",
        "linkedin.publications",
    }
)
_HEADER = re.compile(
    r"^(Lens|Kind|Org|Year|Skills|Artifacts|People|Hunt):\s*(.*)$",
    re.I,
)


def draft_record(record: Record, corpus: Corpus) -> list[ClaimCard]:
    """One pending card when the sentence is already in the record. Else nothing."""
    proposal = _proposal(record)
    if proposal is None:
        return []
    evidence = corpus.evidence_by_uri()
    if record.uri not in evidence:
        evidence = {**evidence, record.uri: record.text}
    status, reason = adjudicate(proposal.claim, proposal.citations, evidence)
    if status != STATUS_PENDING:
        return []
    card = ClaimCard(
        id=card_id(proposal.claim, proposal.citations),
        claim=proposal.claim,
        citations=list(proposal.citations),
        source=record.source,
        status=status,
        reason=reason,
        record_id=record.id,
        extras=dict(proposal.extras),
    )
    corpus.put_card(card)
    return [card]


def _proposal(record: Record) -> ProposedClaim | None:
    if record.table in _LINKEDIN_TABLES or record.uri.startswith("linkedin://"):
        return _linkedin(record)
    headers = _headers(record.text)
    if "lens" in headers and "kind" in headers:
        return _seeker(record, headers)
    if record.source in _PLAIN_SOURCES:
        return _plain(record)
    return None


def _plain(record: Record) -> ProposedClaim | None:
    """A sentence already in an export, employer file, or commit subject."""
    if "Binary body not ingested" in record.text:
        return None
    sentence = _first_body(record.text)
    if sentence and evidence_carries(sentence, record.text):
        return ProposedClaim(claim=sentence, citations=[record.uri])
    title = record.title.strip()
    if title and evidence_carries(title, record.text):
        return ProposedClaim(claim=title, citations=[record.uri])
    return None


def _linkedin(record: Record) -> ProposedClaim | None:
    if record.table == "linkedin.skills" or record.uri == "linkedin://skills":
        claim = record.text.strip()
    else:
        claim = record.title.strip()
    if not claim or not evidence_carries(claim, record.text):
        claim = _first_body(record.text)
    if not claim or not evidence_carries(claim, record.text):
        return None
    return ProposedClaim(claim=claim, citations=[record.uri])


def _seeker(record: Record, headers: dict[str, str]) -> ProposedClaim | None:
    claim = record.title.strip()
    if not claim or not evidence_carries(claim, record.text):
        claim = _first_body(record.text)
    if not claim or not evidence_carries(claim, record.text):
        return None
    extras: dict[str, str] = {}
    if headers.get("lens"):
        extras["lens"] = headers["lens"].split(",")[0].strip()
    if headers.get("kind"):
        extras["kind"] = headers["kind"]
    if headers.get("org"):
        extras["org"] = headers["org"]
    if headers.get("year"):
        extras["period"] = headers["year"]
    if headers.get("skills"):
        extras["skills"] = headers["skills"]
    return ProposedClaim(claim=claim, citations=[record.uri], extras=extras)


def _headers(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in text.splitlines():
        match = _HEADER.match(line.strip())
        if not match:
            continue
        found[match.group(1).lower()] = match.group(2).strip()
    return found


def _first_body(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or _HEADER.match(stripped):
            continue
        return stripped
    return ""
