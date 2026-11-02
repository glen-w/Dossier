from __future__ import annotations

from pathlib import Path

from dossier.cards import STATUS_APPROVED, ClaimCard, current_span, span_in_text
from dossier.match import match_posting
from dossier.show import audit_cards, render_packet, stale_spans
from dossier.store import Corpus, Record
from dossier.tailor import select_cards

SPAN = "Quinn wrote a synthetic paper on coastal governance."
CLAIM = "synthetic paper on coastal governance"


def _seed(corpus: Corpus, text: str = SPAN) -> ClaimCard:
    corpus.upsert_record(
        Record(id="r1", source="slack", uri="slack://1", title="Note", text=text)
    )
    card = ClaimCard(
        id="c1",
        claim=CLAIM,
        citations=["slack://1"],
        source="slack",
        status=STATUS_APPROVED,
        extras={"span": SPAN, "span_uri": "slack://1", "lens": "delivered", "kind": "chapter"},
    )
    corpus.put_card(card)
    return card


def test_span_in_text_ignores_whitespace() -> None:
    assert span_in_text("a  b\nc", "x a b c y")
    assert not span_in_text("", "anything")
    assert not span_in_text("a b d", "a b c")


def test_fresh_span_is_current(corpus: Corpus) -> None:
    card = _seed(corpus)
    assert current_span(corpus, card) == SPAN
    assert stale_spans(corpus) == []
    assert audit_cards(corpus) == []


def test_reingest_with_new_text_clears_the_stored_span(corpus: Corpus) -> None:
    _seed(corpus)
    corpus.upsert_record(
        Record(
            id="r1",
            source="slack",
            uri="slack://1",
            title="Note",
            text="Quinn wrote nothing about that topic any more.",
        )
    )
    after = corpus.get_card("c1")
    assert after is not None
    assert current_span(corpus, after) == ""
    assert not (after.extras.get("span") or "")


def test_drift_that_bypasses_ingest_makes_the_span_stale(corpus: Corpus) -> None:
    """An older locker may hold a span the record no longer carries."""
    card = _seed(corpus)
    corpus._conn.execute(
        "UPDATE records SET text = ? WHERE uri = ?",
        ("Quinn wrote nothing about that topic any more.", "slack://1"),
    )
    corpus._conn.commit()
    assert current_span(corpus, card) == ""
    assert [c.id for c in stale_spans(corpus)] == ["c1"]
    assert [c.id for c, _reason in audit_cards(corpus)] == ["c1"]


def test_audit_names_a_span_the_record_no_longer_holds(corpus: Corpus) -> None:
    _seed(corpus)
    corpus._conn.execute(
        "UPDATE records SET text = ? WHERE uri = ?",
        ("Quinn wrote a synthetic paper on coastal governance and later reports.", "slack://1"),
    )
    corpus._conn.commit()
    reasons = [reason for _card, reason in audit_cards(corpus)]
    assert reasons == ["stored span is no longer in the cited record"]


def test_missing_record_makes_the_span_stale(corpus: Corpus) -> None:
    card = ClaimCard(
        id="c2",
        claim=CLAIM,
        citations=["slack://gone"],
        source="slack",
        status=STATUS_APPROVED,
        extras={"span": SPAN, "span_uri": "slack://gone"},
    )
    corpus.put_card(card)
    assert current_span(corpus, card) == ""


def test_packet_and_tailor_drop_a_stale_span(corpus: Corpus) -> None:
    _seed(corpus, text="Something unrelated now.")
    text = render_packet(corpus)
    assert f"> {SPAN}" not in text
    assert CLAIM in text.split("# Not included", 1)[1]
    picked, bare = select_cards(corpus, "A paper on coastal governance.", limit=5)
    assert picked == []
    assert [card.id for card in bare] == ["c1"]


def test_packet_keeps_a_fresh_span(corpus: Corpus) -> None:
    _seed(corpus)
    assert f"> {SPAN}" in render_packet(corpus)
    picked, _bare = select_cards(corpus, "A paper on coastal governance.", limit=5)
    assert [item.card.id for item in picked] == ["c1"]


def test_match_does_not_quote_a_stale_span(corpus: Corpus, tmp_path: Path) -> None:
    _seed(corpus, text="Something unrelated now.")
    report = match_posting(corpus, "- A paper on coastal governance\n", _NoCfg())
    quotes = [item.quote for req in report.requirements for item in req.evidence]
    assert SPAN not in quotes


def test_match_quotes_a_fresh_span(corpus: Corpus) -> None:
    _seed(corpus)
    report = match_posting(corpus, "- A paper on coastal governance\n", _NoCfg())
    routes = {item.route for req in report.requirements for item in req.evidence}
    assert "span" in routes


class _NoCfg:
    ask_passages = True
    ask_fts = True
    ask_embed = False
    ask_limit = 5
    lexicon = None
    embed_model = "nomic-embed-text"


def test_doctor_deep_reports_stale_spans_and_schema(tmp_path: Path, monkeypatch, capsys) -> None:
    from dossier.cli import main
    from dossier.store import SCHEMA_VERSION

    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    monkeypatch.setenv("DOSSIER_LLM_PROVIDER", "off")
    store = Corpus(tmp_path / "evidence.db")
    _seed(store)
    store._conn.execute(
        "UPDATE records SET text = ? WHERE uri = ?",
        ("Quinn wrote a synthetic paper on coastal governance and later reports.", "slack://1"),
    )
    store._conn.commit()
    store.close()
    main(["doctor", "--deep"])
    out = capsys.readouterr().out
    assert "stale_spans: 1" in out
    assert f"schema: v{SCHEMA_VERSION}" in out
