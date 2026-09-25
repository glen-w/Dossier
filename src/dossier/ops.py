"""Library helpers shared by the workbench (and thin CLI wrappers later)."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Any

from dossier.cards import STATUS_APPROVED, STATUS_PENDING, STATUS_REFUSED
from dossier.config import Config
from dossier.contributions import CONTRIBUTIONS, contribution
from dossier.llm import EGRESS_NOTICE, egress_status, get_client, llm_egress_is_remote
from dossier.llm.client import LLMClient, LLMClientError, NullLLMClient
from dossier.paths import (
    applications_dir,
    chatgpt_export,
    cursor_projects_root,
    employer_paths,
    evidence_db,
    git_paths,
    git_user,
    grok_blobs_dir,
    pubs_collection,
    slack_export,
    transcriptx_library,
    warehouse_db,
    zotero_db,
)
from dossier.store import Corpus


def default_path(name: str) -> Path | None:
    if name == "chatgpt":
        return chatgpt_export() or warehouse_db()
    if name == "slack":
        return slack_export() or warehouse_db()
    if name == "employer":
        paths = employer_paths()
        return paths[0] if paths else None
    if name == "git":
        paths = git_paths()
        return paths[0] if paths else None
    if name in {"linkedin", "mbox"}:
        return warehouse_db()
    if name == "applications":
        return applications_dir()
    if name == "transcripts":
        return cursor_projects_root()
    if name == "meetings":
        return transcriptx_library()
    if name == "pubs":
        return zotero_db()
    return None


def extra_paths(name: str) -> list[Path]:
    if name == "transcripts":
        return [grok_blobs_dir()]
    if name == "employer":
        return list(employer_paths()[1:])
    if name == "git":
        return list(git_paths()[1:])
    return []


def detected_targets(
    allowlist: tuple[str, ...] | None = None,
) -> list[tuple[Any, Path]]:
    names = allowlist or tuple(item.name for item in CONTRIBUTIONS)
    targets: list[tuple[Any, Path]] = []
    for name in names:
        item = contribution(name)
        if item is None:
            continue
        paths: list[Path] = []
        default = default_path(name)
        if default is not None and item.source.detect(default):
            paths.append(default)
        for extra in extra_paths(name):
            if item.source.detect(extra):
                paths.append(extra)
        for path in paths:
            targets.append((item, path))
    return targets


def source_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in CONTRIBUTIONS:
        default = default_path(item.name)
        detected = default is not None and item.source.detect(default)
        extras = [str(p) for p in extra_paths(item.name) if item.source.detect(p)]
        rows.append(
            {
                "name": item.name,
                "path": str(default) if default is not None else "",
                "detected": detected,
                "extras": extras,
            }
        )
    return rows


def loop_counts(cfg: Config, corpus: Corpus) -> dict[str, int]:
    """Counts the result loop uses to name a next step."""
    pending = len(corpus.cards(STATUS_PENDING))
    approved = len(corpus.cards(STATUS_APPROVED))
    spanned = sum(
        1
        for card in corpus.cards(STATUS_APPROVED)
        if (card.extras.get("span") or "").strip()
    )
    adapters = source_rows()
    return {
        "records": len(corpus.records()),
        "pending": pending,
        "approved": approved,
        "refused": len(corpus.cards(STATUS_REFUSED)),
        "spanned": spanned,
        "vectors": corpus.vector_count(cfg.embed_model),
        "detected": sum(1 for row in adapters if row["detected"]),
    }


def readiness_notes(cfg: Config, corpus: Corpus) -> list[str]:
    """Shared doctor and locker warnings. Does not write."""
    from dossier.identity import (
        configured_slack_user_ids,
        is_sent_metadata_uri,
        resolve_speaker_names,
    )
    from dossier.office import office_extra_ready

    notes: list[str] = []
    if not corpus.fts_ok:
        notes.append("FTS5 is off. Prove and ask prefer it. Check this Python SQLite build.")
    if llm_egress_is_remote(cfg):
        notes.append("Egress is on. Text can leave the machine for a remote model.")
    identity_empty = not configured_slack_user_ids() and not resolve_speaker_names()
    for item in CONTRIBUTIONS:
        default = default_path(item.name)
        seen = default is not None and item.source.detect(default)
        if item.name == "pubs" and seen:
            rows = len(item.source.records_for(default))  # type: ignore[attr-defined]
            if pubs_collection() and rows == 0:
                notes.append("Pubs collection is set but rows=0. Check the collection name and zotero_db.")
        if seen and item.name == "slack" and identity_empty:
            notes.append("Slack is detected but identity is empty. Set slack_user_ids or speaker_names.")
        if seen and item.name == "meetings" and not resolve_speaker_names():
            notes.append("Meetings are detected but speaker_names is empty.")
    sent_meta = sum(1 for rec in corpus.records("mbox") if is_sent_metadata_uri(rec.uri))
    if sent_meta:
        notes.append(
            f"{sent_meta} mail records are Sent-folder metadata only (subjects and attachments, no body)."
        )
    office = 0
    for rec in corpus.records():
        if "Binary body not ingested" in rec.text and any(
            rec.uri.lower().endswith(ext) for ext in (".pdf", ".docx", ".pptx")
        ):
            office += 1
    if office and not office_extra_ready():
        notes.append(
            f"{office} office files are still inventory. Install the office extra to read PDF text "
            "(uv sync --extra office). Word and PowerPoint use the standard library."
        )
    elif office:
        notes.append(f"{office} office files are still inventory. Re-ingest after the office extra is installed.")
    spanned = sum(
        1
        for card in corpus.cards(STATUS_APPROVED)
        if (card.extras.get("span") or "").strip()
    )
    if spanned == 0 and corpus.cards(STATUS_APPROVED):
        notes.append("Approved cards need defend before tailor can quote them.")
    return notes


def _next_stage(href: str, counts: dict[str, int]) -> str:
    """Which readiness stage the next step is pointing at. Empty when the loop is past them."""
    if href == "/sources":
        return "detected" if counts["detected"] < 1 else "records"
    if href == "/extract":
        return "records"
    if href == "/review":
        return "pending" if counts["pending"] else "spanned"
    if href == "/index":
        return "vectors"
    return ""


def locker_snapshot(cfg: Config, corpus: Corpus) -> dict[str, Any]:
    from dossier.nextstep import next_step

    counts = loop_counts(cfg, corpus)
    href, sentence = next_step(
        records=counts["records"],
        pending=counts["pending"],
        approved=counts["approved"],
        spanned=counts["spanned"],
        vectors=counts["vectors"],
        detected=counts["detected"],
    )
    return {
        "data_dir": cfg.data_dir,
        "evidence_db": str(evidence_db(Path(cfg.data_dir))),
        "records": counts["records"],
        "pending": counts["pending"],
        "approved": counts["approved"],
        "refused": counts["refused"],
        "spanned": counts["spanned"],
        "vectors": counts["vectors"],
        "next": sentence,
        "next_href": href,
        "next_stage": _next_stage(href, counts),
        "stages": (
            ("detected", "Detected"),
            ("records", "Records"),
            ("pending", "Pending"),
            ("spanned", "Spanned"),
            ("vectors", "Vectors"),
        ),
        "notes": readiness_notes(cfg, corpus),
        "fts5": corpus.fts_ok,
        "python": sys.executable,
        "sqlite": sqlite3.sqlite_version,
        "provider": cfg.llm_provider if cfg.llm_enabled else "off",
        "egress": egress_status(cfg),
        "egress_remote": llm_egress_is_remote(cfg),
        "effort": cfg.effort,
        "model": cfg.llm_model,
        "max_calls": cfg.llm_max_calls,
        "ask_mode": cfg.ask_mode,
        "ask_planner": cfg.ask_planner,
        "extract_llm": cfg.extract_llm,
        "embed_model": cfg.embed_model,
        "pubs_collection": pubs_collection() or "",
        "employer_paths": len(employer_paths()),
        "git_paths": len(git_paths()),
        "git_user": git_user() or "",
        "adapters": source_rows(),
    }


_YELLOW = "\033[33m"
_RESET = "\033[0m"


def note_egress(cfg: Config) -> None:
    """Print the yellow egress notice once per process when remote LLM is on."""
    if getattr(note_egress, "done", False) or not llm_egress_is_remote(cfg):
        return
    note_egress.done = True  # type: ignore[attr-defined]
    print(f"{_YELLOW}{EGRESS_NOTICE}{_RESET}", file=sys.stderr)


class LazyClient:
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
            note_egress(self.cfg)
            inner = get_client(self.cfg)
            ok, msg = inner.check_config(self.cfg.llm_model)
            if not ok:
                raise LLMClientError(msg)
            self._inner = inner
        return self._inner


def client_for_mode(cfg: Config, mode: str) -> tuple[LLMClient, int | None]:
    """A client, and an exit code when rich mode cannot reach a model."""
    if mode == "exact" or not cfg.llm_enabled:
        return NullLLMClient(), None
    if llm_egress_is_remote(cfg):
        note_egress(cfg)
    client = get_client(cfg)
    ok, msg = client.check_config(cfg.llm_model)
    if ok:
        return client, None
    if mode == "rich":
        print(msg, file=sys.stderr)
        return client, 2
    print(msg, file=sys.stderr)
    return NullLLMClient(), None


def query_embedder(cfg: Config, corpus: Corpus):
    """Embed the question only when this model already has vectors."""
    from dossier.embed import OllamaEmbedder
    from dossier.llm.validate import LlmConfigError, validate_ollama_url

    if not cfg.ask_embed or not cfg.llm_enabled:
        return None
    if corpus.vector_count(cfg.embed_model) < 1:
        return None
    try:
        validate_ollama_url(cfg.llm_base_url, False)
    except LlmConfigError:
        if not cfg.llm_allow_remote:
            return None
        note_egress(cfg)
    return OllamaEmbedder(cfg.llm_base_url, cfg.llm_allow_remote, cfg.embed_model)


def detected_targets_report(
    allowlist: tuple[str, ...] | None = None,
) -> tuple[list[tuple[Any, Path]], list[str]]:
    """Targets plus skip lines for ``run`` / doctor-style reports."""
    names = allowlist or tuple(item.name for item in CONTRIBUTIONS)
    targets: list[tuple[Any, Path]] = []
    skipped: list[str] = []
    for name in names:
        item = contribution(name)
        if item is None:
            skipped.append(f"skip {name}: unknown adapter")
            continue
        paths: list[Path] = []
        default = default_path(name)
        if default is not None and item.source.detect(default):
            paths.append(default)
        for extra in extra_paths(name):
            if item.source.detect(extra):
                paths.append(extra)
        if not paths:
            skipped.append(f"skip {name}: not detected")
            continue
        for path in paths:
            targets.append((item, path))
    return targets, skipped
