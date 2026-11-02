"""JSON export and import of cards, spans, and answers. No record bodies."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from dossier.cards import ClaimCard, span_in_text
from dossier.store import Corpus


def export_locker(corpus: Corpus, dest: Path) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "cards": [
            {
                "id": card.id,
                "claim": card.claim,
                "citations": list(card.citations),
                "source": card.source,
                "status": card.status,
                "reason": card.reason,
                "record_id": card.record_id,
                "extras": dict(card.extras),
            }
            for card in corpus.cards()
        ],
        "answers": _answers(corpus),
    }
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return dest


@dataclass(frozen=True)
class ImportResult:
    imported: int
    skipped: int


def import_locker(corpus: Corpus, src: Path) -> ImportResult:
    """Load cards whose citations are in this locker. Skip the rest. Do not replay answers."""
    data = json.loads(Path(src).read_text(encoding="utf-8"))
    cards = data.get("cards") or []
    imported = 0
    skipped = 0
    for row in cards:
        if not isinstance(row, dict) or not row.get("id"):
            skipped += 1
            continue
        card = ClaimCard(
            id=str(row["id"]),
            claim=str(row.get("claim") or ""),
            citations=[str(c) for c in (row.get("citations") or [])],
            source=str(row.get("source") or ""),
            status=str(row.get("status") or "pending"),
            reason=str(row.get("reason") or ""),
            record_id=str(row.get("record_id") or ""),
            extras={str(k): str(v) for k, v in (row.get("extras") or {}).items() if v is not None},
        )
        if not _importable(corpus, card):
            skipped += 1
            continue
        corpus.put_card(card)
        imported += 1
    return ImportResult(imported, skipped)


def _importable(corpus: Corpus, card: ClaimCard) -> bool:
    if not card.citations:
        return False
    for uri in card.citations:
        if corpus.get_record(uri) is None:
            return False
    span = (card.extras.get("span") or "").strip()
    if not span:
        return True
    pinned = (card.extras.get("span_uri") or "").strip()
    targets = [pinned] if pinned else list(card.citations)
    for uri in targets:
        record = corpus.get_record(uri)
        if record is not None and span_in_text(span, record.text):
            return True
    return False


def _answers(corpus: Corpus) -> list[dict]:
    rows = corpus._conn.execute(
        "SELECT question, mode, text, citations, refused, reason FROM answers"
    ).fetchall()
    out: list[dict] = []
    for row in rows:
        cites = row["citations"]
        try:
            parsed = json.loads(cites or "[]")
        except json.JSONDecodeError:
            parsed = []
        out.append(
            {
                "question": row["question"],
                "mode": row["mode"],
                "text": row["text"],
                "citations": parsed,
                "refused": bool(row["refused"]),
                "reason": row["reason"] or "",
            }
        )
    return out
