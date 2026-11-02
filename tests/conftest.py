from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from dossier.store import Corpus


def sqlite_has_fts5() -> bool:
    probe = sqlite3.connect(":memory:")
    try:
        probe.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
    except sqlite3.OperationalError:
        return False
    finally:
        probe.close()
    return True


needs_fts5 = pytest.mark.skipif(
    not sqlite_has_fts5(),
    reason="sqlite build has no fts5",
)


@pytest.fixture
def corpus(tmp_path: Path) -> Corpus:
    db = tmp_path / "evidence.db"
    store = Corpus(db)
    yield store
    store.close()
