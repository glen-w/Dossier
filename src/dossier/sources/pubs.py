"""Own-pubs retrieve. Does not embed hoops/ocean. Live ingest stays gated."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

import httpx

from dossier.paths import pubs_seed, pubs_top_k, pubs_url
from dossier.store import Corpus, Record
from dossier.util import record_id


class PubsRetriever(Protocol):
    def ping(self) -> bool: ...

    def records(self) -> list[Record]: ...

    def search(self, query: str, *, top_k: int = 5) -> list[Record]: ...


class StubPubsRetriever:
    """Tests only. Never pointed at a live Zotero library."""

    def __init__(self, items: list[Record] | None = None) -> None:
        self._items = list(items or [])

    def ping(self) -> bool:
        return True

    def records(self) -> list[Record]:
        return list(self._items)

    def search(self, query: str, *, top_k: int = 5) -> list[Record]:
        from dossier.cards import content_token_set, content_tokens

        cap = max(1, top_k)
        tokens = content_tokens(query)
        if not tokens:
            return list(self._items)[:cap]
        out: list[Record] = []
        for rec in self._items:
            blob = content_token_set(f"{rec.title}\n{rec.text}")
            if any(token in blob for token in tokens):
                out.append(rec)
            if len(out) >= cap:
                break
        return out


class HttpPubsRetriever:
    """HTTP client for zotero-rag-pubs.

    Contract: ``POST {url}/search`` with ``{"query", "top_k"}`` returns
    ``{"hits": [{"uri","title","text", ...}]}``. Ping tries ``/health`` then ``/``.
    Live ingest stays off until the collection name and scope are confirmed.
    """

    def __init__(self, url: str | None = None) -> None:
        self.url = (url or pubs_url()).rstrip("/")

    def ping(self) -> bool:
        for path in ("/health", "/"):
            try:
                with httpx.Client(timeout=2.0) as client:
                    resp = client.get(f"{self.url}{path}")
                if resp.status_code < 500:
                    return True
            except httpx.HTTPError:
                continue
        return False

    def records(self) -> list[Record]:
        return self.search(pubs_seed(), top_k=pubs_top_k())

    def search(self, query: str, *, top_k: int = 5) -> list[Record]:
        text = query.strip()
        if not text:
            return []
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{self.url}/search",
                    json={"query": text, "top_k": max(1, top_k)},
                )
            if resp.status_code >= 400:
                return []
            data = resp.json()
        except (httpx.HTTPError, json.JSONDecodeError, ValueError):
            return []
        if not isinstance(data, dict):
            return []
        hits = data.get("hits") or []
        out: list[Record] = []
        for item in hits:
            if not isinstance(item, dict):
                continue
            uri = str(item.get("uri") or item.get("url") or "").strip()
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


def optional_pubs_hits(question: str, *, enabled: bool, limit: int) -> list:
    """Hits for one ask. Nothing is written to the corpus."""
    from dossier.ask import Hit

    if not enabled or not question.strip():
        return []
    rows = HttpPubsRetriever().search(question, top_k=max(1, min(int(limit), 8)))
    return [
        Hit(uri=rec.uri, title=rec.title, text=rec.text, score=1)
        for rec in rows
        if rec.uri and rec.text.strip()
    ]


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
