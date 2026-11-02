from __future__ import annotations

import random
import sqlite3
import struct
from pathlib import Path

import pytest

from conftest import needs_fts5
from dossier import ask as ask_mod
from dossier.ask import collect_hits
from dossier.embed import pack_vector
from dossier.eval import ExactConfig
from dossier.store import Corpus, Record
from dossier.vecindex import PythonBackend, SqliteVecBackend, backend, set_backend

TOPICS = ["kelp", "marsh", "harbour", "cable", "charter", "survey", "forum", "estuary"]


def _locker(path: Path, n: int = 60) -> Corpus:
    rng = random.Random(7)
    corpus = Corpus(path)
    for index in range(n):
        a, b = rng.sample(TOPICS, 2)
        corpus.upsert_record(
            Record(
                id=f"r{index}",
                source="slack" if index % 2 else "notes",
                uri=f"scale://{index}",
                title=f"Note {index}",
                text=(
                    f"Quinn studied {a} restoration near the {b} town. "
                    f"Entry {index} lists participants from the {a} committee."
                ),
            )
        )
    return corpus


@needs_fts5
@pytest.mark.parametrize("question", ["kelp restoration", "harbour committee participants", "cable survey"])
@pytest.mark.parametrize("source", [None, "slack"])
def test_fts_first_matches_the_full_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, question: str, source: str | None
) -> None:
    corpus = _locker(tmp_path / "evidence.db")
    try:
        cfg = ExactConfig()
        quick = collect_hits(corpus, question, cfg, limit=5, source=source)
        monkeypatch.setattr(ask_mod, "_fts_first", lambda *a, **k: None)
        full = collect_hits(corpus, question, cfg, limit=5, source=source)
        assert quick == full
        assert quick
    finally:
        corpus.close()


@needs_fts5
def test_fts_first_does_not_load_the_whole_locker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus = _locker(tmp_path / "evidence.db")
    try:
        def boom(*_a, **_k):
            raise AssertionError("loaded every record")

        monkeypatch.setattr(corpus, "records", boom)
        monkeypatch.setattr(corpus, "passage_rows", boom)
        hits = collect_hits(corpus, "kelp restoration", ExactConfig(), limit=5)
        assert hits
    finally:
        corpus.close()


@needs_fts5
def test_a_miss_in_full_text_still_falls_back_to_the_scan(tmp_path: Path) -> None:
    corpus = _locker(tmp_path / "evidence.db")
    try:
        assert collect_hits(corpus, "zzzz qqqq", ExactConfig(), limit=5) == []
    finally:
        corpus.close()


def _vec(*values: float) -> list[float]:
    return list(values)


def test_python_backend_ranks_by_cosine_and_keeps_one_passage_per_record(tmp_path: Path) -> None:
    corpus = Corpus(tmp_path / "evidence.db")
    try:
        for uri, text in (("a", "alpha text."), ("b", "beta text."), ("c", "gamma text.")):
            corpus.upsert_record(Record(id=uri, source="s", uri=uri, title=uri, text=text))
        corpus.upsert_vector("a", 0, "m", _vec(1, 0, 0))
        corpus.upsert_vector("b", 0, "m", _vec(0.9, 0.1, 0))
        corpus.upsert_vector("c", 0, "m", _vec(0, 1, 0))
        found = corpus.nearest_passages(_vec(1, 0, 0), "m", limit=2)
        assert [uri for uri, _t, _s in found] == ["a", "b"]
        assert found[0][2] == pytest.approx(1.0)
        assert found[0][1] == "alpha text."
        scoped = corpus.nearest_passages(_vec(1, 0, 0), "m", limit=3, uris=frozenset({"c"}))
        assert [uri for uri, _t, _s in scoped] == ["c"]
    finally:
        corpus.close()


def test_other_models_and_other_sizes_never_score(tmp_path: Path) -> None:
    corpus = Corpus(tmp_path / "evidence.db")
    try:
        corpus.upsert_record(Record(id="a", source="s", uri="a", title="a", text="alpha text."))
        corpus.upsert_vector("a", 0, "old", _vec(1, 0, 0))
        assert corpus.nearest_passages(_vec(1, 0, 0), "new", limit=3) == []
        assert corpus.nearest_passages(_vec(1, 0), "old", limit=3) == []
    finally:
        corpus.close()


def test_truncated_vector_blob_is_skipped_not_zero_padded(tmp_path: Path) -> None:
    corpus = Corpus(tmp_path / "evidence.db")
    try:
        corpus.upsert_record(Record(id="a", source="s", uri="a", title="a", text="alpha text."))
        corpus.upsert_record(Record(id="b", source="s", uri="b", title="b", text="beta text."))
        corpus.upsert_vector("b", 0, "m", _vec(1, 0, 0))
        corpus._conn.execute(
            "INSERT INTO passage_vec (record_uri, ordinal, model, vector, norm, dim) "
            "VALUES ('a', 0, 'm', ?, 1.0, 3)",
            (pack_vector([1.0, 0.0, 0.0])[:7],),
        )
        corpus._conn.commit()
        found = corpus.nearest_passages(_vec(1, 0, 0), "m", limit=5)
        assert [uri for uri, _t, _s in found] == ["b"]
    finally:
        corpus.close()


def test_backend_can_be_swapped_and_restored(tmp_path: Path) -> None:
    class Fixed:
        name = "fixed"

        def nearest(self, conn: sqlite3.Connection, vector, model, *, limit, uris=None):
            return [("a", 0, 0.5)]

    corpus = Corpus(tmp_path / "evidence.db")
    previous = set_backend(Fixed())
    try:
        assert backend().name == "fixed"
        corpus.upsert_record(Record(id="a", source="s", uri="a", title="a", text="alpha."))
        assert corpus.nearest_passages(_vec(1, 0), "m", limit=1) == [("a", "alpha.", 0.5)]
    finally:
        set_backend(previous)
        corpus.close()
    assert backend().name in {"python", "sqlite-vec"}


def test_vector_bytes_are_little_endian_float32() -> None:
    assert pack_vector([1.0]) == struct.pack("<f", 1.0)


def _have_vec() -> bool:
    try:
        SqliteVecBackend()
    except ImportError:
        return False
    probe = sqlite3.connect(":memory:")
    try:
        return SqliteVecBackend()._ready(probe)
    finally:
        probe.close()


needs_vec = pytest.mark.skipif(not _have_vec(), reason="sqlite-vec extra is not installed")


@needs_vec
def test_sqlite_vec_matches_the_python_backend(tmp_path: Path) -> None:
    rng = random.Random(3)
    corpus = Corpus(tmp_path / "evidence.db")
    try:
        for index in range(80):
            uri = f"v://{index}"
            corpus.upsert_record(
                Record(id=uri, source="s", uri=uri, title=uri, text=f"Passage number {index}.")
            )
            corpus.upsert_vector(uri, 0, "m", [rng.uniform(-1, 1) for _ in range(16)])
        query = [rng.uniform(-1, 1) for _ in range(16)]
        python = PythonBackend().nearest(corpus._conn, query, "m", limit=10)
        native = SqliteVecBackend().nearest(corpus._conn, query, "m", limit=10)
        assert [u for u, _o, _s in native] == [u for u, _o, _s in python]
        for (_u1, _o1, a), (_u2, _o2, b) in zip(native, python, strict=True):
            assert a == pytest.approx(b, abs=1e-5)
    finally:
        corpus.close()


@needs_vec
def test_sqlite_vec_skips_bad_blobs_and_honours_scope(tmp_path: Path) -> None:
    corpus = Corpus(tmp_path / "evidence.db")
    try:
        for uri in ("a", "b"):
            corpus.upsert_record(Record(id=uri, source="s", uri=uri, title=uri, text=f"{uri} text."))
        corpus.upsert_vector("b", 0, "m", [1.0, 0.0, 0.0])
        corpus._conn.execute(
            "INSERT INTO passage_vec (record_uri, ordinal, model, vector, norm, dim) "
            "VALUES ('a', 0, 'm', ?, 1.0, 3)",
            (pack_vector([1.0, 0.0, 0.0])[:7],),
        )
        corpus._conn.commit()
        native = SqliteVecBackend()
        found = native.nearest(corpus._conn, [1.0, 0.0, 0.0], "m", limit=5)
        assert [u for u, _o, _s in found] == ["b"]
        scoped = native.nearest(corpus._conn, [1.0, 0.0, 0.0], "m", limit=5, uris=frozenset({"b"}))
        assert [u for u, _o, _s in scoped] == ["b"]
    finally:
        corpus.close()


def test_env_can_force_the_python_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOSSIER_VEC", "python")
    previous = set_backend(None)
    try:
        assert backend().name == "python"
    finally:
        set_backend(previous)
