#!/usr/bin/env python3
"""Read-only list of Zotero collection names and item counts.

Does not ingest, embed, or start zotero-rag-pubs. Use the printed names to
confirm the own-pubs collection before any live ingest.

Usage:
  uv run python scripts/list_zotero_collections.py
  ZOTERO_DB=~/Zotero/zotero.sqlite uv run python scripts/list_zotero_collections.py
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path


def main() -> int:
    try:
        from dossier.paths import zotero_db

        db = zotero_db()
    except ImportError:
        raw = os.environ.get("ZOTERO_DB", "").strip()
        db = Path(raw).expanduser() if raw else Path.home() / "Zotero" / "zotero.sqlite"
    if not db.is_file():
        print(f"no Zotero database at {db}", file=sys.stderr)
        print("set ZOTERO_DB to the zotero.sqlite path", file=sys.stderr)
        return 1
    conn = sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True)
    try:
        rows = conn.execute(
            """
            SELECT c.collectionName AS name, COUNT(ci.itemID) AS items
            FROM collections c
            LEFT JOIN collectionItems ci ON ci.collectionID = c.collectionID
            GROUP BY c.collectionID
            ORDER BY items DESC, name COLLATE NOCASE
            """
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        print("no collections found")
        return 0
    width = max(len(str(name)) for name, _ in rows)
    print(f"{'collection'.ljust(width)}  items")
    print(f"{'-' * width}  -----")
    for name, count in rows:
        print(f"{str(name).ljust(width)}  {count}")
    print()
    print("Confirm the own-pubs name and ~353-item scope before starting zotero-rag-pubs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
