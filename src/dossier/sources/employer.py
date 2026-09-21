"""One allowlisted employer folder. Not a walk of Documents."""

from __future__ import annotations

from pathlib import Path

from dossier.paths import employer_paths
from dossier.store import Corpus, Record
from dossier.util import record_id

TEXT_SUFFIXES = {".txt", ".md", ".html", ".htm", ".json", ".tex", ".csv"}
SKIP_NAMES = {".ds_store", "thumbs.db"}
SKIP_DIRS = {".git", ".hg"}
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
        for child in sorted(root.rglob("*")):
            if not child.is_file():
                continue
            if child.name.lower() in SKIP_NAMES:
                continue
            rel = child.relative_to(root)
            if any(part in SKIP_DIRS for part in rel.parts):
                continue
            slug = root.name or "folder"
            uri = f"file://employer/{slug}/{rel.as_posix()}"
            parent = child.parent.name
            suffix = child.suffix.lower()
            if suffix in TEXT_SUFFIXES:
                try:
                    body = child.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    body = ""
                text = body.strip()[:TEXT_CAP]
                if not text:
                    continue
                title = child.stem
            else:
                title = child.name
                text = (
                    f"Employer folder file '{rel.as_posix()}'. Folder: {parent}. "
                    "Binary body not ingested."
                )
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

    def tables(self) -> list[str]:
        return ["employer.files"]


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
