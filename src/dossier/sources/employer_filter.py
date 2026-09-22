"""Pre-filter an employer folder before any record is written.

Lane 1 is deterministic and on by default: skip cache trees and junk types,
then keep the newest copy when names look like versions of one file.
Lane 2 runs only when a model is enabled: one prompt over folder names,
not file bodies. A bad reply keeps the deterministic set.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from dossier.llm.budget import CallBudget
from dossier.llm.client import CompletionRequest, LLMClient, LLMClientError

# Directory names that are machinery, not work. Matched on one path part.
SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "node_modules",
        "bower_components",
        "site-packages",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        ".eggs",
        ".ipynb_checkpoints",
        "htmlcov",
        "cache",
        "caches",
        ".cache",
    }
)

# Types that are never career evidence. Office files and source text stay.
SKIP_SUFFIXES = frozenset(
    {
        ".pkl",
        ".pickle",
        ".pyc",
        ".pyo",
        ".pyd",
        ".so",
        ".dylib",
        ".dll",
        ".exe",
        ".o",
        ".obj",
        ".a",
        ".lib",
        ".class",
        ".jar",
        ".war",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".eot",
        ".parquet",
        ".feather",
        ".arrow",
        ".npy",
        ".npz",
        ".h5",
        ".hdf5",
        ".sqlite",
        ".sqlite3",
        ".db",
        ".pt",
        ".pth",
        ".ckpt",
        ".onnx",
        ".safetensors",
        ".gz",
        ".tgz",
        ".bz2",
        ".xz",
        ".7z",
        ".rar",
        ".iso",
        ".dmg",
        ".zip",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".svg",
        ".ico",
        ".bmp",
        ".tif",
        ".tiff",
        ".mp4",
        ".mov",
        ".mp3",
        ".wav",
        ".avi",
        ".mkv",
        ".whl",
    }
)

SKIP_FILE_NAMES = frozenset(
    {
        ".ds_store",
        "thumbs.db",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "cargo.lock",
        "pipfile.lock",
    }
)

_HEX_NAME = re.compile(r"^[0-9a-f]{16,}$")
_COPY_PREFIX = re.compile(r"(?i)^copy of ")
_VERSION_TAIL = re.compile(
    r"(?i)(?:\s*\(\d+\)|\s*\(final\)\d*|\s*[-_ ]copy|\s*[-_ ]final|\s*[-_ ]v\d+)$"
)
_SPACE = re.compile(r"[\s_-]+")

_PROMPT = """You are filtering folders before a career dossier ingest.
Keep a folder when the names look like work a person wrote, facilitated, delivered, or decided: notes, minutes, reports, decks, agendas, strategy, coaching.
Drop a folder when the names look like a cache, a dependency tree, a raw dataset, a hashed dump, a chat export, or generated assets.
Reply with JSON only: {"drop": ["relative/path", ...]}
Drop a path only when you are sure. A path you omit is kept. Do not drop ".".
Folders:
@@LIST@@
"""

_BATCH = 40
_NAMES = 8


@dataclass(frozen=True)
class KeptFile:
    path: Path
    rel: str
    mtime: float


@dataclass
class FilterStats:
    scan_dirs: int = 0
    skip_dirs: int = 0
    skip_files: int = 0
    version_drops: int = 0
    llm_drops: int = 0
    llm_calls: int = 0
    llm_unreviewed: int = 0
    llm_note: str = ""
    files: list[KeptFile] = field(default_factory=list)


OnDir = Callable[[str, FilterStats], None]


def select_files(
    root: Path,
    *,
    enabled: bool = True,
    client: LLMClient | None = None,
    model: str = "",
    max_calls: int = 4,
    timeout_seconds: float = 300.0,
    on_dir: OnDir | None = None,
) -> FilterStats:
    """Walk ``root``. When ``enabled`` is false, keep the old broad inventory."""
    stats = FilterStats()
    found = _walk(root, enabled=enabled, stats=stats, on_dir=on_dir)
    if not enabled:
        stats.files = found
        return stats
    kept, dropped = collapse_versions(found)
    stats.version_drops = dropped
    stats.files = kept
    if client is None or max_calls < 1:
        if client is None:
            stats.llm_note = "off"
        return stats
    parents = {_parent(item.rel) for item in kept}
    if len(parents) < 2:
        stats.llm_note = "skipped (one folder)"
        return stats
    dropped_dirs, note = _llm_drop(
        kept,
        client,
        model=model,
        max_calls=max_calls,
        timeout_seconds=timeout_seconds,
        stats=stats,
    )
    stats.llm_note = note
    if dropped_dirs:
        before = len(stats.files)
        stats.files = [
            item for item in stats.files if not _under(_parent(item.rel), dropped_dirs)
        ]
        stats.llm_drops = before - len(stats.files)
    return stats


def collapse_versions(files: list[KeptFile]) -> tuple[list[KeptFile], int]:
    """Keep the newest file in each same-folder, same-type, same-stem group."""
    groups: dict[tuple[str, str, str], list[KeptFile]] = {}
    order: list[tuple[str, str, str]] = []
    for item in files:
        path = Path(item.rel)
        key = (_parent(item.rel), path.suffix.casefold(), version_stem(path.name))
        if key not in groups:
            order.append(key)
            groups[key] = []
        groups[key].append(item)
    kept: list[KeptFile] = []
    dropped = 0
    for key in order:
        group = groups[key]
        if len(group) == 1 or not key[2]:
            kept.extend(group)
            continue
        winner = max(group, key=lambda item: (item.mtime, item.rel))
        kept.append(winner)
        dropped += len(group) - 1
    return kept, dropped


def version_stem(name: str) -> str:
    """Stem with copy markers removed, so ``notes (final).md`` matches ``notes.md``."""
    stem = Path(name).stem
    stem = _COPY_PREFIX.sub("", stem).strip()
    previous = None
    while previous != stem:
        previous = stem
        stem = _VERSION_TAIL.sub("", stem).strip()
    return _SPACE.sub(" ", stem).strip().casefold()


def _walk(
    root: Path,
    *,
    enabled: bool,
    stats: FilterStats,
    on_dir: OnDir | None,
) -> list[KeptFile]:
    found: list[KeptFile] = []
    stack = [root]
    while stack:
        current = stack.pop()
        stats.scan_dirs += 1
        rel_dir = _rel(root, current)
        if on_dir is not None:
            on_dir(rel_dir or ".", stats)
        try:
            entries = list(os.scandir(current))
        except OSError:
            stats.skip_dirs += 1
            continue
        dirs: list[os.DirEntry[str]] = []
        files: list[os.DirEntry[str]] = []
        for entry in entries:
            try:
                if entry.is_symlink():
                    stats.skip_files += 1
                    continue
                if entry.is_dir(follow_symlinks=False):
                    dirs.append(entry)
                elif entry.is_file(follow_symlinks=False):
                    files.append(entry)
            except OSError:
                stats.skip_files += 1
        for entry in dirs:
            if _skip_dir(entry.name, enabled=enabled):
                stats.skip_dirs += 1
                continue
            stack.append(Path(entry.path))
        for entry in files:
            if _skip_file(entry.name, enabled=enabled):
                stats.skip_files += 1
                continue
            try:
                mtime = entry.stat(follow_symlinks=False).st_mtime
            except OSError:
                stats.skip_files += 1
                continue
            rel = _rel(root, Path(entry.path))
            found.append(KeptFile(path=Path(entry.path), rel=rel, mtime=mtime))
    return found


def _skip_dir(name: str, *, enabled: bool) -> bool:
    folded = name.casefold()
    if folded in {".git", ".hg"}:
        return True
    if not enabled:
        return False
    if folded in SKIP_DIR_NAMES or folded.endswith(".egg-info"):
        return True
    return False


def _skip_file(name: str, *, enabled: bool) -> bool:
    folded = name.casefold()
    if folded in {".ds_store", "thumbs.db"}:
        return True
    if not enabled:
        return False
    if folded in SKIP_FILE_NAMES or folded.startswith("~$"):
        return True
    suffix = Path(folded).suffix
    if suffix in SKIP_SUFFIXES:
        return True
    stem = Path(folded).stem
    if _HEX_NAME.match(stem):
        return True
    return False


def _rel(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _parent(rel: str) -> str:
    parent = Path(rel).parent.as_posix()
    if parent == ".":
        return ""
    return parent


def _under(parent: str, drops: set[str]) -> bool:
    for drop in drops:
        if parent == drop or parent.startswith(drop + "/"):
            return True
    return False


def _llm_drop(
    files: list[KeptFile],
    client: LLMClient,
    *,
    model: str,
    max_calls: int,
    timeout_seconds: float,
    stats: FilterStats,
) -> tuple[set[str], str]:
    lines = _folder_lines(files)
    budget = CallBudget(max_calls)
    wrapped = budget.wrap(client)
    drops: set[str] = set()
    known = {_parent(item.rel) for item in files}
    known.discard("")
    note = ""
    reviewed = 0
    for start in range(0, len(lines), _BATCH):
        batch = lines[start : start + _BATCH]
        if budget.calls >= budget.max_calls:
            stats.llm_unreviewed = len(lines) - reviewed
            note = "kept remainder (budget)"
            break
        prompt = _PROMPT.replace("@@LIST@@", "\n".join(batch))
        try:
            data = wrapped.complete_json(
                CompletionRequest(
                    model=model,
                    prompt=prompt,
                    json_mode=True,
                    timeout_seconds=timeout_seconds,
                    temperature=0.0,
                )
            )
        except LLMClientError:
            stats.llm_calls = budget.calls
            stats.llm_unreviewed = len(lines) - reviewed
            return drops, "kept remainder (model error)"
        stats.llm_calls = budget.calls
        reviewed += len(batch)
        raw = data.get("drop")
        if not isinstance(raw, list):
            continue
        for item in raw:
            path = str(item).strip().strip("/")
            if not path or path == ".":
                continue
            if any(
                path == folder or folder.startswith(path + "/") or path.startswith(folder + "/")
                for folder in known
            ):
                drops.add(path)
    if not note:
        note = "ok"
    return drops, note


def _folder_lines(files: list[KeptFile]) -> list[str]:
    by_dir: dict[str, list[str]] = {}
    for item in files:
        folder = _parent(item.rel) or "."
        by_dir.setdefault(folder, []).append(Path(item.rel).name)
    lines: list[str] = []
    for folder, names in sorted(by_dir.items()):
        shown = ", ".join(names[:_NAMES])
        extra = len(names) - _NAMES
        if extra > 0:
            shown = f"{shown} (+{extra})"
        lines.append(f"{folder} :: {shown}")
    return lines
