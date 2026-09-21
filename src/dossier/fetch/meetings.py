"""Fetch the named speaker's turns from one TranscriptX meeting. Not the room."""

from __future__ import annotations

from pathlib import Path

from dossier.identity import resolve_speaker_names
from dossier.seekers.hits import Hit
from dossier.seekers.meetings import _read_json, user_speech


def fetch_meeting_body(
    root: Path,
    hit: Hit,
    names: tuple[str, ...] | None = None,
) -> str:
    who = names if names is not None else resolve_speaker_names()
    if not hit.folder_name or not who:
        return hit.preview
    base = root if root.is_dir() else root.parent
    transcript = base / hit.folder_name
    if not transcript.is_file():
        return hit.preview
    sidecar = _sidecar_for(base, transcript)
    doc = _read_json(transcript)
    side = _read_json(sidecar) if sidecar is not None else {}
    speech = user_speech(doc, side, who)
    return speech or hit.preview


def _sidecar_for(root: Path, transcript: Path) -> Path | None:
    mirrored = root / "metadata" / "speaker_maps" / transcript.relative_to(root)
    mirrored = mirrored.with_name(f"{transcript.stem}.speaker_map.json")
    if mirrored.is_file():
        return mirrored
    colocated = transcript.with_name(f"{transcript.stem}.speaker_map.json")
    if colocated.is_file():
        return colocated
    return None
