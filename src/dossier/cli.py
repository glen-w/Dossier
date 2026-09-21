"""dossier — ingest, extract claim cards, ask the corpus, approve a buffet."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dossier.ask import ASK_MODES
from dossier.brief import run_pack, write_brief
from dossier.cards import STATUS_APPROVED
from dossier.config import Config
from dossier.contributions import CONTRIBUTIONS, contribution
from dossier.extract import extract_corpus
from dossier.interview import conduct
from dossier.llm import EGRESS_NOTICE, get_client, llm_egress_is_remote
from dossier.llm.budget import CallBudget
from dossier.llm.client import LLMClient, LLMClientError, NullLLMClient
from dossier.packs import load_pack, posting_pack
from dossier.paths import (
    applications_dir,
    cursor_projects_root,
    evidence_db,
    grok_blobs_dir,
    warehouse_db,
)
from dossier.store import Corpus

_YELLOW = "\033[33m"
_RESET = "\033[0m"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dossier",
        description="Local-first work-evidence locker. Dumps stay off git.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ing = sub.add_parser("ingest", help="Load one adapter into the local corpus")
    p_ing.add_argument(
        "--adapter",
        help="pubs, chatgpt, linkedin, applications, transcripts, slack, mbox",
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
    p_ok.add_argument("card_id")

    p_ask = sub.add_parser("ask", help="Answer from ingested records, with citations")
    p_ask.add_argument("question")
    p_ask.add_argument("--limit", type=int, default=None)
    p_ask.add_argument("--source", help="Limit retrieval to one adapter name")
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

    p_run = sub.add_parser(
        "run",
        help="Ingest detected adapters, draft claims, then write a brief",
    )
    p_run.add_argument("--pack", default=None, help="career, or a path to a JSON pack")
    p_run.add_argument("--posting", type=Path, help="Local posting text for the posting pack")
    p_run.add_argument("--mode", choices=ASK_MODES, default=None)

    p_doc = sub.add_parser("doctor", help="Print local readiness without writing")

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
    _note_egress.done = False
    if args.cmd == "referees":
        return _referees(args)
    cfg = Config.from_env()
    if args.cmd == "doctor":
        return _doctor(cfg)
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
        if args.cmd == "ask":
            return _ask(args, cfg, corpus)
        if args.cmd == "brief":
            return _brief(args, cfg, corpus)
        if args.cmd == "run":
            return _run(args, cfg, corpus)
    finally:
        corpus.close()
    return 2


def _ingest(args: argparse.Namespace, corpus: Corpus) -> int:
    if args.adapter:
        item = contribution(args.adapter)
        if item is None:
            print(f"unknown adapter {args.adapter!r}", file=sys.stderr)
            print("known:", ", ".join(c.name for c in CONTRIBUTIONS), file=sys.stderr)
            return 2
        path = args.path or _default_path(item.name)
        if path is None:
            print(f"{item.name}: no path", file=sys.stderr)
            return 2
        targets = [(item, path)]
        if item.name == "transcripts" and args.path is None:
            for extra in _extra_paths(item.name):
                if item.source.detect(extra):
                    targets.append((item, extra))
    elif args.path:
        matches = [c for c in CONTRIBUTIONS if c.source.detect(args.path)]
        if not matches:
            print(f"no adapter owns {args.path}", file=sys.stderr)
            return 2
        targets = [(m, args.path) for m in matches]
    else:
        targets = []
        for item in CONTRIBUTIONS:
            default = _default_path(item.name)
            if default is not None and item.source.detect(default):
                targets.append((item, default))
            for extra_path in _extra_paths(item.name):
                if item.source.detect(extra_path):
                    targets.append((item, extra_path))
        if not targets:
            print("nothing to ingest (no default source detected)", file=sys.stderr)
            return 1
    n_before = len(corpus.records())
    for item, path in targets:
        print(f"ingest {item.name} from {path}")
        item.source.load(path, corpus)
    n_after = len(corpus.records())
    print(f"records: {n_after} (+{n_after - n_before})")
    return 0


def _extract(args: argparse.Namespace, cfg: Config, corpus: Corpus) -> int:
    return _extract_cards(cfg, corpus, source=args.source, limit=args.limit, strict_llm=True)


def _note_egress(cfg: Config) -> None:
    if getattr(_note_egress, "done", False) or not llm_egress_is_remote(cfg):
        return
    _note_egress.done = True  # type: ignore[attr-defined]
    print(f"{_YELLOW}{EGRESS_NOTICE}{_RESET}", file=sys.stderr)


class _LazyClient:
    """Open the model on the first completion. Exact answers never get that far."""

    provider = "lazy"

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self._inner: LLMClient | None = None

    def check_config(self, model: str) -> tuple[bool, str]:
        return True, "ok"

    def complete(self, request):  # noqa: ANN001
        return self._client().complete(request)

    def complete_json(self, request):  # noqa: ANN001
        return self._client().complete_json(request)

    def _client(self) -> LLMClient:
        if self._inner is None:
            _note_egress(self.cfg)
            inner = get_client(self.cfg)
            ok, msg = inner.check_config(self.cfg.llm_model)
            if not ok:
                raise LLMClientError(msg)
            self._inner = inner
        return self._inner


def _extract_cards(
    cfg: Config,
    corpus: Corpus,
    *,
    source: str | None,
    limit: int | None,
    strict_llm: bool,
) -> int:
    use_llm = cfg.extract_llm and cfg.llm_enabled
    client: LLMClient = NullLLMClient()
    if use_llm:
        if llm_egress_is_remote(cfg):
            _note_egress(cfg)
        client = get_client(cfg)
        ok, msg = client.check_config(cfg.llm_model)
        if not ok:
            drafted = extract_corpus(
                corpus,
                NullLLMClient(),
                cfg.llm_model,
                source=source,
                limit=limit,
                use_llm=False,
            )
            _print_extract(drafted)
            print(msg, file=sys.stderr)
            return 2 if strict_llm else 0
    cards = extract_corpus(
        corpus,
        client,
        cfg.llm_model,
        source=source,
        limit=limit,
        use_llm=use_llm,
    )
    _print_extract(cards)
    return 0


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
    from dossier.referees.rank import format_suggestion, rank

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
    shortlist = rank(
        posting,
        people,
        policy,
        employer=args.employer,
        include_students=args.students,
    )
    for index, suggestion in enumerate(shortlist, start=1):
        print(format_suggestion(suggestion, index))
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


def _approve(args: argparse.Namespace, corpus: Corpus) -> int:
    try:
        card = corpus.approve(args.card_id)
    except KeyError:
        print(f"unknown card {args.card_id}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"{STATUS_APPROVED} {card.id}  {card.claim}")
    return 0


def _ask(args: argparse.Namespace, cfg: Config, corpus: Corpus) -> int:
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


def _brief(
    args: argparse.Namespace,
    cfg: Config,
    corpus: Corpus,
    *,
    budget: CallBudget | None = None,
) -> int:
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
    items = run_pack(corpus, questions, cfg, spent.wrap(client), mode=mode)
    path = write_brief(items, Path(cfg.data_dir) / "briefs")
    print(path)
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
    return load_pack(pack)


def _run(args: argparse.Namespace, cfg: Config, corpus: Corpus) -> int:
    targets, skipped = _detected_targets(cfg.run_adapters)
    for line in skipped:
        print(line)
    if not targets and not corpus.records():
        print("nothing to ingest (no default source detected)")
    n_before = len(corpus.records())
    for item, path in targets:
        print(f"ingest {item.name} from {path}")
        item.source.load(path, corpus)
    n_after = len(corpus.records())
    if targets:
        print(f"records: {n_after} (+{n_after - n_before})")
    budget = CallBudget(cfg.llm_max_calls)
    _extract_cards(cfg, corpus, source=None, limit=None, strict_llm=False)
    code = _brief(args, cfg, corpus, budget=budget)
    print(
        f"ledger: records={len(corpus.records())} "
        f"adapters_skipped={len(skipped)} "
        f"model_calls={budget.calls} "
        f"egress={'yes' if llm_egress_is_remote(cfg) else 'no'}"
    )
    return code


def _doctor(cfg: Config) -> int:
    db = evidence_db(Path(cfg.data_dir))
    corpus = Corpus(db)
    try:
        print(f"data_dir: {cfg.data_dir}")
        print(f"evidence_db: {db}")
        print(f"fts5: {'yes' if corpus.fts_ok else 'no'}")
        print(f"provider: {cfg.llm_provider}")
        print(f"max_calls: {cfg.llm_max_calls}")
        print(f"ask.mode: {cfg.ask_mode}")
        print(f"ask.cards_first: {cfg.ask_cards_first}")
        print(f"ask.passages: {cfg.ask_passages}")
        print(f"ask.hops: {cfg.ask_hops}")
        print(f"ask.decompose: {cfg.ask_decompose}")
        print(f"ask.planner: {cfg.ask_planner}")
        for item in CONTRIBUTIONS:
            default = _default_path(item.name)
            seen = default is not None and item.source.detect(default)
            print(f"adapter {item.name}: {'detected' if seen else 'not detected'}")
    finally:
        corpus.close()
    return 0


def _client_for_mode(cfg: Config, mode: str) -> tuple[LLMClient, int | None]:
    """A client, and an exit code when rich mode cannot reach a model."""
    if mode == "exact" or not cfg.llm_enabled:
        return NullLLMClient(), None
    if llm_egress_is_remote(cfg):
        _note_egress(cfg)
    client = get_client(cfg)
    ok, msg = client.check_config(cfg.llm_model)
    if ok:
        return client, None
    if mode == "rich":
        print(msg, file=sys.stderr)
        return client, 2
    print(msg, file=sys.stderr)
    return NullLLMClient(), None


def _detected_targets(
    allowlist: tuple[str, ...],
) -> tuple[list[tuple], list[str]]:
    names = allowlist or tuple(item.name for item in CONTRIBUTIONS)
    targets: list[tuple] = []
    skipped: list[str] = []
    for name in names:
        item = contribution(name)
        if item is None:
            skipped.append(f"skip {name}: unknown adapter")
            continue
        paths: list[Path] = []
        default = _default_path(name)
        if default is not None and item.source.detect(default):
            paths.append(default)
        for extra in _extra_paths(name):
            if item.source.detect(extra):
                paths.append(extra)
        if not paths:
            skipped.append(f"skip {name}: not detected")
            continue
        for path in paths:
            targets.append((item, path))
    return targets, skipped


def _default_path(name: str) -> Path | None:
    if name in {"chatgpt", "linkedin", "slack", "mbox"}:
        return warehouse_db()
    if name == "applications":
        return applications_dir()
    if name == "transcripts":
        return cursor_projects_root()
    if name == "pubs":
        # Sentinel; PubsSource.detect uses retriever.ping(), not this path.
        return Path("/nonexistent/zotero-rag-pubs")
    return None


def _extra_paths(name: str) -> list[Path]:
    if name == "transcripts":
        return [grok_blobs_dir()]
    return []


if __name__ == "__main__":
    raise SystemExit(main())
