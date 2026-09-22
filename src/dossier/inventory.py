"""Lists for the career pack. A question about roles is not one shared verb."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote

from dossier.ask import Answer
from dossier.cards import header_values
from dossier.identity import noise_folder
from dossier.lenses import SKILL_NAMES, infer_kind, is_noise_name
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
_OFFICE = re.compile(r"\.(?:pdf|docx?|pptx?|xlsx?)$", re.I)
_YEAR = re.compile(r"(?:19|20)\d{2}")
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
        "mvvp",
        "chatgpt",
        "gemini",
        "testing",
    }
)
_BAD_TITLE = re.compile(
    r"^(?:fwd:|re:|fw:|thank you|done|\*done\*|image|hey team|good afternoon|fyi,|@)\b|"
    r"<!subteam|^tr:|^aw:",
    re.I,
)
_EMPLOYER_ROOTS = frozenset({"publications", "events", "projects", "slides"})
_PER_KIND = 12
_EXTRA_PER_YEAR = 1
_MAX_LINES = 100
_SOURCE_WEIGHT = {
    "mbox": 3,
    "employer": 3,
    "meetings": 2,
    "linkedin": 2,
    "slack": 1,
}
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
_CONTRIBUTIONS = ("review", "editing", "outreach", "teaching")
_PUBLICATIONS = ("paper", "chapter", "book")
_DATA_ON_DELIVERED = True


@dataclass(frozen=True)
class _Cand:
    kind: str
    year: int
    label: str
    uri: str
    stem: str
    source: str
    org: str
    art: str
    title: str
    rank: tuple[int, ...]


def try_inventory(corpus: Corpus, item: PackQuestion) -> Answer | None:
    """A cited list for a built-in career question. Other questions return None."""
    if _QUESTIONS.get(item.id) != item.question:
        return None
    if item.id == "roles":
        return _roles(corpus)
    if item.id == "skills":
        return _skills(corpus)
    if item.id == "delivered":
        return _files(corpus, ("delivered",), _DELIVERED, claim_data=True)
    if item.id == "contributions":
        return _files(corpus, ("contributions",), _CONTRIBUTIONS, claim_data=False)
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
    zotero = _zotero_publications(corpus)
    if zotero is not None:
        return _listed(*zotero)
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
        corpus, ("delivered", "contributions"), _PUBLICATIONS, claim_data=False
    )
    room = _MAX_LINES - len(lines)
    lines.extend(more_lines[:room])
    citations.extend(more_cites[:room])
    return _listed(lines, citations)


def _zotero_publications(corpus: Corpus) -> tuple[list[str], list[str]] | None:
    rows: list[tuple[int, str, str, str]] = []
    for rec in corpus.records("pubs"):
        if rec.table != "pubs.records":
            continue
        title = rec.title.strip()
        if not title:
            continue
        year = ""
        years = header_values(rec.text, "Year")
        if years and years[0].isdigit():
            year = years[0]
        rows.append((int(year) if year else 0, title, rec.uri, year))
    if not rows:
        return None
    rows.sort(key=lambda row: (-row[0], row[1].casefold(), row[2]))
    lines = [f"- {year} · {title}" if year else f"- {title}" for _num, title, _uri, year in rows]
    citations = [uri for _num, _title, uri, _year in rows]
    return lines, citations


def _files(
    corpus: Corpus,
    lenses: tuple[str, ...],
    kinds: tuple[str, ...],
    *,
    claim_data: bool,
) -> Answer:
    lines, citations = _artifact_lines(corpus, lenses, kinds, claim_data=claim_data)
    return _listed(lines, citations)


def _artifact_lines(
    corpus: Corpus,
    lenses: tuple[str, ...],
    kinds: tuple[str, ...],
    *,
    claim_data: bool,
) -> tuple[list[str], list[str]]:
    kind_set = set(kinds)
    if claim_data and _DATA_ON_DELIVERED:
        kind_set.add("data")
    cands = _collect(corpus, lenses, kind_set)
    best = _collapse(cands)
    by_kind: dict[str, list[_Cand]] = {kind: [] for kind in kinds}
    for cand in best.values():
        if cand.kind in by_kind:
            by_kind[cand.kind].append(cand)
    lines: list[str] = []
    citations: list[str] = []
    remainders: list[str] = []
    for kind in kinds:
        pool = by_kind.get(kind, [])
        picked = _year_spread(pool)
        skipped = max(0, len(pool) - len(picked))
        for cand in picked:
            if len(lines) >= _MAX_LINES:
                break
            lines.append(_format(cand))
            citations.append(cand.uri)
        if skipped:
            remainders.append(f"({kind}: {skipped} more in corpus)")
        if len(lines) >= _MAX_LINES:
            break
    lines.extend(remainders)
    return lines, citations


def _collect(
    corpus: Corpus,
    lenses: tuple[str, ...],
    kinds: set[str],
) -> list[_Cand]:
    out: list[_Cand] = []
    seen: set[str] = set()
    for lens in lenses:
        for rec in _lens(corpus, lens):
            if rec.uri in seen:
                continue
            seen.add(rec.uri)
            out.extend(_from_seeker(rec, kinds))
    for rec in corpus.records(source="employer"):
        if rec.uri in seen:
            continue
        cand = _from_employer(rec, kinds)
        if cand is not None:
            seen.add(rec.uri)
            out.append(cand)
    return out


def _from_seeker(rec: Record, kinds: set[str]) -> list[_Cand]:
    stored = _one(rec, "Kind")
    year = _year_key(_one(rec, "Year"))
    org = _one(rec, "Org")
    arts = [a.strip() for a in header_values(rec.text, "Artifacts") if a.strip()]
    folder = _mbox_folder(rec.uri) if rec.source == "mbox" else ""
    if folder and noise_folder(folder):
        return []
    cands: list[_Cand] = []
    for art in arts or [""]:
        if art and (not _DOC.search(art) or is_noise_name(art, rec.title)):
            continue
        if not art and is_noise_name(rec.title):
            continue
        kind = stored
        if kind == "other" or not kind:
            kind = infer_kind(
                folder=folder,
                subject=rec.title,
                artifacts=tuple(a for a in arts if a) or ((art,) if art else ()),
            )
        if kind not in kinds:
            continue
        if art and is_noise_name(art):
            continue
        label_src = art or rec.title
        if is_noise_name(label_src, rec.title):
            continue
        cands.append(
            _make_cand(
                kind=kind,
                year=year,
                uri=rec.uri,
                source=rec.source,
                org=org,
                art=art,
                title=rec.title,
            )
        )
    return cands


def _from_employer(rec: Record, kinds: set[str]) -> _Cand | None:
    path = _employer_rel(rec.uri)
    if path is None:
        return None
    root, rel = path
    name = rel.rsplit("/", 1)[-1]
    if not _OFFICE.search(name) or is_noise_name(name, rel):
        return None
    year = _year_key(rel) or _year_key(name)
    folder = f"{root}/{'/'.join(rel.split('/')[:-1])}"
    kind = infer_kind(folder=folder, subject=name, artifacts=(name,))
    if root == "publications" and kind == "other":
        kind = "paper"
    if root == "slides" and kind == "other":
        kind = "slides"
    if root == "events" and kind == "other":
        kind = infer_kind(folder=folder, subject=rel, artifacts=(name,))
        if kind == "other":
            kind = "workshop" if "workshop" in rel.casefold() else "other"
    if kind not in kinds:
        # publications section asks for paper/chapter/book
        if "paper" in kinds and root == "publications" and kind in {"report", "brief", "other"}:
            kind = "paper"
        elif kind not in kinds:
            return None
    return _make_cand(
        kind=kind,
        year=year,
        uri=rec.uri,
        source="employer",
        org="",
        art=name,
        title=rec.title or name,
    )


def _employer_rel(uri: str) -> tuple[str, str] | None:
    if not uri.startswith("file://employer/"):
        return None
    rest = unquote(uri[len("file://employer/") :])
    parts = [p for p in rest.split("/") if p]
    if len(parts) < 2:
        return None
    # file://employer/<slug>/<rel...>
    slug = parts[0].casefold()
    if slug in {"*unsorted", "unsorted", "admin"}:
        return None
    for i, part in enumerate(parts):
        key = part.casefold()
        if key in _EMPLOYER_ROOTS:
            rel = "/".join(parts[i + 1 :])
            if not rel:
                return None
            return key, rel
    return None


def _make_cand(
    *,
    kind: str,
    year: int,
    uri: str,
    source: str,
    org: str,
    art: str,
    title: str,
) -> _Cand:
    label = _label(title, art)
    stem = _stem(art or title or label)
    weight = _SOURCE_WEIGHT.get(source, 0)
    clean = 1 if not _messy(art or title) else 0
    named = 1 if label and not _BAD_TITLE.search(label) else 0
    doc = 1 if art and _DOC.search(art) else 0
    rank = (doc, named, weight, clean, year, -len(art or title))
    return _Cand(
        kind=kind,
        year=year,
        label=label,
        uri=uri,
        stem=stem,
        source=source,
        org=org,
        art=art,
        title=title,
        rank=rank,
    )


def _collapse(cands: list[_Cand]) -> dict[tuple[str, str], _Cand]:
    best: dict[tuple[str, str], _Cand] = {}
    by_uri: dict[str, _Cand] = {}
    for cand in cands:
        if not cand.stem:
            continue
        prev_uri = by_uri.get(cand.uri)
        if prev_uri is not None and prev_uri.rank >= cand.rank:
            continue
        key = (cand.kind, cand.stem)
        current = best.get(key)
        if current is not None and current.rank >= cand.rank:
            continue
        if current is not None and current.uri in by_uri and by_uri[current.uri] is current:
            del by_uri[current.uri]
        best[key] = cand
        by_uri[cand.uri] = cand
    # one URI wins across kinds: keep the better-ranked kind
    winners: dict[str, _Cand] = {}
    for cand in best.values():
        prev = winners.get(cand.uri)
        if prev is None or cand.rank > prev.rank:
            winners[cand.uri] = cand
    out: dict[tuple[str, str], _Cand] = {}
    for cand in winners.values():
        out[(cand.kind, cand.stem)] = cand
    return out


def _year_spread(pool: list[_Cand]) -> list[_Cand]:
    if not pool:
        return []
    by_year: dict[int, list[_Cand]] = {}
    for cand in sorted(pool, key=lambda c: c.rank, reverse=True):
        by_year.setdefault(cand.year, []).append(cand)
    picked: list[_Cand] = []
    seen: set[str] = set()
    # one per year, oldest to newest so early career is visible
    for year in sorted(y for y in by_year if y > 0):
        for cand in by_year[year]:
            if cand.uri in seen:
                continue
            picked.append(cand)
            seen.add(cand.uri)
            break
        if len(picked) >= _PER_KIND:
            return picked[:_PER_KIND]
    # undated
    for cand in by_year.get(0, []):
        if cand.uri in seen:
            continue
        picked.append(cand)
        seen.add(cand.uri)
        if len(picked) >= _PER_KIND:
            return picked[:_PER_KIND]
        break
    # extras in thick years (newest first)
    room = _PER_KIND - len(picked)
    extras: list[_Cand] = []
    for year in sorted((y for y in by_year if y > 0), reverse=True):
        taken = 0
        for cand in by_year[year]:
            if cand.uri in seen:
                continue
            extras.append(cand)
            seen.add(cand.uri)
            taken += 1
            if taken >= _EXTRA_PER_YEAR or len(extras) >= room:
                break
        if len(extras) >= room:
            break
    picked.extend(extras[:room])
    return picked[:_PER_KIND]


def _format(cand: _Cand) -> str:
    when = f"{cand.year} · " if cand.year else ""
    org = f"{cand.org} · " if cand.org else ""
    return f"- {cand.kind} · {when}{org}{cand.label}"


def _label(title: str, art: str) -> str:
    title = (title or "").strip()
    art = (art or "").strip()
    if _slack_prose(title) or _BAD_TITLE.search(title) or is_noise_name(title):
        return art or title
    if title and art and _DOC.search(art):
        if len(title) >= 12 and art.casefold() not in title.casefold():
            return title
        return art
    return title or art


def _slack_prose(title: str) -> bool:
    if not title:
        return False
    if "\n" in title or "<!" in title:
        return True
    if title.startswith("@") or title.startswith("*"):
        return True
    return len(title) > 120


def _messy(name: str) -> bool:
    blob = (name or "").casefold()
    return any(
        token in blob
        for token in (
            "edits to design",
            "mvvp",
            "chatgpt",
            "gemini",
            "final_edits",
            "to design",
        )
    )


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
    found = _YEAR.search(year or "")
    if not found:
        return 0
    value = int(found.group(0))
    if 1990 <= value <= 2100:
        return value
    return 0


def _mbox_folder(uri: str) -> str:
    # mbox://account/folder/.../message-id
    if not uri.startswith("mbox://"):
        return ""
    parts = [unquote(p) for p in uri[len("mbox://") :].split("/") if p]
    if len(parts) < 3:
        return parts[1] if len(parts) > 1 else ""
    return "/".join(parts[1:-1])


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
