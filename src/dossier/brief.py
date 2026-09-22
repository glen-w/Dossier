"""Run a question pack and write a markdown brief under data/briefs."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from dossier.ask import Answer, collect_hits
from dossier.config import Config
from dossier.interview import conduct
from dossier.inventory import try_inventory
from dossier.llm.client import LLMClient
from dossier.packs import PackQuestion, follow_up
from dossier.sources.pubs import optional_pubs_hits
from dossier.store import Corpus


def ask_hits(
    corpus: Corpus,
    question: str,
    cfg: Config,
    *,
    limit: int,
    source: str | None = None,
    lens: str | None = None,
    kind: str | None = None,
) -> list:
    return collect_hits(
        corpus,
        question,
        cfg,
        limit=limit,
        source=source,
        lens=lens,
        kind=kind,
    )


def run_pack(
    corpus: Corpus,
    questions: list[PackQuestion],
    cfg: Config,
    client: LLMClient,
    *,
    mode: str,
    on_progress: Callable[[int, int, PackQuestion, Answer], None] | None = None,
    embedder: object | None = None,
) -> list[tuple[PackQuestion, Answer]]:
    queue = list(questions)
    out: list[tuple[PackQuestion, Answer]] = []
    index = 0
    blobs = [f"{rec.title}\n{rec.text}" for rec in corpus.records()]
    while index < len(queue):
        item = queue[index]
        listed = try_inventory(corpus, item)
        if listed is not None:
            result = listed
        else:
            extra = optional_pubs_hits(
                item.question,
                enabled=cfg.ask_pubs,
                limit=cfg.ask_limit,
            )
            result = conduct(
                corpus,
                item.question,
                cfg,
                client,
                mode=mode,
                limit=cfg.ask_limit,
                source=item.source,
                lens=item.lens,
                embedder=embedder,
                extra_hits=extra or None,
            )
        corpus.add_answer(
            question=item.question,
            mode=mode,
            text=result.text,
            citations=result.citations,
            refused=result.refused,
            reason=result.reason,
        )
        out.append((item, result))
        if on_progress is not None:
            on_progress(index + 1, len(queue), item, result)
        if result.refused and listed is None:
            nxt = follow_up(
                item.id,
                item.question,
                blobs,
                source=item.source,
                lens=item.lens,
            )
            if nxt is not None:
                queue.append(nxt)
        index += 1
    return out


def write_brief(items: list[tuple[PackQuestion, Answer]], directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%y%m%d-%H%M%S")
    path = directory / f"{stamp}.md"
    if path.exists():
        stamp = datetime.now(UTC).strftime("%y%m%d-%H%M%S-%f")
        path = directory / f"{stamp}.md"
    path.write_text(_render(items), encoding="utf-8")
    return path


def _render(items: list[tuple[PackQuestion, Answer]]) -> str:
    lines = ["# Dossier brief", ""]
    for item, result in items:
        lines.append(f"## {item.id}")
        lines.append("")
        lines.append(item.question)
        lines.append("")
        if result.text:
            lines.append(result.text)
        if result.route:
            lines.append(f"mode: {result.route}")
        if result.refused:
            lines.append(f"refused: {result.reason}")
        elif result.citations:
            lines.append("")
            lines.append("citations: " + ", ".join(result.citations))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
