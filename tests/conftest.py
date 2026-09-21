from __future__ import annotations

from pathlib import Path

import pytest

from dossier.store import Corpus


@pytest.fixture
def corpus(tmp_path: Path) -> Corpus:
    db = tmp_path / "evidence.db"
    store = Corpus(db)
    yield store
    store.close()
