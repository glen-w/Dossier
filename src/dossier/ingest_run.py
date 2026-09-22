"""Shared ingest loop with pinned progress (used by cli and prove)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from dossier.contributions import Contribution
from dossier.store import Corpus
from dossier.ui import Progress, note, ok, trunc


def run_ingest_targets(
    targets: Sequence[tuple[Contribution, Path]],
    corpus: Corpus,
    *,
    emit_summary: bool = True,
    on_source_done: Callable[[str], None] | None = None,
) -> tuple[int, int]:
    """Ingest each target. Returns (records_before_delta_start, records_after)."""
    if not targets:
        return len(corpus.records()), len(corpus.records())
    n_before = len(corpus.records())
    n_sources = len(targets)
    with Progress(n_sources, label="ingest") as bar:
        for idx, (item, path) in enumerate(targets, start=1):
            slug = trunc(path.name or str(path), 28)
            bar.status(f"{item.name} · {slug}")
            note(f"ingest {item.name} from {path}")
            n_at_start = len(corpus.records())
            item.source.load(path, corpus)
            added = len(corpus.records()) - n_at_start
            bar.tick(sources=idx, added=added)
            if on_source_done is not None:
                on_source_done(item.name)
    n_after = len(corpus.records())
    if emit_summary:
        note(f"records: {n_after} (+{n_after - n_before})")
        ok(f"ingest done · {n_after} records (+{n_after - n_before})")
    return n_before, n_after
