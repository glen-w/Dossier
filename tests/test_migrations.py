from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from dossier.store import SCHEMA_VERSION, Corpus, LockerSchemaTooNew, Record


def _version(path: Path) -> int:
    conn = sqlite3.connect(path)
    try:
        return int(conn.execute("PRAGMA user_version").fetchone()[0])
    finally:
        conn.close()


def _make_v1(path: Path) -> None:
    """A synthetic locker as 0.10 wrote it: schema v1, vectors without a dim column."""
    store = Corpus(path)
    store.upsert_record(
        Record(id="r1", source="slack", uri="slack://1", title="Note", text="Quinn wrote a paper.")
    )
    store.upsert_vector("slack://1", 0, "m", [1.0, 0.0, 0.0])
    store.close()
    conn = sqlite3.connect(path)
    conn.execute("ALTER TABLE passage_vec DROP COLUMN dim")
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()


def test_new_locker_is_current_and_needs_no_backup(tmp_path: Path) -> None:
    path = tmp_path / "evidence.db"
    Corpus(path).close()
    assert _version(path) == SCHEMA_VERSION
    assert list(tmp_path.glob("*.pre-v*.db")) == []


def test_old_locker_is_backed_up_then_migrated(tmp_path: Path) -> None:
    path = tmp_path / "evidence.db"
    _make_v1(path)
    store = Corpus(path)
    try:
        assert _version(path) == SCHEMA_VERSION
        row = store._conn.execute("SELECT dim FROM passage_vec").fetchone()
        assert row["dim"] == 3
        assert store.get_record("slack://1") is not None
    finally:
        store.close()
    backup = tmp_path / "evidence.pre-v1.db"
    assert backup.is_file()
    assert _version(backup) == 1
    conn = sqlite3.connect(backup)
    try:
        assert conn.execute("SELECT count(*) FROM records").fetchone()[0] == 1
    finally:
        conn.close()


def test_backup_is_not_overwritten_on_reopen(tmp_path: Path) -> None:
    path = tmp_path / "evidence.db"
    _make_v1(path)
    Corpus(path).close()
    backup = tmp_path / "evidence.pre-v1.db"
    first = backup.stat().st_mtime_ns
    Corpus(path).close()
    assert backup.stat().st_mtime_ns == first


def test_locker_from_a_newer_dossier_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "evidence.db"
    Corpus(path).close()
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 5}")
    conn.commit()
    conn.close()
    with pytest.raises(LockerSchemaTooNew):
        Corpus(path)
    assert _version(path) == SCHEMA_VERSION + 5


def test_v2_locker_gains_a_text_hash(tmp_path: Path) -> None:
    path = tmp_path / "evidence.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE records (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            uri TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            text TEXT NOT NULL,
            table_name TEXT,
            ingested_at TEXT NOT NULL
        );
        CREATE TABLE cards (
            id TEXT PRIMARY KEY,
            claim TEXT NOT NULL,
            citations TEXT NOT NULL,
            source TEXT NOT NULL,
            record_id TEXT,
            status TEXT NOT NULL,
            reason TEXT,
            created_at TEXT NOT NULL,
            extras TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO records VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "r1",
            "slack",
            "slack://1",
            "Note",
            "Quinn wrote a paper.",
            "",
            "2020-01-01T00:00:00+00:00",
        ),
    )
    conn.execute("PRAGMA user_version = 2")
    conn.commit()
    conn.close()
    store = Corpus(path)
    try:
        assert store.schema_version() == SCHEMA_VERSION
        row = store._conn.execute(
            "SELECT text_hash, text_changed_at FROM records"
        ).fetchone()
        assert row["text_hash"]
        assert row["text_changed_at"] == "2020-01-01T00:00:00+00:00"
    finally:
        store.close()
    assert (tmp_path / "evidence.pre-v2.db").is_file()


def test_gitignore_covers_the_backup_name() -> None:
    root = Path(__file__).resolve().parents[1]
    lines = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "*.db" in lines
