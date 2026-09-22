"""Slack export zip or folder. Quotas apply. The export is not copied into git."""

from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from dossier.fetch.snippet import record_from_hit
from dossier.identity import configured_slack_user_ids, resolve_speaker_names
from dossier.lenses import infer_kind, infer_lenses, infer_org, infer_skills, primary_lens
from dossier.seekers.hits import Hit, merge_hits
from dossier.seekers.quota import apply_quotas
from dossier.store import Corpus

_SKIP = {
    "users.json",
    "channels.json",
    "dms.json",
    "mpims.json",
    "groups.json",
    "integration_logs.json",
    "canvases.json",
    "file_conversations.json",
    "huddle_transcripts.json",
}
_MAX_MEMBER = 20_000_000


def is_slack_export(path: Path) -> bool:
    if path.is_dir():
        return (path / "users.json").is_file()
    if path.is_file() and path.suffix.lower() == ".zip":
        return _zip_has(path, "users.json")
    return False


def load_slack_export(path: Path, corpus: Corpus) -> None:
    users = _users(path)
    wanted = _wanted_ids(users)
    if not wanted:
        return
    hits: list[Hit] = []
    bodies: dict[str, str] = {}
    for name, payload in _json_members(path):
        if Path(name).name in _SKIP:
            continue
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, list):
            continue
        channel = Path(name).parent.name or Path(name).stem
        for msg in data:
            hit, body = _message(msg, channel, wanted)
            if hit is None or not body:
                continue
            hits.append(hit)
            bodies[hit.uri] = body
    for hit in apply_quotas(merge_hits(hits)):
        corpus.upsert_record(record_from_hit(hit, bodies.get(hit.uri, hit.preview)))


def _message(msg: object, channel: str, wanted: set[str]) -> tuple[Hit | None, str]:
    if not isinstance(msg, dict):
        return None, ""
    if msg.get("subtype") in {"bot_message", "channel_join", "channel_leave"}:
        return None, ""
    user = str(msg.get("user") or "")
    if user not in wanted:
        return None, ""
    text = str(msg.get("text") or "").strip()
    if len(text) <= 40:
        return None, ""
    ts = str(msg.get("ts") or "")
    if not ts:
        return None, ""
    title = text.split("\n", 1)[0][:160]
    artifacts = _files(msg)
    kind = infer_kind(channel=channel, subject=title, artifacts=artifacts)
    skills = infer_skills(channel, title, text)
    lenses = infer_lenses(kind=kind, artifacts=artifacts, authored=True, skills=skills)
    hit = Hit(
        source="slack",
        uri=f"slack://{channel}/{ts}",
        title=title,
        preview=text[:240],
        year=_year(ts),
        org=infer_org(source="slack", channel=channel),
        kind=kind,
        lenses=lenses,
        primary_lens=primary_lens(lenses),
        artifacts=artifacts,
        people=(user,),
        skills=skills,
        score=min(len(text), 400) / 10,
        hunts=("export",),
        fetch_body=True,
        channel_id=channel,
        ts=ts,
    )
    return hit, text


def _files(msg: dict) -> tuple[str, ...]:
    raw = msg.get("files") or []
    if not isinstance(raw, list):
        return ()
    return tuple(
        str(item["name"])
        for item in raw
        if isinstance(item, dict) and item.get("name")
    )


def _year(ts: str) -> int:
    try:
        return datetime.fromtimestamp(float(ts), UTC).year
    except (TypeError, ValueError, OSError):
        return 0


def _wanted_ids(users: list[dict]) -> set[str]:
    by_id = {str(user.get("id") or ""): user for user in users if user.get("id")}
    configured = configured_slack_user_ids()
    if configured:
        wanted: set[str] = set()
        for token in configured:
            if token in by_id:
                wanted.add(token)
                continue
            needle = token.casefold()
            for user_id, user in by_id.items():
                if any(needle in name.casefold() for name in _names(user)):
                    wanted.add(user_id)
        return wanted
    names = tuple(name.casefold() for name in resolve_speaker_names())
    if not names:
        return set()
    return {
        user_id
        for user_id, user in by_id.items()
        if any(needle in label.casefold() for needle in names for label in _names(user))
    }


def _names(user: dict) -> tuple[str, ...]:
    profile = user.get("profile") if isinstance(user.get("profile"), dict) else {}
    values = (
        user.get("real_name"),
        user.get("name"),
        profile.get("display_name"),
        profile.get("real_name"),
    )
    return tuple(str(value) for value in values if value)


def _users(path: Path) -> list[dict]:
    raw = _read_named(path, "users.json")
    if raw is None:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _json_members(path: Path):
    if path.is_dir():
        for child in sorted(path.rglob("*.json")):
            try:
                if child.stat().st_size > _MAX_MEMBER:
                    continue
                yield child.relative_to(path).as_posix(), child.read_bytes()
            except OSError:
                continue
        return
    if not path.is_file() or path.suffix.lower() != ".zip":
        return
    try:
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                if info.is_dir() or info.file_size > _MAX_MEMBER:
                    continue
                if info.filename.endswith(".json"):
                    yield info.filename, archive.read(info)
    except (OSError, zipfile.BadZipFile):
        return


def _read_named(path: Path, filename: str) -> bytes | None:
    if path.is_dir():
        target = path / filename
        if not target.is_file():
            return None
        try:
            return target.read_bytes()
        except OSError:
            return None
    if path.is_file() and path.suffix.lower() == ".zip":
        try:
            with zipfile.ZipFile(path) as archive:
                for info in archive.infolist():
                    if Path(info.filename).name == filename and info.file_size <= _MAX_MEMBER:
                        return archive.read(info)
        except (OSError, zipfile.BadZipFile):
            return None
    return None


def _zip_has(path: Path, filename: str) -> bool:
    try:
        with zipfile.ZipFile(path) as archive:
            return any(Path(info.filename).name == filename for info in archive.infolist())
    except (OSError, zipfile.BadZipFile):
        return False
