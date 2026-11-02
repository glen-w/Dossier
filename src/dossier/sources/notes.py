"""Markdown / Obsidian notes folder you list. No vault scan of home."""

from __future__ import annotations

from pathlib import Path

from dossier.lists import excluded
from dossier.store import Corpus, Record
from dossier.text import TEXT_CAP
from dossier.util import record_id

_SUFFIXES = {".md", ".markdown", ".txt"}


class NotesSource:
    name = "notes"

    def detect(self, path: Path) -> bool:
        if not path.is_dir():
            return False
        try:
            return any(child.is_file() and child.suffix.lower() in _SUFFIXES for child in path.iterdir())
        except OSError:
            return False

    def load(self, path: Path, corpus: Corpus) -> None:
        root = path.resolve()
        if not root.is_dir():
            return
        for child in sorted(root.rglob("*")):
            if child.is_symlink() or not child.is_file():
                continue
            if child.suffix.lower() not in _SUFFIXES:
                continue
            rel = child.relative_to(root).as_posix()
            if excluded("notes", child.name, rel):
                continue
            try:
                body = child.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            text = body.strip()[:TEXT_CAP]
            if not text:
                continue
            uri = f"file://notes/{rel}"
            corpus.upsert_record(
                Record(
                    id=record_id(uri),
                    source="notes",
                    uri=uri,
                    title=child.stem,
                    text=f"Lens: delivered\nKind: note\n{text}",
                    table="notes.file",
                )
            )

    def tables(self) -> list[str]:
        return ["notes.file"]
