"""Cursor agent transcripts and Grok Bot blobs. Local scan. Not committed."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dossier.store import Corpus, Record
from dossier.util import record_id

TEXT_CAP = 8000
JSONL_FILE_CAP = 500
BLOB_FILE_CAP = 200


class TranscriptsSource:
    name = "transcripts"

    def detect(self, path: Path) -> bool:
        if path.is_file():
            return path.suffix.lower() in {".jsonl", ".blob", ".json"}
        if not path.is_dir():
            return False
        if path.name in {"agent-transcripts", "sand-client-persistence"}:
            return True
        if (path / "agent-transcripts").is_dir():
            return True
        if any(path.glob("*/agent-transcripts")):
            return True
        if any(path.glob("*.blob")):
            return True
        return False

    def load(self, path: Path, corpus: Corpus) -> None:
        if path.is_file():
            _load_file(path, corpus)
            return
        jsonl_files: list[Path] = []
        if path.name == "agent-transcripts":
            jsonl_files = sorted(path.glob("*.jsonl"))
        else:
            jsonl_files = sorted(path.glob("*/agent-transcripts/*.jsonl"))
            jsonl_files.extend(sorted(path.glob("agent-transcripts/*.jsonl")))
        for item in jsonl_files[:JSONL_FILE_CAP]:
            _load_jsonl(item, corpus)
        blobs: list[Path] = []
        if path.name == "sand-client-persistence" or any(path.glob("*.blob")):
            blobs = sorted(path.glob("*.blob"))
        for item in blobs[:BLOB_FILE_CAP]:
            _load_blob(item, corpus)

    def tables(self) -> list[str]:
        return ["transcripts.cursor", "transcripts.grok"]


def _load_file(path: Path, corpus: Corpus) -> None:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        _load_jsonl(path, corpus)
    elif suffix in {".blob", ".json"}:
        _load_blob(path, corpus)


def _load_jsonl(path: Path, corpus: Corpus) -> None:
    queries = _user_queries(path)
    if not queries:
        return
    stem = path.stem
    project = path.parent.parent.name if path.parent.name == "agent-transcripts" else "cursor"
    uri = f"cursor://{project}/{stem}"
    corpus.upsert_record(
        Record(
            id=record_id(uri),
            source="transcripts",
            uri=uri,
            title=f"Cursor {project}",
            text=queries[:TEXT_CAP],
            table="transcripts.cursor",
        )
    )


def _user_queries(path: Path) -> str:
    parts: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        if obj.get("role") != "user":
            continue
        text = _content_text(obj.get("message"))
        if "<user_query>" in text:
            text = text.split("<user_query>", 1)[1]
            text = text.split("</user_query>", 1)[0]
        text = text.strip()
        if text:
            parts.append(text)
        if sum(len(p) for p in parts) > TEXT_CAP:
            break
    return "\n---\n".join(parts)


def _content_text(message: Any) -> str:
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        bits: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                bits.append(str(item.get("text") or ""))
        return "\n".join(bits)
    return ""


def _load_blob(path: Path, corpus: Corpus) -> None:
    text = _blob_text(path)
    if not text:
        return
    uri = f"grok://{path.name}"
    corpus.upsert_record(
        Record(
            id=record_id(uri),
            source="transcripts",
            uri=uri,
            title="Grok Bot blob",
            text=text[:TEXT_CAP],
            table="transcripts.grok",
        )
    )


def _blob_text(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError:
        return ""
    if not raw or b"\x00" in raw[:64]:
        return ""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ""
    parts = _json_strings(data)
    return "\n".join(parts)[:TEXT_CAP]


def _json_strings(node: Any, *, depth: int = 0) -> list[str]:
    if depth > 6:
        return []
    if isinstance(node, str):
        text = node.strip()
        return [text] if len(text) > 40 else []
    if isinstance(node, list):
        out: list[str] = []
        for item in node:
            out.extend(_json_strings(item, depth=depth + 1))
        return out
    if isinstance(node, dict):
        out = []
        for key, value in node.items():
            if key.lower() in {"text", "content", "message", "prompt", "query"}:
                out.extend(_json_strings(value, depth=depth + 1))
        if not out:
            for value in node.values():
                out.extend(_json_strings(value, depth=depth + 1))
        return out
    return []
