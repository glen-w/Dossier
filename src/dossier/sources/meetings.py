"""TranscriptX meetings. Seek turns where you are a named speaker."""

from __future__ import annotations

from pathlib import Path

from dossier.fetch.meetings import fetch_meeting_body
from dossier.fetch.snippet import record_from_hit
from dossier.identity import resolve_speaker_names
from dossier.seekers.hits import merge_hits
from dossier.seekers.meetings import hunt_meetings, iter_meeting_pairs
from dossier.seekers.quota import apply_quotas
from dossier.store import Corpus


class MeetingsSource:
    name = "meetings"

    def detect(self, path: Path) -> bool:
        return bool(iter_meeting_pairs(path))

    def load(self, path: Path, corpus: Corpus) -> None:
        names = resolve_speaker_names()
        hits = apply_quotas(merge_hits(hunt_meetings(path, names)))
        for hit in hits:
            body = fetch_meeting_body(path, hit, names) if hit.fetch_body else ""
            corpus.upsert_record(record_from_hit(hit, body))

    def tables(self) -> list[str]:
        return ["meetings.hits"]
