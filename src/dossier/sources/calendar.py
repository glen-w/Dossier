"""``.ics`` calendar exports. Events as evidence of talks and meetings."""

from __future__ import annotations

from pathlib import Path

from dossier.lists import excluded
from dossier.store import Corpus, Record
from dossier.text import TEXT_CAP
from dossier.util import record_id

_ICS_KEYS = ("SUMMARY", "DESCRIPTION", "LOCATION", "DTSTART", "ORGANIZER")


class CalendarSource:
    name = "ics"

    def detect(self, path: Path) -> bool:
        if path.is_file():
            return path.suffix.lower() == ".ics"
        if not path.is_dir():
            return False
        try:
            return any(child.suffix.lower() == ".ics" and child.is_file() for child in path.iterdir())
        except OSError:
            return False

    def load(self, path: Path, corpus: Corpus) -> None:
        files: list[Path]
        if path.is_file():
            files = [path]
        else:
            files = [child for child in sorted(path.iterdir()) if child.is_file() and child.suffix.lower() == ".ics"]
        for file in files:
            if file.is_symlink():
                continue
            if excluded("ics", file.name):
                continue
            try:
                raw = file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for index, block in enumerate(_events(raw)):
                title = block.get("SUMMARY") or file.stem
                body = _format(block)[:TEXT_CAP]
                if not body:
                    continue
                uri = f"ics://{file.stem}/{index}"
                corpus.upsert_record(
                    Record(
                        id=record_id(uri),
                        source="ics",
                        uri=uri,
                        title=title,
                        text=body,
                        table="ics.event",
                    )
                )

    def tables(self) -> list[str]:
        return ["ics.event"]


def _events(raw: str) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    key = ""
    for line in raw.splitlines():
        if line.startswith("BEGIN:VEVENT"):
            current = {}
            key = ""
            continue
        if line.startswith("END:VEVENT"):
            if current:
                events.append(current)
            current = None
            continue
        if current is None:
            continue
        if line.startswith(" ") and key:
            current[key] = current.get(key, "") + line[1:]
            continue
        if ":" not in line:
            continue
        name, _, value = line.partition(":")
        name = name.split(";", 1)[0].upper()
        if name in _ICS_KEYS:
            current[name] = value
            key = name
        else:
            key = ""
    return events


def _format(block: dict[str, str]) -> str:
    year = ""
    start = block.get("DTSTART") or ""
    if len(start) >= 4 and start[:4].isdigit():
        year = start[:4]
    lines = [
        "Lens: contributions",
        "Kind: talk",
        f"Year: {year}" if year else "",
        block.get("SUMMARY") or "",
        block.get("LOCATION") or "",
        block.get("DESCRIPTION") or "",
        block.get("ORGANIZER") or "",
        block.get("DTSTART") or "",
    ]
    return "\n".join(line for line in lines if line)
