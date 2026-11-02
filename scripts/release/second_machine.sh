#!/usr/bin/env bash
# Synthetic second-machine path: ingest → extract → approve → defend → packet.
# Assert every quoted span is at or under SPAN_MAX. No personal corpus.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export DOSSIER_DATA="$TMP"
export DOSSIER_LLM_PROVIDER=off
export DOSSIER_EXTRACT_SPAN_MAX="${DOSSIER_EXTRACT_SPAN_MAX:-320}"
uv sync --extra dev --extra render
uv run python - <<'PY'
from pathlib import Path
import os
from dossier.store import Corpus, Record
from dossier.cards import STATUS_APPROVED, ClaimCard, card_id, span_max
from dossier.show import defend_cards, write_packet

root = Path(os.environ["DOSSIER_DATA"])
corpus = Corpus(root / "evidence.db")
rec = Record(
    id="s1",
    source="slack",
    uri="slack://coastal",
    title="Note",
    text="Lens: delivered\nKind: chapter\nQuinn wrote a synthetic paper on coastal governance.",
)
corpus.upsert_record(rec)
claim = "synthetic paper on coastal governance"
corpus.put_card(
    ClaimCard(
        id=card_id(claim, [rec.uri]),
        claim=claim,
        citations=[rec.uri],
        source="slack",
        status=STATUS_APPROVED,
    )
)
spanned, unspanned = defend_cards(corpus)
assert unspanned == []
assert spanned
assert all(len(c.extras.get("span") or "") <= span_max() for c in spanned)
path = write_packet(corpus, root / "packets")
text = path.read_text(encoding="utf-8")
for line in text.splitlines():
    if line.startswith("> "):
        assert len(line[2:]) <= span_max(), line
print("ok", path)

# Render the same cards and read each file back: only stored spans and labels.
from dossier.render import render_bytes
from dossier.tailor import build_doc, select_cards

picked, bare = select_cards(corpus, "A synthetic paper on coastal governance.", limit=4)
assert picked, "nothing to render"
doc = build_doc(kind="cv", posting="A synthetic paper on coastal governance.", picked=picked, bare=bare)
for fmt in ("markdown", "html", "docx"):
    assert render_bytes(doc, fmt)
for run in doc.runs():
    assert run.strip() in doc.texts(), run
corpus.close()
PY
# Golden eval and retrieval metrics: refusals refuse, citations resolve, no model needed.
uv run dossier eval --retrieval
# Schema v2 migrates, a backup checks, and drift sees the synthetic sentence twice.
uv run python - <<'PY'
import os
import sqlite3
from pathlib import Path

from dossier.store import SCHEMA_VERSION, Corpus, Record, read_backup, text_hash

root = Path(os.environ["DOSSIER_DATA"])
live = Corpus(root / "evidence.db")
live.upsert_record(
    Record(
        id="s2",
        source="notes",
        uri="file://notes/copy.md",
        title="Copy",
        text="Quinn wrote a synthetic paper on coastal governance.",
    )
)
live.close()

path = root / "v2.db"
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
sentence = "Quinn wrote a synthetic paper on coastal governance."
conn.execute(
    "INSERT INTO records VALUES (?, ?, ?, ?, ?, ?, ?)",
    ("r", "slack", "slack://v2", "Note", sentence, "", "2020-01-01T00:00:00+00:00"),
)
conn.execute("PRAGMA user_version = 2")
conn.commit()
conn.close()
store = Corpus(path)
assert store.schema_version() == SCHEMA_VERSION
row = store._conn.execute("SELECT text_hash FROM records").fetchone()
assert row["text_hash"] == text_hash(sentence)
dest = store.backup(root / "backups" / "from-v2.db")
store.close()
info = read_backup(dest)
assert info.ok and info.records == 1
print("migrated", dest)
PY
uv run dossier drift
BACKUP="$(uv run dossier backup)"
uv run dossier restore "$BACKUP"
uv run python - <<'PY'
import os
import sqlite3
from pathlib import Path

path = Path(os.environ["DOSSIER_DATA"]) / "newer.db"
conn = sqlite3.connect(path)
conn.execute(
    "CREATE TABLE records (id TEXT PRIMARY KEY, source TEXT, uri TEXT, title TEXT, text TEXT, table_name TEXT, ingested_at TEXT)"
)
conn.execute(
    "CREATE TABLE cards (id TEXT PRIMARY KEY, claim TEXT, citations TEXT, source TEXT, record_id TEXT, status TEXT, reason TEXT, created_at TEXT, extras TEXT)"
)
conn.execute("PRAGMA user_version = 99")
conn.commit()
conn.close()
PY
if uv run dossier restore "$TMP/newer.db"; then
  echo "newer schema should refuse" >&2
  exit 1
fi
