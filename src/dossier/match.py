"""Ordered evidence for each requirement in a pasted job spec.

No completion. A query embedding, when the locker already has vectors for
this model, does not spend the call budget. If that embed fails, the
lexical list still returns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dossier.ask import (
    COSINE_QUOTE,
    MAX_HITS,
    Hit,
    _GENERIC,
    _fuse,
    _vector_hits,
    collect_hits,
)
from dossier.cards import (
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REFUSED,
    ClaimCard,
    carrying_span,
    content_token_set,
    content_tokens,
    header_values,
    sentences,
)
from dossier.interview import _query_vector
from dossier.lenses import infer_skills, kinds_mentioned
from dossier.store import Corpus
from dossier.ui import note, stage

REQ_CAP = 20
PER_REQUIREMENT = 5
SOURCE_CAP = 2
GAP_BROAD = "requirement is too broad"
GAP_NONE = "no carrying evidence"

_BOILERPLATE = (
    "about us",
    "about the organisation",
    "about the organization",
    "about the company",
    "benefits",
    "how to apply",
    "equal opportunit",
    "salary",
    "compensation",
    "what we offer",
)
_CUE = re.compile(
    r"\b(experience|responsible|ability|must|proven)\b|you will|knowledge of",
    re.I,
)
_BULLET = re.compile(r"^(?:[-*•]|\d{1,3}[.)])\s+(\S.*)$")
_STATUS_RANK = {STATUS_APPROVED: 0, STATUS_PENDING: 1, STATUS_REFUSED: 2}


@dataclass(frozen=True)
class Requirement:
    text: str
    unsplit: bool = False


@dataclass(frozen=True)
class Evidence:
    rank: int
    source: str
    title: str
    year: str
    quote: str
    uri: str
    route: str
    card_id: str = ""
    card_status: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "source": self.source,
            "title": self.title,
            "year": self.year,
            "quote": self.quote,
            "uri": self.uri,
            "route": self.route,
            "card_id": self.card_id,
            "card_status": self.card_status,
        }


@dataclass(frozen=True)
class RequirementMatch:
    text: str
    unsplit: bool
    broad: bool
    gap: str
    evidence: tuple[Evidence, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "unsplit": self.unsplit,
            "broad": self.broad,
            "gap": self.gap,
            "evidence": [item.as_dict() for item in self.evidence],
        }


@dataclass(frozen=True)
class MatchReport:
    requirements: tuple[RequirementMatch, ...]

    def as_dict(self) -> dict[str, Any]:
        return {"requirements": [item.as_dict() for item in self.requirements]}


@dataclass(frozen=True)
class _Row:
    source: str
    title: str
    year: str
    quote: str
    uri: str
    route: str
    card_id: str = ""
    card_status: str = ""


def split_requirements(text: str) -> list[Requirement]:
    """Bullets, numbered lines, and requirement-cue sentences, in spec order."""
    raw = text.strip()
    if not raw:
        return []
    kept: list[str] = []
    boilerplate = False
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        heading = _heading_name(stripped)
        if heading is not None:
            boilerplate = _is_boilerplate(heading)
            continue
        bullet = _BULLET.match(stripped)
        if bullet:
            body = " ".join(bullet.group(1).split())
            if body and not (boilerplate and not _has_cue(body)):
                kept.append(body)
            continue
        for sentence in sentences(stripped):
            if _has_cue(sentence):
                kept.append(" ".join(sentence.split()))
    deduped: list[str] = []
    seen: set[str] = set()
    for item in kept:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= REQ_CAP:
            break
    if not deduped:
        return [Requirement(" ".join(raw.split()), unsplit=True)]
    return [Requirement(item) for item in deduped]


def match_posting(
    corpus: Corpus,
    posting: str,
    cfg: object,
    *,
    embedder: object | None = None,
) -> MatchReport:
    """One ranked evidence list per requirement. Does not approve cards."""
    requirements = split_requirements(posting)
    stage("match", f"{len(requirements)} requirements")
    cards = _index_cards(corpus)
    rows: list[RequirementMatch] = []
    total = len(requirements)
    for index, requirement in enumerate(requirements, start=1):
        note(f"{index}/{total} {requirement.text[:80]}")
        rows.append(_match_one(corpus, requirement, cfg, embedder, cards))
    return MatchReport(tuple(rows))


def write_match(report: MatchReport, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%y%m%d-%H%M%S")
    path = directory / f"{stamp}.md"
    if path.exists():
        stamp = datetime.now(UTC).strftime("%y%m%d-%H%M%S-%f")
        path = directory / f"{stamp}.md"
    path.write_text(_render(report), encoding="utf-8")
    return path


def _match_one(
    corpus: Corpus,
    requirement: Requirement,
    cfg: object,
    embedder: object | None,
    cards: dict[str, ClaimCard],
) -> RequirementMatch:
    if not _specific(requirement.text):
        return RequirementMatch(
            requirement.text,
            requirement.unsplit,
            True,
            GAP_BROAD,
            (),
        )
    ordered = _approved_rows(corpus, requirement.text, cards)
    ordered.extend(_search_rows(corpus, requirement.text, cfg, embedder, cards))
    evidence = _cap(ordered)
    gap = "" if evidence else GAP_NONE
    return RequirementMatch(
        requirement.text,
        requirement.unsplit,
        False,
        gap,
        evidence,
    )


def _search_rows(
    corpus: Corpus,
    requirement: str,
    cfg: object,
    embedder: object | None,
    cards: dict[str, ClaimCard],
) -> list[_Row]:
    hits = _candidates(corpus, requirement, cfg, embedder)
    kinds = set(kinds_mentioned(requirement))
    skills = set(infer_skills(requirement))
    paired = list(enumerate(hits))
    paired.sort(key=lambda pair: (0 if _boosted(pair[1], kinds, skills) else 1, pair[0]))
    rows: list[_Row] = []
    for _index, hit in paired:
        row = _row_from_hit(corpus, requirement, hit, cards)
        if row is not None:
            rows.append(row)
    return rows


def _candidates(
    corpus: Corpus,
    requirement: str,
    cfg: object,
    embedder: object | None,
) -> list[Hit]:
    """Lexical passages, then fuse neighbors even when several lexical hits exist."""
    lexical = collect_hits(
        corpus,
        requirement,
        cfg,
        limit=MAX_HITS,
        query_vec=None,
    )
    if not getattr(cfg, "ask_embed", True):
        return lexical
    query_vec = _query_vector(embedder, requirement)
    embed_model = str(getattr(embedder, "model", "") or "") if query_vec else ""
    if not query_vec or not embed_model:
        return lexical
    neighbors = _vector_hits(corpus, query_vec, embed_model, corpus.records(), MAX_HITS)
    if not neighbors:
        return lexical
    if not lexical:
        return neighbors[:MAX_HITS]
    return _fuse(lexical, neighbors, MAX_HITS)


def _row_from_hit(
    corpus: Corpus,
    requirement: str,
    hit: Hit,
    cards: dict[str, ClaimCard],
) -> _Row | None:
    record = corpus.get_record(hit.uri)
    if record is None:
        return None
    quote = carrying_span(requirement, hit.text)
    if quote and _shares_specific(requirement, quote):
        route = "passage"
        shown = " ".join(quote.split())
    elif hit.cosine >= COSINE_QUOTE:
        route = "neighbor"
        shown = _short_quote(hit.text)
        if not shown:
            return None
    else:
        return None
    card = cards.get(hit.uri)
    year_values = header_values(record.text, "Year")
    return _Row(
        source=record.source,
        title=record.title,
        year=year_values[0] if year_values else "",
        quote=shown,
        uri=hit.uri,
        route=route,
        card_id=card.id if card else "",
        card_status=card.status if card else "",
    )


def _approved_rows(
    corpus: Corpus,
    requirement: str,
    cards: dict[str, ClaimCard],
) -> list[_Row]:
    rows: list[_Row] = []
    approved = [card for card in cards.values() if card.status == STATUS_APPROVED]
    seen_ids: set[str] = set()
    for card in sorted(approved, key=lambda item: item.id):
        if card.id in seen_ids:
            continue
        seen_ids.add(card.id)
        span = (card.extras.get("span") or "").strip()
        if not span or not _shares_specific(requirement, span):
            continue
        if not carrying_span(requirement, span):
            continue
        uri = (card.extras.get("span_uri") or "").strip()
        if not uri and card.citations:
            uri = card.citations[0].strip()
        if not uri:
            continue
        record = corpus.get_record(uri)
        year = ""
        title = card.claim
        source = card.source
        if record is not None:
            source = record.source or source
            title = record.title or title
            values = header_values(record.text, "Year")
            year = values[0] if values else ""
        rows.append(
            _Row(
                source=source,
                title=title,
                year=year,
                quote=" ".join(span.split()),
                uri=uri,
                route="span",
                card_id=card.id,
                card_status=card.status,
            )
        )
    return rows


def _cap(rows: list[_Row]) -> tuple[Evidence, ...]:
    kept: list[Evidence] = []
    seen: set[str] = set()
    counts: dict[str, int] = {}
    for row in rows:
        if row.uri in seen:
            continue
        if counts.get(row.source, 0) >= SOURCE_CAP:
            continue
        seen.add(row.uri)
        counts[row.source] = counts.get(row.source, 0) + 1
        kept.append(
            Evidence(
                rank=len(kept) + 1,
                source=row.source,
                title=row.title,
                year=row.year,
                quote=row.quote,
                uri=row.uri,
                route=row.route,
                card_id=row.card_id,
                card_status=row.card_status,
            )
        )
        if len(kept) >= PER_REQUIREMENT:
            break
    return tuple(kept)


def _index_cards(corpus: Corpus) -> dict[str, ClaimCard]:
    best: dict[str, ClaimCard] = {}

    def consider(uri: str, card: ClaimCard) -> None:
        key = uri.strip()
        if not key:
            return
        prev = best.get(key)
        if prev is None or _STATUS_RANK.get(card.status, 9) < _STATUS_RANK.get(prev.status, 9):
            best[key] = card

    for card in corpus.cards():
        for uri in card.citations:
            consider(uri, card)
        consider(card.extras.get("span_uri") or "", card)
    return best


def _specific(text: str) -> set[str]:
    return {token for token in content_tokens(text) if token not in _GENERIC}


def _shares_specific(requirement: str, quote: str) -> bool:
    return bool(_specific(requirement) & content_token_set(quote))


def _boosted(hit: Hit, kinds: set[str], skills: set[str]) -> bool:
    found = header_values(hit.text, "Kind")
    if found and found[0] in kinds:
        return True
    text = hit.text.lower()
    return any(skill.replace("-", " ") in text for skill in skills)


def _short_quote(text: str) -> str:
    for sentence in sentences(text):
        if content_tokens(sentence):
            return " ".join(sentence.split())[:240]
    return ""


def _heading_name(line: str) -> str | None:
    text = line.strip()
    if text.startswith("#"):
        name = text.lstrip("#").strip()
    elif text.endswith(":") and "." not in text and len(text) <= 80:
        name = text[:-1].strip()
    else:
        folded = " ".join(text.lower().split())
        if len(folded) <= 40 and _is_boilerplate(folded):
            return folded
        return None
    folded = " ".join(name.lower().split())
    if not folded or len(folded) > 80:
        return None
    return folded


def _is_boilerplate(name: str) -> bool:
    return any(phrase in name for phrase in _BOILERPLATE)


def _has_cue(text: str) -> bool:
    return _CUE.search(text) is not None


def _render(report: MatchReport) -> str:
    lines = ["# Match", ""]
    for index, item in enumerate(report.requirements, start=1):
        lines.extend([f"## {index}. {item.text}", ""])
        if item.unsplit:
            lines.extend(["unsplit", ""])
        if item.broad:
            lines.extend(["broad", ""])
        if item.gap:
            lines.extend([f"gap: {item.gap}", ""])
        for hit in item.evidence:
            year = f" · {hit.year}" if hit.year else ""
            lines.append(f"{hit.rank}. {hit.route} · {hit.source} · {hit.title}{year}")
            lines.append("")
            lines.append(f"> {hit.quote}")
            lines.append("")
            lines.append(f"uri: {hit.uri}")
            if hit.card_id:
                lines.append(f"card: {hit.card_id} {hit.card_status}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"
