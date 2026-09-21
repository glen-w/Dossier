"""Gitignored SQLite corpus + claim cards."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from dossier.cards import STATUS_APPROVED, STATUS_PENDING, ClaimCard


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class Record:
    id: str
    source: str
    uri: str
    title: str
    text: str
    table: str = ""


class Corpus:
    """Local evidence locker. Path must stay off git (`data/evidence.db`)."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self.fts_ok = False
        self.passages_fts_ok = False
        self._init()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Corpus:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _init(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS records (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                uri TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                text TEXT NOT NULL,
                table_name TEXT,
                ingested_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS cards (
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
        cols = {
            r[1] for r in self._conn.execute("PRAGMA table_info(cards)").fetchall()
        }
        if "extras" not in cols:
            self._conn.execute("ALTER TABLE cards ADD COLUMN extras TEXT")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                mode TEXT NOT NULL,
                text TEXT NOT NULL,
                citations TEXT NOT NULL,
                refused INTEGER NOT NULL,
                reason TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()
        self._ensure_fts()
        self._ensure_passages()

    def upsert_record(self, record: Record) -> None:
        self._conn.execute(
            """
            INSERT INTO records (id, source, uri, title, text, table_name, ingested_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(uri) DO UPDATE SET
                title=excluded.title,
                text=excluded.text,
                table_name=excluded.table_name,
                ingested_at=excluded.ingested_at
            """,
            (
                record.id,
                record.source,
                record.uri,
                record.title,
                record.text,
                record.table,
                _now(),
            ),
        )
        self._index_record(record)
        self._replace_passages(record)
        self._conn.commit()

    def get_record(self, uri: str) -> Record | None:
        row = self._conn.execute(
            "SELECT id, source, uri, title, text, table_name FROM records WHERE uri = ?",
            (uri,),
        ).fetchone()
        if row is None:
            return None
        return Record(
            id=row["id"],
            source=row["source"],
            uri=row["uri"],
            title=row["title"],
            text=row["text"],
            table=row["table_name"] or "",
        )

    def records(self, source: str | None = None) -> list[Record]:
        if source:
            rows = self._conn.execute(
                "SELECT id, source, uri, title, text, table_name FROM records WHERE source = ?",
                (source,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, source, uri, title, text, table_name FROM records"
            ).fetchall()
        return [
            Record(
                id=r["id"],
                source=r["source"],
                uri=r["uri"],
                title=r["title"],
                text=r["text"],
                table=r["table_name"] or "",
            )
            for r in rows
        ]

    def evidence_by_uri(self) -> dict[str, str]:
        return {r.uri: r.text for r in self.records()}

    def put_card(self, card: ClaimCard) -> None:
        self._conn.execute(
            """
            INSERT INTO cards (id, claim, citations, source, record_id, status, reason, created_at, extras)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                claim=excluded.claim,
                citations=excluded.citations,
                source=excluded.source,
                record_id=excluded.record_id,
                status=excluded.status,
                reason=excluded.reason,
                extras=excluded.extras
            """,
            (
                card.id,
                card.claim,
                json.dumps(list(card.citations)),
                card.source,
                card.record_id,
                card.status,
                card.reason,
                _now(),
                json.dumps(dict(card.extras)),
            ),
        )
        self._conn.commit()

    def get_card(self, card_id: str) -> ClaimCard | None:
        row = self._conn.execute(
            "SELECT id, claim, citations, source, record_id, status, reason, extras FROM cards WHERE id = ?",
            (card_id,),
        ).fetchone()
        if row is None:
            return None
        return _card_from_row(row)

    def cards(self, status: str | None = None) -> list[ClaimCard]:
        if status:
            rows = self._conn.execute(
                "SELECT id, claim, citations, source, record_id, status, reason, extras FROM cards WHERE status = ?",
                (status,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, claim, citations, source, record_id, status, reason, extras FROM cards"
            ).fetchall()
        return [_card_from_row(r) for r in rows]

    def approve(self, card_id: str) -> ClaimCard:
        card = self.get_card(card_id)
        if card is None:
            raise KeyError(card_id)
        if card.status != STATUS_PENDING:
            raise ValueError(f"card {card_id} is {card.status}, not pending")
        approved = ClaimCard(
            id=card.id,
            claim=card.claim,
            citations=list(card.citations),
            source=card.source,
            status=STATUS_APPROVED,
            reason="",
            record_id=card.record_id,
            extras=dict(card.extras),
        )
        self.put_card(approved)
        return approved

    def record_has_open_card(self, record_id: str) -> bool:
        if not record_id:
            return False
        row = self._conn.execute(
            """
            SELECT 1 FROM cards
            WHERE record_id = ? AND status IN (?, ?)
            LIMIT 1
            """,
            (record_id, STATUS_PENDING, STATUS_APPROVED),
        ).fetchone()
        return row is not None

    def search_fts(self, match: str, *, limit: int) -> list[tuple[str, float]] | None:
        """(uri, rank) pairs, best rank first. None when FTS5 cannot run."""
        if not self.fts_ok or not match.strip() or limit < 1:
            return None if not self.fts_ok else []
        try:
            rows = self._conn.execute(
                """
                SELECT uri, rank FROM records_fts
                WHERE records_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (match, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return None
        return [(str(row["uri"]), float(row["rank"])) for row in rows]

    def add_answer(
        self,
        *,
        question: str,
        mode: str,
        text: str,
        citations: list[str],
        refused: bool,
        reason: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO answers (question, mode, text, citations, refused, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                question,
                mode,
                text,
                json.dumps(list(citations)),
                1 if refused else 0,
                reason,
                _now(),
            ),
        )
        self._conn.commit()

    def recent_accepted_texts(self, limit: int = 3) -> list[str]:
        rows = self._conn.execute(
            """
            SELECT text FROM answers
            WHERE refused = 0 AND text != ''
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [str(row["text"]) for row in reversed(rows)]

    def _ensure_fts(self) -> None:
        existing = self._conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'records_fts'"
        ).fetchone()
        if existing is not None:
            sql = (existing[0] or "").lower()
            # Title and text only. An older index also stored source and a searchable URI.
            if "source" in sql or "unindexed" not in sql:
                self._conn.execute("DROP TABLE records_fts")
                self._conn.commit()
        try:
            self._conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS records_fts USING fts5(
                    uri UNINDEXED,
                    title,
                    text,
                    tokenize='unicode61'
                )
                """
            )
        except sqlite3.OperationalError:
            self.fts_ok = False
            return
        self.fts_ok = True
        n_fts = self._conn.execute("SELECT count(*) FROM records_fts").fetchone()[0]
        n_rec = self._conn.execute("SELECT count(*) FROM records").fetchone()[0]
        if n_fts == n_rec:
            return
        self._conn.execute("DELETE FROM records_fts")
        rows = self._conn.execute(
            "SELECT uri, title, text FROM records"
        ).fetchall()
        for row in rows:
            self._conn.execute(
                "INSERT INTO records_fts (uri, title, text) VALUES (?, ?, ?)",
                (row["uri"], row["title"], row["text"]),
            )
        self._conn.commit()

    def search_passages(self, match: str, *, limit: int) -> list[tuple[str, float]] | None:
        """Best (record uri, rank) per record. None when FTS5 cannot run."""
        if not self.passages_fts_ok or not match.strip() or limit < 1:
            return None if not self.passages_fts_ok else []
        try:
            rows = self._conn.execute(
                """
                SELECT record_uri, rank FROM passages_fts
                WHERE passages_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (match, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return None
        best: dict[str, float] = {}
        for row in rows:
            uri = str(row["record_uri"])
            rank = float(row["rank"])
            if uri not in best or rank < best[uri]:
                best[uri] = rank
        return sorted(best.items(), key=lambda item: (item[1], item[0]))

    def passage_rows(self) -> list[tuple[str, str]]:
        rows = self._conn.execute(
            "SELECT record_uri, text FROM passages ORDER BY record_uri, ordinal"
        ).fetchall()
        return [(str(row["record_uri"]), str(row["text"])) for row in rows]

    def _ensure_passages(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS passages (
                record_uri TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                text TEXT NOT NULL,
                PRIMARY KEY (record_uri, ordinal)
            )
            """
        )
        self.passages_fts_ok = False
        if self.fts_ok:
            try:
                self._conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts USING fts5(
                        record_uri UNINDEXED,
                        ordinal UNINDEXED,
                        text,
                        tokenize='unicode61'
                    )
                    """
                )
                self.passages_fts_ok = True
            except sqlite3.OperationalError:
                self.passages_fts_ok = False
        self._conn.commit()
        n_rec = self._conn.execute("SELECT count(*) FROM records").fetchone()[0]
        n_uri = self._conn.execute(
            "SELECT count(DISTINCT record_uri) FROM passages"
        ).fetchone()[0]
        if n_rec != n_uri:
            for record in self.records():
                self._replace_passages(record)
            self._conn.commit()

    def _replace_passages(self, record: Record) -> None:
        from dossier.passages import split_passages

        chunks = split_passages(record.text)
        self._conn.execute("DELETE FROM passages WHERE record_uri = ?", (record.uri,))
        if self.passages_fts_ok:
            self._delete_passage_fts(record.uri)
        for ordinal, chunk in enumerate(chunks):
            self._conn.execute(
                "INSERT INTO passages (record_uri, ordinal, text) VALUES (?, ?, ?)",
                (record.uri, ordinal, chunk),
            )
            if self.passages_fts_ok:
                self._conn.execute(
                    """
                    INSERT INTO passages_fts (record_uri, ordinal, text)
                    VALUES (?, ?, ?)
                    """,
                    (record.uri, ordinal, chunk),
                )

    def _delete_passage_fts(self, uri: str) -> None:
        rows = self._conn.execute(
            "SELECT rowid, record_uri FROM passages_fts"
        ).fetchall()
        for row in rows:
            if str(row["record_uri"]) == uri:
                self._conn.execute(
                    "DELETE FROM passages_fts WHERE rowid = ?",
                    (row["rowid"],),
                )

    def _index_record(self, record: Record) -> None:
        if not getattr(self, "fts_ok", False):
            return
        self._conn.execute("DELETE FROM records_fts WHERE uri = ?", (record.uri,))
        self._conn.execute(
            "INSERT INTO records_fts (uri, title, text) VALUES (?, ?, ?)",
            (record.uri, record.title, record.text),
        )


def _card_from_row(row: sqlite3.Row) -> ClaimCard:
    citations = json.loads(row["citations"] or "[]")
    if not isinstance(citations, list):
        citations = []
    extras_raw = {}
    try:
        extras_raw = json.loads(row["extras"] or "{}")
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        extras_raw = {}
    if not isinstance(extras_raw, dict):
        extras_raw = {}
    return ClaimCard(
        id=row["id"],
        claim=row["claim"],
        citations=[str(c) for c in citations],
        source=row["source"],
        status=row["status"],
        reason=row["reason"] or "",
        record_id=row["record_id"] or "",
        extras={str(k): str(v) for k, v in extras_raw.items() if v is not None},
    )
