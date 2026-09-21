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
                created_at TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

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
            INSERT INTO cards (id, claim, citations, source, record_id, status, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                claim=excluded.claim,
                citations=excluded.citations,
                source=excluded.source,
                record_id=excluded.record_id,
                status=excluded.status,
                reason=excluded.reason
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
            ),
        )
        self._conn.commit()

    def get_card(self, card_id: str) -> ClaimCard | None:
        row = self._conn.execute(
            "SELECT id, claim, citations, source, record_id, status, reason FROM cards WHERE id = ?",
            (card_id,),
        ).fetchone()
        if row is None:
            return None
        return _card_from_row(row)

    def cards(self, status: str | None = None) -> list[ClaimCard]:
        if status:
            rows = self._conn.execute(
                "SELECT id, claim, citations, source, record_id, status, reason FROM cards WHERE status = ?",
                (status,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, claim, citations, source, record_id, status, reason FROM cards"
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
        )
        self.put_card(approved)
        return approved


def _card_from_row(row: sqlite3.Row) -> ClaimCard:
    citations = json.loads(row["citations"] or "[]")
    if not isinstance(citations, list):
        citations = []
    return ClaimCard(
        id=row["id"],
        claim=row["claim"],
        citations=[str(c) for c in citations],
        source=row["source"],
        status=row["status"],
        reason=row["reason"] or "",
        record_id=row["record_id"] or "",
    )
