"""Thunderbird Gloda hunts. Metadata only until a small folder is fetched."""

from __future__ import annotations

from pathlib import Path

import duckdb

from dossier.identity import (
    ACTIVITY_FOLDER_RE,
    DELIVERY_SUBJECT_RE,
    DOC_ATTACH_RE,
    NOISE_SIGNALS,
    activity_folder,
    noise_folder,
    skip_folder,
)
from dossier.lenses import infer_kind, infer_lenses, infer_org, infer_skills, primary_lens
from dossier.seekers.hits import Hit
from dossier.sources.warehouse import has_table


def hunt_mail(conn: duckdb.DuckDBPyConnection) -> list[Hit]:
    if not has_table(conn, "thunderbird.messages") or not has_table(
        conn, "thunderbird.folders"
    ):
        return []
    has_signals = has_table(conn, "thunderbird.signals")
    hits: list[Hit] = []
    hits.extend(_sent_docs_activity(conn, has_signals))
    hits.extend(_sent_delivery_activity(conn, has_signals))
    hits.extend(_starred_activity(conn, has_signals))
    hits.extend(_sent_docs_elsewhere(conn, has_signals))
    return hits


def _noise_sql(has_signals: bool) -> str:
    folder = (
        "NOT regexp_matches(lower(coalesce(f.name, '')), "
        "'newsletter|receipt|news etc|la vie de l.?iddri|bounced|out of office')"
    )
    if not has_signals:
        return folder
    kinds = ", ".join("?" for _ in NOISE_SIGNALS)
    return f"""{folder}
        AND NOT EXISTS (
            SELECT 1 FROM thunderbird.signals s
            WHERE s.message_id = m.gloda_id AND s.kind IN ({kinds})
        )"""


def _noise_params(has_signals: bool) -> list[str]:
    return list(NOISE_SIGNALS) if has_signals else []


def _year(value: object) -> int:
    try:
        return int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0


def _mid(header_id: object, gloda_id: object) -> str:
    raw = str(header_id or "").strip()
    if raw:
        return raw.strip("<>")
    return f"gloda-{gloda_id}"


def _artifacts(names: object) -> tuple[str, ...]:
    text = str(names or "").strip()
    if not text:
        return ()
    parts = [p.strip() for p in text.replace("\n", ";").split(";") if p.strip()]
    return tuple(parts)


def _row_hit(
    row: tuple,
    *,
    hunt: str,
    score: float,
    fetch_body: bool,
    authored: bool,
    coordinated: bool,
) -> Hit:
    (
        gloda_id,
        header_id,
        subject,
        attachment_names,
        year,
        folder,
        account_key,
        from_name,
        starred,
        replied,
    ) = row
    folder_name = str(folder or "")
    subj = str(subject or "").strip() or folder_name or "message"
    artifacts = _artifacts(attachment_names)
    kind = infer_kind(folder=folder_name, subject=subj, artifacts=artifacts)
    skills = infer_skills(folder_name, subj, " ".join(artifacts))
    lenses = infer_lenses(
        kind=kind,
        artifacts=artifacts,
        authored=authored,
        coordinated=coordinated or bool(starred) or bool(replied),
        skills=skills,
    )
    mid = _mid(header_id, gloda_id)
    account = str(account_key or "mail")
    preview_bits = [subj]
    if artifacts:
        preview_bits.append("Attachments: " + ", ".join(artifacts))
    return Hit(
        source="mbox",
        uri=f"mbox://{account}/{folder_name}/{mid}",
        title=subj[:160],
        preview=" | ".join(preview_bits),
        year=_year(year),
        org=infer_org(source="mbox", account_key=account),
        kind=kind,
        lenses=lenses,
        primary_lens=primary_lens(lenses),
        artifacts=artifacts,
        people=tuple(p for p in (str(from_name or ""),) if p),
        skills=skills,
        score=score,
        hunts=(hunt,),
        fetch_body=fetch_body and not skip_folder(folder_name),
        account_key=account,
        folder_name=folder_name,
        header_message_id=str(header_id or mid),
    )


_SELECT = """
    m.gloda_id, m.header_message_id, m.subject, m.attachment_names, m.year,
    f.name AS folder, f.account_key, m.from_name, m.starred, m.replied
"""


def _sent_docs_activity(conn: duckdb.DuckDBPyConnection, has_signals: bool) -> list[Hit]:
    sql = f"""
        SELECT {_SELECT}
        FROM thunderbird.messages m
        JOIN thunderbird.folders f ON f.folder_id = m.folder_id
        WHERE m.direction = 'sent'
          AND coalesce(m.has_attachment, FALSE)
          AND regexp_matches(lower(coalesce(m.attachment_names, '')), ?)
          AND regexp_matches(lower(coalesce(f.name, '')), ?)
          AND {_noise_sql(has_signals)}
        """
    params: list[object] = [DOC_ATTACH_RE.pattern, ACTIVITY_FOLDER_RE.pattern]
    params.extend(_noise_params(has_signals))
    rows = conn.execute(sql, params).fetchall()
    return [
        _row_hit(row, hunt="sent_doc_activity", score=50, fetch_body=True, authored=True, coordinated=False)
        for row in rows
    ]


def _sent_delivery_activity(
    conn: duckdb.DuckDBPyConnection, has_signals: bool
) -> list[Hit]:
    sql = f"""
        SELECT {_SELECT}
        FROM thunderbird.messages m
        JOIN thunderbird.folders f ON f.folder_id = m.folder_id
        WHERE m.direction = 'sent'
          AND regexp_matches(lower(coalesce(m.subject, '')), ?)
          AND regexp_matches(lower(coalesce(f.name, '')), ?)
          AND {_noise_sql(has_signals)}
        """
    params: list[object] = [DELIVERY_SUBJECT_RE.pattern, ACTIVITY_FOLDER_RE.pattern]
    params.extend(_noise_params(has_signals))
    rows = conn.execute(sql, params).fetchall()
    return [
        _row_hit(
            row,
            hunt="sent_delivery_activity",
            score=30,
            fetch_body=True,
            authored=True,
            coordinated=False,
        )
        for row in rows
    ]


def _starred_activity(conn: duckdb.DuckDBPyConnection, has_signals: bool) -> list[Hit]:
    sql = f"""
        SELECT {_SELECT}
        FROM thunderbird.messages m
        JOIN thunderbird.folders f ON f.folder_id = m.folder_id
        WHERE (coalesce(m.starred, FALSE) OR coalesce(m.replied, FALSE))
          AND regexp_matches(lower(coalesce(f.name, '')), ?)
          AND {_noise_sql(has_signals)}
        """
    params: list[object] = [ACTIVITY_FOLDER_RE.pattern]
    params.extend(_noise_params(has_signals))
    rows = conn.execute(sql, params).fetchall()
    return [
        _row_hit(
            row,
            hunt="starred_activity",
            score=25,
            fetch_body=True,
            authored=True,
            coordinated=True,
        )
        for row in rows
    ]


def _sent_docs_elsewhere(conn: duckdb.DuckDBPyConnection, has_signals: bool) -> list[Hit]:
    sql = f"""
        SELECT {_SELECT}
        FROM thunderbird.messages m
        JOIN thunderbird.folders f ON f.folder_id = m.folder_id
        WHERE m.direction = 'sent'
          AND coalesce(m.has_attachment, FALSE)
          AND regexp_matches(lower(coalesce(m.attachment_names, '')), ?)
          AND NOT regexp_matches(lower(coalesce(f.name, '')), ?)
          AND {_noise_sql(has_signals)}
        """
    params: list[object] = [
        DOC_ATTACH_RE.pattern,
        ACTIVITY_FOLDER_RE.pattern,
    ]
    params.extend(_noise_params(has_signals))
    rows = conn.execute(sql, params).fetchall()
    out: list[Hit] = []
    for row in rows:
        folder = str(row[5] or "")
        if noise_folder(folder):
            continue
        out.append(
            _row_hit(
                row,
                hunt="sent_doc_elsewhere",
                score=15,
                fetch_body=False,
                authored=True,
                coordinated=False,
            )
        )
    return out


def hunt_mbox_folder(root: Path, *, max_bytes: int) -> list[Hit]:
    """Thin-user path: score headers in a small exported folder. Never IDDRI."""
    from dossier.fetch.mbox import iter_mbox_files, mbox_openable, parse_headers

    hits: list[Hit] = []
    for mbox_path, folder_name in iter_mbox_files(root):
        if skip_folder(folder_name) or noise_folder(folder_name):
            continue
        if not mbox_openable(mbox_path, folder_name, max_bytes):
            continue
        allow_body = activity_folder(folder_name)
        for hdr in parse_headers(mbox_path):
            if not _thin_keep(hdr, folder_name):
                continue
            artifacts = tuple(hdr.get("artifacts") or ())
            subj = hdr.get("subject") or folder_name
            kind = infer_kind(folder=folder_name, subject=subj, artifacts=artifacts)
            skills = infer_skills(folder_name, subj, " ".join(artifacts))
            authored = bool(hdr.get("from_me"))
            lenses = infer_lenses(
                kind=kind, artifacts=artifacts, authored=authored, skills=skills
            )
            mid = hdr.get("message_id") or hdr.get("key") or "unknown"
            hits.append(
                Hit(
                    source="mbox",
                    uri=f"mbox://export/{folder_name}/{mid}",
                    title=subj[:160],
                    preview=subj,
                    year=int(hdr.get("year") or 0),
                    org="",
                    kind=kind,
                    lenses=lenses,
                    primary_lens=primary_lens(lenses),
                    artifacts=artifacts,
                    people=tuple(p for p in (hdr.get("from") or "",) if p),
                    skills=skills,
                    score=40 if artifacts else 20,
                    hunts=("folder_walk",),
                    fetch_body=allow_body,
                    folder_name=folder_name,
                    header_message_id=str(hdr.get("message_id") or mid),
                )
            )
    return hits


def _thin_keep(hdr: dict, folder_name: str) -> bool:
    subj = hdr.get("subject") or ""
    arts = " ".join(hdr.get("artifacts") or ())
    if DOC_ATTACH_RE.search(arts):
        return True
    if DELIVERY_SUBJECT_RE.search(subj) and activity_folder(folder_name):
        return True
    return activity_folder(folder_name) and bool(subj)


