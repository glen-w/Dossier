"""ChatGPT export zip or folder. conversations.json only. No unpack into the repo."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from dossier.lists import excluded
from dossier.store import Corpus, Record
from dossier.util import record_id

CHATGPT_LIMIT = 2000
TEXT_CAP = 8000
MIN_CHARS = 40
_MAX_JSON = 80_000_000


def is_chatgpt_export(path: Path) -> bool:
    if path.is_file() and path.name == "conversations.json":
        return True
    if path.is_dir() and (path / "conversations.json").is_file():
        return True
    if path.is_file() and path.suffix.lower() == ".zip":
        return _zip_has(path, "conversations.json")
    return False


def load_chatgpt_export(path: Path, corpus: Corpus) -> None:
    conversations = _conversations(_load_json(path))
    kept = 0
    for conv in conversations:
        if kept >= CHATGPT_LIMIT:
            break
        if not isinstance(conv, dict):
            continue
        cid = str(conv.get("id") or conv.get("conversation_id") or "unknown")
        title = str(conv.get("title") or "").strip()
        for mid, role, text in _messages(conv):
            if kept >= CHATGPT_LIMIT:
                break
            if role not in {"user", "assistant"}:
                continue
            body = text.strip()
            if len(body) <= MIN_CHARS:
                continue
            uri = f"chatgpt://{cid}/{mid}"
            heading = title or f"ChatGPT {role}"
            if excluded("chatgpt", heading):
                continue
            corpus.upsert_record(
                Record(
                    id=record_id(uri),
                    source="chatgpt",
                    uri=uri,
                    title=heading,
                    text=body[:TEXT_CAP],
                    table="chatgpt.messages",
                )
            )
            kept += 1


def _conversations(data: object) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        raw = data.get("conversations") or data.get("items") or []
        if isinstance(raw, list):
            return raw
    return []


def _messages(conv: dict) -> list[tuple[str, str, str]]:
    mapping = conv.get("mapping")
    rows: list[tuple[float, str, str, str]] = []
    if isinstance(mapping, dict):
        nodes = mapping.values()
    else:
        raw = conv.get("messages") or []
        nodes = raw if isinstance(raw, list) else []
    for node in nodes:
        message = node.get("message") if isinstance(node, dict) and "message" in node else node
        if not isinstance(message, dict):
            continue
        role, text = _role_text(message)
        if not text:
            continue
        mid = str(message.get("id") or record_id(text))
        rows.append((_when(message.get("create_time")), mid, role, text))
    rows.sort(key=lambda item: (item[0], item[1]))
    return [(mid, role, text) for _when_value, mid, role, text in rows]


def _role_text(message: dict) -> tuple[str, str]:
    author = message.get("author")
    if isinstance(author, dict):
        role = str(author.get("role") or "")
    else:
        role = str(message.get("role") or "")
    content = message.get("content")
    if isinstance(content, dict):
        parts = content.get("parts") or []
        return role, "\n".join(str(part) for part in parts if isinstance(part, str))
    if isinstance(content, str):
        return role, content
    return role, str(message.get("text") or "")


def _when(value: object) -> float:
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _load_json(path: Path) -> object:
    raw = _read_conversations(path)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _read_conversations(path: Path) -> bytes | None:
    if path.is_file() and path.name == "conversations.json":
        return _read_file(path)
    if path.is_dir():
        target = path / "conversations.json"
        return _read_file(target) if target.is_file() else None
    if path.is_file() and path.suffix.lower() == ".zip":
        try:
            with zipfile.ZipFile(path) as archive:
                for info in archive.infolist():
                    if Path(info.filename).name != "conversations.json":
                        continue
                    if info.file_size > _MAX_JSON:
                        return None
                    return archive.read(info)
        except (OSError, zipfile.BadZipFile):
            return None
    return None


def _read_file(path: Path) -> bytes | None:
    try:
        if path.stat().st_size > _MAX_JSON:
            return None
        return path.read_bytes()
    except OSError:
        return None


def _zip_has(path: Path, filename: str) -> bool:
    try:
        with zipfile.ZipFile(path) as archive:
            return any(Path(info.filename).name == filename for info in archive.infolist())
    except (OSError, zipfile.BadZipFile):
        return False
