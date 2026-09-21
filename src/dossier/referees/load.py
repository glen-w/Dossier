"""JSON people and policy files. Personal names stay in the file, not in code."""

from __future__ import annotations

import json
from pathlib import Path

from dossier.referees.rank import Person, Policy


def load_people(path: Path) -> list[Person]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("people", payload) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError(f"{path}: expected a list of people")
    return [_person(row) for row in rows]


def load_policy(path: Path) -> Policy:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a policy object")
    aliases_raw = payload.get("employer_aliases") or {}
    aliases = {
        str(canon): tuple(str(item) for item in extra)
        for canon, extra in aliases_raw.items()
    }
    return Policy(
        hard_skips=_names(payload.get("hard_skips")),
        students=_names(payload.get("students")),
        scarce=_names(payload.get("scarce")),
        ruled_out=_names(payload.get("ruled_out")),
        this_quarter=_names(payload.get("this_quarter")),
        employer_aliases=aliases,
    )


def _names(value: object) -> frozenset[str]:
    if not value:
        return frozenset()
    if not isinstance(value, list):
        raise ValueError("policy name lists must be arrays")
    return frozenset(str(item) for item in value)


def _person(row: object) -> Person:
    if not isinstance(row, dict):
        raise ValueError("each person must be an object")
    coauthor = _first(row, "coAuthorWithGlen", "co_author_with_glen", default=0)
    timeline = _first(row, "timelineCount", "timeline_count", default=0)
    last = _first(row, "lastContactAt", "last_contact_at", default=None)
    return Person(
        name=str(_first(row, "name", default="")).strip(),
        company=str(_first(row, "company", default="") or ""),
        job_title=str(_first(row, "jobTitle", "job_title", default="") or ""),
        keywords=str(_first(row, "keywords", default="") or ""),
        bio=str(_first(row, "bio", default="") or ""),
        note=str(_first(row, "note", default="") or ""),
        enrichment_status=str(
            _first(row, "enrichmentStatus", "enrichment_status", default="") or ""
        ),
        co_author_with_glen=int(coauthor or 0),
        last_contact_at=str(last) if last else None,
        timeline_count=int(timeline or 0),
    )


def _first(row: dict, *keys: str, default: object) -> object:
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]
    return default
