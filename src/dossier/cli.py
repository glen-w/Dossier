"""dossier — ingest, extract claim cards, ask the corpus, approve a buffet."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from dataclasses import replace
from pathlib import Path

from dossier.ask import ASK_MODES
from dossier.brief import run_pack, write_brief
from dossier.cards import STATUS_APPROVED, STATUS_PENDING, STATUS_REFUSED, span_max
from dossier.config import Config
from dossier.contributions import CONTRIBUTIONS
from dossier.extract import ExtractProgress, extract_corpus
from dossier.ingest_run import run_ingest_targets
from dossier.interview import conduct
from dossier.llm import egress_status, get_client, llm_egress_is_remote
from dossier.llm.budget import CallBudget
from dossier.llm.client import (
    LLMClient,
    NullLLMClient,
    select_fast_model,
)
from dossier.match import match_posting, match_postings, write_match, write_postings
from dossier.packs import posting_pack, resolve_pack
from dossier.paths import (
    TomlConfigError,
    employer_paths,
    evidence_db,
    git_paths,
    git_user,
    pubs_collection,
)
from dossier.prove import DEFAULT_ADAPTERS, run_prove
from dossier.show import defend_cards, find_span, gap_report, write_packet
from dossier.sources.pubs import optional_pubs_hits
from dossier.store import Corpus
from dossier.ui import HUES, Progress, note, ok, paint, stage, trunc

_YELLOW = "\033[33m"
_RESET = "\033[0m"


def fail(message: str, code: int = 2) -> int:
    print(f"FAIL: {message}", file=sys.stderr)
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dossier",
        description="Local-first work-evidence locker. Dumps stay off git.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ing = sub.add_parser("ingest", help="Load one adapter into the local corpus")
    p_ing.add_argument(
        "--adapter",
        help="pubs, chatgpt, linkedin, applications, transcripts, slack, mbox, meetings, employer, git, notes, ics",
    )
    p_ing.add_argument("path", nargs="?", type=Path, help="Override the default path")

    p_ex = sub.add_parser("extract", help="Propose claim cards from ingested records")
    p_ex.add_argument("--source", help="Limit to one adapter name")
    p_ex.add_argument("--limit", type=int, default=None)

    p_buf = sub.add_parser("buffet", help="List claim cards")
    p_buf.add_argument(
        "--status",
        choices=("pending", "approved", "refused"),
        default=None,
    )

    p_ok = sub.add_parser("approve", help="Human gate: mark a pending card approved")
    p_ok.add_argument("card_id", nargs="?", default=None)
    _add_gate_filters(p_ok)

    p_no = sub.add_parser("refuse", help="Human gate: mark a pending card refused")
    p_no.add_argument("card_id", nargs="?", default=None)
    _add_gate_filters(p_no)

    p_reopen = sub.add_parser("reopen", help="Send an approved or refused card back to pending")
    p_reopen.add_argument("card_id", nargs="?", default=None)
    _add_gate_filters(p_reopen)

    p_review = sub.add_parser(
        "review",
        help="Open the workbench review page (needs the [web] extra)",
    )
    p_review.add_argument("--port", type=int, default=8766)

    p_gui = sub.add_parser(
        "gui",
        help="Loopback workbench (needs the [web] extra)",
    )
    p_gui.add_argument("--port", type=int, default=8766)
    p_gui.add_argument("--host", default="127.0.0.1")

    p_ask = sub.add_parser("ask", help="Answer from ingested records, with citations")
    p_ask.add_argument("question")
    p_ask.add_argument("--limit", type=int, default=None)
    p_ask.add_argument("--source", help="Limit retrieval to one adapter name")
    _add_scope_flags(p_ask)
    p_ask.add_argument("--lens", help="Limit retrieval to a seeker lens header")
    p_ask.add_argument("--kind", help="Limit retrieval to a seeker kind header")
    p_ask.add_argument("--mode", choices=ASK_MODES, default=None)
    p_ask.add_argument(
        "--follow",
        action="store_true",
        help="Include up to three earlier accepted answers as context",
    )

    p_brief = sub.add_parser("brief", help="Answer a question pack into data/briefs")
    p_brief.add_argument("--pack", default=None, help="career, or a path to a JSON pack")
    p_brief.add_argument("--posting", type=Path, help="Local posting text for the posting pack")
    p_brief.add_argument("--mode", choices=ASK_MODES, default=None)
    _add_scope_flags(p_brief)

    p_run = sub.add_parser(
        "run",
        help="Ingest detected adapters, draft claims, then write a brief",
    )
    p_run.add_argument("--pack", default=None, help="career, or a path to a JSON pack")
    p_run.add_argument("--posting", type=Path, help="Local posting text for the posting pack")
    p_run.add_argument("--mode", choices=ASK_MODES, default=None)

    p_span = sub.add_parser("span", help="Print the sentence that carries a claim")
    p_span.add_argument("claim")
    p_span.add_argument("--uri", help="Limit the search to one record URI")
    p_span.add_argument("--source", help="Limit the search to one adapter name")

    p_def = sub.add_parser(
        "defend",
        help="Store the carrying sentence on pending and approved cards",
    )
    p_def.add_argument("--source", help="Limit to one adapter name")
    p_def.add_argument(
        "--refresh",
        action="store_true",
        help="Recompute spans under the current span rule",
    )
    p_def.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the histogram and unspanned count without writing",
    )
    sub.add_parser(
        "gaps",
        help="Show empty lenses, unspanned cards, and records still waiting on extract",
    )
    sub.add_parser("packet", help="Write a markdown packet of spanned approved cards")
    p_tailor = sub.add_parser(
        "tailor",
        help="Write CV or letter markdown from spanned approved cards",
    )
    p_tailor.add_argument("--posting", type=Path, required=True)
    p_tailor.add_argument("--kind", choices=("cv", "letter"), default="cv")
    p_tailor.add_argument(
        "--format",
        choices=("markdown", "json-resume", "html", "docx", "pdf"),
        default="markdown",
        dest="fmt",
    )
    p_tailor.add_argument(
        "--with-sources",
        action="store_true",
        help="Append the cited record URIs for you to check (not for sending)",
    )
    p_tailor.add_argument(
        "--arrange",
        action="store_true",
        help="Letter only: one completion that may only reuse the selected spans",
    )
    p_match = sub.add_parser(
        "match",
        help="List evidence for each requirement in a job spec",
    )
    match_spec = p_match.add_mutually_exclusive_group(required=True)
    match_spec.add_argument("--posting", type=Path)
    match_spec.add_argument(
        "--postings",
        type=Path,
        help="Directory of posting files; write gaps that repeat in two or more",
    )
    _add_scope_flags(p_match)
    p_index = sub.add_parser(
        "index", help="Embed passages into evidence.db with the local model (resumable)"
    )
    p_index.add_argument(
        "--sources",
        help="Comma-separated sources to embed this run (default: every source)",
    )
    p_index.add_argument(
        "--limit", type=int, help="Embed at most this many passages this run"
    )

    p_doc = sub.add_parser("doctor", help="Print local readiness without writing")
    p_doc.add_argument(
        "--deep",
        action="store_true",
        help="Integrity check, span histogram, FTS parity, orphan cards",
    )

    p_audit = sub.add_parser(
        "audit-cards",
        help="List approved cards whose claim would now be refused",
    )
    p_audit.add_argument(
        "--from-audit",
        action="store_true",
        dest="write_ids",
        help="Print card ids one per line for reopen --from-audit",
    )

    p_reopen.add_argument(
        "--from-audit",
        action="store_true",
        help="Reopen every card listed by audit-cards",
    )

    sub.add_parser("backup", help="Copy evidence.db via the SQLite backup API")
    p_restore = sub.add_parser(
        "restore",
        help="Check a backup. Replace the live locker only with --replace",
    )
    p_restore.add_argument("backup", type=Path)
    p_restore.add_argument(
        "--replace",
        action="store_true",
        help="Copy the live locker aside, then swap in the backup",
    )
    sub.add_parser(
        "drift",
        help="Report stale cards, duplicate sentences, and unseen full-walk URIs",
    )
    p_drop = sub.add_parser(
        "drop-record",
        help="Remove one record that no approved card cites",
    )
    p_drop.add_argument("uri")
    sub.add_parser("rebuild-index", help="Rebuild FTS tables without opening-time rewrite")

    p_eval = sub.add_parser("eval", help="Run the synthetic golden set")
    p_eval.add_argument("--path", type=Path, help="JSON golden set (default: bundled)")
    p_eval.add_argument(
        "--retrieval",
        action="store_true",
        help="Also report recall@k and MRR on a generated locker (no model needed)",
    )

    p_exp = sub.add_parser("export", help="Write cards, spans, and answers as JSON")
    p_exp.add_argument("--out", type=Path, required=True)
    p_imp = sub.add_parser("import", help="Load cards whose citations are still in the locker")
    p_imp.add_argument("--path", type=Path, required=True)

    p_prove = sub.add_parser(
        "prove",
        help="Disposable real-corpus pass into a throwaway data dir (never approves)",
    )
    p_prove.add_argument(
        "--data",
        default=None,
        help="Data directory (default: a new temp dir)",
    )
    p_prove.add_argument(
        "--adapters",
        default=",".join(DEFAULT_ADAPTERS),
        help=f"Comma-separated allowlist (default: {','.join(DEFAULT_ADAPTERS)})",
    )
    p_prove.add_argument(
        "--allow-overlap",
        action="store_true",
        help="Continue when this interpreter has no FTS5",
    )
    p_prove.add_argument(
        "--with-llm",
        action="store_true",
        help="Allow model calls during extract (default: off)",
    )
    p_prove.add_argument(
        "--pubs",
        action="store_true",
        help="Include the pubs adapter (the named Zotero collection)",
    )

    p_ref = sub.add_parser("referees", help="Read-only referee shortlist")
    posting = p_ref.add_mutually_exclusive_group(required=True)
    posting.add_argument("--posting", type=Path, help="Posting text file")
    posting.add_argument("--text", help="Posting text")
    p_ref.add_argument("--employer", default="", help="Hiring organisation name")
    p_ref.add_argument("--people", type=Path, help="JSON people file")
    p_ref.add_argument("--policy", type=Path, help="JSON skip and alias file")
    p_ref.add_argument(
        "--students",
        action="store_true",
        help="Keep people listed as students in the policy file",
    )

    args = parser.parse_args(argv)
    from dossier.ops import note_egress

    note_egress.done = False  # type: ignore[attr-defined]
    if args.cmd == "referees":
        return _referees(args)
    if args.cmd == "prove":
        names = tuple(part.strip() for part in args.adapters.split(",") if part.strip())
        raw = args.data
        data: Path | None
        if raw is None or not str(raw).strip():
            data = None
        else:
            data = Path(str(raw)).expanduser().resolve()
        return run_prove(
            data=data,
            adapters=names or None,
            allow_overlap=args.allow_overlap,
            with_llm=args.with_llm,
            include_pubs=args.pubs,
        )
    try:
        cfg = Config.from_env()
    except TomlConfigError as exc:
        return fail(str(exc))
    if args.cmd == "doctor":
        return _doctor(cfg, deep=getattr(args, "deep", False))
    if args.cmd == "gui":
        return _gui(args)
    if args.cmd == "review":
        return _review(args)
    db = evidence_db(Path(cfg.data_dir))
    corpus = Corpus(db)
    try:
        if args.cmd == "ingest":
            return _ingest(args, corpus)
        if args.cmd == "extract":
            return _extract(args, cfg, corpus)
        if args.cmd == "buffet":
            return _buffet(args, corpus)
        if args.cmd == "approve":
            return _approve(args, corpus)
        if args.cmd == "refuse":
            return _refuse(args, corpus)
        if args.cmd == "reopen":
            return _reopen(args, corpus)
        if args.cmd == "ask":
            return _ask(args, cfg, corpus)
        if args.cmd == "brief":
            return _brief(args, cfg, corpus)
        if args.cmd == "run":
            return _run(args, cfg, corpus)
        if args.cmd == "span":
            return _span(args, corpus)
        if args.cmd == "defend":
            return _defend(
                corpus,
                source=getattr(args, "source", None),
                dry_run=getattr(args, "dry_run", False),
            )
        if args.cmd == "gaps":
            return _gaps(corpus)
        if args.cmd == "packet":
            return _packet(cfg, corpus)
        if args.cmd == "tailor":
            return _tailor(args, cfg, corpus)
        if args.cmd == "match":
            return _match(args, cfg, corpus)
        if args.cmd == "index":
            return _index(
                cfg,
                corpus,
                sources=tuple(
                    part.strip()
                    for part in (getattr(args, "sources", None) or "").split(",")
                    if part.strip()
                ),
                limit=getattr(args, "limit", None),
            )
        if args.cmd == "audit-cards":
            return _audit_cards(corpus, write_ids=getattr(args, "write_ids", False))
        if args.cmd == "backup":
            return _backup(cfg, corpus)
        if args.cmd == "restore":
            return _restore(cfg, corpus, args.backup, replace=bool(args.replace))
        if args.cmd == "drift":
            return _drift(cfg, corpus)
        if args.cmd == "drop-record":
            return _drop_record(corpus, args.uri)
        if args.cmd == "rebuild-index":
            corpus.rebuild_index()
            print("rebuilt")
            return 0
        if args.cmd == "eval":
            from dossier.eval import run_eval

            report = run_eval(corpus, path=getattr(args, "path", None))
            print(report)
            if getattr(args, "retrieval", False):
                from dossier.eval import retrieval_metrics

                print(retrieval_metrics())
            return 0 if report.ok else 1
        if args.cmd == "export":
            from dossier.portability import export_locker

            path = export_locker(corpus, args.out)
            print(path)
            return 0
        if args.cmd == "import":
            from dossier.portability import import_locker

            result = import_locker(corpus, args.path)
            print(f"imported {result.imported}")
            if result.skipped:
                print(f"skipped {result.skipped}", file=sys.stderr)
                return 1
            return 0
    finally:
        corpus.close()
    return 2


def _ingest(args: argparse.Namespace, corpus: Corpus) -> int:
    from dossier.ops import ingest

    try:
        ingest(corpus, adapter=args.adapter, path=args.path)
    except ValueError as extra:
        msg = str(extra)
        if msg.startswith("unknown adapter"):
            print("known:", ", ".join(c.name for c in CONTRIBUTIONS), file=sys.stderr)
        return fail(msg)
    except FileNotFoundError as extra:
        return fail(str(extra), 1)
    return 0


def _extract(args: argparse.Namespace, cfg: Config, corpus: Corpus) -> int:
    return _extract_cards(
        cfg,
        corpus,
        source=args.source,
        limit=args.limit,
        strict_llm=True,
        budget=CallBudget(cfg.llm_max_calls),
    )


def _note_egress(cfg: Config) -> None:
    from dossier.ops import note_egress

    note_egress(cfg)


class _LazyClient:
    """CLI alias for :class:`dossier.ops.LazyClient`."""

    def __new__(cls, cfg: Config):
        from dossier.ops import LazyClient

        return LazyClient(cfg)


def _extract_cards(
    cfg: Config,
    corpus: Corpus,
    *,
    source: str | None,
    limit: int | None,
    strict_llm: bool,
    budget: CallBudget | None = None,
) -> int:
    use_llm = cfg.extract_llm and cfg.llm_enabled
    client: LLMClient = NullLLMClient()
    spent = budget
    model = cfg.fast_model
    if use_llm:
        if llm_egress_is_remote(cfg):
            _note_egress(cfg)
        client = get_client(cfg)
        model, note = select_fast_model(cfg, client)
        if note:
            print(note, file=sys.stderr)
        ok_cfg, msg = client.check_config(model)
        if not ok_cfg:
            drafted = extract_corpus(
                corpus,
                NullLLMClient(),
                model,
                source=source,
                limit=limit,
                use_llm=False,
                timeout_seconds=min(cfg.llm_timeout_seconds, 60.0),
                chunk_chars=cfg.extract_chunk_chars,
                max_chunks=cfg.extract_max_chunks,
                max_num_ctx=cfg.llm_max_num_ctx,
                on_progress=_extract_progress(use_llm=False, model=model),
            )
            _print_extract(drafted)
            print(msg, file=sys.stderr)
            return 2 if strict_llm else 0
        if spent is None:
            spent = CallBudget(cfg.llm_max_calls)
        client = spent.wrap(client)
    cards = extract_corpus(
        corpus,
        client,
        model,
        source=source,
        limit=limit,
        use_llm=use_llm,
        timeout_seconds=min(cfg.llm_timeout_seconds, 60.0),
        chunk_chars=cfg.extract_chunk_chars,
        max_chunks=cfg.extract_max_chunks,
        max_num_ctx=cfg.llm_max_num_ctx,
        on_progress=_extract_progress(use_llm=use_llm, model=model),
    )
    _print_extract(cards)
    return 0


def _extract_progress(*, use_llm: bool, model: str):
    bar: Progress | None = None
    drafted = 0
    llm_n = 0
    passed = 0
    cards_n = 0

    def on_progress(ev: ExtractProgress) -> None:
        nonlocal bar, drafted, llm_n, passed, cards_n
        if ev.phase == "start":
            mode = f"llm={model}" if use_llm else "llm=off (drafts only)"
            detail = f"{mode} · {ev.total} to draft"
            if ev.skipped:
                detail = f"{detail} · {ev.skipped} already open"
            stage("extract", detail)
            if ev.total == 0:
                note("nothing new to extract")
                return
            bar = Progress(ev.total, label="extract")
            bar.__enter__()
            return
        if ev.phase == "llm":
            if bar is not None:
                bar.status(
                    paint(
                        f"model ← {ev.source}/{trunc(ev.title)}",
                        HUES["yellow"],
                    )
                )
            return
        if ev.phase == "draft":
            drafted += 1
            cards_n += ev.cards_added
        elif ev.phase == "llm_done":
            llm_n += 1
            cards_n += ev.cards_added
        elif ev.phase == "pass":
            passed += 1
        if bar is not None and ev.phase in {"draft", "llm_done", "pass"}:
            bar.tick(drafted=drafted, llm=llm_n, cards=cards_n)
        if ev.phase == "done" and bar is not None:
            bar.finish(drafted=drafted, llm=llm_n, cards=cards_n)
            bar.__exit__(None, None, None)
            bar = None
            bits = [f"{cards_n} cards"]
            if drafted:
                bits.append(f"{drafted} drafted")
            if llm_n:
                bits.append(f"{llm_n} via model")
            if passed:
                bits.append(f"{passed} empty")
            ok("extract · " + " · ".join(bits))

    return on_progress


def _print_extract(cards: list) -> None:
    pending = sum(1 for card in cards if card.status == "pending")
    refused = len(cards) - pending
    print(f"cards: {len(cards)} pending={pending} refused={refused}")


def _buffet(args: argparse.Namespace, corpus: Corpus) -> int:
    cards = corpus.cards(args.status)
    if not cards:
        print("no cards")
        return 0
    for card in cards:
        print(f"{card.status:8} {card.id}  {card.claim}")
        if card.citations:
            print(f"         citations: {', '.join(card.citations)}")
        if card.extras:
            bits = ", ".join(f"{k}={v}" for k, v in card.extras.items() if v)
            if bits:
                print(f"         {bits}")
        if card.reason:
            print(f"         {card.reason}")
    return 0


def _referees(args: argparse.Namespace) -> int:
    from dataclasses import replace

    from dossier.referees.rank import format_suggestion, note_pubs_coauthors, rank
    from dossier.tailor import CV_CAP, select_cards, speak_to

    try:
        posting = _posting_text(args)
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if not posting.strip():
        print("posting is empty", file=sys.stderr)
        return 2
    try:
        people = _people_source(args)
    except (OSError, ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if people is None:
        print("no people source", file=sys.stderr)
        return 1
    try:
        policy = _policy_source(args)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    cfg = Config.from_env()
    db = evidence_db(Path(cfg.data_dir))
    corpus = Corpus(db) if db.is_file() else None
    try:
        if corpus is not None and cfg.referee_pubs:
            blobs = [f"{rec.title}\n{rec.text}" for rec in corpus.records("pubs")]
            people = note_pubs_coauthors(people, blobs)
        picked = select_cards(corpus, posting, limit=CV_CAP)[0] if corpus is not None else []
        shortlist = rank(
            posting,
            people,
            policy,
            employer=args.employer,
            include_students=args.students,
        )
        for index, suggestion in enumerate(shortlist, start=1):
            person = next((item for item in people if item.name == suggestion.name), None)
            profile = ""
            if person is not None:
                profile = " ".join((person.job_title, person.keywords, person.company))
            claims = speak_to(profile, picked)
            shown = replace(suggestion, speaks=tuple(claims)) if claims else suggestion
            print(format_suggestion(shown, index))
    finally:
        if corpus is not None:
            corpus.close()
    return 0


def _posting_text(args: argparse.Namespace) -> str:
    if args.text is not None:
        return args.text
    return args.posting.read_text(encoding="utf-8")


def _people_source(args: argparse.Namespace):
    path = args.people or _env_path("DOSSIER_PEOPLE")
    if path is not None:
        from dossier.referees.load import load_people

        return load_people(path)
    url = os.environ.get("DOSSIER_TWENTY_API_URL", "").strip()
    key = os.environ.get("DOSSIER_TWENTY_API_KEY", "").strip()
    if url or key:
        if not (url and key):
            raise RuntimeError(
                "Twenty read needs both DOSSIER_TWENTY_API_URL and DOSSIER_TWENTY_API_KEY"
            )
        from dossier.referees.twenty import fetch_people

        return fetch_people(url, key)
    return None


def _policy_source(args: argparse.Namespace):
    from dossier.referees.load import load_policy
    from dossier.referees.rank import Policy

    path = args.policy or _env_path("DOSSIER_REFEREE_POLICY")
    if path is None:
        return Policy.empty()
    return load_policy(path)


def _env_path(name: str) -> Path | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    return Path(raw)


def _add_gate_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--all",
        action="store_true",
        help="Apply to every pending card in the filter",
    )
    parser.add_argument(
        "--source",
        default="",
        help="Comma-separated sources to include",
    )
    parser.add_argument(
        "--except",
        dest="exclude",
        default="",
        help="Comma-separated sources to skip",
    )


def _names(raw: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _gate(args: argparse.Namespace, corpus: Corpus, *, action: str) -> int:
    card_id = getattr(args, "card_id", None)
    if args.all and card_id:
        print("pass a card id or --all, not both", file=sys.stderr)
        return 2
    if args.all:
        return _bulk(args, corpus, action=action)
    if not card_id:
        print("pass a card id or --all", file=sys.stderr)
        return 2
    try:
        if action == "approve":
            card = corpus.approve(card_id)
            label = STATUS_APPROVED
        elif action == "refuse":
            card = corpus.refuse(card_id)
            label = STATUS_REFUSED
        else:
            card = corpus.reopen(card_id)
            label = STATUS_PENDING
    except KeyError:
        print(f"unknown card {card_id}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"{label} {card.id}  {card.claim}")
    return 0


def _bulk(args: argparse.Namespace, corpus: Corpus, *, action: str) -> int:
    sources = _names(args.source)
    exclude = _names(args.exclude)
    both = sorted(set(sources) & set(exclude))
    if both:
        print(
            "listed in --source and --except: " + ", ".join(both),
            file=sys.stderr,
        )
    known = corpus.known_sources()
    missing = [name for name in sources if name not in known]
    if missing:
        print("no cards for " + ", ".join(missing), file=sys.stderr)
    if action == "reopen":
        counts = corpus.matching_counts(
            (STATUS_APPROVED, STATUS_REFUSED),
            sources=sources,
            exclude=exclude,
        )
        noun = "to reopen"
    else:
        counts = corpus.pending_counts(sources=sources, exclude=exclude)
        noun = "pending"
    if not counts:
        print("no pending cards" if action != "reopen" else "nothing to reopen")
        return 0
    for source, count in counts:
        print(f"{source}  {count} {noun}")
    if action == "approve":
        changed = corpus.approve_pending(sources=sources, exclude=exclude)
        verb = "approved"
    elif action == "refuse":
        changed = corpus.refuse_pending(sources=sources, exclude=exclude)
        verb = "refused"
    else:
        changed = corpus.reopen_filtered(sources=sources, exclude=exclude)
        verb = "reopened"
    print(f"{verb} {changed}")
    return 0


def _approve(args: argparse.Namespace, corpus: Corpus) -> int:
    return _gate(args, corpus, action="approve")


def _refuse(args: argparse.Namespace, corpus: Corpus) -> int:
    return _gate(args, corpus, action="refuse")


def _reopen(args: argparse.Namespace, corpus: Corpus) -> int:
    if getattr(args, "from_audit", False):
        from dossier.show import audit_cards

        ids = [card.id for card, _reason in audit_cards(corpus)]
        if not ids:
            print("reopened 0")
            return 0
        n = corpus.reopen_filtered(ids=tuple(ids))
        print(f"reopened {n}")
        return 0
    return _gate(args, corpus, action="reopen")


def _gui(args: argparse.Namespace) -> int:
    from dossier.web.__main__ import main as web_main

    return web_main(["--host", args.host, "--port", str(args.port)])


def _review(args: argparse.Namespace) -> int:
    port = args.port
    if port < 1 or port > 65535:
        print("port must be 1-65535", file=sys.stderr)
        return 2
    print(f"http://127.0.0.1:{port}/review")
    from dossier.web.__main__ import main as web_main

    return web_main(["--host", "127.0.0.1", "--port", str(port)])


def _ask(args: argparse.Namespace, cfg: Config, corpus: Corpus) -> int:
    try:
        cfg = _with_request_scope(args, cfg)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    mode = args.mode or cfg.ask_mode
    limit = cfg.ask_limit if args.limit is None else args.limit
    budget = CallBudget(cfg.llm_max_calls)
    if mode == "exact" or not cfg.llm_enabled:
        client: LLMClient = NullLLMClient()
    elif mode == "auto":
        client = budget.wrap(_LazyClient(cfg))
    else:
        client, code = _client_for_mode(cfg, mode)
        if code is not None:
            return code
        client = budget.wrap(client)
    prior = corpus.recent_accepted_texts(3) if args.follow else None
    extra = optional_pubs_hits(args.question, enabled=cfg.ask_pubs, limit=limit)
    result = conduct(
        corpus,
        args.question,
        cfg,
        client,
        mode=mode,
        limit=limit,
        source=args.source,
        lens=args.lens,
        kind=args.kind,
        prior=prior,
        embedder=_query_embedder(cfg, corpus),
        extra_hits=extra or None,
    )
    corpus.add_answer(
        question=args.question,
        mode=mode,
        text=result.text,
        citations=result.citations,
        refused=result.refused,
        reason=result.reason,
    )
    if result.refused:
        print("refused")
        if result.reason:
            print(result.reason)
        return 1
    print(result.text)
    print("citations: " + ", ".join(result.citations))
    return 0


def _add_scope_flags(parser: argparse.ArgumentParser) -> None:
    from dossier.effort import EFFORT_NAMES

    parser.add_argument("--sources", help="Comma-separated sources for this command")
    parser.add_argument("--year-from", type=int, default=None)
    parser.add_argument("--year-to", type=int, default=None)
    parser.add_argument("--effort", choices=EFFORT_NAMES, default=None)


def _with_request_scope(args: argparse.Namespace, cfg: Config) -> Config:
    from dossier.scope import (
        RequestScope,
        apply_request_scope,
        parse_year,
        sources_for_request,
    )

    sources = cfg.scope_sources
    raw_sources = getattr(args, "sources", None)
    if raw_sources:
        sources = sources_for_request(
            [part.strip() for part in str(raw_sources).split(",") if part.strip()]
        )
    year_from = cfg.scope_year_from
    year_to = cfg.scope_year_to
    if getattr(args, "year_from", None) is not None:
        year_from = parse_year(str(args.year_from))
    if getattr(args, "year_to", None) is not None:
        year_to = parse_year(str(args.year_to))
    if year_from and year_to and year_from > year_to:
        raise ValueError("year range")
    effort = str(getattr(args, "effort", None) or "")
    return apply_request_scope(
        cfg,
        RequestScope(sources, year_from, year_to, effort),
    )


def _brief(
    args: argparse.Namespace,
    cfg: Config,
    corpus: Corpus,
    *,
    budget: CallBudget | None = None,
) -> int:
    try:
        cfg = _with_request_scope(args, cfg)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    mode = args.mode or cfg.ask_mode
    try:
        questions = _pack_questions(args, cfg)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    spent = budget or CallBudget(cfg.llm_max_calls)
    client, code = _client_for_mode(cfg, mode)
    if code is not None:
        return code
    stage("brief", f"{len(questions)} questions · mode={mode}")
    cited = 0
    refused = 0
    from dossier.prompts import start_prompt_log, stop_prompt_log

    token = start_prompt_log()
    try:
        with Progress(len(questions), label="brief") as bar:

            def on_progress(done: int, total: int, item, result) -> None:
                nonlocal cited, refused
                bar.set_total(total)
                if result.refused:
                    refused += 1
                else:
                    cited += 1
                bar.tick(
                    cited=cited,
                    refused=refused,
                )
                bar.status(trunc(item.question, 40))

            items = run_pack(
                corpus,
                questions,
                cfg,
                spent.wrap(client),
                mode=mode,
                on_progress=on_progress,
                embedder=_query_embedder(cfg, corpus),
            )
            bar.finish(cited=cited, refused=refused)
        prompt_stamp = stop_prompt_log(token, empty="ask=none")
    except Exception:
        stop_prompt_log(token, empty="ask=none")
        raise
    path = write_brief(items, Path(cfg.data_dir) / "briefs", prompt_stamp=prompt_stamp)
    print(path)
    ok(f"brief · {cited} cited · {refused} refused")
    return 0


def _pack_questions(args: argparse.Namespace, cfg: Config) -> list:
    posting = getattr(args, "posting", None) or (
        Path(cfg.run_posting) if cfg.run_posting else None
    )
    pack = getattr(args, "pack", None) or cfg.run_pack
    if posting is not None or pack == "posting":
        if posting is None:
            raise ValueError("posting pack needs --posting or DOSSIER_RUN_POSTING")
        return posting_pack(posting.read_text(encoding="utf-8"))
    return resolve_pack(pack, Path(cfg.data_dir), allow_path=True)


def _run(args: argparse.Namespace, cfg: Config, corpus: Corpus) -> int:
    if cfg.llm_enabled and cfg.extract_llm and cfg.fast_model != cfg.llm_model:
        client = get_client(cfg)
        model, note = select_fast_model(cfg, client)
        if note:
            print(note, file=sys.stderr)
        if model != cfg.fast_model:
            cfg = replace(cfg, fast_model=model)
    targets, skipped = _detected_targets(cfg.run_adapters)
    for line in skipped:
        print(line)
    if not targets and not corpus.records():
        print("nothing to ingest (no default source detected)")
    if targets:
        stage("ingest", f"{len(targets)} source{'s' if len(targets) != 1 else ''}")
        run_ingest_targets(targets, corpus)
    extract_budget = CallBudget(cfg.llm_max_calls)
    _extract_cards(
        cfg, corpus, source=None, limit=None, strict_llm=False, budget=extract_budget
    )
    brief_budget = CallBudget(cfg.llm_max_calls)
    code = _brief(args, cfg, corpus, budget=brief_budget)
    print(
        f"ledger: records={len(corpus.records())} "
        f"adapters_skipped={len(skipped)} "
        f"model_calls={extract_budget.calls + brief_budget.calls} "
        f"egress={'yes' if llm_egress_is_remote(cfg) else 'no'}"
    )
    return code


def _span(args: argparse.Namespace, corpus: Corpus) -> int:
    claim = args.claim.strip()
    if not claim:
        print("refused")
        print("empty claim")
        return 1
    shown = find_span(corpus, claim, uri=args.uri, source=args.source)
    if shown is None:
        print("refused")
        print("no sentence carries this claim")
        return 1
    print(shown.sentence)
    print(f"title: {shown.title}")
    print(f"uri: {shown.uri}")
    return 0


def _defend(
    corpus: Corpus,
    *,
    source: str | None = None,
    dry_run: bool = False,
) -> int:
    from dossier.show import span_histogram

    spanned, unspanned = defend_cards(corpus, source=source, dry_run=dry_run)
    if not spanned and not unspanned:
        print("no cards")
        return 0
    hist = span_histogram(spanned)
    print(
        "histogram "
        + " ".join(f"{bucket}={count}" for bucket, count in hist.items())
    )
    print(f"spanned={len(spanned)} unspanned={len(unspanned)} cap={span_max()}")
    if dry_run:
        print("dry-run: not written")
    for card in spanned:
        print(f"spanned {card.id}  {card.claim}")
    for card in unspanned:
        print(f"unspanned {card.id}  {card.claim}")
    return 0


def _audit_cards(corpus: Corpus, *, write_ids: bool) -> int:
    from dossier.show import audit_cards

    rows = audit_cards(corpus)
    if write_ids:
        for card, _reason in rows:
            print(card.id)
        return 0
    if not rows:
        print("audit: 0")
        return 0
    print(f"audit: {len(rows)}")
    for card, reason in rows:
        print(f"{card.id}  {reason}  {card.claim}")
    return 0


def _backup(cfg: Config, corpus: Corpus) -> int:
    from datetime import UTC, datetime

    stamp = datetime.now(UTC).strftime("%y%m%d-%H%M%S")
    dest = Path(cfg.data_dir) / "backups" / f"evidence-{stamp}.db"
    try:
        path = corpus.backup(dest)
    except (OSError, RuntimeError) as exc:
        return fail(str(exc))
    print(path)
    return 0


def _restore(cfg: Config, corpus: Corpus, backup: Path, *, replace: bool) -> int:
    from dossier.store import read_backup, replace_locker

    del cfg
    info = read_backup(backup)
    print(f"backup: {backup}")
    print(f"schema: v{info.schema}")
    print(f"records: {info.records}")
    print(f"cards: {info.cards}")
    if not info.ok:
        return fail(info.reason or "backup is not usable")
    print("integrity: ok")
    if not replace:
        print("restore: check only")
        return 0
    live = Path(corpus.db_path)
    pre = live.with_name(f"{live.stem}.pre-restore.db")
    try:
        corpus._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        saved = corpus.backup(pre)
    except (OSError, RuntimeError, sqlite3.Error) as exc:
        return fail(str(exc))
    print(f"saved: {saved}")
    corpus.close()
    try:
        replace_locker(live, backup)
    except (OSError, RuntimeError) as exc:
        return fail(str(exc))
    print(f"restored: {live}")
    return 0


def _drift(cfg: Config, corpus: Corpus) -> int:
    from dossier.drift import write_drift

    path, report = write_drift(corpus, Path(cfg.data_dir) / "drift")
    print(path)
    print(
        f"stale: {len(report.stale)} · "
        f"duplicates: {len(report.duplicates)} · "
        f"unseen: {len(report.unseen)}"
    )
    return 0


def _drop_record(corpus: Corpus, uri: str) -> int:
    citing = corpus.approved_citing(uri)
    if citing:
        print(f"approved card cites {uri}", file=sys.stderr)
        for card in citing:
            print(card.id, file=sys.stderr)
        return 1
    if not corpus.drop_record(uri):
        return fail(f"no record {uri}")
    print(f"dropped {uri}")
    return 0


def _gaps(corpus: Corpus) -> int:
    from dossier.lenses import LENSES

    report = gap_report(corpus)
    for lens in LENSES:
        print(f"lens {lens}: {report.lens_counts[lens]}")
    for kind in sorted(report.kind_counts):
        print(f"kind {kind}: {report.kind_counts[kind]}")
    if report.empty_lenses:
        print("empty: " + ", ".join(report.empty_lenses))
    for line in report.singles:
        print(f"single {line.lens}/{line.kind} {line.card.id}  {line.card.claim}")
    for lens, hint in report.hints:
        print(f"hint {lens}: {hint}")
    for card in report.unspanned_approved:
        print(f"unspanned {card.id}  {card.claim}")
    for uri in report.extract_targets:
        print(f"extract {uri}")
    return 0


def _match(args: argparse.Namespace, cfg: Config, corpus: Corpus) -> int:
    try:
        cfg = _with_request_scope(args, cfg)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    embedder = _query_embedder(cfg, corpus)
    folder = getattr(args, "postings", None)
    if folder is not None:
        try:
            repeated, used, total = match_postings(corpus, folder, cfg, embedder=embedder)
        except (OSError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        path = write_postings(
            repeated,
            Path(cfg.data_dir) / "matches",
            used=used,
            total=total,
        )
        print(path)
        print(f"postings: {used} of {total} · repeated gaps: {len(repeated)}")
        return 0
    try:
        posting = args.posting.read_text(encoding="utf-8")
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if not posting.strip():
        print("posting is empty", file=sys.stderr)
        return 2
    report = match_posting(
        corpus,
        posting,
        cfg,
        embedder=embedder,
    )
    path = write_match(report, Path(cfg.data_dir) / "matches")
    evidenced = sum(1 for item in report.requirements if item.evidence)
    gaps = len(report.requirements) - evidenced
    print(path)
    print(
        f"requirements: {len(report.requirements)} · "
        f"with evidence: {evidenced} · gaps: {gaps}"
    )
    return 0


def _tailor(args: argparse.Namespace, cfg: Config, corpus: Corpus) -> int:
    from dossier.tailor import (
        CV_CAP,
        LETTER_CAP,
        arrange_letter,
        linkedin_subtitle,
        render_draft,
        select_cards,
        write_draft,
    )

    try:
        posting = args.posting.read_text(encoding="utf-8")
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if not posting.strip():
        print("posting is empty", file=sys.stderr)
        return 2
    limit = LETTER_CAP if args.kind == "letter" else CV_CAP
    picked, bare = select_cards(corpus, posting, limit=limit)
    paragraphs = None
    if args.arrange and args.kind == "letter" and picked and cfg.llm_enabled:
        if llm_egress_is_remote(cfg):
            _note_egress(cfg)
        client = CallBudget(cfg.llm_max_calls).wrap(get_client(cfg))
        arrange_model, arrange_note = select_fast_model(cfg, client)
        if arrange_note:
            print(arrange_note, file=sys.stderr)
        spans = [item.card.extras["span"] for item in picked]
        from dossier.prompts import start_prompt_log, stop_prompt_log

        token = start_prompt_log()
        try:
            paragraphs = arrange_letter(
                spans,
                client,
                arrange_model,
                max_num_ctx=cfg.llm_max_num_ctx,
                timeout_seconds=cfg.llm_timeout_seconds,
            )
            prompt_stamp = stop_prompt_log(token, empty="none")
        except Exception:
            stop_prompt_log(token, empty="none")
            raise
        if paragraphs is None:
            print("arrange refused; kept the selected spans", file=sys.stderr)
    else:
        prompt_stamp = "prompts: none"
    if getattr(args, "fmt", "markdown") == "json-resume":
        from dossier.tailor import render_json_resume

        text = render_json_resume(
            picked=picked,
            name=cfg.cv_name,
            subtitle=linkedin_subtitle(corpus),
        )
        dest = Path(cfg.data_dir) / "drafts"
        dest.mkdir(parents=True, exist_ok=True)
        from datetime import UTC, datetime

        path = dest / f"{datetime.now(UTC).strftime('%y%m%d-%H%M%S')}.json"
        path.write_text(text, encoding="utf-8")
        print(path)
        return 0
    fmt = getattr(args, "fmt", "markdown")
    if fmt in ("html", "docx", "pdf"):
        return _tailor_render(
            args, cfg, corpus, posting=posting, picked=picked, bare=bare, paragraphs=paragraphs, fmt=fmt
        )
    text = render_draft(
        kind=args.kind,
        posting=posting,
        picked=picked,
        bare=bare,
        name=cfg.cv_name,
        subtitle=linkedin_subtitle(corpus),
        paragraphs=paragraphs,
    )
    path = write_draft(text, Path(cfg.data_dir) / "drafts", prompt_stamp=prompt_stamp)
    print(path)
    if not picked:
        print("nothing to quote; approve and defend first", file=sys.stderr)
        return 1
    return 0


def _tailor_render(
    args: argparse.Namespace,
    cfg: Config,
    corpus: Corpus,
    *,
    posting: str,
    picked: list,
    bare: list,
    paragraphs: list[str] | None,
    fmt: str,
) -> int:
    """HTML, DOCX, or PDF from the same typed draft. Layout only; no prose is added."""
    from dossier.render import RenderError, Theme, write_render
    from dossier.tailor import build_doc, linkedin_subtitle

    doc = build_doc(
        kind=args.kind,
        posting=posting,
        picked=picked,
        bare=bare,
        name=cfg.cv_name,
        subtitle=linkedin_subtitle(corpus),
        contact=cfg.render_contact,
        paragraphs=paragraphs,
        with_sources=bool(getattr(args, "with_sources", False)),
    )
    theme = Theme(
        font_pt=cfg.render_font_pt,
        margin_mm=cfg.render_margin_mm,
        page=cfg.render_page,
        accent=cfg.render_accent,
    )
    try:
        path = write_render(doc, fmt, Path(cfg.data_dir) / "drafts", theme)
    except RenderError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2
    print(path)
    if not picked:
        print("nothing to quote; approve and defend first", file=sys.stderr)
        return 1
    return 0


def _packet(cfg: Config, corpus: Corpus) -> int:
    path = write_packet(corpus, Path(cfg.data_dir) / "packets")
    print(path)
    return 0


def _doctor(cfg: Config, *, deep: bool = False) -> int:
    from dossier.identity import (
        configured_slack_user_ids,
        is_sent_metadata_uri,
        resolve_speaker_names,
    )

    db = evidence_db(Path(cfg.data_dir))
    corpus = Corpus(db)
    try:
        print(f"data_dir: {cfg.data_dir}")
        print(f"evidence_db: {db}")
        print(f"python: {sys.executable}")
        print(f"sqlite: {sqlite3.sqlite_version}")
        print(f"fts5: {'yes' if corpus.fts_ok else 'no'}")
        print(f"provider: {cfg.llm_provider if cfg.llm_enabled else 'off'}")
        print(egress_status(cfg))
        print(f"effort: {cfg.effort}")
        print(f"model: {cfg.llm_model}")
        print(f"fast: {cfg.fast_model}")
        from dossier.effort import effort_model_tags

        tags = effort_model_tags(cfg)
        if not tags:
            print("models: none")
        else:
            tag_client = get_client(cfg)
            bits = []
            for tag in tags:
                ok_tag, _msg = tag_client.check_config(tag)
                bits.append(f"{tag} {'installed' if ok_tag else 'missing'}")
            print("models: " + ", ".join(bits))
            _chosen, fast_note = select_fast_model(cfg, tag_client)
            if fast_note:
                print(fast_note)
        print(f"llm.timeout: {cfg.llm_timeout_seconds}")
        print(f"llm.max_ctx: {cfg.llm_max_num_ctx}")
        print(
            "max_calls: "
            + ("unlimited" if cfg.llm_max_calls == 0 else str(cfg.llm_max_calls))
        )
        print(f"ask.mode: {cfg.ask_mode}")
        print(f"ask.cards_first: {cfg.ask_cards_first}")
        print(f"ask.passages: {cfg.ask_passages}")
        print(f"ask.hops: {cfg.ask_hops}")
        print(f"ask.decompose: {cfg.ask_decompose}")
        print(f"ask.planner: {cfg.ask_planner}")
        print(f"embed_model: {cfg.embed_model}")
        print(f"vectors: {corpus.vector_count(cfg.embed_model)}")
        from dossier.vecindex import backend as _vec_backend

        print(f"vector_search: {_vec_backend().name}")
        print(f"ask.pubs: {'yes' if cfg.ask_pubs else 'no'}")
        print(f"pubs_url: {cfg.pubs_url}")
        from dossier.cards import span_is_usable

        approved = corpus.cards(STATUS_APPROVED)
        spanned = sum(
            1 for card in approved if span_is_usable(card.claim, card.extras.get("span") or "")
        )
        over = sum(
            1
            for card in approved
            if (card.extras.get("span") or "").strip()
            and not span_is_usable(card.claim, card.extras.get("span") or "")
        )
        print(f"tailor: {spanned}")
        print(f"span_max: {span_max()}")
        if over:
            print(f"warn: {over} stored spans exceed cap or no longer carry")
        if spanned == 0:
            print("tailor: approve and defend before tailor will quote")
        collection = pubs_collection()
        if collection:
            print(f"pubs_collection: {collection}")
        print(f"employer_paths: {len(employer_paths())}")
        print(f"employer.filter: {'yes' if cfg.employer_filter else 'no'}")
        print(
            f"employer.filter_llm: {'yes' if cfg.employer_filter_llm and cfg.llm_enabled else 'no'}"
            f" ({cfg.employer_filter_llm_calls})"
        )
        print(f"git_paths: {len(git_paths())}")
        if user := git_user():
            print(f"git_user: {user}")
        sent_meta = sum(
            1 for rec in corpus.records("mbox") if is_sent_metadata_uri(rec.uri)
        )
        if sent_meta:
            print(
                f"mbox_sent_metadata: {sent_meta} "
                "(folder closed; subjects/attachments only, no body)"
            )
        identity_empty = not configured_slack_user_ids() and not resolve_speaker_names()
        for item in CONTRIBUTIONS:
            default = _default_path(item.name)
            seen = default is not None and item.source.detect(default)
            if item.name == "pubs" and seen:
                rows = len(item.source.records_for(default))  # type: ignore[attr-defined]
                print(f"adapter pubs: detected rows={rows}")
                if collection and rows == 0:
                    print(
                        "warn: pubs_collection set but rows=0 "
                        "(check collection name and zotero_db)"
                    )
            else:
                print(f"adapter {item.name}: {'detected' if seen else 'not detected'}")
            if seen and item.name == "slack" and identity_empty:
                print(
                    "warn: slack detected but identity empty "
                    "(set [identity] slack_user_ids or speaker_names)"
                )
            if seen and item.name == "meetings" and not resolve_speaker_names():
                print(
                    "warn: meetings detected but speaker_names empty "
                    "(set [identity] speaker_names)"
                )
        from dossier.ops import readiness_notes

        for line in readiness_notes(cfg, corpus):
            print(f"note: {line}")
        if deep:
            _doctor_deep(corpus)
    finally:
        corpus.close()
    return 0


def _doctor_deep(corpus: Corpus) -> None:
    from dossier.show import span_histogram

    print(f"integrity: {'ok' if corpus.integrity_ok() else 'FAIL'}")
    n_rec, n_fts = corpus.fts_parity()
    print(f"fts_parity: records={n_rec} fts={n_fts}")
    hist = span_histogram(corpus.cards())
    print("span_histogram " + " ".join(f"{k}={v}" for k, v in hist.items()))
    cited = set()
    for card in corpus.cards():
        cited.update(card.citations)
        if card.record_id and corpus.get_card(card.id) is None:
            print(f"orphan_card {card.id}")
    missing = [uri for uri in cited if corpus.get_record(uri) is None]
    print(f"orphan_citations: {len(missing)}")
    from dossier.show import stale_spans

    print(f"stale_spans: {len(stale_spans(corpus))}")
    marked = sum(
        1
        for card in corpus.cards(STATUS_APPROVED)
        if card.extras.get("stale_reason")
    )
    print(f"stale_marked: {marked}")
    print(f"schema: v{corpus.schema_version()}")


def _client_for_mode(cfg: Config, mode: str) -> tuple[LLMClient, int | None]:
    from dossier.ops import client_for_mode

    return client_for_mode(cfg, mode)


def _detected_targets(
    allowlist: tuple[str, ...],
) -> tuple[list[tuple], list[str]]:
    from dossier.ops import detected_targets_report

    return detected_targets_report(allowlist)


def _index(
    cfg: Config,
    corpus: Corpus,
    *,
    sources: tuple[str, ...] = (),
    limit: int | None = None,
) -> int:
    from dossier.embed import EmbedError, OllamaEmbedder, index_passages
    from dossier.llm.validate import LlmConfigError, validate_ollama_url

    if not cfg.llm_enabled:
        print("index: skipped (provider off)")
        return 0
    remote = False
    try:
        validate_ollama_url(cfg.llm_base_url, False)
    except LlmConfigError:
        if not cfg.llm_allow_remote:
            print("index: skipped (remote embeddings are not allowed)")
            return 0
        remote = True
    if remote:
        _note_egress(cfg)
    embedder = OllamaEmbedder(cfg.llm_base_url, cfg.llm_allow_remote, cfg.embed_model)
    ready, msg = embedder.check()
    if not ready:
        print(f"index: skipped ({msg})")
        return 0
    try:
        count = index_passages(corpus, embedder, sources=sources, limit=limit)
    except (EmbedError, LlmConfigError) as exc:
        print(f"index: skipped ({exc})")
        return 0
    print(f"vectors: {count}")
    return 0


def _query_embedder(cfg: Config, corpus: Corpus):
    from dossier.ops import query_embedder

    return query_embedder(cfg, corpus)


def _default_path(name: str) -> Path | None:
    from dossier.ops import default_path

    return default_path(name)


def _extra_paths(name: str) -> list[Path]:
    from dossier.ops import extra_paths

    return extra_paths(name)


if __name__ == "__main__":
    raise SystemExit(main())
