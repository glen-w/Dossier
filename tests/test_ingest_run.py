"""Ingest progress loop."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from dossier.contributions import Contribution
from dossier.ingest_run import run_ingest_targets
from dossier.store import Corpus, Record


class _StubSource:
    name = "stub"

    def __init__(self, n: int = 2) -> None:
        self.n = n

    def detect(self, path) -> bool:  # noqa: ANN001
        return True

    def load(self, path, corpus: Corpus) -> None:  # noqa: ANN001
        for i in range(self.n):
            uri = f"stub://{path.name}/{i}"
            corpus.upsert_record(
                Record(
                    id=f"id{i}",
                    source="stub",
                    uri=uri,
                    title=f"t{i}",
                    text=f"body {i}",
                )
            )

    def tables(self) -> list[str]:
        return ["stub"]


def test_run_ingest_targets_progress(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    err = io.StringIO()
    monkeypatch.setattr("sys.stderr", err)
    root = tmp_path / "apps"
    root.mkdir()
    corpus = Corpus(tmp_path / "evidence.db")
    src = _StubSource(3)
    item = Contribution("applications", src)
    n_before, n_after = run_ingest_targets([(item, root)], corpus)
    corpus.close()
    assert n_after - n_before == 3
    text = err.getvalue()
    assert "ingest applications" in text
    assert "ingest done" in text
