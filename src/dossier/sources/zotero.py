"""One named Zotero collection, as bibliography records.

Reads ``zotero.sqlite`` (a copy, so a running Zotero is left alone). Does not
parse PDFs, embed, or open any other collection.
"""

from __future__ import annotations

import re
import shutil
import sqlite3
import tempfile
from pathlib import Path

from dossier.paths import pubs_collection, zotero_db
from dossier.store import Record
from dossier.util import record_id

_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_CACHE: tuple[tuple[str, str, int, int], list[Record]] | None = None

_ITEMS = """
WITH RECURSIVE tree AS (
    SELECT collectionID
    FROM collections
    WHERE collectionName = ? OR key = ?
    UNION ALL
    SELECT c.collectionID
    FROM collections c
    JOIN tree t ON c.parentCollectionID = t.collectionID
)
SELECT
    i.itemID,
    i.key,
    MAX(CASE WHEN f.fieldName = 'title' THEN idv.value END),
    MAX(CASE WHEN f.fieldName IN ('date', 'year') THEN idv.value END),
    MAX(CASE WHEN f.fieldName = 'publicationTitle' THEN idv.value END),
    MAX(CASE WHEN f.fieldName = 'DOI' THEN idv.value END),
    MAX(CASE WHEN f.fieldName = 'abstractNote' THEN idv.value END)
FROM tree
JOIN collectionItems ci ON ci.collectionID = tree.collectionID
JOIN items i ON i.itemID = ci.itemID
JOIN itemTypes it ON i.itemTypeID = it.itemTypeID
LEFT JOIN itemData id ON i.itemID = id.itemID
LEFT JOIN fields f ON id.fieldID = f.fieldID
LEFT JOIN itemDataValues idv ON id.valueID = idv.valueID
WHERE it.typeName NOT IN ('attachment', 'note')
  AND i.itemID NOT IN (SELECT itemID FROM deletedItems)
GROUP BY i.itemID, i.key
"""


def collection_records() -> list[Record] | None:
    """Records for the configured collection.

    ``None`` means no collection is configured, so a caller may use another
    retrieve path. A list, including an empty one, means the collection is
    configured and nothing else should be ingested.
    """
    collection = pubs_collection()
    if not collection:
        return None
    db = zotero_db()
    if not db.is_file():
        return []
    return _cached(db, collection)


def _cached(db: Path, collection: str) -> list[Record]:
    global _CACHE
    try:
        stat = db.stat()
    except OSError:
        return []
    key = (str(db), collection, stat.st_mtime_ns, stat.st_size)
    if _CACHE is not None and _CACHE[0] == key:
        return list(_CACHE[1])
    rows = _read(db, collection)
    _CACHE = (key, rows)
    return list(rows)


def _read(db: Path, collection: str) -> list[Record]:
    try:
        copied = _snapshot(db)
    except OSError:
        return []
    try:
        conn = sqlite3.connect(f"file:{copied}?mode=ro", uri=True)
        try:
            found = conn.execute(
                """
                WITH RECURSIVE tree AS (
                    SELECT collectionID FROM collections
                    WHERE collectionName = ? OR key = ?
                    UNION ALL
                    SELECT c.collectionID FROM collections c
                    JOIN tree t ON c.parentCollectionID = t.collectionID
                )
                SELECT 1 FROM tree LIMIT 1
                """,
                (collection, collection),
            ).fetchone()
            if found is None:
                return []
            raw = conn.execute(_ITEMS, (collection, collection)).fetchall()
            authors = _authors(conn, [row[0] for row in raw])
        finally:
            conn.close()
    except sqlite3.Error:
        return []
    finally:
        shutil.rmtree(copied.parent, ignore_errors=True)

    out: list[Record] = []
    for item_id, key, title, date, journal, doi, abstract in raw:
        item_key = str(key or "").strip()
        heading = str(title or "").strip()
        if not item_key or not heading:
            continue
        year = _year(date)
        uri = f"zotero://{item_key}"
        text = _bibliography(
            heading,
            authors.get(item_id, ""),
            year,
            str(journal or "").strip(),
            str(doi or "").strip(),
            str(abstract or "").strip(),
        )
        if not text:
            continue
        out.append(
            Record(
                id=record_id(uri),
                source="pubs",
                uri=uri,
                title=heading,
                text=text,
                table="pubs.records",
            )
        )
    out.sort(key=lambda rec: (-_year_num(rec.text), rec.title.casefold(), rec.uri))
    return out


def _snapshot(db: Path) -> Path:
    folder = Path(tempfile.mkdtemp(prefix="dossier-zotero-"))
    dest = folder / "zotero.sqlite"
    shutil.copy2(db, dest)
    for suffix in ("-wal", "-shm"):
        side = Path(str(db) + suffix)
        if side.is_file():
            shutil.copy2(side, Path(str(dest) + suffix))
    return dest


def _authors(conn: sqlite3.Connection, item_ids: list[int]) -> dict[int, str]:
    if not item_ids:
        return {}
    grouped: dict[int, list[str]] = {}
    for start in range(0, len(item_ids), 500):
        chunk = item_ids[start : start + 500]
        marks = ",".join("?" for _ in chunk)
        rows = conn.execute(
            f"""
            SELECT ic.itemID, c.lastName, c.firstName
            FROM itemCreators ic
            JOIN creators c ON ic.creatorID = c.creatorID
            JOIN creatorTypes ct ON ic.creatorTypeID = ct.creatorTypeID
            WHERE ct.creatorType = 'author'
              AND ic.itemID IN ({marks})
            ORDER BY ic.itemID, ic.orderIndex
            """,
            chunk,
        ).fetchall()
        for item_id, last, first in rows:
            name = ", ".join(part.strip() for part in (str(last or ""), str(first or "")) if part and str(part).strip())
            if name:
                grouped.setdefault(int(item_id), []).append(name)
    return {item_id: "; ".join(names) for item_id, names in grouped.items()}


def _bibliography(
    title: str,
    authors: str,
    year: str,
    journal: str,
    doi: str,
    abstract: str,
) -> str:
    if authors and year:
        lead = f"{authors} ({year})"
    elif authors:
        lead = authors
    else:
        lead = year
    parts = [part for part in (lead, title, journal, _doi(doi)) if part]
    sentence = ". ".join(parts)
    if sentence and not sentence.endswith("."):
        sentence += "."
    lines: list[str] = []
    if year:
        lines.extend([f"Year: {year}", ""])
    lines.append(sentence)
    if abstract and abstract != title:
        lines.extend(["", abstract])
    return "\n".join(lines).strip()


def _doi(doi: str) -> str:
    raw = doi.strip()
    if not raw:
        return ""
    if raw.lower().startswith("http://") or raw.lower().startswith("https://"):
        return raw
    return f"https://doi.org/{raw.removeprefix('doi:').strip()}"


def _year(date: object) -> str:
    found = _YEAR.search(str(date or ""))
    return found.group(0) if found else ""


def _year_num(text: str) -> int:
    for line in text.splitlines():
        if line.lower().startswith("year:"):
            found = _YEAR.search(line)
            return int(found.group(0)) if found else 0
    return 0
