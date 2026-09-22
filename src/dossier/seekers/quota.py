"""Diversity quotas: a broad buffet, not 6k of one kind."""

from __future__ import annotations

import os

from dossier.lenses import is_noise_name
from dossier.seekers.hits import Hit

DEFAULT_PER_STRATUM = 20
DEFAULT_OVERALL = 1000
DEFAULT_YEAR_FLOOR = 15
DEFAULT_YEAR_CEILING = 80
_DOC = (".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".csv")


def quota_limits() -> tuple[int, int]:
    per = _env_int("DOSSIER_SEEKER_PER_STRATUM", DEFAULT_PER_STRATUM)
    overall = _env_int("DOSSIER_SEEKER_OVERALL", DEFAULT_OVERALL)
    return max(1, per), max(1, overall)


def year_limits() -> tuple[int, int]:
    floor = _env_int("DOSSIER_SEEKER_YEAR_FLOOR", DEFAULT_YEAR_FLOOR)
    ceiling = _env_int("DOSSIER_SEEKER_YEAR_CEILING", DEFAULT_YEAR_CEILING)
    return max(0, floor), max(1, ceiling)


def apply_quotas(
    hits: list[Hit],
    *,
    per_stratum: int | None = None,
    overall: int | None = None,
    year_floor: int | None = None,
    year_ceiling: int | None = None,
) -> list[Hit]:
    default_per, default_overall = quota_limits()
    default_floor, default_ceiling = year_limits()
    per_stratum = default_per if per_stratum is None else per_stratum
    overall = default_overall if overall is None else overall
    year_floor = default_floor if year_floor is None else year_floor
    year_ceiling = default_ceiling if year_ceiling is None else year_ceiling
    if not hits:
        return []
    ranked = sorted(hits, key=lambda h: (-h.score, h.uri))
    seen: set[str] = set()
    chosen: list[Hit] = []
    stratum_counts: dict[tuple[str, str, str, int], int] = {}
    year_counts: dict[int, int] = {}

    def stratum(hit: Hit) -> tuple[str, str, str, int]:
        return (hit.source, hit.primary_lens, hit.kind, hit.year)

    def take(hit: Hit) -> bool:
        if hit.uri in seen:
            return False
        if len(chosen) >= overall:
            return False
        year = hit.year or 0
        if year and year_counts.get(year, 0) >= year_ceiling:
            return False
        chosen.append(hit)
        seen.add(hit.uri)
        stratum_counts[stratum(hit)] = stratum_counts.get(stratum(hit), 0) + 1
        if year:
            year_counts[year] = year_counts.get(year, 0) + 1
        return True

    # Pass 1: one hit per (source, lens, kind, year).
    for hit in ranked:
        if stratum_counts.get(stratum(hit), 0) == 0:
            take(hit)
            if len(chosen) >= overall:
                return chosen

    # Pass 2: career year floor — round-robin years for document hits.
    if year_floor > 0:
        by_year: dict[int, list[Hit]] = {}
        for hit in ranked:
            if hit.uri in seen or not hit.year:
                continue
            if not _document_hit(hit) or _noisy(hit):
                continue
            by_year.setdefault(hit.year, []).append(hit)
        years = sorted(by_year)
        progressed = True
        while progressed and len(chosen) < overall:
            progressed = False
            for year in years:
                if year_counts.get(year, 0) >= year_floor:
                    continue
                bucket = by_year.get(year, [])
                while bucket:
                    hit = bucket.pop(0)
                    if take(hit):
                        progressed = True
                        break
                if len(chosen) >= overall:
                    return chosen

    # Pass 3: score fill under per-stratum and per-year ceilings.
    for hit in ranked:
        if hit.uri in seen:
            continue
        if stratum_counts.get(stratum(hit), 0) >= per_stratum:
            continue
        take(hit)
        if len(chosen) >= overall:
            break
    return chosen


def _document_hit(hit: Hit) -> bool:
    for art in hit.artifacts:
        lower = art.casefold()
        if any(lower.endswith(ext) for ext in _DOC):
            return True
    return False


def _noisy(hit: Hit) -> bool:
    return is_noise_name(hit.title, *hit.artifacts)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default
