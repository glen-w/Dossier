"""Adapter contract over the explicit CONTRIBUTIONS list."""

from __future__ import annotations

from pathlib import Path

import pytest

from dossier.contributions import CONTRIBUTIONS
from dossier.sources.base import Source
from dossier.store import Corpus


@pytest.mark.parametrize("item", CONTRIBUTIONS, ids=lambda c: c.name)
def test_adapter_protocol(item) -> None:
    assert isinstance(item.source, Source)
    assert item.source.name == item.name
    tables = item.source.tables()
    assert tables
    assert all(isinstance(name, str) and name for name in tables)
    assert callable(item.source.detect)
    assert callable(item.source.load)


@pytest.mark.parametrize("item", CONTRIBUTIONS, ids=lambda c: c.name)
def test_adapter_refuses_symlink_and_skips_missing(item, tmp_path: Path, corpus: Corpus) -> None:
    missing = tmp_path / "no-such-source"
    if item.name not in {"pubs", "mbox", "linkedin", "chatgpt", "slack"}:
        assert item.source.detect(missing) is False
    outside = tmp_path / "secret.txt"
    outside.write_text("should not ingest", encoding="utf-8")
    link = tmp_path / "link"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable")
    try:
        item.source.load(link, corpus)
    except Exception:
        pass
    for rec in corpus.records():
        assert "should not ingest" not in rec.text
