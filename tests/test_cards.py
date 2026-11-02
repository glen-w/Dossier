from dossier.cards import (
    STATUS_PENDING,
    STATUS_REFUSED,
    ProposedClaim,
    adjudicate,
    carrying_span,
    evidence_carries,
    sentences,
    span_is_usable,
    span_max,
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
    text = "Quinn led the Oceana BBNJ working group in 2023."
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
        text="Quinn drafted a coastal governance briefing for Oceana.",
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
        text="Quinn drafted a coastal governance briefing for Oceana.",
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


def test_empty_content_tokens_are_refused() -> None:
    status, reason = adjudicate("a", ["doc://1"], {"doc://1": "a is a letter."})
    assert status == STATUS_REFUSED
    assert "content" in reason
    assert not evidence_carries("a", "aaaa aaaa aaaa aaaa")


def test_sentences_split_on_newlines_and_drop_over_cap() -> None:
    long_line = "word " * 200
    parts = sentences(f"Short claim lives here.\n{long_line}")
    assert "Short claim lives here." in parts
    assert all(len(part) <= span_max() for part in parts)


def test_body_without_punctuation_does_not_become_the_file() -> None:
    body = "\n".join(["alpha beta gamma delta"] * 40)
    span = carrying_span("alpha beta gamma delta", body)
    assert span
    assert len(span) <= span_max()
    assert span_is_usable("alpha beta gamma delta", span)


def test_giant_first_line_is_not_a_span() -> None:
    line = "Coastal governance " + ("kelp " * 400)
    assert carrying_span("coastal governance kelp", line) == ""
