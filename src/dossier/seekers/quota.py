"""Diversity quotas: a broad buffet, not 6k of one kind."""

from __future__ import annotations

import os

from dossier.seekers.hits import Hit

DEFAULT_PER_STRATUM = 20
DEFAULT_OVERALL = 400


def quota_limits() -> tuple[int, int]:
    per = _env_int("DOSSIER_SEEKER_PER_STRATUM", DEFAULT_PER_STRATUM)
    overall = _env_int("DOSSIER_SEEKER_OVERALL", DEFAULT_OVERALL)
    return max(1, per), max(1, overall)


def apply_quotas(
    hits: list[Hit],
    *,
    per_stratum: int | None = None,
    overall: int | None = None,
) -> list[Hit]:
    default_per, default_overall = quota_limits()
    per_stratum = default_per if per_stratum is None else per_stratum
    overall = default_overall if overall is None else overall
    if not hits:
        return []
    ranked = sorted(hits, key=lambda h: (-h.score, h.uri))
    seen: set[str] = set()
    chosen: list[Hit] = []
    counts: dict[tuple[str, str, str, int], int] = {}

    def key(hit: Hit) -> tuple[str, str, str, int]:
        return (hit.source, hit.primary_lens, hit.kind, hit.year)

    for hit in ranked:
        if hit.uri in seen:
            continue
        stratum = key(hit)
        if counts.get(stratum, 0) == 0:
            chosen.append(hit)
            seen.add(hit.uri)
            counts[stratum] = 1
            if len(chosen) >= overall:
                return chosen
    for hit in ranked:
        if hit.uri in seen:
            continue
        stratum = key(hit)
        if counts.get(stratum, 0) >= per_stratum:
            continue
        chosen.append(hit)
        seen.add(hit.uri)
        counts[stratum] = counts.get(stratum, 0) + 1
        if len(chosen) >= overall:
            break
    return chosen


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default
