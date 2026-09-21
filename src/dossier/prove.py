"""Disposable real-corpus prove pass. Never auto-approves."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from dossier.brief import run_pack, write_brief
from dossier.cards import STATUS_APPROVED, STATUS_PENDING, STATUS_REFUSED
from dossier.config import Config
from dossier.extract import extract_corpus
from dossier.interview import conduct
from dossier.llm import llm_egress_is_remote
from dossier.llm.budget import CallBudget
from dossier.llm.client import NullLLMClient
from dossier.packs import load_pack
from dossier.paths import evidence_db
from dossier.show import defend_cards, gap_report, write_packet
from dossier.store import Corpus

DEFAULT_ADAPTERS = ("linkedin", "chatgpt", "applications")
PROVE_QUESTIONS = (
    "what work is in this corpus?",
    "what did I publish or write?",
    "what roles or positions appear?",
)


@dataclass
class ProveLedger:
    data_dir: str
    stamp: str
    fts5: bool
    python: str
    sqlite: str
    provider: str
    egress: bool
    adapters_requested: list[str]
    adapters_ingested: list[str] = field(default_factory=list)
    adapters_skipped: list[str] = field(default_factory=list)
    records_by_source: dict[str, int] = field(default_factory=dict)
    records_total: int = 0
    cards_pending: int = 0
    cards_approved: int = 0
    cards_refused: int = 0
    spanned: int = 0
    unspanned: int = 0
    brief_path: str = ""
    packet_path: str = ""
    ask_results: list[dict] = field(default_factory=list)
    pubs_rows: int = 0
    pubs_note: str = ""
    model_calls: int = 0
    next_steps: list[str] = field(default_factory=list)


def run_prove(
    *,
    data: Path | None = None,
    adapters: tuple[str, ...] | None = None,
    allow_overlap: bool = False,
    with_llm: bool = False,
    include_pubs: bool = False,
) -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if data is not None and not str(data).strip():
        data = None
    root = data or Path(tempfile.mkdtemp(prefix=f"dossier-prove-{stamp}-"))
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)

    saved = {
        key: os.environ.get(key)
        for key in (
            "DOSSIER_DATA",
            "DOSSIER_SEEKER_OVERALL",
            "DOSSIER_SEEKER_PER_STRATUM",
            "DOSSIER_LLM_PROVIDER",
            "DOSSIER_EXTRACT_LLM",
            "DOSSIER_RUN_ADAPTERS",
        )
    }
    try:
        return _run_prove_body(
            root=root,
            stamp=stamp,
            adapters=adapters,
            allow_overlap=allow_overlap,
            with_llm=with_llm,
            include_pubs=include_pubs,
        )
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _run_prove_body(
    *,
    root: Path,
    stamp: str,
    adapters: tuple[str, ...] | None,
    allow_overlap: bool,
    with_llm: bool,
    include_pubs: bool,
) -> int:
    os.environ["DOSSIER_DATA"] = str(root)
    os.environ.setdefault("DOSSIER_SEEKER_OVERALL", "80")
    os.environ.setdefault("DOSSIER_SEEKER_PER_STRATUM", "10")
    if not with_llm:
        os.environ["DOSSIER_LLM_PROVIDER"] = "off"
        os.environ["DOSSIER_EXTRACT_LLM"] = "false"

    names = list(adapters or DEFAULT_ADAPTERS)
    if include_pubs and "pubs" not in names:
        names.append("pubs")
    os.environ["DOSSIER_RUN_ADAPTERS"] = ",".join(names)

    cfg = Config.from_env()
    db = evidence_db(Path(cfg.data_dir))
    corpus = Corpus(db)

    ledger = ProveLedger(
        data_dir=str(root),
        stamp=stamp,
        fts5=corpus.fts_ok,
        python=sys.executable,
        sqlite=sqlite3.sqlite_version,
        provider=cfg.llm_provider if cfg.llm_enabled else "off",
        egress=llm_egress_is_remote(cfg),
        adapters_requested=names,
    )

    try:
        if not corpus.fts_ok and not allow_overlap:
            print("prove refused: fts5 unavailable in this interpreter", file=sys.stderr)
            print(f"python: {sys.executable}", file=sys.stderr)
            print("re-run with --allow-overlap to use whole-word fallback", file=sys.stderr)
            _write_ledger(root, ledger)
            return 2

        from dossier.cli import _detected_targets

        targets, skipped = _detected_targets(tuple(names))
        ledger.adapters_skipped = list(skipped)
        for line in skipped:
            print(line)

        n_before = len(corpus.records())
        for item, path in targets:
            print(f"ingest {item.name} from {path}")
            item.source.load(path, corpus)
            if item.name not in ledger.adapters_ingested:
                ledger.adapters_ingested.append(item.name)
        n_after = len(corpus.records())
        if targets:
            print(f"records: {n_after} (+{n_after - n_before})")

        pubs = corpus.records("pubs")
        ledger.pubs_rows = len(pubs)
        if "pubs" in names and ledger.pubs_rows == 0:
            ledger.pubs_note = "skipped (gate or empty /search)"
        elif ledger.pubs_rows:
            ledger.pubs_note = f"rows={ledger.pubs_rows}"

        if not corpus.records():
            print("prove refused: no records ingested", file=sys.stderr)
            _finalize_counts(corpus, ledger)
            _write_ledger(root, ledger)
            return 1

        budget = CallBudget(cfg.llm_max_calls)
        client: object = NullLLMClient()
        use_llm = bool(with_llm and cfg.llm_enabled)
        if use_llm:
            from dossier.cli import _client_for_mode

            live, code = _client_for_mode(cfg, "auto")
            if code is not None:
                _finalize_counts(corpus, ledger)
                _write_ledger(root, ledger)
                return code
            client = budget.wrap(live)

        from dossier.cli import _extract_progress

        cards = extract_corpus(
            corpus,
            client,  # type: ignore[arg-type]
            cfg.llm_model,
            source=None,
            limit=None,
            use_llm=bool(use_llm and cfg.extract_llm),
            timeout_seconds=cfg.llm_timeout_seconds,
            chunk_chars=cfg.extract_chunk_chars,
            max_chunks=cfg.extract_max_chunks,
            on_progress=_extract_progress(
                use_llm=bool(use_llm and cfg.extract_llm),
                model=cfg.llm_model,
            ),
        )
        print(f"extract: {len(cards)} cards")

        questions = load_pack(cfg.run_pack)
        items = run_pack(
            corpus,
            questions,
            cfg,
            client if use_llm else NullLLMClient(),  # type: ignore[arg-type]
            mode="exact",
        )
        brief = write_brief(items, root / "briefs")
        ledger.brief_path = str(brief)
        print(brief)

        spanned, unspanned = defend_cards(corpus)
        ledger.spanned = len(spanned)
        ledger.unspanned = len(unspanned)
        print(f"defend: spanned={ledger.spanned} unspanned={ledger.unspanned}")
        from dossier.lenses import LENSES

        report = gap_report(corpus)
        for lens in LENSES:
            print(f"lens {lens}: {report.lens_counts[lens]}")
        if report.empty_lenses:
            print("empty: " + ", ".join(report.empty_lenses))
        for line in report.singles:
            print(f"single {line.lens}/{line.kind} {line.card.id}  {line.card.claim}")

        packet = write_packet(corpus, root / "packets")
        ledger.packet_path = str(packet)
        print(packet)

        for question in PROVE_QUESTIONS:
            result = conduct(
                corpus,
                question,
                cfg,
                NullLLMClient(),
                mode="exact",
                limit=cfg.ask_limit,
            )
            entry = {
                "question": question,
                "refused": result.refused,
                "reason": result.reason,
                "citations": list(result.citations),
            }
            ledger.ask_results.append(entry)
            if result.refused:
                print(f"ask refused: {question}")
                if result.reason:
                    print(f"  {result.reason}")
            else:
                print(f"ask cited: {question}")
                print(f"  citations: {', '.join(result.citations)}")

        ledger.model_calls = budget.calls
        _finalize_counts(corpus, ledger)
        ledger.next_steps = [
            f"DOSSIER_DATA={root} uv run dossier buffet --status pending",
            f"DOSSIER_DATA={root} uv run dossier approve <card-id>",
            f'DOSSIER_DATA={root} uv run dossier ask "…"',
        ]
        path = _write_ledger(root, ledger)
        print(f"ledger: {path}")
        for step in ledger.next_steps:
            print(f"next: {step}")
        if ledger.records_total == 0:
            return 1
        return 0
    finally:
        corpus.close()


def _finalize_counts(corpus: Corpus, ledger: ProveLedger) -> None:
    by_source: dict[str, int] = {}
    for rec in corpus.records():
        by_source[rec.source] = by_source.get(rec.source, 0) + 1
    ledger.records_by_source = by_source
    ledger.records_total = sum(by_source.values())
    ledger.cards_pending = len(corpus.cards(STATUS_PENDING))
    ledger.cards_approved = len(corpus.cards(STATUS_APPROVED))
    ledger.cards_refused = len(corpus.cards(STATUS_REFUSED))
    ledger.pubs_rows = by_source.get("pubs", 0)


def _write_ledger(root: Path, ledger: ProveLedger) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    data = asdict(ledger)
    json_path = root / "ledger.json"
    json_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    md = root / "ledger.md"
    lines = [
        f"# Prove ledger ({ledger.stamp})",
        "",
        f"- data_dir: `{ledger.data_dir}`",
        f"- fts5: {'yes' if ledger.fts5 else 'no'}",
        f"- python: `{ledger.python}`",
        f"- sqlite: {ledger.sqlite}",
        f"- provider: {ledger.provider}",
        f"- egress: {'yes' if ledger.egress else 'no'}",
        f"- records: {ledger.records_total}",
        f"- pubs: {ledger.pubs_note or ledger.pubs_rows}",
        f"- cards pending/approved/refused: "
        f"{ledger.cards_pending}/{ledger.cards_approved}/{ledger.cards_refused}",
        f"- spanned/unspanned: {ledger.spanned}/{ledger.unspanned}",
        f"- brief: `{ledger.brief_path}`",
        f"- packet: `{ledger.packet_path}`",
        f"- model_calls: {ledger.model_calls}",
        "",
        "## Records by source",
        "",
    ]
    for source, count in sorted(ledger.records_by_source.items()):
        lines.append(f"- {source}: {count}")
    if ledger.adapters_skipped:
        lines.extend(["", "## Skipped adapters", ""])
        for line in ledger.adapters_skipped:
            lines.append(f"- {line}")
    lines.extend(["", "## Ask smoke", ""])
    for item in ledger.ask_results:
        status = "refused" if item["refused"] else "cited"
        lines.append(f"- {status}: {item['question']}")
        if item.get("citations"):
            lines.append(f"  - citations: {', '.join(item['citations'])}")
        if item.get("reason"):
            lines.append(f"  - reason: {item['reason']}")
    if ledger.next_steps:
        lines.extend(["", "## Next (human)", ""])
        for step in ledger.next_steps:
            lines.append(f"- `{step}`")
    lines.append("")
    md.write_text("\n".join(lines), encoding="utf-8")
    return json_path
