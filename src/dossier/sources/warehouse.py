"""Read-only DuckDB helper. Does not implement data_dumps loaders."""

from __future__ import annotations

from pathlib import Path

import duckdb


def resolve_warehouse(path: Path) -> Path:
    if path.is_dir():
        return path / "catalog.duckdb"
    return path


def connect_readonly(path: Path) -> duckdb.DuckDBPyConnection:
    db = resolve_warehouse(path)
    return duckdb.connect(str(db), read_only=True)


def has_table(conn: duckdb.DuckDBPyConnection, qualified: str) -> bool:
    if not qualified.replace("_", "").replace(".", "").isalnum():
        return False
    try:
        conn.execute(f"SELECT 1 FROM {qualified} LIMIT 0")
    except duckdb.Error:
        return False
    return True
