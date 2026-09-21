from dossier.cards import (
    STATUS_PENDING,
    STATUS_REFUSED,
    ProposedClaim,
    adjudicate,
    evidence_carries,
)
from dossier.extract import lock_claims
from dossier.store import Record


def test_uncited_claim_is_refused() -> None:
    status, reason = adjudicate("Led a working group", [], {"doc://1": "Led a working group"})
    assert status == STATUS_REFUSED
    assert "citation" in reason


def test_empty_citation_is_refused() -> None:
    status, reason = adjudicate("Led a working group", ["doc://missing"], {})
    assert status == STATUS_REFUSED
    assert "missing" in reason


def test_substring_inside_another_word_does_not_count() -> None:
    assert not evidence_carries("port policy", "This report covers opportunity.")


def test_evidence_must_carry_the_claim() -> None:
    evidence = "shopping list: milk, eggs, butter"
    assert not evidence_carries("Led the Oceana BBNJ working group", evidence)
    status, _ = adjudicate(
        "Led the Oceana BBNJ working group",
        ["doc://1"],
        {"doc://1": evidence},
    )
    assert status == STATUS_REFUSED


def test_matching_evidence_is_pending() -> None:
    text = "Glen led the Oceana BBNJ working group in 2023."
    status, reason = adjudicate(
        "Led the Oceana BBNJ working group",
        ["doc://1"],
        {"doc://1": text},
    )
    assert status == STATUS_PENDING
    assert reason == ""


def test_lock_claims_writes_refused_and_pending() -> None:
    record = Record(
        id="r1",
        source="chatgpt",
        uri="chatgpt://c/m",
        title="Synthetic",
        text="Glen drafted a coastal governance briefing for Oceana.",
    )
    cards = lock_claims(
        record,
        [
            ProposedClaim("Drafted a coastal governance briefing", [record.uri]),
            ProposedClaim("Commanded a lunar base", [record.uri]),
            ProposedClaim("Did something", []),
        ],
        {record.uri: record.text},
    )
    by_claim = {c.claim: c.status for c in cards}
    assert by_claim["Drafted a coastal governance briefing"] == STATUS_PENDING
    assert by_claim["Commanded a lunar base"] == STATUS_REFUSED
    assert by_claim["Did something"] == STATUS_REFUSED


def test_lock_claims_drops_near_duplicate_wording() -> None:
    record = Record(
        id="r1",
        source="slack",
        uri="slack://C/1",
        title="Synthetic",
        text="Glen drafted a coastal governance briefing for Oceana.",
    )
    cards = lock_claims(
        record,
        [
            ProposedClaim("Drafted a coastal governance briefing", [record.uri]),
            ProposedClaim("  drafted a Coastal Governance briefing  ", [record.uri]),
        ],
        {record.uri: record.text},
    )
    assert len(cards) == 1
    assert cards[0].status == STATUS_PENDING
