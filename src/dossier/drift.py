"""What changed under an approved card. Read-only except the report file."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from dossier.cards import STATUS_APPROVED, sentences
from dossier.show import stale_spans
from dossier.store import Corpus

_MIN_SENTENCE = 40


@dataclass(frozen=True)
class DriftReport:
    stale: tuple[tuple[str, str, str], ...]
    duplicates: tuple[tuple[str, tuple[str, ...]], ...]
    unseen: tuple[tuple[str, str, str], ...]


def collect_drift(corpus: Corpus) -> DriftReport:
    """Stale approved cards, exact duplicate sentences, and unseen full-walk URIs."""
    stale_ids = {card.id for card in stale_spans(corpus)}
    stale: list[tuple[str, str, str]] = []
    for card in corpus.cards(STATUS_APPROVED):
        reasons: list[str] = []
        if card.extras.get("stale_reason"):
            reasons.append(str(card.extras["stale_reason"]))
        if card.id in stale_ids:
            reasons.append("span_left_record")
        if reasons:
            stale.append((card.id, card.claim, ",".join(reasons)))
    groups: dict[str, list[str]] = {}
    for record in corpus.records():
        seen: set[str] = set()
        for sentence in sentences(record.text):
            norm = " ".join(sentence.split())
            if len(norm) < _MIN_SENTENCE or norm in seen:
                continue
            seen.add(norm)
            groups.setdefault(norm, []).append(record.uri)
    duplicates = tuple(
        (text, tuple(uris))
        for text, uris in sorted(groups.items())
        if len(set(uris)) >= 2
    )
    return DriftReport(
        stale=tuple(stale),
        duplicates=duplicates,
        unseen=tuple(corpus.unseen_rows()),
    )


def render_drift(report: DriftReport) -> str:
    lines = ["# Drift", ""]
    lines.append(f"stale: {len(report.stale)}")
    lines.append(f"duplicates: {len(report.duplicates)}")
    lines.append(f"unseen: {len(report.unseen)}")
    lines.append("")
    lines.append("## Stale cards")
    lines.append("")
    if not report.stale:
        lines.append("None.")
    for card_id, claim, reason in report.stale:
        lines.append(f"- {card_id} ({reason}): {claim}")
    lines.append("")
    lines.append("## Duplicate sentences")
    lines.append("")
    if not report.duplicates:
        lines.append("None.")
    for text, uris in report.duplicates:
        lines.append(f"- {text}")
        for uri in uris:
            lines.append(f"  - {uri}")
    lines.append("")
    lines.append("## Unseen")
    lines.append("")
    if not report.unseen:
        lines.append("None.")
    for source, root, uri in report.unseen:
        lines.append(f"- {source} {uri}")
        lines.append(f"  - {root}")
    lines.append("")
    return "\n".join(lines)


def write_drift(corpus: Corpus, directory: Path) -> tuple[Path, DriftReport]:
    directory.mkdir(parents=True, exist_ok=True)
    report = collect_drift(corpus)
    stamp = datetime.now(UTC).strftime("%y%m%d-%H%M%S")
    path = directory / f"{stamp}.md"
    if path.exists():
        stamp = datetime.now(UTC).strftime("%y%m%d-%H%M%S-%f")
        path = directory / f"{stamp}.md"
    path.write_text(render_drift(report), encoding="utf-8")
    return path, report
