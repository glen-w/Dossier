"""Lists for the career pack. A question about roles is not one shared verb."""

from __future__ import annotations

import re

from dossier.ask import Answer
from dossier.cards import header_values
from dossier.lenses import SKILL_NAMES
from dossier.packs import PackQuestion
from dossier.store import Corpus, Record

_QUESTIONS = {
    "roles": "What roles have I held?",
    "delivered": "What work did I deliver?",
    "skills": "What skills does the record show?",
    "contributions": "What contributions are recorded?",
    "publications": "What did I publish?",
}
_MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
_DATE = re.compile(
    rf"{_MONTH}\s+\d{{4}}(?:\s*[–—-]\s*(?:{_MONTH}\s+)?\d{{4}})?",
    re.I,
)
_DOC = re.compile(r"\.(?:pdf|docx?|pptx?|xlsx?|csv)$", re.I)
_ADMIN = re.compile(
    r"(form|consent|registration|invoice|receipt|passport|duplicat|bulletin|judging|appointment|engagement)",
    re.I,
)
_YEAR = re.compile(r"\d{4}")
_STEM_DROP = frozenset(
    {
        "draft",
        "final",
        "edit",
        "edits",
        "edited",
        "revised",
        "revision",
        "clean",
        "anonymous",
        "version",
        "design",
        "gw",
        "opt",
    }
)
_PER_KIND = 3
_MAX_LINES = 24
_DELIVERED = (
    "report",
    "brief",
    "tables",
    "slides",
    "workshop",
    "webinar",
    "side_event",
    "data",
    "other",
)
_CONTRIBUTIONS = ("review", "editing", "outreach", "teaching", "data")
_PUBLICATIONS = ("paper", "chapter", "book")


def try_inventory(corpus: Corpus, item: PackQuestion) -> Answer | None:
    """A cited list for a built-in career question. Other questions return None."""
    if _QUESTIONS.get(item.id) != item.question:
        return None
    if item.id == "roles":
        return _roles(corpus)
    if item.id == "skills":
        return _skills(corpus)
    if item.id == "delivered":
        return _files(corpus, ("delivered",), _DELIVERED)
    if item.id == "contributions":
        return _files(corpus, ("contributions",), _CONTRIBUTIONS)
    return _publications(corpus)


def _roles(corpus: Corpus) -> Answer:
    lines: list[str] = []
    citations: list[str] = []
    for rec in corpus.records():
        if rec.table != "linkedin.positions" and not rec.uri.startswith("linkedin://positions/"):
            continue
        title = rec.title.strip()
        if not title:
            continue
        found = _DATE.search(rec.text)
        line = f"- {title} ({found.group(0)})" if found else f"- {title}"
        lines.append(line)
        citations.append(rec.uri)
        if len(lines) == 30:
            break
    return _listed(lines, citations)


def _skills(corpus: Corpus) -> Answer:
    lines: list[str] = []
    citations: list[str] = []
    seen: set[str] = set()
    counted: dict[str, tuple[int, str]] = {}
    linkedin = ""
    linkedin_uri = ""
    for rec in corpus.records():
        if rec.uri == "linkedin://skills" or rec.table == "linkedin.skills":
            linkedin = _linkedin_skills(rec.text)
            linkedin_uri = rec.uri
            continue
        for name in header_values(rec.text, "Skills"):
            if name not in SKILL_NAMES:
                continue
            count, uri = counted.get(name, (0, rec.uri))
            counted[name] = (count + 1, uri)
    for name, (_count, uri) in sorted(counted.items(), key=lambda item: (-item[1][0], item[0])):
        if name in seen:
            continue
        seen.add(name)
        lines.append(f"- {name}")
        citations.append(uri)
    if linkedin:
        lines.append(f"LinkedIn: {linkedin}")
        if linkedin_uri:
            citations.append(linkedin_uri)
    return _listed(lines, citations)


def _linkedin_skills(text: str) -> str:
    body = text.strip()
    if body.lower().startswith("skills:"):
        body = body.split(":", 1)[1].strip()
    return body


def _publications(corpus: Corpus) -> Answer:
    lines: list[str] = []
    citations: list[str] = []
    for rec in corpus.records():
        if rec.table != "linkedin.publications" and not rec.uri.startswith(
            "linkedin://publications/"
        ):
            continue
        title = rec.title.strip()
        if not title:
            continue
        lines.append(f"- {title}")
        citations.append(rec.uri)
    more_lines, more_cites = _artifact_lines(
        corpus, ("delivered", "contributions"), _PUBLICATIONS
    )
    room = _MAX_LINES - len(lines)
    lines.extend(more_lines[:room])
    citations.extend(more_cites[:room])
    return _listed(lines, citations)


def _files(corpus: Corpus, lenses: tuple[str, ...], kinds: tuple[str, ...]) -> Answer:
    lines, citations = _artifact_lines(corpus, lenses, kinds)
    return _listed(lines, citations)


def _artifact_lines(
    corpus: Corpus,
    lenses: tuple[str, ...],
    kinds: tuple[str, ...],
) -> tuple[list[str], list[str]]:
    buckets: dict[str, list[tuple[int, str, str]]] = {kind: [] for kind in kinds}
    best: dict[tuple[str, str], tuple[int, str, str]] = {}
    seen_records: set[str] = set()
    for lens in lenses:
        for rec in _lens(corpus, lens):
            if rec.uri in seen_records:
                continue
            seen_records.add(rec.uri)
            kind = _one(rec, "Kind")
            if kind not in buckets:
                continue
            year = _year_key(_one(rec, "Year"))
            for art in header_values(rec.text, "Artifacts"):
                if not _DOC.search(art) or _ADMIN.search(art):
                    continue
                key = (kind, _stem(art))
                current = best.get(key)
                if current is None or year > current[0]:
                    best[key] = (year, art, rec.uri)
    for (kind, _stem_key), row in best.items():
        buckets[kind].append(row)
    lines: list[str] = []
    citations: list[str] = []
    for kind in kinds:
        ranked = sorted(buckets[kind], key=lambda row: (-row[0], row[1]))
        for year, art, uri in ranked[:_PER_KIND]:
            if len(lines) == _MAX_LINES:
                return lines, citations
            when = f"{year} · " if year else ""
            lines.append(f"- {kind} · {when}{art}")
            citations.append(uri)
    return lines, citations


def _stem(name: str) -> str:
    base = re.sub(r"\.[a-z0-9]+$", "", name.casefold())
    words = [
        word
        for word in re.sub(r"[^a-z]+", " ", base).split()
        if word not in _STEM_DROP and len(word) > 2
    ]
    return " ".join(words)


def _lens(corpus: Corpus, lens: str) -> list[Record]:
    want = lens.strip().lower()
    return [rec for rec in corpus.records() if want in header_values(rec.text, "Lens")]


def _one(rec: Record, key: str) -> str:
    values = header_values(rec.text, key)
    return values[0] if values else ""


def _year_key(year: str) -> int:
    found = _YEAR.search(year)
    return int(found.group(0)) if found else 0


def _listed(lines: list[str], citations: list[str]) -> Answer:
    if not lines:
        return Answer(
            text="",
            citations=[],
            refused=True,
            reason="nothing recorded",
            route="inventory",
        )
    unique: list[str] = []
    for uri in citations:
        if uri not in unique:
            unique.append(uri)
    return Answer(
        text="\n".join(lines),
        citations=unique,
        refused=False,
        reason="",
        route="inventory",
    )
