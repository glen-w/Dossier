"""Closed lenses and kinds for mail/Slack seekers. Not unsupervised clusters."""

from __future__ import annotations

import re

LENSES = ("delivered", "skills", "contributions")

KINDS = (
    "brief",
    "paper",
    "chapter",
    "book",
    "report",
    "tables",
    "slides",
    "workshop",
    "webinar",
    "teaching",
    "side_event",
    "review",
    "outreach",
    "data",
    "editing",
    "other",
)

_KIND_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("workshop", re.compile(r"workshop")),
    ("webinar", re.compile(r"webinar")),
    ("teaching", re.compile(r"teach|course|lecture|\bseminar\b")),
    ("side_event", re.compile(r"side[- ]event")),
    ("review", re.compile(r"peer review|\breview\b")),
    ("brief", re.compile(r"\bbrief")),
    ("paper", re.compile(r"\bpaper\b|marine policy|publication")),
    ("book", re.compile(r"\bbook\b")),
    ("chapter", re.compile(r"chapter|\bsection_|\bgsr_section")),
    ("editing", re.compile(r"\bedit|\bdesign_")),
    ("outreach", re.compile(r"outreach|\bcomms|\bcomm_")),
    ("report", re.compile(r"\bgsr_|\bgfr_|\breport\b")),
    ("data", re.compile(r"\bdata\b|knowledge")),
)

_SKILL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("knowledge-and-data", re.compile(r"knowledge|\bdata\b|tables|\.xlsx?$")),
    ("editing", re.compile(r"\bedit")),
    ("teaching", re.compile(r"teach|course|lecture")),
    ("facilitation", re.compile(r"workshop|webinar|convene")),
    ("science-policy", re.compile(r"policy|bbnj|\bbrief")),
    ("legal-analysis", re.compile(r"\blegal\b")),
    ("ocean-governance", re.compile(r"ocean|bbnj|seabed|maritime")),
)

_EVENT_KINDS = frozenset(
    {
        "workshop",
        "webinar",
        "teaching",
        "side_event",
        "brief",
        "paper",
        "book",
        "report",
        "chapter",
    }
)
_DOC_EXT = re.compile(r"\.(pdf|docx?|pptx?|xlsx?|csv)$", re.I)


def infer_kind(
    *,
    folder: str = "",
    channel: str = "",
    subject: str = "",
    artifacts: tuple[str, ...] = (),
) -> str:
    arts = " ".join(artifacts).lower()
    if re.search(r"\.pptx?$", arts):
        return "slides"
    if re.search(r"\.(xlsx?|csv)$", arts):
        return "tables"
    blob = f"{folder} {channel} {subject} {arts}".lower()
    for kind, pattern in _KIND_PATTERNS:
        if pattern.search(blob):
            return kind
    return "other"


def infer_skills(*parts: str) -> tuple[str, ...]:
    blob = " ".join(p for p in parts if p).lower()
    found: list[str] = []
    for skill, pattern in _SKILL_PATTERNS:
        if pattern.search(blob) and skill not in found:
            found.append(skill)
    return tuple(found)


def infer_lenses(
    *,
    kind: str,
    artifacts: tuple[str, ...] = (),
    authored: bool = False,
    coordinated: bool = False,
    skills: tuple[str, ...] = (),
) -> tuple[str, ...]:
    lenses: list[str] = []
    has_doc = any(_DOC_EXT.search(a or "") for a in artifacts)
    if has_doc or kind in _EVENT_KINDS or kind in {"slides", "tables"}:
        lenses.append("delivered")
    if coordinated or kind in {"editing", "review", "outreach", "teaching"} or (
        authored and (has_doc or kind in _EVENT_KINDS)
    ):
        lenses.append("contributions")
    if skills:
        lenses.append("skills")
    if not lenses:
        lenses.append("contributions" if authored else "delivered")
    return tuple(dict.fromkeys(lenses))


def primary_lens(lenses: tuple[str, ...]) -> str:
    for name in LENSES:
        if name in lenses:
            return name
    return "delivered"


def infer_org(*, source: str, account_key: str = "", channel: str = "") -> str:
    if source == "slack" or channel:
        return "REN21"
    key = (account_key or "").lower()
    if "sciencespo" in key or "iddri" in key:
        return "IDDRI"
    return ""
