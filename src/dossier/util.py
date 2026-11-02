"""Stable ids for corpus rows. Not secrets."""

from __future__ import annotations

import hashlib


def record_id(uri: str) -> str:
    return hashlib.sha256(uri.encode()).hexdigest()[:16]


def to_int(value: object, default: int = 0) -> int:
    """An int from a loosely typed value (row cell, JSON, config). Never raises."""
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError, OverflowError):
        return default
