#!/usr/bin/env bash
# Assemble Pages payload: marketing site + Sphinx guide.
# Usage: bash scripts/release/assemble_pages_site.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

OUT="${PAGES_OUT:-_site}"
GUIDE_DIR="${OUT}/guide"

if [[ ! -d website ]]; then
  echo "error: website/ missing" >&2
  exit 1
fi
if [[ ! -f docs/conf.py ]]; then
  echo "error: docs/conf.py missing" >&2
  exit 1
fi

rm -rf "$OUT"
mkdir -p "$OUT"

shopt -s dotglob nullglob
for item in website/*; do
  base="$(basename "$item")"
  if [[ "$base" == "README.md" ]]; then
    continue
  fi
  cp -a "$item" "$OUT/"
done
shopt -u dotglob nullglob

echo "Building Sphinx HTML → ${GUIDE_DIR}"
DOCS_BUILD_DIR="$GUIDE_DIR" bash scripts/release/build_docs.sh

rm -rf "${GUIDE_DIR}/.doctrees" "${GUIDE_DIR}/.buildinfo" 2>/dev/null || true

echo "OK: Pages site assembled at ${OUT}/ (guide at ${GUIDE_DIR}/)"
