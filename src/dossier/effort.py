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

    ``balanced`` leaves loaded ask/extract knobs, timeout, and context cap
    alone, and substitutes a model only when ``[efforts.balanced]`` sets one.
    ``light`` turns extract LLM off, sets ask mode to ``exact``, and caps
    context at 8192 and timeout at 120. ``high`` sets ask ``rich`` and planner
    ``rich``, and raises timeout to 600 with the same 32768 context cap.
    """
    name = normalize_effort(effort if effort is not None else getattr(cfg, "effort", None))
    updated = replace(cfg, effort=name)
    override = _effort_model(cfg, name)
    model = override or cfg.llm_model
    if name == "light":
        return replace(
            updated,
            extract_llm=False,
            ask_mode="exact",
            llm_model=model,
            llm_timeout_seconds=120.0,
            llm_max_num_ctx=8192,
        )
    if name == "high":
        return replace(
            updated,
            ask_mode="rich",
            ask_planner="rich",
            llm_model=model,
            llm_timeout_seconds=600.0,
            llm_max_num_ctx=32_768,
        )
    if override:
        return replace(updated, llm_model=override)
    return updated


def _effort_model(cfg: "Config", name: str) -> str:
    field = {
        "light": "effort_model_light",
        "balanced": "effort_model_balanced",
        "high": "effort_model_high",
    }.get(name, "")
    return str(getattr(cfg, field, "") or "").strip()


def effort_blurb(name: str) -> str:
    name = normalize_effort(name)
    if name == "light":
        return "Extract drafts only; ask stays exact. Context 8192, timeout 120s."
    if name == "high":
        return "Ask uses rich mode and the planner. Timeout 600s."
    return "Same behaviour as today's defaults."
