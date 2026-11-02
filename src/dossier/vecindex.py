"""Nearest-passage search over vectors stored in evidence.db.

Pure Python is the floor: it streams rows, never builds the whole table in memory,
and keeps one best passage per record. `sqlite-vec` is an optional extra that can
take over the same call; both return the same shape.
"""

from __future__ import annotations

import heapq
import math
import sqlite3
import struct
from collections.abc import Iterable
from typing import Protocol


class VectorBackend(Protocol):
    name: str

    def nearest(
        self,
        conn: sqlite3.Connection,
        vector: list[float],
        model: str,
        *,
        limit: int,
        uris: frozenset[str] | None = None,
    ) -> list[tuple[str, int, float]]:
        """Best (record uri, passage ordinal, cosine) per record, highest first."""


def vector_norm(values: Iterable[float]) -> float:
    return math.sqrt(sum(float(v) * float(v) for v in values))


class PythonBackend:
    """Streaming scan. Memory is one row plus one best score per record."""

    name = "python"

    def nearest(
        self,
        conn: sqlite3.Connection,
        vector: list[float],
        model: str,
        *,
        limit: int,
        uris: frozenset[str] | None = None,
    ) -> list[tuple[str, int, float]]:
        dim = len(vector)
        qnorm = vector_norm(vector)
        if limit < 1 or dim == 0 or qnorm <= 0.0:
            return []
        want = dim * 4
        unpack = struct.Struct(f"<{dim}f").unpack
        best: dict[str, tuple[float, int]] = {}
        cursor = conn.execute(
            "SELECT record_uri, ordinal, vector, norm FROM passage_vec "
            "WHERE model = ? AND (dim = ? OR dim IS NULL)",
            (model, dim),
        )
        for uri, ordinal, blob, stored_norm in cursor:
            if uris is not None and uri not in uris:
                continue
            if len(blob) != want:
                # A truncated or other-sized vector never scores. It is not zero-padded.
                continue
            stored = unpack(blob)
            norm = float(stored_norm) if stored_norm else vector_norm(stored)
            if norm <= 0.0:
                continue
            dot = 0.0
            for a, b in zip(vector, stored, strict=True):
                dot += a * b
            score = dot / (qnorm * norm)
            prev = best.get(uri)
            if prev is None or score > prev[0]:
                best[uri] = (score, int(ordinal))
        top = heapq.nsmallest(limit, best.items(), key=lambda item: (-item[1][0], item[0]))
        return [(uri, ordinal, score) for uri, (score, ordinal) in top]


class SqliteVecBackend:
    """The same scan in C, through the optional `sqlite-vec` distance function.

    No second table and nothing to keep in sync: it reads `passage_vec` directly, so
    a re-ingest can never leave a stale index behind. It is a scan, not an ANN graph.
    A scoped call (`uris`) uses the Python backend.
    """

    name = "sqlite-vec"
    OVERFETCH = 12

    def __init__(self) -> None:
        import sqlite_vec  # noqa: F401  (import error means the extra is absent)

        self._fallback = PythonBackend()

    def _ready(self, conn: sqlite3.Connection) -> bool:
        try:
            conn.execute("SELECT vec_version()").fetchone()
            return True
        except sqlite3.OperationalError:
            pass
        try:
            import sqlite_vec

            conn.enable_load_extension(True)
            try:
                sqlite_vec.load(conn)
            finally:
                conn.enable_load_extension(False)
            conn.execute("SELECT vec_version()").fetchone()
        except (sqlite3.Error, AttributeError):
            return False
        return True

    def nearest(
        self,
        conn: sqlite3.Connection,
        vector: list[float],
        model: str,
        *,
        limit: int,
        uris: frozenset[str] | None = None,
    ) -> list[tuple[str, int, float]]:
        dim = len(vector)
        if uris is not None or limit < 1 or dim == 0 or vector_norm(vector) <= 0.0:
            return self._fallback.nearest(conn, vector, model, limit=limit, uris=uris)
        if not self._ready(conn):
            return self._fallback.nearest(conn, vector, model, limit=limit, uris=uris)
        query = struct.pack(f"<{dim}f", *[float(v) for v in vector])
        rows = conn.execute(
            """
            SELECT record_uri, ordinal, 1.0 - vec_distance_cosine(vector, ?) AS score
            FROM passage_vec
            WHERE model = ? AND dim = ? AND length(vector) = ?
            ORDER BY score DESC, record_uri, ordinal
            LIMIT ?
            """,
            (query, model, dim, dim * 4, limit * self.OVERFETCH),
        ).fetchall()
        best: dict[str, tuple[float, int]] = {}
        for uri, ordinal, score in rows:
            if score is None:
                continue
            prev = best.get(uri)
            if prev is None or score > prev[0]:
                best[uri] = (float(score), int(ordinal))
        top = heapq.nsmallest(limit, best.items(), key=lambda item: (-item[1][0], item[0]))
        return [(uri, ordinal, score) for uri, (score, ordinal) in top]


_BACKEND: VectorBackend | None = None


def _choose() -> VectorBackend:
    """`DOSSIER_VEC` = auto (default), python, or sqlite-vec."""
    import os

    wanted = os.environ.get("DOSSIER_VEC", "auto").strip().lower() or "auto"
    if wanted == "python":
        return PythonBackend()
    try:
        return SqliteVecBackend()
    except ImportError:
        if wanted == "sqlite-vec":
            raise
        return PythonBackend()


def backend() -> VectorBackend:
    global _BACKEND
    if _BACKEND is None:
        _BACKEND = _choose()
    return _BACKEND


def set_backend(new: VectorBackend | None) -> VectorBackend | None:
    """Swap the backend (tests, or the optional extra). None re-reads `DOSSIER_VEC`."""
    global _BACKEND
    previous = _BACKEND
    _BACKEND = new
    return previous
