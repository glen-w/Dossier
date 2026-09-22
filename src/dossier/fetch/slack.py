"""Slack snippet fetch: selected rows plus tight thread context. No channel dump."""

from __future__ import annotations

from collections.abc import Sequence

import duckdb

from dossier.identity import configured_slack_user_ids
from dossier.seekers.hits import Hit
from dossier.sources.warehouse import has_table

TEXT_CAP = 8000
THREAD_REPLIES = 8


def fetch_slack_body(
    conn: duckdb.DuckDBPyConnection, hit: Hit, glen_ids: Sequence[str] | None = None
) -> str:
    if not hit.channel_id or not hit.ts:
        return hit.preview
    ids = tuple(glen_ids or configured_slack_user_ids())
    row = conn.execute(
        """
        SELECT coalesce(text, ''), coalesce(thread_ts, ts),
               coalesce(is_thread_root, FALSE), coalesce(is_reply, FALSE),
               coalesce(user_name, '')
        FROM slack.messages
        WHERE channel_id = ? AND ts = ?
        """,
        [hit.channel_id, hit.ts],
    ).fetchone()
    if row is None:
        return hit.preview
    text, thread_ts, is_root, is_reply, user_name = row
    chunks = [f"{user_name}: {text}".strip() if user_name else str(text)]
    if thread_ts and (is_root or is_reply) and has_table(conn, "slack.messages"):
        chunks.extend(_thread_context(conn, hit.channel_id, str(thread_ts), ids, hit.ts))
    if hit.artifacts:
        chunks.append("Files: " + ", ".join(hit.artifacts))
    body = "\n".join(c for c in chunks if c).strip()
    return (body or hit.preview)[:TEXT_CAP]


def _thread_context(
    conn: duckdb.DuckDBPyConnection,
    channel_id: str,
    thread_ts: str,
    glen_ids: Sequence[str],
    skip_ts: str,
) -> list[str]:
    ph = ",".join("?" for _ in glen_ids)
    root = conn.execute(
        """
        SELECT coalesce(user_name, ''), coalesce(text, ''), ts
        FROM slack.messages
        WHERE channel_id = ? AND ts = ?
        """,
        [channel_id, thread_ts],
    ).fetchone()
    lines: list[str] = []
    if root and str(root[2]) != skip_ts:
        who, body, _ = root
        lines.append(f"Thread root {who}: {body}".strip())
    if glen_ids:
        replies = conn.execute(
            f"""
            SELECT coalesce(user_name, ''), coalesce(text, '')
            FROM slack.messages
            WHERE channel_id = ? AND thread_ts = ? AND ts <> ?
              AND user_id IN ({ph})
            ORDER BY ts
            LIMIT ?
            """,
            [channel_id, thread_ts, skip_ts, *list(glen_ids), THREAD_REPLIES],
        ).fetchall()
        for who, body in replies:
            lines.append(f"{who}: {body}".strip())
    return lines
