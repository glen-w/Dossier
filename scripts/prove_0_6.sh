#!/usr/bin/env bash
# Local real-corpus prove. Does not approve cards. Does not start pubs ingest.
# Usage (from repo root): bash scripts/prove_0_6.sh [--pubs] [extra dossier prove args...]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

EXTRA=()
if [[ "${1:-}" == "--pubs" ]]; then
  EXTRA+=(--pubs)
  shift
fi

exec uv run dossier prove "${EXTRA[@]}" "$@"
