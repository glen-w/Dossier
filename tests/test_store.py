import pytest

from dossier.cards import STATUS_PENDING, STATUS_REFUSED, ClaimCard
from dossier.store import Record


def test_refused_card_cannot_be_approved(corpus) -> None:
    corpus.put_card(
        ClaimCard(
            id="nope",
            claim="Synthetic claim",
            citations=["fixture://note-1"],
            source="fixture",
            status=STATUS_REFUSED,
            reason="no citations",
        )
    )
    with pytest.raises(ValueError):
        corpus.approve("nope")


def test_card_extras_round_trip(corpus) -> None:
    corpus.put_card(
        ClaimCard(
            id="extra",
            claim="Synthetic claim for tests. Not a real job.",
            citations=["fixture://note-1"],
            source="fixture",
            status=STATUS_PENDING,
            extras={"lens": "policy"},
        )
    )
    loaded = corpus.get_card("extra")
    assert loaded is not None
    assert loaded.extras == {"lens": "policy"}


def test_upsert_replaces_text_for_the_same_uri(corpus) -> None:
    first = Record(
        id="r1",
        source="pubs",
        uri="zotero://fixture/1",
        title="One",
        text="first text about coastal governance",
    )
    corpus.upsert_record(first)
    corpus.upsert_record(
        Record(
            id="r2",
            source="pubs",
            uri=first.uri,
            title="Two",
            text="second text about coastal governance",
        )
    )
    recs = corpus.records()
    assert len(recs) == 1
    assert recs[0].text.startswith("second text")


def test_upsert_rebuilds_passages(corpus) -> None:
    corpus.upsert_record(
        Record(
            id="r1",
            source="pubs",
            uri="zotero://fixture/1",
            title="One",
            text="First block about ships.\n\nSecond block about coastal governance.",
        )
    )
    first = corpus.passage_rows()
    assert len(first) >= 2
    corpus.upsert_record(
        Record(
            id="r1",
            source="pubs",
            uri="zotero://fixture/1",
            title="One",
            text="Only one coastal block now.",
        )
    )
    again = corpus.passage_rows()
    assert len(again) == 1
    assert again[0][0] == "zotero://fixture/1"
    assert "Only one coastal block" in again[0][1]
