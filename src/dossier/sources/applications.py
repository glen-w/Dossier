"""Prior job-application packs. One directory only. PDF bodies stay off the corpus."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dossier.lists import application_dirs, application_files, excluded
from dossier.store import Corpus, Record
from dossier.util import record_id

TEXT_SUFFIXES = {".txt", ".md", ".html", ".htm", ".json", ".tex", ".csv"}
TEXT_CAP = 20_000
DEFAULT_MAX_FILES = 2_000


def applications_max_files() -> int:
    raw = os.environ.get("DOSSIER_APPLICATIONS_MAX_FILES", "").strip()
    if not raw:
        return DEFAULT_MAX_FILES
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_FILES
    return value if value > 0 else DEFAULT_MAX_FILES


class ApplicationsSource:
    name = "applications"

    def detect(self, path: Path) -> bool:
        if not path.is_dir():
            return False
        name = path.name.lower().replace("_", " ")
        return "job application" in name or name == "applications"

    def load(self, path: Path, corpus: Corpus) -> None:
        root = path.resolve()
        if not root.is_dir():
            return
        skipped = application_dirs()
        limit = applications_max_files()
        seen = 0
        capped = False
        for child in sorted(root.rglob("*")):
            if not child.is_file():
                continue
            rel_path = child.relative_to(root)
            if any(
                part.casefold() in skipped or part.startswith(".")
                for part in rel_path.parts[:-1]
            ):
                continue
            if child.name.casefold() in application_files():
                continue
            rel = rel_path.as_posix()
            if excluded("applications", child.name, rel):
                continue
            if seen >= limit:
                capped = True
                break
            seen += 1
            uri = f"file://applications/{rel}"
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
                    f"Job application pack file '{rel}'. Folder: {parent}. "
                    "Binary body not ingested."
                )
            corpus.upsert_record(
                Record(
                    id=record_id(uri),
                    source="applications",
                    uri=uri,
                    title=title,
                    text=text,
                    table="applications.files",
                )
            )
        if capped:
            print(
                f"applications: stopped after {limit} files "
                f"(set DOSSIER_APPLICATIONS_MAX_FILES to raise)",
                file=sys.stderr,
            )

    def tables(self) -> list[str]:
        return ["applications.files"]
