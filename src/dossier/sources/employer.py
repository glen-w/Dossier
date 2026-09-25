"""One allowlisted employer folder. Not a walk of Documents."""

from __future__ import annotations

from pathlib import Path

from dossier.config import Config
from dossier.llm import EGRESS_NOTICE, get_client, llm_egress_is_remote
from dossier.llm.client import LLMClient
from dossier.office import INVENTORY_MARK, OFFICE_SUFFIXES, extract_office
from dossier.paths import employer_paths
from dossier.sources.employer_filter import FilterStats, select_files
from dossier.store import Corpus, Record
from dossier.ui import Progress, note, trunc, warn
from dossier.util import record_id

TEXT_SUFFIXES = {".txt", ".md", ".html", ".htm", ".json", ".tex", ".csv"}
TEXT_CAP = 20_000


class EmployerSource:
    name = "employer"

    def detect(self, path: Path) -> bool:
        return path.is_dir() and _listed(path)

    def load(self, path: Path, corpus: Corpus) -> None:
        root = path.expanduser()
        if not root.is_dir() or not _listed(root):
            return
        root = root.resolve()
        slug = root.name or "folder"
        cfg = Config.from_env()
        client = _filter_client(cfg)
        with Progress(0, label=f"filter {slug}") as scan:

            def on_dir(rel: str, stats: FilterStats) -> None:
                scan.tick(
                    skip_dirs=stats.skip_dirs,
                    skip_files=stats.skip_files,
                    at=trunc(rel, 40),
                )

            chosen = select_files(
                root,
                enabled=cfg.employer_filter,
                client=client,
                model=cfg.llm_model,
                max_calls=cfg.employer_filter_llm_calls,
                timeout_seconds=min(cfg.llm_timeout_seconds, 60.0),
                on_dir=on_dir,
            )
            scan.finish(
                skip_dirs=chosen.skip_dirs,
                skip_files=chosen.skip_files,
                versions=chosen.version_drops,
                llm_drop=chosen.llm_drops,
            )
        extra = ""
        if chosen.llm_unreviewed:
            extra = f" llm_unreviewed={chosen.llm_unreviewed}"
        note(
            f"filter {slug} · keep={len(chosen.files)} "
            f"skip_dirs={chosen.skip_dirs} skip_files={chosen.skip_files} "
            f"versions={chosen.version_drops} llm={chosen.llm_note} "
            f"llm_calls={chosen.llm_calls}{extra}"
        )
        stored = 0
        inventory = 0
        with Progress(len(chosen.files), label=f"employer {slug}") as bar:
            for item in chosen.files:
                child = item.path
                rel = child.relative_to(root)
                uri = f"file://employer/{slug}/{rel.as_posix()}"
                parent = child.parent.name
                suffix = child.suffix.lower()
                kind = "stored"
                if suffix in TEXT_SUFFIXES:
                    try:
                        body = child.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        body = ""
                    text = body.strip()[:TEXT_CAP]
                    if not text:
                        bar.tick(stored=stored, inventory=inventory)
                        bar.status(trunc(rel.as_posix(), 48))
                        continue
                    title = child.stem
                    stored += 1
                elif suffix in OFFICE_SUFFIXES:
                    body, reason = extract_office(child)
                    if body:
                        title = child.stem
                        text = body
                        stored += 1
                    else:
                        title = child.name
                        text = (
                            f"Employer folder file '{rel.as_posix()}'. Folder: {parent}. "
                            f"{INVENTORY_MARK}. {reason}"
                        )
                        kind = "inventory"
                        inventory += 1
                else:
                    title = child.name
                    text = (
                        f"Employer folder file '{rel.as_posix()}'. Folder: {parent}. "
                        f"{INVENTORY_MARK}."
                    )
                    kind = "inventory"
                    inventory += 1
                corpus.upsert_record(
                    Record(
                        id=record_id(uri),
                        source="employer",
                        uri=uri,
                        title=title,
                        text=text,
                        table="employer.files",
                    )
                )
                bar.tick(stored=stored, inventory=inventory)
                bar.status(f"{kind} {trunc(rel.as_posix(), 48)}")
            bar.finish(stored=stored, inventory=inventory)

    def tables(self) -> list[str]:
        return ["employer.files"]


def _filter_client(cfg: Config) -> LLMClient | None:
    if not cfg.employer_filter or not cfg.employer_filter_llm or not cfg.llm_enabled:
        return None
    if llm_egress_is_remote(cfg) and not getattr(_filter_client, "noted", False):
        _filter_client.noted = True  # type: ignore[attr-defined]
        warn(EGRESS_NOTICE)
    return get_client(cfg)


def _listed(path: Path) -> bool:
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        return False
    for allowed in employer_paths():
        try:
            if allowed.expanduser().resolve() == resolved:
                return True
        except OSError:
            continue
    return False
