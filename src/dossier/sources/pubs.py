"""Own-pubs retrieve. Does not embed hoops/ocean. Ingest stays off until confirmed."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

import httpx

from dossier.paths import pubs_url
from dossier.store import Corpus, Record
from dossier.util import record_id


class PubsRetriever(Protocol):
    def ping(self) -> bool: ...

    def records(self) -> list[Record]: ...


class StubPubsRetriever:
    """Tests only. Never pointed at a live Zotero library."""

    def __init__(self, items: list[Record] | None = None) -> None:
        self._items = list(items or [])

    def ping(self) -> bool:
        return True

    def records(self) -> list[Record]:
        return list(self._items)


class HttpPubsRetriever:
    """Ping zotero-rag-pubs. Returns no records until ingest is confirmed."""

    def __init__(self, url: str | None = None) -> None:
        self.url = (url or pubs_url()).rstrip("/")

    def ping(self) -> bool:
        try:
            with httpx.Client(timeout=2.0) as client:
                resp = client.get(self.url)
            return resp.status_code < 500
        except httpx.HTTPError:
            return False

    def records(self) -> list[Record]:
        return []


class PubsSource:
    name = "pubs"

    def __init__(self, retriever: PubsRetriever | None = None) -> None:
        self.retriever = retriever or HttpPubsRetriever()

    def detect(self, path: Path) -> bool:
        if _is_pubs_fixture(path):
            return True
        return self.retriever.ping()

    def load(self, path: Path, corpus: Corpus) -> None:
        if _is_pubs_fixture(path):
            for rec in _records_from_fixture(path):
                corpus.upsert_record(rec)
            return
        for rec in self.retriever.records():
            corpus.upsert_record(rec)

    def tables(self) -> list[str]:
        return ["pubs.records"]


def _is_pubs_fixture(path: Path) -> bool:
    if not path.is_file() or path.suffix.lower() != ".json":
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(data, dict) and "records" in data


def _records_from_fixture(path: Path) -> list[Record]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[Record] = []
    for item in data.get("records") or []:
        if not isinstance(item, dict):
            continue
        uri = str(item.get("uri") or "").strip()
        text = str(item.get("text") or "").strip()
        if not uri or not text:
            continue
        title = str(item.get("title") or uri)
        out.append(
            Record(
                id=record_id(uri),
                source="pubs",
                uri=uri,
                title=title,
                text=text,
                table="pubs.records",
            )
        )
    return out
