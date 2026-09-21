"""dossier — ingest adapters, extract claim cards, human-approve a buffet."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dossier.cards import STATUS_APPROVED
from dossier.config import Config
from dossier.contributions import CONTRIBUTIONS, contribution
from dossier.extract import extract_corpus
from dossier.llm import EGRESS_NOTICE, get_client, llm_egress_is_remote
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
        "--adapter", help="pubs, chatgpt, linkedin, applications, transcripts"
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

    args = parser.parse_args(argv)
    cfg = Config.from_env()
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
    if llm_egress_is_remote(cfg):
        print(f"{_YELLOW}{EGRESS_NOTICE}{_RESET}", file=sys.stderr)
    client = get_client(cfg)
    ok, msg = client.check_config(cfg.llm_model)
    if not ok:
        print(msg, file=sys.stderr)
        return 2
    cards = extract_corpus(
        corpus,
        client,
        cfg.llm_model,
        source=args.source,
        limit=args.limit,
    )
    pending = sum(1 for c in cards if c.status == "pending")
    refused = len(cards) - pending
    print(f"cards: {len(cards)} pending={pending} refused={refused}")
    return 0


def _buffet(args: argparse.Namespace, corpus: Corpus) -> int:
    cards = corpus.cards(args.status)
    if not cards:
        print("no cards")
        return 0
    for card in cards:
        print(f"{card.status:8} {card.id}  {card.claim}")
        if card.citations:
            print(f"         citations: {', '.join(card.citations)}")
        if card.reason:
            print(f"         {card.reason}")
    return 0


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


def _default_path(name: str) -> Path | None:
    if name in {"chatgpt", "linkedin"}:
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
