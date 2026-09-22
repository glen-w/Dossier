"""Which records a request may use.

Settings and profiles store the default sources, year range, and effort.
One ask, match, or brief can narrow that default without writing the file.
An empty source list means every registered source. A record with no Year
header stays in when a range is set.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from dossier.cards import header_values
from dossier.effort import EFFORT_NAMES, apply_effort
from dossier.store import Record

_YEAR = re.compile(r"\d{4}")


@dataclass(frozen=True)
class RequestScope:
    """``sources`` is None for every registered source, or a tuple that may be empty."""

    sources: tuple[str, ...] | None = None
    year_from: int = 0
    year_to: int = 0
    effort: str = ""


def known_sources() -> tuple[str, ...]:
    from dossier.contributions import CONTRIBUTIONS

    return tuple(item.name for item in CONTRIBUTIONS)


def sources_for_request(selected: list[str]) -> tuple[str, ...] | None:
    """Checked names. Every known source, or an empty selection, becomes None or ()."""
    known = known_sources()
    wanted = {name.strip() for name in selected if name.strip()}
    chosen = tuple(name for name in known if name in wanted)
    if chosen == known:
        return None
    return chosen


def parse_year(raw: str) -> int:
    text = (raw or "").strip()
    if not text:
        return 0
    if not _YEAR.fullmatch(text):
        raise ValueError("year must be a four-digit year")
    year = int(text)
    if year < 1900 or year > 2100:
        raise ValueError("year must be a four-digit year")
    return year


def scope_toml(sources: tuple[str, ...] | None, year_from: int, year_to: int) -> dict:
    """``all`` true means every source. An empty ``sources`` list means none."""
    if sources is None:
        return {"all": True, "sources": [], "year_from": year_from, "year_to": year_to}
    return {"all": False, "sources": list(sources), "year_from": year_from, "year_to": year_to}


def apply_request_scope(cfg, scope: RequestScope):
    updated = replace(
        cfg,
        scope_sources=scope.sources,
        scope_year_from=scope.year_from,
        scope_year_to=scope.year_to,
    )
    if scope.effort in EFFORT_NAMES:
        updated = apply_effort(updated, scope.effort)
    return updated


def source_in_scope(source: str, cfg: object) -> bool:
    selected = getattr(cfg, "scope_sources", None)
    return selected is None or source in selected


def in_scope(record: Record, cfg: object) -> bool:
    if not source_in_scope(record.source, cfg):
        return False
    year_from = int(getattr(cfg, "scope_year_from", 0) or 0)
    year_to = int(getattr(cfg, "scope_year_to", 0) or 0)
    if not year_from and not year_to:
        return True
    year = record_year(record)
    if year <= 0:
        return True
    if year_from and year < year_from:
        return False
    if year_to and year > year_to:
        return False
    return True


def record_year(record: Record) -> int:
    values = header_values(record.text, "Year")
    if not values:
        return 0
    found = _YEAR.search(values[0])
    if not found:
        return 0
    return int(found.group(0))


def scope_label(cfg: object) -> str:
    selected = getattr(cfg, "scope_sources", None)
    if selected is None:
        sources = "all sources"
    elif not selected:
        sources = "no sources"
    else:
        sources = "sources " + ", ".join(selected)
    year_from = int(getattr(cfg, "scope_year_from", 0) or 0)
    year_to = int(getattr(cfg, "scope_year_to", 0) or 0)
    if year_from and year_to:
        years = f"{year_from}–{year_to}"
    elif year_from:
        years = f"from {year_from}"
    elif year_to:
        years = f"through {year_to}"
    else:
        years = "any year"
    return f"{sources} · {years} · effort {getattr(cfg, 'effort', '')}"
