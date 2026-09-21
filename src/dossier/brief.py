"""Run a question pack and write a markdown brief under data/briefs."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from dossier.ask import Answer, Hit, expand_tokens, match_query, respond, retrieve
from dossier.config import Config
from dossier.llm.client import LLMClient
from dossier.packs import PackQuestion
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
) -> list[Hit]:
    tokens = expand_tokens(question, cfg.lexicon)
    fts_rank: dict[str, float] | None = None
    if cfg.ask_fts:
        query = match_query(tokens)
        if query:
            found = corpus.search_fts(query, limit=max(limit * 5, 30))
            if found:
                fts_rank = {uri: rank for uri, rank in found}
    return retrieve(
        corpus.records(),
        question,
        limit=limit,
        source=source,
        lens=lens,
        kind=kind,
        tokens=tokens,
        fts_rank=fts_rank,
    )


def run_pack(
    corpus: Corpus,
    questions: list[PackQuestion],
    cfg: Config,
    client: LLMClient,
    *,
    mode: str,
) -> list[tuple[PackQuestion, Answer]]:
    out: list[tuple[PackQuestion, Answer]] = []
    for item in questions:
        hits = ask_hits(
            corpus,
            item.question,
            cfg,
            limit=cfg.ask_limit,
            source=item.source,
            lens=item.lens,
        )
        result = respond(item.question, hits, client, cfg.llm_model, mode=mode)
        corpus.add_answer(
            question=item.question,
            mode=mode,
            text=result.text,
            citations=result.citations,
            refused=result.refused,
            reason=result.reason,
        )
        out.append((item, result))
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
        if result.refused:
            lines.append(f"refused: {result.reason}")
        else:
            lines.append(result.text)
            if result.citations:
                lines.append("")
                lines.append("citations: " + ", ".join(result.citations))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
