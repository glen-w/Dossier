"""Claim-card listing and bulk actions. The workbench hosts the UI."""

from __future__ import annotations

import json

from dossier.cards import carrying_span
from dossier.scope import parse_year
from dossier.show import store_span
from dossier.store import Corpus

PAGE_SIZE = 20
PER_PAGE_CHOICES = (10, 20, 50, 100)
_FACETS = ("lens", "kind")
_STATUSES = frozenset({"", "pending", "approved", "refused"})
_SNIPPET = 400


def summary(corpus: Corpus) -> dict:
    """Counts per source, and per lens/kind inside that source."""
    rows = corpus._conn.execute(
        """
        SELECT source, status,
               lower(trim(COALESCE(json_extract(extras, '$.lens'), ''))) AS lens,
               lower(trim(COALESCE(json_extract(extras, '$.kind'), ''))) AS kind,
               COUNT(*) AS n
        FROM cards
        GROUP BY 1, 2, 3, 4
        ORDER BY source, lens, kind
        """
    ).fetchall()
    sources: dict[str, dict] = {}
    for row in rows:
        name = str(row["source"] or "")
        src = sources.setdefault(
            name,
            {"source": name, "pending": 0, "approved": 0, "refused": 0, "groups": {}},
        )
        status = str(row["status"] or "")
        count = int(row["n"])
        if status in ("pending", "approved", "refused"):
            src[status] += count
        lens = str(row["lens"] or "") or "(none)"
        kind = str(row["kind"] or "") or "(none)"
        group = src["groups"].setdefault(
            (lens, kind),
            {"lens": lens, "kind": kind, "pending": 0, "approved": 0, "refused": 0},
        )
        if status in ("pending", "approved", "refused"):
            group[status] += count
    out = []
    for src in sources.values():
        groups = list(src["groups"].values())
        groups.sort(key=lambda item: (-item["pending"], item["lens"], item["kind"]))
        src["groups"] = groups
        out.append(src)
    out.sort(key=lambda item: (-item["pending"], item["source"]))
    return {"sources": out}


def card_sources(corpus: Corpus) -> list[str]:
    rows = corpus._conn.execute(
        "SELECT DISTINCT source FROM cards WHERE TRIM(source) != '' ORDER BY source"
    ).fetchall()
    return [str(row["source"]) for row in rows]


def card_years(corpus: Corpus) -> list[str]:
    """Distinct source-record years behind the cards, newest first."""
    rows = corpus._conn.execute(
        f"SELECT DISTINCT {_YEAR_SQL} AS year FROM cards WHERE {_YEAR_SQL} != '' ORDER BY year DESC"
    ).fetchall()
    return [str(row["year"]) for row in rows]


def list_cards(
    corpus: Corpus,
    *,
    status: str = "",
    source: str = "",
    lens: str | None = None,
    kind: str | None = None,
    year_from: str = "",
    year_to: str = "",
    q: str = "",
    offset: int = 0,
    limit: int = PAGE_SIZE,
) -> dict:
    if status not in _STATUSES:
        raise ValueError("unknown status")
    query = q.strip()
    if len(query) > 200:
        raise ValueError("search is too long")
    where, params = _list_filter(
        status=status,
        source=source,
        lens=lens,
        kind=kind,
        year_from=year_from,
        year_to=year_to,
        q=query,
    )
    total = int(
        corpus._conn.execute(f"SELECT COUNT(*) AS n FROM cards WHERE {where}", params).fetchone()["n"]
    )
    capped = max(1, min(limit, 100))
    start = max(0, offset)
    rows = corpus._conn.execute(
        f"""
        SELECT id, claim, citations, source, status, reason, extras
        FROM cards WHERE {where}
        ORDER BY source, id
        LIMIT ? OFFSET ?
        """,
        [*params, capped, start],
    ).fetchall()
    packed = []
    first_uris: list[str] = []
    for row in rows:
        extras = _extras(row["extras"])
        citations = _citations(row["citations"])
        if citations:
            first_uris.append(citations[0])
        packed.append((row, extras, citations))
    snippets = _snippets(corpus, first_uris)
    cards = []
    for row, extras, citations in packed:
        cards.append(
            {
                "id": row["id"],
                "claim": row["claim"],
                "citations": citations,
                "source": row["source"],
                "status": row["status"],
                "reason": row["reason"] or "",
                "lens": (extras.get("lens") or "").strip().lower() or "(none)",
                "kind": (extras.get("kind") or "").strip().lower() or "(none)",
                "span": (extras.get("span") or "").strip(),
                "carrying": _carrying(corpus, row["claim"], extras, citations),
                "snippet": snippets.get(citations[0], "") if citations else "",
            }
        )
        for card in cards:
            before, hit, after = _mark(card["snippet"], card["carrying"])
            card["mark_before"] = before
            card["mark_hit"] = hit
            card["mark_after"] = after
    return {"total": total, "cards": cards}


def apply_action(corpus: Corpus, body: dict) -> int:
    """Approve, refuse, or reopen cards by id, or by source and optional lens/kind."""
    action = str(body.get("action") or "").strip()
    if action not in ("approve", "refuse", "reopen", "defend"):
        raise ValueError("action must be approve, refuse, reopen, or defend")
    raw_ids = body.get("ids") or []
    if not isinstance(raw_ids, list):
        raise ValueError("ids must be a list")
    if len(raw_ids) > 200:
        raise ValueError("too many ids; use a source")
    ids = tuple(str(item).strip() for item in raw_ids if str(item).strip())
    source = str(body.get("source") or "").strip()
    if not ids and not source:
        raise ValueError("pass ids or a source")
    lens = _optional_facet(body, "lens") if not ids else None
    kind = _optional_facet(body, "kind") if not ids else None
    sources = () if ids else ((source,) if source else ())
    year_from = str(body.get("year_from") or "").strip() if not ids else ""
    year_to = str(body.get("year_to") or "").strip() if not ids else ""
    if year_from or year_to:
        where, params = _list_filter(
            status="", source=source, lens=lens, kind=kind, year_from=year_from, year_to=year_to
        )
        ids = tuple(
            str(row["id"])
            for row in corpus._conn.execute(f"SELECT id FROM cards WHERE {where}", params)
        )
        if not ids:
            return 0
        lens = kind = None
        sources = ()
    if action == "defend":
        return _defend_matching(corpus, ids=ids, source=source, lens=lens, kind=kind)
    if action == "approve":
        return corpus.approve_pending(sources=sources, lens=lens, kind=kind, ids=ids)
    if action == "refuse":
        return corpus.refuse_pending(sources=sources, lens=lens, kind=kind, ids=ids)
    return corpus.reopen_filtered(sources=sources, lens=lens, kind=kind, ids=ids)


def _mark(snippet: str, carrying: str) -> tuple[str, str, str]:
    if not snippet or not carrying or carrying not in snippet:
        return "", "", ""
    at = snippet.index(carrying)
    return snippet[:at], carrying, snippet[at + len(carrying) :]


def _carrying(corpus: Corpus, claim: str, extras: dict[str, str], citations: list[str]) -> str:
    stored = (extras.get("span") or "").strip()
    if stored:
        return stored
    for uri in citations:
        rec = corpus.get_record(uri)
        if rec is None:
            continue
        sentence = carrying_span(claim, rec.text)
        if sentence:
            return sentence
    return ""


def _defend_matching(
    corpus: Corpus,
    *,
    ids: tuple[str, ...],
    source: str,
    lens: str | None,
    kind: str | None,
) -> int:
    """Store spans on pending and approved cards. Status stays put."""
    changed = 0
    if ids:
        targets = []
        for card_id in ids:
            card = corpus.get_card(card_id)
            if card is not None and card.status in ("pending", "approved"):
                targets.append(card)
    else:
        where, params = _list_filter(status="", source=source, lens=lens, kind=kind)
        rows = corpus._conn.execute(
            f"""
            SELECT id FROM cards
            WHERE {where} AND status IN ('pending', 'approved')
            """,
            params,
        ).fetchall()
        targets = []
        for row in rows:
            card = corpus.get_card(str(row["id"]))
            if card is not None:
                targets.append(card)
    for card in targets:
        if store_span(corpus, card):
            changed += 1
    return changed


def _optional_facet(body: dict, key: str) -> str | None:
    if key not in body or body[key] is None:
        return None
    return str(body[key])


# Year of the first cited record, read from its "Year: YYYY" line; '' when absent.
_YEAR_SQL = """COALESCE((
    SELECT CASE
        WHEN instr(char(10) || r.text, char(10) || 'Year: ') > 0
         AND substr(r.text, instr(char(10) || r.text, char(10) || 'Year: ') + 6, 4) GLOB '[0-9][0-9][0-9][0-9]'
        THEN substr(r.text, instr(char(10) || r.text, char(10) || 'Year: ') + 6, 4)
        ELSE '' END
    FROM records r WHERE r.uri = json_extract(cards.citations, '$[0]')
), '')"""


def _list_filter(
    *,
    status: str,
    source: str,
    lens: str | None,
    kind: str | None,
    year_from: str = "",
    year_to: str = "",
    q: str = "",
) -> tuple[str, list]:
    clauses = ["1 = 1"]
    params: list = []
    low, high = parse_year(year_from), parse_year(year_to)
    if low and high and low > high:
        low, high = high, low
    if low or high:
        clauses.append(f"{_YEAR_SQL} != ''")
    if low:
        clauses.append(f"{_YEAR_SQL} >= ?")
        params.append(str(low))
    if high:
        clauses.append(f"{_YEAR_SQL} <= ?")
        params.append(str(high))
    if status:
        clauses.append("status = ?")
        params.append(status)
    if source:
        clauses.append("source = ?")
        params.append(source)
    if q:
        clauses.append("claim LIKE ? ESCAPE '\\'")
        params.append(_like(q))
    for key, value in zip(_FACETS, (lens, kind), strict=True):
        facet, facet_params = _list_facet(key, value)
        if facet:
            clauses.append(facet)
            params.extend(facet_params)
    return " AND ".join(clauses), params


def _like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _snippets(corpus: Corpus, uris: list[str]) -> dict[str, str]:
    unique: list[str] = []
    seen: set[str] = set()
    for uri in uris:
        if uri and uri not in seen:
            seen.add(uri)
            unique.append(uri)
    found: dict[str, str] = {}
    for start in range(0, len(unique), 40):
        chunk = unique[start : start + 40]
        marks = ",".join("?" * len(chunk))
        rows = corpus._conn.execute(
            f"""
            SELECT uri, title, substr(text, 1, ?) AS snippet
            FROM records WHERE uri IN ({marks})
            """,
            [_SNIPPET, *chunk],
        ).fetchall()
        for row in rows:
            title = str(row["title"] or "").strip()
            text = " ".join(str(row["snippet"] or "").split())
            shown = f"{title}: {text}" if title else text
            found[str(row["uri"])] = shown[:_SNIPPET]
    return found


def _list_facet(key: str, value: str | None) -> tuple[str, list]:
    if key not in _FACETS:
        raise ValueError(f"unknown facet {key}")
    if value is None or value == "":
        return "", []
    column = f"lower(trim(COALESCE(json_extract(extras, '$.{key}'), '')))"
    if value == "(none)":
        return f"{column} = ''", []
    return f"{column} = ?", [value.strip().lower()]


def _extras(raw: str | None) -> dict[str, str]:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): str(val) for key, val in data.items() if val is not None}


def _citations(raw: str | None) -> list[str]:
    try:
        data = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(item) for item in data]

