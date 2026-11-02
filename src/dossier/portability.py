"""JSON export and import of cards, spans, and answers. No record bodies."""

from __future__ import annotations

import json
from pathlib import Path

from dossier.cards import ClaimCard
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


def import_locker(corpus: Corpus, src: Path) -> int:
    data = json.loads(Path(src).read_text(encoding="utf-8"))
    cards = data.get("cards") or []
    n = 0
    for row in cards:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        card = ClaimCard(
            id=str(row["id"]),
            claim=str(row.get("claim") or ""),
            citations=[str(c) for c in (row.get("citations") or [])],
            source=str(row.get("source") or ""),
            status=str(row.get("status") or "pending"),
            reason=str(row.get("reason") or ""),
            record_id=str(row.get("record_id") or ""),
            extras={str(k): str(v) for k, v in (row.get("extras") or {}).items()},
        )
        corpus.put_card(card)
        n += 1
    return n


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
