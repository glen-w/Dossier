"""Stable ids for corpus rows. Not secrets."""

from __future__ import annotations

import hashlib


def record_id(uri: str) -> str:
    return hashlib.sha256(uri.encode()).hexdigest()[:16]
