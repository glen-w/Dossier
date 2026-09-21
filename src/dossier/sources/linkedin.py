"""LinkedIn positions / education / skills / publications from the warehouse."""

from __future__ import annotations

from pathlib import Path

from dossier.sources.warehouse import connect_readonly, has_table, resolve_warehouse
from dossier.store import Corpus, Record
from dossier.util import record_id

_TABLES = (
    "linkedin.positions",
    "linkedin.education",
    "linkedin.skills",
    "linkedin.publications",
)


class LinkedInSource:
    name = "linkedin"

    def detect(self, path: Path) -> bool:
        db = resolve_warehouse(path)
        if not db.is_file():
            return False
        try:
            conn = connect_readonly(path)
        except Exception:
            return False
        try:
            return any(has_table(conn, t) for t in _TABLES)
        finally:
            conn.close()

    def load(self, path: Path, corpus: Corpus) -> None:
        conn = connect_readonly(path)
        try:
            if has_table(conn, "linkedin.positions"):
                rows = conn.execute(
                    """
                    SELECT company_name, title, description, location,
                           started_on, finished_on
                    FROM linkedin.positions
                    """
                ).fetchall()
                for i, (company, title, desc, location, started, finished) in enumerate(
                    rows
                ):
                    uri = f"linkedin://positions/{i}"
                    heading = " ".join(
                        p for p in (title, "at" if company else "", company) if p
                    ).strip() or f"Position {i}"
                    bits = [
                        heading,
                        location or "",
                        f"{started or ''}–{finished or ''}".strip("–"),
                        desc or "",
                    ]
                    text = ". ".join(b.strip() for b in bits if b and str(b).strip())
                    if text:
                        _put(corpus, uri, heading, text, "linkedin.positions")
            if has_table(conn, "linkedin.education"):
                rows = conn.execute(
                    """
                    SELECT school_name, degree_name, notes, start_date, end_date
                    FROM linkedin.education
                    """
                ).fetchall()
                for i, (school, degree, notes, start, end) in enumerate(rows):
                    uri = f"linkedin://education/{i}"
                    heading = " ".join(
                        p for p in (degree, "at" if school else "", school) if p
                    ).strip() or f"Education {i}"
                    bits = [heading, f"{start or ''}–{end or ''}".strip("–"), notes or ""]
                    text = ". ".join(b.strip() for b in bits if b and str(b).strip())
                    if text:
                        _put(corpus, uri, heading, text, "linkedin.education")
            if has_table(conn, "linkedin.skills"):
                rows = conn.execute("SELECT name FROM linkedin.skills").fetchall()
                names = [str(r[0]).strip() for r in rows if r and r[0]]
                if names:
                    uri = "linkedin://skills"
                    text = "Skills: " + ", ".join(names)
                    _put(corpus, uri, "LinkedIn skills", text, "linkedin.skills")
            if has_table(conn, "linkedin.publications"):
                rows = conn.execute(
                    """
                    SELECT name, published_on, description, publisher, url
                    FROM linkedin.publications
                    """
                ).fetchall()
                for i, (name, published, desc, publisher, url) in enumerate(rows):
                    uri = str(url or "").strip() or f"linkedin://publications/{i}"
                    heading = str(name or f"Publication {i}")
                    bits = [heading, publisher or "", published or "", desc or ""]
                    text = ". ".join(b.strip() for b in bits if b and str(b).strip())
                    if text:
                        _put(corpus, uri, heading, text, "linkedin.publications")
        finally:
            conn.close()

    def tables(self) -> list[str]:
        return list(_TABLES)


def _put(corpus: Corpus, uri: str, title: str, text: str, table: str) -> None:
    corpus.upsert_record(
        Record(
            id=record_id(uri),
            source="linkedin",
            uri=uri,
            title=title,
            text=text,
            table=table,
        )
    )
