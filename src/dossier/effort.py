"""Global LLM investment presets (Rollup-style effort).

``balanced`` keeps the answer model and uses the fast model for extract.
``light`` and ``high`` remap ask/extract knobs at resolve time.
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
    alone. ``[efforts.balanced] model`` overrides the answer model only.
    The fast role stays on ``[llm] fast`` unless that preset sets ``fast``.
    ``light`` turns extract LLM off, sets ask mode to ``exact``, and caps
    context at 8192 and timeout at 120. ``high`` sets ask ``rich`` and planner
    ``rich``, raises timeout to 600, and points both roles at the answer model
    unless that preset sets ``fast``.
    """
    name = normalize_effort(effort if effort is not None else getattr(cfg, "effort", None))
    updated = replace(cfg, effort=name)
    override = _effort_field(cfg, name, "model")
    model = override or cfg.llm_model
    fast_override = _effort_field(cfg, name, "fast")
    if name == "high":
        fast = fast_override or model
    else:
        fast = fast_override or cfg.llm_fast or cfg.fast_model
    if name == "light":
        return replace(
            updated,
            extract_llm=False,
            ask_mode="exact",
            llm_model=model,
            fast_model=fast,
            llm_timeout_seconds=120.0,
            llm_max_num_ctx=8192,
        )
    if name == "high":
        return replace(
            updated,
            ask_mode="rich",
            ask_planner="rich",
            llm_model=model,
            fast_model=fast,
            llm_timeout_seconds=600.0,
            llm_max_num_ctx=32_768,
        )
    return replace(updated, llm_model=model, fast_model=fast)


def _effort_field(cfg: "Config", name: str, key: str) -> str:
    field = {
        ("light", "model"): "effort_model_light",
        ("balanced", "model"): "effort_model_balanced",
        ("high", "model"): "effort_model_high",
        ("light", "fast"): "effort_fast_light",
        ("balanced", "fast"): "effort_fast_balanced",
        ("high", "fast"): "effort_fast_high",
    }.get((name, key), "")
    return str(getattr(cfg, field, "") or "").strip()


def effort_model_tags(cfg: "Config") -> tuple[str, ...]:
    """Tags this effort will call. Light drafts and quotes, so the list is empty."""
    if not getattr(cfg, "llm_enabled", True) or normalize_effort(cfg.effort) == "light":
        return ()
    answer = str(getattr(cfg, "llm_model", "") or "").strip()
    fast = str(getattr(cfg, "fast_model", "") or "").strip()
    if normalize_effort(cfg.effort) == "high":
        tags = [answer] if answer else []
        if fast and fast not in tags:
            tags.append(fast)
        return tuple(tags)
    tags = []
    for tag in (fast, answer):
        if tag and tag not in tags:
            tags.append(tag)
    return tuple(tags)


def effort_blurb(name: str) -> str:
    name = normalize_effort(name)
    if name == "light":
        return "Extract drafts only; ask stays exact. Context 8192, timeout 120s."
    if name == "high":
        return "Ask and extract use the answer model. Ask is rich, with the planner. Timeout 600s."
    return "Extract uses the fast model. Ask uses the answer model."
