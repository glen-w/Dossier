from __future__ import annotations

from pathlib import Path

import pytest

from dossier.embed import HashEmbedder, index_passages
from dossier.eval import retrieval_metrics
from dossier.store import Corpus, Record


def test_each_route_finds_its_record_on_the_synthetic_locker() -> None:
    report = retrieval_metrics(n=30, k=3)
    assert report.queries == 30
    for route in ("lexical", "vector", "fused"):
        assert report.recall[route] >= 0.9, str(report)
        assert report.mrr[route] >= 0.8, str(report)
    assert "recall@3" in str(report)


def _locker(tmp_path: Path, n: int = 40) -> Corpus:
    corpus = Corpus(tmp_path / "evidence.db")
    for index in range(n):
        corpus.upsert_record(
            Record(
                id=f"r{index}",
                source="slack" if index % 2 else "notes",
                uri=f"idx://{index}",
                title="t",
                text=f"Quinn wrote about topic{index} for the harbour group.",
            )
        )
    return corpus


def test_indexing_embeds_everything_and_records_the_dimension(tmp_path: Path) -> None:
    corpus = _locker(tmp_path)
    try:
        total = index_passages(corpus, HashEmbedder(dim=32))
        assert total == corpus._conn.execute("SELECT count(*) FROM passages").fetchone()[0]
        assert corpus.vector_dim("hash-bow") == 32
        assert corpus.count_missing_vectors("hash-bow") == 0
    finally:
        corpus.close()


def test_indexing_can_stop_and_resume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("dossier.embed.PAGE", 8)
    corpus = _locker(tmp_path)
    try:
        embedder = HashEmbedder()
        calls = {"n": 0}

        def stop_after_first_page() -> bool:
            calls["n"] += 1
            return calls["n"] > 1

        first = index_passages(corpus, embedder, should_stop=stop_after_first_page)
        everything = corpus.count_missing_vectors("hash-bow") + first
        assert 0 < first < everything
        resumed = index_passages(corpus, embedder)
        assert resumed == everything
        assert corpus.count_missing_vectors("hash-bow") == 0
    finally:
        corpus.close()


def test_indexing_can_narrow_to_a_source_and_a_limit(tmp_path: Path) -> None:
    corpus = _locker(tmp_path)
    try:
        embedder = HashEmbedder()
        done = index_passages(corpus, embedder, sources=("notes",), limit=5)
        assert done == 5
        rows = corpus._conn.execute(
            "SELECT DISTINCT r.source FROM passage_vec v JOIN records r ON r.uri = v.record_uri"
        ).fetchall()
        assert [row[0] for row in rows] == ["notes"]
        assert corpus.count_missing_vectors("hash-bow", sources=("notes",)) == 15
        assert corpus.count_missing_vectors("hash-bow", sources=("slack",)) == 20
    finally:
        corpus.close()


def test_a_model_that_changes_size_is_refused(tmp_path: Path) -> None:
    from dossier.embed import EmbedError

    corpus = _locker(tmp_path, n=10)
    try:
        index_passages(corpus, HashEmbedder(dim=16), limit=3)
        with pytest.raises(EmbedError):
            index_passages(corpus, HashEmbedder(dim=24))
    finally:
        corpus.close()
