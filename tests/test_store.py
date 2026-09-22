import pytest

from dossier.cards import STATUS_PENDING, STATUS_REFUSED, ClaimCard
from dossier.store import Corpus, Record


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


def test_upsert_skips_unchanged_record(corpus) -> None:
    record = Record(
        id="r1",
        source="pubs",
        uri="zotero://fixture/1",
        title="One",
        text="coastal governance token",
    )
    corpus.upsert_record(record)
    first = corpus.get_record(record.uri)
    assert first is not None
    corpus.upsert_record(record)
    again = corpus.get_record(record.uri)
    assert again is not None
    assert again.text == first.text


def test_upsert_fts_map_keeps_search(corpus) -> None:
    corpus.upsert_record(
        Record(
            id="a",
            source="pubs",
            uri="zotero://fixture/a",
            title="Alpha",
            text="obsoletexyz kelp token",
        )
    )
    corpus.upsert_record(
        Record(
            id="b",
            source="pubs",
            uri="zotero://fixture/b",
            title="Beta",
            text="ships at sea token",
        )
    )
    corpus.upsert_record(
        Record(
            id="a",
            source="pubs",
            uri="zotero://fixture/a",
            title="Alpha",
            text="revised kelp forest token",
        )
    )
    hits = corpus.search_fts("ships", limit=5)
    assert hits is not None
    assert hits[0][0] == "zotero://fixture/b"
    revised = corpus.search_fts("revised", limit=5)
    assert revised is not None
    assert revised[0][0] == "zotero://fixture/a"
    gone = corpus.search_fts("obsoletexyz", limit=5)
    assert gone == []


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


def test_passage_fts_delete_leaves_other_records(corpus) -> None:
    corpus.upsert_record(
        Record(
            id="a",
            source="pubs",
            uri="zotero://fixture/a",
            title="Alpha",
            text="Alpha token about kelp.",
        )
    )
    corpus.upsert_record(
        Record(
            id="b",
            source="pubs",
            uri="zotero://fixture/b",
            title="Beta",
            text="Beta token about ships.",
        )
    )
    corpus.upsert_record(
        Record(
            id="a",
            source="pubs",
            uri="zotero://fixture/a",
            title="Alpha",
            text="Revised token about kelp.",
        )
    )
    ships = corpus.search_passages("ships", limit=5)
    assert ships is not None
    assert ships[0][0] == "zotero://fixture/b"
    revised = corpus.search_passages("Revised", limit=5)
    assert revised is not None
    assert revised[0][0] == "zotero://fixture/a"
    gone = corpus.search_passages("Alpha", limit=5)
    assert gone == []


def test_passage_fts_delete_leaves_other_records(corpus) -> None:
    corpus.upsert_record(
        Record(
            id="a",
            source="pubs",
            uri="zotero://fixture/a",
            title="Alpha",
            text="Alpha token about kelp.",
        )
    )
    corpus.upsert_record(
        Record(
            id="b",
            source="pubs",
            uri="zotero://fixture/b",
            title="Beta",
            text="Beta token about ships.",
        )
    )
    corpus.upsert_record(
        Record(
            id="a",
            source="pubs",
            uri="zotero://fixture/a",
            title="Alpha",
            text="Revised token about kelp.",
        )
    )
    ships = corpus.search_passages("ships", limit=5)
    assert ships is not None
    assert ships[0][0] == "zotero://fixture/b"
    revised = corpus.search_passages("Revised", limit=5)
    assert revised is not None
    assert revised[0][0] == "zotero://fixture/a"
    gone = corpus.search_passages("Alpha", limit=5)
    assert gone == []


def test_empty_text_does_not_rebuild_on_reopen(tmp_path, monkeypatch) -> None:
    db = tmp_path / "evidence.db"
    corpus = Corpus(db)
    corpus.upsert_record(
        Record(id="e", source="pubs", uri="u://empty", title="Empty", text="   ")
    )
    corpus.upsert_record(
        Record(
            id="t",
            source="pubs",
            uri="u://text",
            title="Text",
            text="Coastal governance paper.",
        )
    )
    corpus.close()
    calls: list[str] = []
    original = Corpus._replace_passages

    def spy(self, record):
        calls.append(record.uri)
        return original(self, record)

    monkeypatch.setattr(Corpus, "_replace_passages", spy)
    again = Corpus(db)
    try:
        uris = {uri for uri, _ in again.passage_rows()}
        assert "u://empty" not in uris
        assert "u://text" in uris
        assert calls == []
    finally:
        again.close()
