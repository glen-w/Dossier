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

# Folder and subject patterns first. Extension is a fallback when nothing matches.
_KIND_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("workshop", re.compile(r"workshop")),
    ("webinar", re.compile(r"webinar")),
    ("teaching", re.compile(r"teach|course|lecture|\bseminar\b|\bpanel\b")),
    ("side_event", re.compile(r"side[- ]event")),
    ("review", re.compile(r"peer[- ]?review|\bto review\b|\breviewer")),
    ("brief", re.compile(r"\bbrief|\bfactsheet")),
    ("paper", re.compile(r"\bpaper\b|marine policy|publication|\bjournal\b|\bsubmission\b|\bhandbook\b")),
    ("book", re.compile(r"\bedited book\b|\bbook chapter\b|\bbook proposal\b|\bhandbook\b|(?<![a-z])books?(?![a-z])(?!\s+your)(?!\.com)")),
    ("chapter", re.compile(r"chapter|\bsection_|\bgsr_section")),
    ("editing", re.compile(r"\bedit|\bdesign_")),
    ("outreach", re.compile(r"outreach|\bcomms|\bcomm_|\bblog\b|\bspeech\b")),
    ("report", re.compile(r"\bgsr_|\bgfr_|\breport\b|\bconsultation\b")),
    ("data", re.compile(r"\bdataset\b|\bknowledge[- ]?product\b")),
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

SKILL_NAMES: tuple[str, ...] = tuple(name for name, _pattern in _SKILL_PATTERNS)

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

# Logistics and life-admin. Shared by inventory listing and seeker year floor.
_NOISE = re.compile(
    r"(?:^|[^a-z])(?:"
    r"form|consent|registration|invoice|receipt|passport|duplicat|bulletin|"
    r"judging|appointment|engagement|timesheets?|time[- ]?sheets?|"
    r"attendee report|logistics(?: note)?|ordonnance|holiday dates?|"
    r"chatgpt|gemini testing|booking\.com|"
    r"\*\s*done\s*\*|image\.png|image\.jpe?g"
    r")(?:[^a-z]|$)|"
    r"(?:^|/)agenda\.docx?$|"
    r"^invitation\b|"
    r"^thank you\b|"
    r"^fwd:\s*$",
    re.I,
)


def kinds_mentioned(text: str) -> tuple[str, ...]:
    """Kinds whose names or patterns appear in a local posting. No model."""
    blob = text.lower()
    found: list[str] = []
    for kind, pattern in _KIND_PATTERNS:
        if pattern.search(blob) and kind not in found:
            found.append(kind)
    return tuple(found)


# A form that records a budget, expense, or reimbursement is evidence.
_BUDGET_EVIDENCE = re.compile(
    r"frais|budgets?|expenses?|reimburs|rembours|ordre de mission|mission order",
    re.I,
)
# Still noise when the name is a timesheet or a leave form, even if a project is named.
_LIFE_ADMIN = re.compile(
    r"timesheets?|time[- ]?sheets?|payslips?|bulletins? de paie|cong[eé]s?",
    re.I,
)


def is_noise_name(*parts: str) -> bool:
    """True for logistics, life-admin, or status pings that are not career evidence.

    Expense and budget forms are kept. A timesheet or a leave form is not.
    """
    blob = " ".join(p for p in parts if p).strip()
    if not blob:
        return False
    if _LIFE_ADMIN.search(blob):
        return True
    if _BUDGET_EVIDENCE.search(blob):
        return False
    return bool(_NOISE.search(blob))


def infer_kind(
    *,
    folder: str = "",
    channel: str = "",
    subject: str = "",
    artifacts: tuple[str, ...] = (),
) -> str:
    """Folder and subject beat file extension. Bare spreadsheets stay tables."""
    arts = " ".join(artifacts).lower()
    blob = f"{folder} {channel} {subject} {arts}".lower()
    for kind, pattern in _KIND_PATTERNS:
        if pattern.search(blob):
            return kind
    if re.search(r"\.pptx?$", arts):
        return "slides"
    if re.search(r"\.(xlsx?|csv)$", arts):
        return "tables"
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
