"""Prior job-application packs. One directory only. PDF bodies stay off the corpus."""

from __future__ import annotations

from pathlib import Path

from dossier.store import Corpus, Record
from dossier.util import record_id

TEXT_SUFFIXES = {".txt", ".md", ".html", ".htm", ".json", ".tex", ".csv"}
SKIP_NAMES = {".ds_store", "thumbs.db"}
TEXT_CAP = 20_000


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
        for child in sorted(root.rglob("*")):
            if not child.is_file():
                continue
            if child.name.lower() in SKIP_NAMES:
                continue
            rel = child.relative_to(root).as_posix()
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

    def tables(self) -> list[str]:
        return ["applications.files"]
