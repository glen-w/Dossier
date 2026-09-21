"""Deterministic referee shortlist. The model does not name anyone."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

CONFIRM = "confirm before listing"
SPEND_WARNING = "do not spend on a post you would not take"
MAX_SHORTLIST = 7
EMPLOYER_POINTS = 10
JOB_POINTS_CAP = 3
_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    "a an the of and or to for in on with from by at as is are was were be this that".split()
)


@dataclass(frozen=True)
class Person:
    name: str
    company: str = ""
    job_title: str = ""
    keywords: str = ""
    bio: str = ""
    note: str = ""
    enrichment_status: str = ""
    co_author_with_glen: int = 0
    last_contact_at: str | None = None
    timeline_count: int = 0


@dataclass(frozen=True)
class Policy:
    hard_skips: frozenset[str] = field(default_factory=frozenset)
    students: frozenset[str] = field(default_factory=frozenset)
    scarce: frozenset[str] = field(default_factory=frozenset)
    ruled_out: frozenset[str] = field(default_factory=frozenset)
    this_quarter: frozenset[str] = field(default_factory=frozenset)
    employer_aliases: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> Policy:
        return cls()


@dataclass(frozen=True)
class Suggestion:
    name: str
    company: str
    why: str
    warning: str
    score: int
    speaks: tuple[str, ...] = ()


def note_pubs_coauthors(people: list[Person], blobs: list[str]) -> list[Person]:
    """Same coauthor point when the name is already on an ingested pubs record."""
    from dataclasses import replace

    haystack = "\n".join(blobs).casefold()
    if not haystack.strip():
        return list(people)
    out: list[Person] = []
    for person in people:
        name = person.name.casefold().strip()
        if person.co_author_with_glen > 0 or not name or name not in haystack:
            out.append(person)
            continue
        out.append(replace(person, co_author_with_glen=1))
    return out


def rank(
    posting: str,
    people: list[Person],
    policy: Policy | None = None,
    *,
    employer: str = "",
    include_students: bool = False,
    today: date | None = None,
) -> list[Suggestion]:
    """Return at most seven people who cleared a positive score."""
    rules = policy or Policy.empty()
    day = today or date.today()
    scored: list[Suggestion] = []
    for person in people:
        if _dropped(person, rules, include_students):
            continue
        suggestion = _score(person, posting, employer, rules, day)
        if suggestion.score > 0:
            scored.append(suggestion)
    scored.sort(key=lambda item: (-item.score, item.name.casefold()))
    return scored[:MAX_SHORTLIST]


def format_suggestion(suggestion: Suggestion, index: int) -> str:
    head = f"{index}. {suggestion.name}"
    if suggestion.company:
        head += f" — {suggestion.company}"
    line = f"{head} — {suggestion.why}"
    if suggestion.speaks:
        line += " — could speak to: " + "; ".join(suggestion.speaks)
    if suggestion.warning:
        line += f" — warning: {suggestion.warning}"
    return f"{line} — {CONFIRM}"


def _dropped(person: Person, policy: Policy, include_students: bool) -> bool:
    if person.enrichment_status.replace("-", "_").upper() == "NEEDS_REVIEW":
        return True
    if _named(person.name, policy.hard_skips) or _named(person.name, policy.ruled_out):
        return True
    if not include_students and _named(person.name, policy.students):
        return True
    return _inbox_only(person)


def _inbox_only(person: Person) -> bool:
    return not any(
        part.strip()
        for part in (person.company, person.job_title, person.keywords, person.note)
    )


def _named(name: str, group: frozenset[str]) -> bool:
    key = name.casefold().strip()
    return any(item.casefold().strip() == key for item in group)


def _score(
    person: Person,
    posting: str,
    employer: str,
    policy: Policy,
    today: date,
) -> Suggestion:
    why: list[str] = []
    points = 0
    if _employer_overlap(person.company, posting, employer, policy.employer_aliases):
        points += EMPLOYER_POINTS
        why.append(f"hiring-firm overlap: {person.company}")
    overlap = _job_overlap(posting, person)
    if overlap:
        points += min(JOB_POINTS_CAP, len(overlap))
        shown = ", ".join(sorted(overlap)[:6])
        why.append(f"job overlap: {shown}")
    if person.note.strip():
        points += 1
        why.append("note on file")
    if person.timeline_count > 0:
        points += 1
        why.append("timeline activity")
    if _recent_contact(person.last_contact_at, today):
        points += 1
        why.append("recent contact")
    if _named(person.name, policy.this_quarter):
        points += 1
        why.append("this quarter")
    if person.co_author_with_glen > 0:
        points += 1
        why.append("coauthor")
    warning = SPEND_WARNING if _named(person.name, policy.scarce) else ""
    return Suggestion(
        name=person.name,
        company=person.company,
        why="; ".join(why),
        warning=warning,
        score=points,
    )


def _job_overlap(posting: str, person: Person) -> set[str]:
    profile = " ".join((person.job_title, person.keywords, person.bio, person.note))
    return _tokens(posting) & _tokens(profile)


def _tokens(text: str) -> set[str]:
    return {tok for tok in _TOKEN.findall(text.casefold()) if len(tok) > 2 and tok not in _STOP}


def _employer_overlap(
    company: str,
    posting: str,
    employer: str,
    aliases: dict[str, tuple[str, ...]],
) -> bool:
    names = _alias_group(company, aliases)
    if not names:
        return False
    employer_l = employer.casefold().strip()
    posting_l = posting.casefold()
    if employer_l and employer_l in names:
        return True
    for name in names:
        if _contains_name(employer_l, name) or _contains_name(posting_l, name):
            return True
    return False


def _alias_group(company: str, aliases: dict[str, tuple[str, ...]]) -> set[str]:
    key = company.casefold().strip()
    names = {key} if key else set()
    for canon, extra in aliases.items():
        group = {canon.casefold().strip(), *(item.casefold().strip() for item in extra)}
        group.discard("")
        if key in group:
            names |= group
    return names


def _contains_name(haystack: str, name: str) -> bool:
    if len(name) < 3 or not haystack:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])", haystack) is not None


def _recent_contact(raw: str | None, today: date) -> bool:
    if not raw:
        return False
    try:
        contacted = datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        return False
    delta = today - contacted
    return timedelta(0) <= delta <= timedelta(days=180)
