import sqlite3
from pathlib import Path

from dossier.brief import run_pack
from dossier.config import Config
from dossier.packs import PackQuestion
from dossier.sources.pubs import HttpPubsRetriever, PubsSource, StubPubsRetriever
from dossier.store import Corpus, Record
from dossier.util import record_id


def test_pubs_fixture_load(tmp_path: Path, corpus: Corpus) -> None:
    fixture = tmp_path / "pubs.json"
    fixture.write_text(
        """
        {"records": [
          {"uri": "zotero://my-pubs/fixture-1",
           "title": "Synthetic coastal paper",
           "text": "Quinn wrote a synthetic paper on coastal governance."}
        ]}
        """,
        encoding="utf-8",
    )
    src = PubsSource(retriever=StubPubsRetriever())
    assert src.detect(fixture)
    src.load(fixture, corpus)
    recs = corpus.records("pubs")
    assert len(recs) == 1
    assert recs[0].uri == "zotero://my-pubs/fixture-1"
    assert "coastal governance" in recs[0].text


def test_http_retriever_returns_empty_without_server(corpus: Corpus, monkeypatch) -> None:
    monkeypatch.setattr("dossier.sources.pubs.collection_records", lambda: None)
    src = PubsSource()
    src.load(Path("/nonexistent/zotero-rag-pubs"), corpus)
    assert corpus.records("pubs") == []


def test_stub_retriever_loads(corpus: Corpus, monkeypatch) -> None:
    monkeypatch.setattr("dossier.sources.pubs.collection_records", lambda: None)
    rec = Record(
        id=record_id("zotero://stub/1"),
        source="pubs",
        uri="zotero://stub/1",
        title="Stub",
        text="Quinn published a stub paper on synthetic reefs.",
        table="pubs.records",
    )
    src = PubsSource(retriever=StubPubsRetriever([rec]))
    src.load(Path("/nonexistent"), corpus)
    assert corpus.records("pubs")[0].uri == rec.uri


class _Boom:
    provider = "boom"

    def check_config(self, model: str) -> tuple[bool, str]:
        return True, "ok"

    def complete(self, request) -> str:
        raise AssertionError("model should not be called")

    def complete_json(self, request) -> dict:
        raise AssertionError("model should not be called")


def test_named_collection_loads_without_a_server(
    tmp_path: Path, corpus: Corpus, monkeypatch
) -> None:
    db = _zotero_fixture(tmp_path)
    monkeypatch.setenv("ZOTERO_DB", str(db))
    monkeypatch.setenv("DOSSIER_PUBS_COLLECTION", "my pubs")

    def boom(*_args, **_kwargs):
        raise AssertionError("pubs must not open an HTTP client")

    monkeypatch.setattr("dossier.sources.pubs.httpx.Client", boom)
    src = PubsSource()
    assert src.detect(db)
    src.load(db, corpus)
    recs = {rec.uri: rec for rec in corpus.records("pubs")}
    assert set(recs) == {"zotero://CHILDKEY1", "zotero://ABCD1234"}
    assert recs["zotero://CHILDKEY1"].title == "Child chapter"
    coastal = recs["zotero://ABCD1234"]
    assert "Hale, Quinn (2019)" in coastal.text
    assert "synthetic abstract on coastal governance" in coastal.text
    assert "https://doi.org/10.1000/coast" in coastal.text
    assert all("Ocean library" not in rec.text for rec in recs.values())

    items = run_pack(
        corpus,
        [PackQuestion("publications", "What did I publish?", source="linkedin")],
        Config(ask_fts=False, ask_passages=False, ask_pubs=False),
        _Boom(),
        mode="exact",
    )
    answer = items[0][1]
    assert answer.route == "inventory"
    assert answer.text.splitlines() == [
        "- 2021 · Child chapter",
        "- 2019 · Coastal governance",
    ]
    assert answer.citations == ["zotero://CHILDKEY1", "zotero://ABCD1234"]


def test_collection_key_skips_notes_and_other_libraries(
    tmp_path: Path, corpus: Corpus, monkeypatch
) -> None:
    db = _zotero_fixture(tmp_path)
    monkeypatch.setenv("ZOTERO_DB", str(db))
    monkeypatch.setenv("DOSSIER_PUBS_COLLECTION", "COLLPUBS")

    def boom(*_args, **_kwargs):
        raise AssertionError("pubs must not open an HTTP client")

    monkeypatch.setattr("dossier.sources.pubs.httpx.Client", boom)
    src = PubsSource()
    src.load(db, corpus)
    uris = {rec.uri for rec in corpus.records("pubs")}
    assert uris == {"zotero://CHILDKEY1", "zotero://ABCD1234"}
    assert all("Meeting note" not in rec.title for rec in corpus.records("pubs"))


def test_unknown_collection_name_does_not_ingest(
    tmp_path: Path, corpus: Corpus, monkeypatch
) -> None:
    db = _zotero_fixture(tmp_path)
    monkeypatch.setenv("ZOTERO_DB", str(db))
    monkeypatch.setenv("DOSSIER_PUBS_COLLECTION", "hoops")

    def _refuse(self) -> bool:
        raise AssertionError("ping")

    monkeypatch.setattr(HttpPubsRetriever, "ping", _refuse)
    src = PubsSource()
    assert src.detect(db) is False
    src.load(db, corpus)
    assert corpus.records("pubs") == []


def test_missing_collection_does_not_call_the_server(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ZOTERO_DB", str(tmp_path / "missing.sqlite"))
    monkeypatch.setenv("DOSSIER_PUBS_COLLECTION", "my pubs")

    def _refuse(self) -> bool:
        raise AssertionError("ping")

    monkeypatch.setattr(HttpPubsRetriever, "ping", _refuse)
    src = PubsSource()
    assert src.detect(tmp_path / "nope") is False


def _zotero_fixture(tmp_path: Path) -> Path:
    db = tmp_path / "zotero.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE itemTypes (itemTypeID INTEGER PRIMARY KEY, typeName TEXT);
        CREATE TABLE items (itemID INTEGER PRIMARY KEY, key TEXT, itemTypeID INTEGER);
        CREATE TABLE deletedItems (itemID INTEGER PRIMARY KEY);
        CREATE TABLE fields (fieldID INTEGER PRIMARY KEY, fieldName TEXT);
        CREATE TABLE itemData (itemID INTEGER, fieldID INTEGER, valueID INTEGER);
        CREATE TABLE itemDataValues (valueID INTEGER PRIMARY KEY, value TEXT);
        CREATE TABLE collections (
            collectionID INTEGER PRIMARY KEY,
            collectionName TEXT,
            key TEXT,
            parentCollectionID INTEGER
        );
        CREATE TABLE collectionItems (collectionID INTEGER, itemID INTEGER);
        CREATE TABLE creators (
            creatorID INTEGER PRIMARY KEY,
            firstName TEXT,
            lastName TEXT
        );
        CREATE TABLE creatorTypes (creatorTypeID INTEGER PRIMARY KEY, creatorType TEXT);
        CREATE TABLE itemCreators (
            itemID INTEGER,
            creatorID INTEGER,
            creatorTypeID INTEGER,
            orderIndex INTEGER
        );
        INSERT INTO itemTypes VALUES (1, 'journalArticle'), (2, 'attachment'), (3, 'note');
        INSERT INTO creatorTypes VALUES (1, 'author');
        INSERT INTO fields VALUES
            (1, 'title'), (2, 'date'), (3, 'publicationTitle'), (4, 'DOI'), (5, 'abstractNote');
        INSERT INTO collections VALUES
            (1, 'my pubs', 'COLLPUBS', NULL),
            (2, 'chapters', 'COLLCHAP', 1),
            (3, 'ocean', 'COLLOCEAN', NULL);
        INSERT INTO items VALUES
            (10, 'ABCD1234', 1),
            (11, 'CHILDKEY1', 1),
            (12, 'OCEANKEY1', 1),
            (13, 'ATTACHKEY', 2),
            (14, 'DELETED01', 1),
            (15, 'NOTEKEY01', 3);
        INSERT INTO deletedItems VALUES (14);
        INSERT INTO collectionItems VALUES
            (1, 10), (2, 11), (3, 12), (1, 13), (1, 14), (1, 15);
        INSERT INTO itemDataValues VALUES (101, 'Meeting note');
        INSERT INTO itemData VALUES (15, 1, 101);
        INSERT INTO itemDataValues VALUES (100, 'Attachment pdf');
        INSERT INTO itemData VALUES (13, 1, 100);
        INSERT INTO creators VALUES (1, 'Quinn', 'Hale');
        INSERT INTO itemCreators VALUES (10, 1, 1, 0);
        """
    )
    values = {
        1: ("Coastal governance", "2019-05", "Marine Policy", "10.1000/coast", "A synthetic abstract on coastal governance."),
        2: ("Child chapter", "2021", None, None, None),
        3: ("Ocean library paper", "2018", None, None, "This ocean item must stay out."),
        4: ("Deleted paper", "2017", None, None, None),
    }
    value_id = 1
    field_ids = (1, 2, 3, 4, 5)
    item_ids = {1: 10, 2: 11, 3: 12, 4: 14}
    for slot, fields in values.items():
        for field_id, value in zip(field_ids, fields, strict=True):
            if not value:
                continue
            conn.execute(
                "INSERT INTO itemDataValues VALUES (?, ?)",
                (value_id, value),
            )
            conn.execute(
                "INSERT INTO itemData VALUES (?, ?, ?)",
                (item_ids[slot], field_id, value_id),
            )
            value_id += 1
    conn.commit()
    conn.close()
    return db
