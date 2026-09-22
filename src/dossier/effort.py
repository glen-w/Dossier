"""Global LLM investment presets (Rollup-style effort).

``balanced`` matches today's defaults. ``light`` and ``high`` remap a few
ask/extract knobs at resolve time. Model ladders stay for a later wave.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dossier.config import Config

EFFORT_NAMES = ("light", "balanced", "high")
DEFAULT_EFFORT = "balanced"


def normalize_effort(raw: str | None) -> str:
    name = (raw or DEFAULT_EFFORT).strip().lower()
    if name in EFFORT_NAMES:
        return name
    return DEFAULT_EFFORT


def apply_effort(cfg: "Config", effort: str | None = None) -> "Config":
    """Return a copy of *cfg* with effort overlays applied.

    ``balanced`` leaves loaded values alone. ``light`` turns extract LLM off
    and sets ask mode to ``exact``. ``high`` sets ask ``rich`` and planner
    ``rich``.
    """
    name = normalize_effort(effort if effort is not None else getattr(cfg, "effort", None))
    updated = replace(cfg, effort=name)
    if name == "light":
        return replace(updated, extract_llm=False, ask_mode="exact")
    if name == "high":
        return replace(updated, ask_mode="rich", ask_planner="rich")
    return updated


def effort_blurb(name: str) -> str:
    name = normalize_effort(name)
    if name == "light":
        return "Extract drafts only; ask stays exact (no model completion)."
    if name == "high":
        return "Ask uses rich mode and the planner."
    return "Same behaviour as today's defaults."
