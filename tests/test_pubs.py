from pathlib import Path

from dossier.sources.pubs import PubsSource, StubPubsRetriever
from dossier.store import Corpus, Record
from dossier.util import record_id


def test_pubs_fixture_load(tmp_path: Path, corpus: Corpus) -> None:
    fixture = tmp_path / "pubs.json"
    fixture.write_text(
        """
        {"records": [
          {"uri": "zotero://my-pubs/fixture-1",
           "title": "Synthetic coastal paper",
           "text": "Glen wrote a synthetic paper on coastal governance."}
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


def test_http_retriever_returns_empty_without_server(corpus: Corpus) -> None:
    src = PubsSource()
    src.load(Path("/nonexistent/zotero-rag-pubs"), corpus)
    assert corpus.records("pubs") == []


def test_stub_retriever_loads(corpus: Corpus) -> None:
    rec = Record(
        id=record_id("zotero://stub/1"),
        source="pubs",
        uri="zotero://stub/1",
        title="Stub",
        text="Glen published a stub paper on synthetic reefs.",
        table="pubs.records",
    )
    src = PubsSource(retriever=StubPubsRetriever([rec]))
    src.load(Path("/nonexistent"), corpus)
    assert corpus.records("pubs")[0].uri == rec.uri
