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
