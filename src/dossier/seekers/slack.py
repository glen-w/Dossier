"""Slack warehouse hunts. Glen-touched rows only — not the full workspace."""

from __future__ import annotations

from collections.abc import Sequence

import duckdb

from dossier.identity import configured_slack_user_ids, resolve_speaker_names
from dossier.lenses import infer_kind, infer_lenses, infer_org, infer_skills, primary_lens
from dossier.lists import phrase_blocked, phrase_pattern, slack_activity, slack_exclude
from dossier.seekers.hits import Hit
from dossier.sources.warehouse import has_table

LONG_TEXT = 400
HOT_REPLY = 3
HOT_REACT = 3
SAMPLE_MIN_LEN = 80


def resolve_slack_user_ids(conn: duckdb.DuckDBPyConnection) -> tuple[str, ...]:
    configured = configured_slack_user_ids()
    if configured:
        return configured
    names = resolve_speaker_names()
    if not names or not has_table(conn, "slack.users"):
        return ()
    clauses: list[str] = []
    params: list[str] = []
    for name in names:
        needle = f"%{name.casefold()}%"
        clauses.append(
            "("
            "lower(coalesce(real_name, '')) LIKE ? "
            "OR lower(coalesce(handle, '')) LIKE ? "
            "OR lower(coalesce(display_name, '')) LIKE ?"
            ")"
        )
        params.extend((needle, needle, needle))
    rows = conn.execute(
        f"""
        SELECT user_id FROM slack.users
        WHERE is_bot IS NOT TRUE
          AND ({" OR ".join(clauses)})
        """,
        params,
    ).fetchall()
    return tuple(str(r[0]) for r in rows if r and r[0])


def hunt_slack(conn: duckdb.DuckDBPyConnection) -> list[Hit]:
    if not has_table(conn, "slack.messages") or not has_table(conn, "slack.channels"):
        return []
    ids = resolve_slack_user_ids(conn)
    if not ids:
        return []
    hits: list[Hit] = []
    hits.extend(_hunt_glen_files(conn, ids))
    hits.extend(_hunt_hot_threads(conn, ids))
    hits.extend(_hunt_long_messages(conn, ids))
    hits.extend(_hunt_file_conversations(conn, ids))
    if has_table(conn, "slack.mentions"):
        hits.extend(_hunt_mentioned_files(conn, ids))
    hits.extend(_hunt_thread_files(conn, ids))
    hits.extend(_hunt_channel_samples(conn, ids))
    return hits


def _channel_blocked(name: str) -> bool:
    return phrase_blocked(slack_exclude(), name)


def _in_clause(ids: Sequence[str]) -> tuple[str, list[str]]:
    return ",".join("?" for _ in ids), list(ids)


def _year(value: object) -> int:
    try:
        return int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0


def _split_agg(raw: object) -> tuple[str, ...]:
    if raw is None:
        return ()
    text = str(raw).strip()
    if not text:
        return ()
    return tuple(p.strip() for p in text.split(";") if p.strip())


def _hit(
    *,
    channel_id: str,
    ts: str,
    title: str,
    preview: str,
    year: int,
    channel: str,
    artifacts: tuple[str, ...],
    people: tuple[str, ...],
    score: float,
    hunt: str,
    authored: bool,
    coordinated: bool,
) -> Hit:
    kind = infer_kind(channel=channel, subject=title, artifacts=artifacts)
    skills = infer_skills(channel, title, " ".join(artifacts), preview)
    lenses = infer_lenses(
        kind=kind,
        artifacts=artifacts,
        authored=authored,
        coordinated=coordinated,
        skills=skills,
    )
    return Hit(
        source="slack",
        uri=f"slack://{channel_id}/{ts}",
        title=title,
        preview=preview,
        year=year,
        org=infer_org(source="slack", channel=channel),
        kind=kind,
        lenses=lenses,
        primary_lens=primary_lens(lenses),
        artifacts=artifacts,
        people=people,
        skills=skills,
        score=score,
        hunts=(hunt,),
        fetch_body=True,
        channel_id=str(channel_id),
        ts=str(ts),
    )


def _hunt_glen_files(conn: duckdb.DuckDBPyConnection, ids: Sequence[str]) -> list[Hit]:
    ph, params = _in_clause(ids)
    has_files = has_table(conn, "slack.files")
    if has_files:
        sql = f"""
            SELECT m.channel_id, m.ts, coalesce(c.name, m.channel_name) AS channel_name,
                   m.user_name, left(coalesce(m.text, ''), 240) AS preview,
                   m.year, m.reply_count, m.n_reactions, m.n_files,
                   string_agg(DISTINCT f.name, '; ') AS file_names
            FROM slack.messages m
            JOIN slack.channels c ON c.channel_id = m.channel_id
            LEFT JOIN slack.files f ON f.channel_id = m.channel_id AND f.ts = m.ts
            WHERE m.user_id IN ({ph}) AND coalesce(m.is_bot, FALSE) IS NOT TRUE
              AND coalesce(m.n_files, 0) > 0
            GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9
            """
    else:
        sql = f"""
            SELECT m.channel_id, m.ts, coalesce(c.name, m.channel_name) AS channel_name,
                   m.user_name, left(coalesce(m.text, ''), 240) AS preview,
                   m.year, m.reply_count, m.n_reactions, m.n_files,
                   CAST(NULL AS VARCHAR) AS file_names
            FROM slack.messages m
            JOIN slack.channels c ON c.channel_id = m.channel_id
            WHERE m.user_id IN ({ph}) AND coalesce(m.is_bot, FALSE) IS NOT TRUE
              AND coalesce(m.n_files, 0) > 0
            """
    rows = conn.execute(sql, params).fetchall()
    out: list[Hit] = []
    for row in rows:
        if _channel_blocked(str(row[2] or "")):
            continue
        artifacts = _split_agg(row[9])
        score = 50 + int(row[6] or 0) + int(row[7] or 0)
        title = artifacts[0] if artifacts else (row[4] or row[2] or "file")
        out.append(
            _hit(
                channel_id=str(row[0]),
                ts=str(row[1]),
                title=str(title)[:160],
                preview=str(row[4] or ""),
                year=_year(row[5]),
                channel=str(row[2] or ""),
                artifacts=artifacts,
                people=tuple(p for p in (str(row[3] or ""),) if p),
                score=score,
                hunt="glen_file",
                authored=True,
                coordinated=False,
            )
        )
    return out


def _hunt_hot_threads(conn: duckdb.DuckDBPyConnection, ids: Sequence[str]) -> list[Hit]:
    ph, params = _in_clause(ids)
    rows = conn.execute(
        f"""
        SELECT m.channel_id, m.ts, coalesce(c.name, m.channel_name) AS channel_name,
               m.user_name, left(coalesce(m.text, ''), 240) AS preview,
               m.year, m.reply_count, m.n_reactions
        FROM slack.messages m
        JOIN slack.channels c ON c.channel_id = m.channel_id
        WHERE m.user_id IN ({ph}) AND coalesce(m.is_bot, FALSE) IS NOT TRUE
          AND coalesce(m.is_thread_root, FALSE)
          AND (coalesce(m.reply_count, 0) >= ? OR coalesce(m.n_reactions, 0) >= ?)
        """,
        params + [HOT_REPLY, HOT_REACT],
    ).fetchall()
    out: list[Hit] = []
    for row in rows:
        if _channel_blocked(str(row[2] or "")):
            continue
        score = 40 + int(row[6] or 0) + int(row[7] or 0)
        out.append(
            _hit(
                channel_id=str(row[0]),
                ts=str(row[1]),
                title=str(row[4] or row[2] or "thread")[:160],
                preview=str(row[4] or ""),
                year=_year(row[5]),
                channel=str(row[2] or ""),
                artifacts=(),
                people=tuple(p for p in (str(row[3] or ""),) if p),
                score=score,
                hunt="hot_thread",
                authored=True,
                coordinated=True,
            )
        )
    return out


def _hunt_long_messages(conn: duckdb.DuckDBPyConnection, ids: Sequence[str]) -> list[Hit]:
    ph, params = _in_clause(ids)
    rows = conn.execute(
        f"""
        SELECT m.channel_id, m.ts, coalesce(c.name, m.channel_name) AS channel_name,
               m.user_name, left(coalesce(m.text, ''), 240) AS preview,
               m.year, m.text_len
        FROM slack.messages m
        JOIN slack.channels c ON c.channel_id = m.channel_id
        WHERE m.user_id IN ({ph}) AND coalesce(m.is_bot, FALSE) IS NOT TRUE
          AND coalesce(m.text_len, 0) >= ?
          AND coalesce(m.n_files, 0) = 0
        """,
        params + [LONG_TEXT],
    ).fetchall()
    out: list[Hit] = []
    for row in rows:
        if _channel_blocked(str(row[2] or "")):
            continue
        out.append(
            _hit(
                channel_id=str(row[0]),
                ts=str(row[1]),
                title=str(row[4] or row[2] or "note")[:160],
                preview=str(row[4] or ""),
                year=_year(row[5]),
                channel=str(row[2] or ""),
                artifacts=(),
                people=tuple(p for p in (str(row[3] or ""),) if p),
                score=20 + min(int(row[6] or 0) / 100, 20),
                hunt="long_message",
                authored=True,
                coordinated=False,
            )
        )
    return out


def _hunt_file_conversations(
    conn: duckdb.DuckDBPyConnection, ids: Sequence[str]
) -> list[Hit]:
    ph, params = _in_clause(ids)
    rows = conn.execute(
        f"""
        SELECT m.channel_id, m.ts, coalesce(c.name, m.channel_name) AS channel_name,
               m.user_name, left(coalesce(m.text, ''), 240) AS preview, m.year
        FROM slack.messages m
        JOIN slack.channels c ON c.channel_id = m.channel_id
        WHERE m.user_id IN ({ph}) AND coalesce(m.is_bot, FALSE) IS NOT TRUE
          AND c.kind = 'file_conversation'
        """,
        params,
    ).fetchall()
    out: list[Hit] = []
    for row in rows:
        if _channel_blocked(str(row[2] or "")):
            continue
        channel = str(row[2] or "")
        out.append(
            _hit(
                channel_id=str(row[0]),
                ts=str(row[1]),
                title=channel or str(row[4] or "file conversation")[:160],
                preview=str(row[4] or ""),
                year=_year(row[5]),
                channel=channel,
                artifacts=(channel,) if channel else (),
                people=tuple(p for p in (str(row[3] or ""),) if p),
                score=35,
                hunt="file_conversation",
                authored=True,
                coordinated=False,
            )
        )
    return out


def _hunt_mentioned_files(
    conn: duckdb.DuckDBPyConnection, ids: Sequence[str]
) -> list[Hit]:
    if not has_table(conn, "slack.files"):
        return []
    ph, params = _in_clause(ids)
    ph2, params2 = _in_clause(ids)
    rows = conn.execute(
        f"""
        SELECT m.channel_id, m.ts, coalesce(c.name, m.channel_name) AS channel_name,
               m.user_name, left(coalesce(m.text, ''), 240) AS preview,
               m.year, string_agg(DISTINCT f.name, '; ') AS file_names
        FROM slack.messages m
        JOIN slack.channels c ON c.channel_id = m.channel_id
        JOIN slack.mentions mt ON mt.channel_id = m.channel_id AND mt.ts = m.ts
        LEFT JOIN slack.files f ON f.channel_id = m.channel_id AND f.ts = m.ts
        WHERE mt.mentioned_user_id IN ({ph})
          AND m.user_id NOT IN ({ph2})
          AND coalesce(m.n_files, 0) > 0
        GROUP BY 1, 2, 3, 4, 5, 6
        """,
        params + params2,
    ).fetchall()
    out: list[Hit] = []
    for row in rows:
        if _channel_blocked(str(row[2] or "")):
            continue
        artifacts = _split_agg(row[6])
        out.append(
            _hit(
                channel_id=str(row[0]),
                ts=str(row[1]),
                title=(artifacts[0] if artifacts else str(row[4] or "mention"))[:160],
                preview=str(row[4] or ""),
                year=_year(row[5]),
                channel=str(row[2] or ""),
                artifacts=artifacts,
                people=tuple(p for p in (str(row[3] or ""),) if p),
                score=30,
                hunt="mentioned_file",
                authored=False,
                coordinated=True,
            )
        )
    return out


def _hunt_thread_files(conn: duckdb.DuckDBPyConnection, ids: Sequence[str]) -> list[Hit]:
    if not has_table(conn, "slack.files"):
        return []
    ph, params = _in_clause(ids)
    ph2, params2 = _in_clause(ids)
    rows = conn.execute(
        f"""
        SELECT fm.channel_id, fm.ts, coalesce(c.name, fm.channel_name) AS channel_name,
               fm.user_name, left(coalesce(fm.text, ''), 240) AS preview,
               fm.year, string_agg(DISTINCT f.name, '; ') AS file_names
        FROM slack.messages r
        JOIN slack.messages fm
          ON fm.channel_id = r.channel_id
         AND fm.thread_ts = r.thread_ts
         AND coalesce(fm.n_files, 0) > 0
         AND fm.user_id NOT IN ({ph})
        JOIN slack.channels c ON c.channel_id = fm.channel_id
        LEFT JOIN slack.files f ON f.channel_id = fm.channel_id AND f.ts = fm.ts
        WHERE r.user_id IN ({ph2}) AND coalesce(r.is_reply, FALSE)
          AND r.thread_ts IS NOT NULL
        GROUP BY 1, 2, 3, 4, 5, 6
        """,
        params + params2,
    ).fetchall()
    out: list[Hit] = []
    for row in rows:
        if _channel_blocked(str(row[2] or "")):
            continue
        artifacts = _split_agg(row[6])
        out.append(
            _hit(
                channel_id=str(row[0]),
                ts=str(row[1]),
                title=(artifacts[0] if artifacts else str(row[4] or "thread file"))[:160],
                preview=str(row[4] or ""),
                year=_year(row[5]),
                channel=str(row[2] or ""),
                artifacts=artifacts,
                people=tuple(p for p in (str(row[3] or ""),) if p),
                score=28,
                hunt="thread_file",
                authored=False,
                coordinated=True,
            )
        )
    return out


def _hunt_channel_samples(
    conn: duckdb.DuckDBPyConnection, ids: Sequence[str]
) -> list[Hit]:
    ph, params = _in_clause(ids)
    rows = conn.execute(
        f"""
        SELECT m.channel_id, m.ts, coalesce(c.name, m.channel_name) AS channel_name,
               m.user_name, left(coalesce(m.text, ''), 240) AS preview,
               m.year, m.text_len
        FROM slack.messages m
        JOIN slack.channels c ON c.channel_id = m.channel_id
        WHERE m.user_id IN ({ph}) AND coalesce(m.is_bot, FALSE) IS NOT TRUE
          AND coalesce(m.text_len, 0) >= ?
          AND regexp_matches(lower(coalesce(c.name, '')), ?)
        """,
        params + [SAMPLE_MIN_LEN, phrase_pattern(slack_activity())],
    ).fetchall()
    out: list[Hit] = []
    for row in rows:
        if _channel_blocked(str(row[2] or "")):
            continue
        out.append(
            _hit(
                channel_id=str(row[0]),
                ts=str(row[1]),
                title=str(row[4] or row[2] or "sample")[:160],
                preview=str(row[4] or ""),
                year=_year(row[5]),
                channel=str(row[2] or ""),
                artifacts=(),
                people=tuple(p for p in (str(row[3] or ""),) if p),
                score=10 + min(int(row[6] or 0) / 200, 10),
                hunt="channel_sample",
                authored=True,
                coordinated=False,
            )
        )
    return out
