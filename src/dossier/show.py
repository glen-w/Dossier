"""Show the sentence that carries a claim. No model."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from dossier.cards import (
    STATUS_APPROVED,
    STATUS_PENDING,
    ClaimCard,
    carrying_span,
    header_values,
)
from dossier.lenses import LENSES
from dossier.store import Corpus

_OPEN = frozenset({STATUS_PENDING, STATUS_APPROVED})


@dataclass(frozen=True)
class ShownSpan:
    sentence: str
    uri: str
    title: str


@dataclass(frozen=True)
class GapLine:
    lens: str
    kind: str
    card: ClaimCard


@dataclass(frozen=True)
class GapReport:
    lens_counts: dict[str, int]
    kind_counts: dict[str, int]
    empty_lenses: tuple[str, ...]
    singles: tuple[GapLine, ...]


def find_span(
    corpus: Corpus,
    claim: str,
    *,
    uri: str | None = None,
    source: str | None = None,
) -> ShownSpan | None:
    """Shortest carrying sentence across records. Empty when none exists."""
    text = claim.strip()
    if not text:
        return None
    records = corpus.records(source)
    if uri:
        records = [rec for rec in records if rec.uri == uri]
    best: ShownSpan | None = None
    for rec in records:
        sentence = carrying_span(text, rec.text)
        if not sentence:
            continue
        if best is None or len(sentence) < len(best.sentence):
            best = ShownSpan(sentence=sentence, uri=rec.uri, title=rec.title)
    return best


def defend_cards(corpus: Corpus) -> tuple[list[ClaimCard], list[ClaimCard]]:
    """Store span extras on pending and approved cards. Status stays put."""
    spanned: list[ClaimCard] = []
    unspanned: list[ClaimCard] = []
    for card in corpus.cards():
        if card.status not in _OPEN:
            continue
        sentence, span_uri = _first_span(corpus, card)
        extras = dict(card.extras)
        if sentence:
            extras["span"] = sentence
            extras["span_uri"] = span_uri
            updated = replace(card, extras=extras)
            corpus.put_card(updated)
            spanned.append(updated)
            continue
        extras.pop("span", None)
        extras.pop("span_uri", None)
        if extras != dict(card.extras):
            corpus.put_card(replace(card, extras=extras))
        unspanned.append(replace(card, extras=extras))
    return spanned, unspanned


def gap_report(corpus: Corpus) -> GapReport:
    """Lens and kind counts, empty lenses, and single-sourced approved cards."""
    lens_counts = {name: 0 for name in LENSES}
    kind_counts: dict[str, int] = {}
    for rec in corpus.records():
        for lens in header_values(rec.text, "Lens"):
            if lens in lens_counts:
                lens_counts[lens] += 1
        for kind in header_values(rec.text, "Kind"):
            kind_counts[kind] = kind_counts.get(kind, 0) + 1
    empty = tuple(name for name in LENSES if lens_counts[name] == 0)
    groups: dict[tuple[str, str], list[ClaimCard]] = {}
    for card in corpus.cards(STATUS_APPROVED):
        if not (card.extras.get("span") or "").strip():
            continue
        lens, kind = _card_lens_kind(corpus, card)
        if not lens or not kind:
            continue
        groups.setdefault((lens, kind), []).append(card)
    singles = tuple(
        GapLine(lens, kind, cards[0])
        for (lens, kind), cards in sorted(groups.items())
        if len(cards) == 1
    )
    return GapReport(
        lens_counts=lens_counts,
        kind_counts=kind_counts,
        empty_lenses=empty,
        singles=singles,
    )


def render_packet(corpus: Corpus) -> str:
    approved = corpus.cards(STATUS_APPROVED)
    spanned = [card for card in approved if (card.extras.get("span") or "").strip()]
    missing = [card for card in approved if card not in spanned]
    lines = ["# Dossier packet", ""]
    for card in spanned:
        lens, kind = _card_lens_kind(corpus, card)
        lines.append(f"## {card.claim}")
        lines.append("")
        lines.append(f"> {card.extras['span']}")
        lines.append("")
        if lens:
            lines.append(f"lens: {lens}")
        if kind:
            lines.append(f"kind: {kind}")
        uri = (card.extras.get("span_uri") or "").strip()
        if uri:
            lines.append(f"citation: {uri}")
        lines.append("")
    if missing:
        lines.append("# Not included")
        lines.append("")
        for card in missing:
            lines.append(f"- {card.id}: {card.claim}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_packet(corpus: Corpus, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%y%m%d-%H%M%S")
    path = directory / f"{stamp}.md"
    if path.exists():
        stamp = datetime.now(UTC).strftime("%y%m%d-%H%M%S-%f")
        path = directory / f"{stamp}.md"
    path.write_text(render_packet(corpus), encoding="utf-8")
    return path


def _first_span(corpus: Corpus, card: ClaimCard) -> tuple[str, str]:
    for cite in card.citations:
        rec = corpus.get_record(cite)
        if rec is None:
            continue
        sentence = carrying_span(card.claim, rec.text)
        if sentence:
            return sentence, rec.uri
    return "", ""


def _card_lens_kind(corpus: Corpus, card: ClaimCard) -> tuple[str, str]:
    lens = (card.extras.get("lens") or "").strip().lower()
    kind = (card.extras.get("kind") or "").strip().lower()
    if lens and kind:
        return lens, kind
    uri = (card.extras.get("span_uri") or "").strip()
    if not uri and card.citations:
        uri = card.citations[0]
    rec = corpus.get_record(uri) if uri else None
    if rec is None:
        return lens, kind
    if not lens:
        values = header_values(rec.text, "Lens")
        lens = values[0] if values else ""
    if not kind:
        values = header_values(rec.text, "Kind")
        kind = values[0] if values else ""
    return lens, kind
