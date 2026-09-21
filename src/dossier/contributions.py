"""Thin explicit adapter registry.

Append a Contribution here when a source is in hand. No entry points, no
plugin directory, no import of every module under sources/.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Contribution:
    name: str


CONTRIBUTIONS: list[Contribution] = []
