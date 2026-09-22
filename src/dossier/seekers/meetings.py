"""TranscriptX library hunt. Named-speaker meetings only. Not a library import."""

from __future__ import annotations

import json
import re
from pathlib import Path

from dossier.identity import resolve_speaker_names
from dossier.lenses import infer_kind, infer_lenses, infer_skills, primary_lens
from dossier.lists import meetings_dirs, meetings_solo
from dossier.seekers.hits import Hit

TEXT_CAP = 8000
PREVIEW_CAP = 240
MAX_BYTES = 8_000_000
PAIR_CAP = 2000
_CONTRIB_RE = re.compile(
    r"\b(draft\w*|edit\w*|coordinat\w*|review\w*|taught|teach\w*|conven\w*|"
    r"facilitat\w*|wrote|written|led|lead\w*|chair\w*|present\w*)\b",
    re.I,
)
_ORG_RE = (
    ("REN21", re.compile(r"\bren21\b|\bgsr\b|\bgfr\b", re.I)),
    ("IDDRI", re.compile(r"\biddri\b|\bsciencespo\b", re.I)),
    ("Oceana", re.compile(r"\boceana\b", re.I)),
)


def hunt_meetings(root: Path, names: tuple[str, ...] | None = None) -> list[Hit]:
    who = names if names is not None else resolve_speaker_names()
    if not who:
        return []
    hits: list[Hit] = []
    for transcript, sidecar in iter_meeting_pairs(root)[:PAIR_CAP]:
        hit = _hit_for(root, transcript, sidecar, who)
        if hit is not None:
            hits.append(hit)
    return hits


def iter_meeting_pairs(root: Path) -> list[tuple[Path, Path]]:
    """Canonical transcript plus its speaker-map sidecar. Library layout first."""
    if not root.exists():
        return []
    base = root if root.is_dir() else root.parent
    skipped = meetings_dirs()
    if root.is_file() and root.suffix.lower() == ".json":
        if root.name.endswith(".speaker_map.json"):
            return []
        if base.name.casefold() in skipped or base.name.startswith("."):
            return []
        if _dir_skipped(root, base, skipped):
            return []
        sidecar = root.with_name(f"{root.stem}.speaker_map.json")
        if sidecar.is_file() and _inside(base, root) and not _rejected(root):
            return [(root, sidecar)]
        return []
    maps_root = base / "metadata" / "speaker_maps"
    if maps_root.is_dir():
        pairs: list[tuple[Path, Path]] = []
        for sidecar in sorted(maps_root.rglob("*.speaker_map.json")):
            rel = sidecar.relative_to(maps_root)
            transcript = base / rel.parent / f"{sidecar.name[: -len('.speaker_map.json')]}.json"
            if not transcript.is_file() or _rejected(transcript):
                continue
            if _dir_skipped(transcript, base, skipped):
                continue
            if not _inside(base, transcript) or not _inside(base, sidecar):
                continue
            pairs.append((transcript, sidecar))
        return pairs
    pairs = []
    for sidecar in sorted(base.rglob("*.speaker_map.json")):
        rel_parent = sidecar.relative_to(base).parts[:-1]
        if any(part.casefold() in skipped or part.startswith(".") for part in rel_parent):
            continue
        transcript = sidecar.with_name(f"{sidecar.name[: -len('.speaker_map.json')]}.json")
        if not transcript.is_file() or _rejected(transcript):
            continue
        if not _inside(base, transcript):
            continue
        pairs.append((transcript, sidecar))
    return pairs


def _dir_skipped(path: Path, base: Path, skipped: frozenset[str]) -> bool:
    try:
        parts = path.resolve().relative_to(base.resolve()).parts[:-1]
    except (OSError, ValueError):
        return False
    return any(part.casefold() in skipped or part.startswith(".") for part in parts)


def user_speech(doc: dict, sidecar: dict, names: tuple[str, ...]) -> str:
    user_ids, _others, labels = _speaker_sets(sidecar, names)
    blocked = _ignored_names(sidecar)
    if not user_ids and not labels:
        return ""
    parts: list[str] = []
    total = 0
    for segment in doc.get("segments") or []:
        if not isinstance(segment, dict):
            continue
        speaker = str(segment.get("speaker") or "")
        if not _segment_is_user(speaker, user_ids, names, blocked):
            continue
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        label = _label_for(speaker, labels, names)
        line = f"{label}: {text}" if label else text
        parts.append(line)
        total += len(line)
        if total >= TEXT_CAP:
            break
    return "\n".join(parts)[:TEXT_CAP]


def _hit_for(root: Path, transcript: Path, sidecar_path: Path, names: tuple[str, ...]) -> Hit | None:
    sidecar = _read_json(sidecar_path)
    doc = _read_json(transcript)
    if not sidecar or not doc:
        return None
    user_ids, others, labels = _speaker_sets(sidecar, names, doc)
    if not user_ids:
        return None
    speech = user_speech(doc, sidecar, names)
    if not speech.strip():
        return None
    stem = transcript.stem
    title = _title(stem)
    kind = infer_kind(folder=stem, subject=title)
    solo = meetings_solo()
    if not others and kind not in solo:
        return None
    skills = infer_skills(stem, title, speech[:PREVIEW_CAP])
    contrib = bool(_CONTRIB_RE.search(speech))
    lenses = infer_lenses(
        kind=kind,
        authored=True,
        coordinated=contrib,
        skills=skills,
    )
    year = _year(stem, doc)
    org = _org(f"{stem} {title}")
    people = tuple(name for name in labels.values() if name and not _name_matches(name, names))
    score = 30.0
    if others:
        score += 20
    if contrib:
        score += 25
    if kind in solo:
        score += 15
    if len(speech) >= 400:
        score += 10
    hunts = ("named-speaker", "contributions") if contrib else ("named-speaker",)
    rel = transcript.relative_to(root if root.is_dir() else root.parent).as_posix()
    uri_stem = transcript.relative_to(root if root.is_dir() else root.parent).with_suffix("")
    return Hit(
        source="meetings",
        uri=f"meetings://{uri_stem.as_posix()}",
        title=title or stem,
        preview=speech.replace("\n", " ")[:PREVIEW_CAP],
        year=year,
        org=org,
        kind=kind,
        lenses=lenses,
        primary_lens=primary_lens(lenses),
        artifacts=(),
        people=people[:12],
        skills=skills,
        score=score,
        hunts=hunts,
        fetch_body=True,
        folder_name=rel,
    )


def _speaker_sets(
    sidecar: dict,
    names: tuple[str, ...],
    doc: dict | None = None,
) -> tuple[set[str], set[str], dict[str, str]]:
    raw_map = sidecar.get("speaker_map") or {}
    if not isinstance(raw_map, dict):
        raw_map = {}
    ignored = {_norm_id(item) for item in (sidecar.get("ignored_speakers") or [])}
    labels: dict[str, str] = {}
    user_ids: set[str] = set()
    known: set[str] = set()
    for speaker_id, display in raw_map.items():
        nid = _norm_id(speaker_id)
        if not nid or nid in ignored:
            continue
        known.add(nid)
        name = str(display or "").strip()
        if not _effective(nid, name):
            continue
        labels[nid] = name
        if _name_matches(name, names):
            user_ids.add(nid)
    blocked = _ignored_names(sidecar)
    if doc is not None:
        for segment in doc.get("segments") or []:
            if not isinstance(segment, dict):
                continue
            raw = str(segment.get("speaker") or "")
            nid = _norm_id(raw)
            if not nid or nid in ignored or _segment_is_user(raw, user_ids, names, blocked):
                continue
            known.add(nid)
    others = known - user_ids
    return user_ids, others, labels


def _ignored_names(sidecar: dict) -> set[str]:
    raw_map = sidecar.get("speaker_map") or {}
    if not isinstance(raw_map, dict):
        return set()
    ignored = {_norm_id(item) for item in (sidecar.get("ignored_speakers") or [])}
    blocked: set[str] = set()
    for speaker_id, display in raw_map.items():
        if _norm_id(speaker_id) not in ignored:
            continue
        name = " ".join(str(display or "").casefold().split())
        if name:
            blocked.add(name)
    return blocked


def _segment_is_user(
    speaker: str,
    user_ids: set[str],
    names: tuple[str, ...],
    ignored_names: set[str] | None = None,
) -> bool:
    text = str(speaker or "").strip()
    folded = " ".join(text.casefold().split())
    if ignored_names and folded in ignored_names:
        return False
    nid = _norm_id(speaker)
    if nid and nid in user_ids:
        return True
    if not text or re.fullmatch(r"SPEAKER_\d+", text.upper()):
        return False
    return _name_matches(text, names)


def _label_for(speaker: str, labels: dict[str, str], names: tuple[str, ...]) -> str:
    nid = _norm_id(speaker)
    if nid in labels:
        return labels[nid]
    text = str(speaker or "").strip()
    if text and _name_matches(text, names) and not re.fullmatch(r"SPEAKER_\d+", text.upper()):
        return text
    return ""


def _norm_id(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    upper = text.upper()
    if upper.isdigit():
        return f"SPEAKER_{int(upper):02d}"
    if upper.startswith("SPEAKER_") and upper[8:].isdigit():
        return f"SPEAKER_{int(upper[8:]):02d}"
    return upper


def _effective(speaker_id: str, display: str) -> bool:
    name = display.strip()
    if not name:
        return False
    if _norm_id(name) == _norm_id(speaker_id):
        return False
    if re.fullmatch(r"SPEAKER_\d+", name.upper()):
        return False
    return True


def _name_matches(display: str, names: tuple[str, ...]) -> bool:
    blob = " ".join(display.casefold().split())
    if not blob:
        return False
    for name in names:
        needle = " ".join(name.casefold().split())
        if not needle:
            continue
        if re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", blob):
            return True
    return False


def _title(stem: str) -> str:
    text = re.sub(r" \(conflicted copy[^)]*\)", "", stem, flags=re.I)
    text = re.sub(r"__inbox$", "", text)
    text = re.sub(r"^\d{6,}(?:-\d+)?[-_ ]*", "", text)
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text or stem


def _year(stem: str, doc: dict) -> int:
    match = re.match(r"^(20\d{2})\d{4}", stem)
    if match:
        return int(match.group(1))
    match = re.match(r"^(\d{2})(\d{2})(\d{2})", stem)
    if match:
        yy = int(match.group(1))
        if 15 <= yy <= 39:
            return 2000 + yy
    source = doc.get("source") if isinstance(doc.get("source"), dict) else {}
    imported = str(source.get("imported_at") or "")
    match = re.match(r"^(20\d{2})", imported)
    return int(match.group(1)) if match else 0


def _org(blob: str) -> str:
    for name, pattern in _ORG_RE:
        if pattern.search(blob):
            return name
    return ""


def _read_json(path: Path) -> dict:
    try:
        if path.stat().st_size > MAX_BYTES:
            return {}
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _rejected(path: Path) -> bool:
    name = path.name
    if "conflicted copy" in name.lower():
        return True
    if name.endswith("__inbox.json"):
        base = path.with_name(name[: -len("__inbox.json")] + ".json")
        if base.is_file():
            return True
    return False


def _inside(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True
