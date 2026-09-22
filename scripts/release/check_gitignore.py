#!/usr/bin/env python3
"""Fail when personal data could be committed.

Run this before every push. A failure means do not push.

The check has two parts:
1. `.gitignore` still has the required shape (the patterns below).
2. Nothing already tracked matches those personal paths.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Lines that must appear in .gitignore, exactly, so a later edit cannot
# quietly drop a personal-data rule. Comments and blanks are ignored.
REQUIRED_LINES = (
    ".env",
    ".env.*",
    "dossier.toml",
    "private/",
    "secrets/",
    "data/",
    "warehouse/",
    "data_dumps_raw/",
    "lancedb/",
    "*.duckdb",
    "*.lance",
    "*.sqlite",
    "*.db",
    "evidence.db",
    "ledger.json",
    "briefs/",
    "packets/",
    "drafts/",
    "*.mbox",
    "*.eml",
    "conversations.json",
    "*.jsonl",
    "*.zip",
    "*.pdf",
    "*.docx",
    "*.csv",
    "/email/",
    "/transcripts/",
    "/exports/",
)

_DENY_NAMES = {
    ".env",
    "dossier.toml",
    "ledger.json",
    "ledger.md",
    "conversations.json",
    "evidence.db",
    "corpus.db",
    "credentials.json",
}
_DENY_SUFFIXES = (
    ".pdf",
    ".mbox",
    ".mbx",
    ".eml",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".duckdb",
    ".docx",
    ".zip",
    ".jsonl",
    ".pem",
    ".key",
)
_DENY_PREFIXES = (
    "data/",
    "warehouse/",
    "private/",
    "secrets/",
    "email/",
    "transcripts/",
    "exports/",
    "briefs/",
    "packets/",
    "drafts/",
    "lancedb/",
)


def missing_patterns(text: str) -> list[str]:
    present = {
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    return [line for line in REQUIRED_LINES if line not in present]


def personal_tracked(paths: list[str]) -> list[str]:
    bad: list[str] = []
    for raw in paths:
        path = raw.strip().replace("\\", "/")
        if not path or path == "dossier.example.toml":
            continue
        name = path.rsplit("/", 1)[-1]
        if name in _DENY_NAMES or path.startswith(_DENY_PREFIXES):
            bad.append(path)
            continue
        lower = name.lower()
        if lower.endswith(_DENY_SUFFIXES):
            bad.append(path)
    return bad


def tracked_paths(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return [part.decode() for part in result.stdout.split(b"\0") if part]


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    ignore = root / ".gitignore"
    if not ignore.is_file():
        print("gitignore shape: FAIL (.gitignore missing)", file=sys.stderr)
        print("Do not push.", file=sys.stderr)
        return 1
    missing = missing_patterns(ignore.read_text(encoding="utf-8"))
    tracked = personal_tracked(tracked_paths(root))
    if missing or tracked:
        print("gitignore shape: FAIL", file=sys.stderr)
        for line in missing:
            print(f"  missing pattern: {line}", file=sys.stderr)
        for path in tracked:
            print(f"  tracked personal path: {path}", file=sys.stderr)
        print("Do not push until this is clean.", file=sys.stderr)
        return 1
    print("gitignore shape: pass")
    print("tracked personal paths: none")
    print("Push only after this check passes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
