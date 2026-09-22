"""Commit subjects from repos you list. No patch bodies, no home scan."""

from __future__ import annotations

import subprocess
from pathlib import Path

from dossier.lists import excluded
from dossier.paths import git_user
from dossier.store import Corpus, Record
from dossier.util import record_id

GIT_LIMIT = 400
FILE_CAP = 40
TEXT_CAP = 8000


class GitSource:
    name = "git"

    def detect(self, path: Path) -> bool:
        return path.is_dir() and (path / ".git").exists()

    def load(self, path: Path, corpus: Corpus) -> None:
        if not self.detect(path):
            return
        raw = _log(path, git_user())
        if not raw:
            return
        name = path.resolve().name or "repo"
        for sha, day, subject, files in _commits(raw):
            if not sha or not subject:
                continue
            if excluded("git", subject, " ".join(files)):
                continue
            lines = [subject]
            if day:
                lines.extend(["", f"Date: {day}"])
            listed = files[:FILE_CAP]
            if listed:
                lines.extend(["", *listed])
            body = "\n".join(lines)
            uri = f"git://{name}/{sha}"
            corpus.upsert_record(
                Record(
                    id=record_id(uri),
                    source="git",
                    uri=uri,
                    title=subject[:160],
                    text=body[:TEXT_CAP],
                    table="git.log",
                )
            )

    def tables(self) -> list[str]:
        return ["git.log"]


def _log(path: Path, author: str = "") -> str | None:
    cmd = [
        "git",
        "-C",
        str(path),
        "log",
        "-n",
        str(GIT_LIMIT),
        "--date=short",
        "--pretty=format:%x1e%H%x1f%ad%x1f%s",
        "--name-only",
    ]
    if author.strip():
        cmd.extend(["--author", author.strip()])
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def _commits(raw: str) -> list[tuple[str, str, str, list[str]]]:
    out: list[tuple[str, str, str, list[str]]] = []
    for block in raw.split("\x1e"):
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        head = lines[0].split("\x1f")
        if len(head) < 3:
            continue
        sha, day, subject = head[0].strip(), head[1].strip(), head[2].strip()
        files = [line.strip() for line in lines[1:] if line.strip()]
        out.append((sha, day, subject, files))
    return out
