"""Slack workspace export already in the data_dumps warehouse. Seek, do not re-ingest."""

from __future__ import annotations

from pathlib import Path

from dossier.fetch.slack import fetch_slack_body
from dossier.fetch.snippet import record_from_hit
from dossier.seekers.quota import apply_quotas
from dossier.seekers.hits import merge_hits
from dossier.seekers.slack import hunt_slack, resolve_slack_user_ids
from dossier.sources.warehouse import connect_readonly, has_table, resolve_warehouse
from dossier.store import Corpus

SLACK_TABLES = [
    "slack.users",
    "slack.channels",
    "slack.messages",
    "slack.reactions",
    "slack.mentions",
    "slack.files",
]


class SlackSource:
    name = "slack"

    def detect(self, path: Path) -> bool:
        db = resolve_warehouse(path)
        if not db.is_file():
            return False
        try:
            conn = connect_readonly(path)
        except Exception:
            return False
        try:
            return has_table(conn, "slack.messages")
        finally:
            conn.close()

    def load(self, path: Path, corpus: Corpus) -> None:
        conn = connect_readonly(path)
        try:
            hits = apply_quotas(merge_hits(hunt_slack(conn)))
            glen_ids = resolve_slack_user_ids(conn)
            for hit in hits:
                body = fetch_slack_body(conn, hit, glen_ids)
                corpus.upsert_record(record_from_hit(hit, body))
        finally:
            conn.close()

    def tables(self) -> list[str]:
        return list(SLACK_TABLES)
