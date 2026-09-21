"""Ranked seeker hits. Citation-ready before a body is fetched."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol, runtime_checkable

from dossier.lenses import primary_lens


@runtime_checkable
class Seeker(Protocol):
    """One hunt. Wired from Source.load. Not discovered from a plugins folder."""

    def hunt(self, conn: object) -> list[Hit]:
        ...


@dataclass(frozen=True)
class Hit:
    source: str
    uri: str
    title: str
    preview: str
    year: int
    org: str
    kind: str
    lenses: tuple[str, ...]
    primary_lens: str
    artifacts: tuple[str, ...]
    people: tuple[str, ...]
    skills: tuple[str, ...]
    score: float
    hunts: tuple[str, ...]
    fetch_body: bool
    channel_id: str = ""
    ts: str = ""
    account_key: str = ""
    folder_name: str = ""
    header_message_id: str = ""


def merge_hits(hits: list[Hit]) -> list[Hit]:
    by_uri: dict[str, Hit] = {}
    for hit in hits:
        prev = by_uri.get(hit.uri)
        if prev is None:
            by_uri[hit.uri] = hit
            continue
        lenses = tuple(dict.fromkeys((*prev.lenses, *hit.lenses)))
        richer = prev if prev.score >= hit.score else hit
        by_uri[hit.uri] = replace(
            richer,
            title=prev.title or hit.title,
            preview=prev.preview if len(prev.preview) >= len(hit.preview) else hit.preview,
            year=prev.year or hit.year,
            org=prev.org or hit.org,
            kind=prev.kind if prev.kind != "other" else hit.kind,
            lenses=lenses,
            primary_lens=primary_lens(lenses),
            artifacts=tuple(dict.fromkeys((*prev.artifacts, *hit.artifacts))),
            people=tuple(dict.fromkeys((*prev.people, *hit.people))),
            skills=tuple(dict.fromkeys((*prev.skills, *hit.skills))),
            score=max(prev.score, hit.score),
            hunts=tuple(dict.fromkeys((*prev.hunts, *hit.hunts))),
            fetch_body=prev.fetch_body and hit.fetch_body,
            channel_id=prev.channel_id or hit.channel_id,
            ts=prev.ts or hit.ts,
            account_key=prev.account_key or hit.account_key,
            folder_name=prev.folder_name or hit.folder_name,
            header_message_id=prev.header_message_id or hit.header_message_id,
        )
    return list(by_uri.values())
