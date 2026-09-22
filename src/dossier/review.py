"""Loopback page for sifting claim cards. Binds 127.0.0.1 only."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from dossier.store import Corpus

PAGE_SIZE = 20
_FACETS = ("lens", "kind")
_STATUSES = frozenset({"", "pending", "approved", "refused"})
_SNIPPET = 400

_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dossier review</title>
<style>
  :root { color-scheme: light; }
  body { margin: 0; font: 15px/1.45 system-ui, sans-serif; color: #1c1b19; background: #f4f2ec; }
  header { padding: 14px 20px; background: #1c2b24; color: #f4f1ea; }
  header p { margin: 4px 0 0; color: #c9d4cc; }
  main { display: grid; grid-template-columns: 280px 1fr; min-height: calc(100vh - 72px); }
  aside { background: #fff; border-right: 1px solid #e2dfd6; padding: 12px; }
  section { padding: 16px 20px 40px; }
  button, select { font: inherit; }
  button { background: #fff; border: 1px solid #c8c4b8; border-radius: 6px; padding: 6px 10px; cursor: pointer; }
  button.primary { background: #1c2b24; color: #f4f1ea; border-color: #1c2b24; }
  button.warn { background: #fff; color: #7a2e24; border-color: #e2b2a8; }
  button:disabled { opacity: 0.45; cursor: default; }
  .src, .grp { display: block; width: 100%; text-align: left; margin: 0 0 6px; }
  .src.on, .grp.on { border-color: #1c2b24; background: #eef3ef; }
  .meta { color: #5c5852; font-size: 13px; }
  .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin: 8px 0 14px; }
  .card { background: #fff; border: 1px solid #e2dfd6; border-radius: 8px; padding: 12px 14px; margin: 0 0 10px; }
  .card h3 { margin: 0 0 6px; font-size: 15px; font-weight: 600; overflow-wrap: anywhere; }
  ul { margin: 6px 0; padding-left: 18px; overflow-wrap: anywhere; }
  input { font: inherit; padding: 6px 8px; border: 1px solid #c8c4b8; border-radius: 6px; }
  #groups { max-height: 220px; overflow: auto; margin-bottom: 8px; }
  aside { max-height: 100vh; overflow: auto; }
  .snippet { margin: 8px 0 0; color: #3d3a34; }
  #notice { color: #7a2e24; min-height: 1.2em; }
  @media (max-width: 800px) { main { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<header>
  <strong>Dossier review</strong>
  <p>Grouped by source, then lens and kind. Approve and refuse touch pending cards. Reopen sends a card back to pending.</p>
</header>
<main>
  <aside id="sources"></aside>
  <section>
    <div class="row">
      <label>Status <select id="status">
        <option value="pending" selected>pending</option>
        <option value="approved">approved</option>
        <option value="refused">refused</option>
        <option value="">all</option>
      </select></label>
      <input id="q" placeholder="Search claims" autocomplete="off">
      <span id="crumb" class="meta"></span>
    </div>
    <p id="notice"></p>
    <div id="actions" class="row"></div>
    <input id="group-q" placeholder="Filter groups" autocomplete="off">
    <div id="groups"></div>
    <div id="cards"></div>
    <div id="pager" class="row"></div>
  </section>
</main>
<script>
const state = { source: "", lens: "", kind: "", status: "pending", q: "", offset: 0, summary: null };

function el(tag, text, cls) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
}

async function loadSummary() {
  const res = await fetch("/api/summary");
  state.summary = await res.json();
  renderSources();
  renderGroups();
}

function renderSources() {
  const aside = document.getElementById("sources");
  aside.replaceChildren();
  aside.appendChild(el("p", "Sources", "meta"));
  for (const src of state.summary.sources) {
    const label = src.source + "  " + src.pending + " pending";
    const btn = el("button", label, "src" + (src.source === state.source ? " on" : ""));
    btn.addEventListener("click", () => {
      state.source = src.source;
      state.lens = "";
      state.kind = "";
      state.offset = 0;
      renderSources();
      renderGroups();
      loadCards();
    });
    aside.appendChild(btn);
  }
}

function selectedSource() {
  return (state.summary.sources || []).find((src) => src.source === state.source) || null;
}

function renderGroups() {
  const box = document.getElementById("groups");
  const actions = document.getElementById("actions");
  box.replaceChildren();
  actions.replaceChildren();
  const src = selectedSource();
  const groupQuery = (document.getElementById("group-q")?.value || "").trim().toLowerCase();
  document.getElementById("crumb").textContent = src
    ? src.source + " · " + src.pending + " pending · " + src.approved + " approved · " + src.refused + " refused"
    : "Pick a source";
  if (!src) return;
  const approve = el("button", "Approve source (" + src.pending + ")", "primary");
  approve.disabled = src.pending < 1;
  approve.addEventListener("click", () => act(
    { action: "approve", source: src.source },
    "Approve " + src.pending + " pending " + src.source + " cards?"
  ));
  const refuse = el("button", "Refuse source (" + src.pending + ")", "warn");
  refuse.disabled = src.pending < 1;
  refuse.addEventListener("click", () => act(
    { action: "refuse", source: src.source },
    "Refuse " + src.pending + " pending " + src.source + " cards?"
  ));
  const reopen = el(
    "button",
    "Reopen source (" + (src.approved + src.refused) + ")"
  );
  reopen.disabled = src.approved + src.refused < 1;
  reopen.addEventListener("click", () => act(
    { action: "reopen", source: src.source },
    "Reopen " + (src.approved + src.refused) + " " + src.source + " cards?"
  ));
  actions.append(approve, refuse, reopen);
  for (const grp of src.groups) {
    const label = grp.lens + " / " + grp.kind;
    if (groupQuery && !label.includes(groupQuery)) continue;
    const on = grp.lens === state.lens && grp.kind === state.kind;
    const btn = el(
      "button",
      label + "  " + grp.pending + " pending · " + grp.approved + " approved",
      "grp" + (on ? " on" : "")
    );
    btn.addEventListener("click", () => {
      state.lens = grp.lens;
      state.kind = grp.kind;
      state.offset = 0;
      renderGroups();
      loadCards();
    });
    box.appendChild(btn);
    if (!on) continue;
    const row = el("div", null, "row");
    const ok = el("button", "Approve group (" + grp.pending + ")", "primary");
    ok.disabled = grp.pending < 1;
    ok.addEventListener("click", () => act({
      action: "approve", source: src.source, lens: grp.lens, kind: grp.kind
    }, "Approve " + grp.pending + " pending cards in this group?"));
    const no = el("button", "Refuse group (" + grp.pending + ")", "warn");
    no.disabled = grp.pending < 1;
    no.addEventListener("click", () => act({
      action: "refuse", source: src.source, lens: grp.lens, kind: grp.kind
    }, "Refuse " + grp.pending + " pending cards in this group?"));
    const back = el("button", "Reopen group (" + (grp.approved + grp.refused) + ")");
    back.disabled = grp.approved + grp.refused < 1;
    back.addEventListener("click", () => act({
      action: "reopen", source: src.source, lens: grp.lens, kind: grp.kind
    }, "Reopen " + (grp.approved + grp.refused) + " cards in this group?"));
    row.append(ok, no, back);
    box.appendChild(row);
  }
}

async function loadCards() {
  if (!state.source) {
    document.getElementById("cards").replaceChildren();
    document.getElementById("pager").replaceChildren();
    return;
  }
  const params = new URLSearchParams({
    source: state.source,
    status: state.status,
    offset: String(state.offset),
    limit: "20"
  });
  if (state.lens) params.set("lens", state.lens);
  if (state.kind) params.set("kind", state.kind);
  if (state.q) params.set("q", state.q);
  const res = await fetch("/api/cards?" + params.toString());
  const data = await res.json();
  if (!res.ok) {
    note(data.error || "could not load cards");
    return;
  }
  renderCards(data);
}

function renderCards(data) {
  const box = document.getElementById("cards");
  box.replaceChildren();
  if (!data.cards.length) {
    box.appendChild(el("p", "No cards in this slice.", "meta"));
  }
  for (const card of data.cards) {
    const block = el("article", null, "card");
    block.appendChild(el("h3", card.claim));
    block.appendChild(el("p", card.status + " · " + card.id, "meta"));
    if (card.span) block.appendChild(el("p", card.span, "snippet"));
    if (card.snippet) block.appendChild(el("p", card.snippet, "snippet"));
    if (card.citations && card.citations.length) {
      const list = document.createElement("ul");
      for (const uri of card.citations) list.appendChild(el("li", uri));
      block.appendChild(list);
    }
    const row = el("div", null, "row");
    if (card.status === "pending") {
      const ok = el("button", "Approve", "primary");
      ok.addEventListener("click", () => act({ action: "approve", ids: [card.id] }));
      const no = el("button", "Refuse", "warn");
      no.addEventListener("click", () => act({ action: "refuse", ids: [card.id] }));
      row.append(ok, no);
    } else {
      const back = el("button", "Reopen");
      back.addEventListener("click", () => act({ action: "reopen", ids: [card.id] }));
      row.appendChild(back);
    }
    block.appendChild(row);
    box.appendChild(block);
  }
  const pager = document.getElementById("pager");
  pager.replaceChildren();
  const prev = el("button", "Previous");
  prev.disabled = state.offset < 1;
  prev.addEventListener("click", () => {
    state.offset = Math.max(0, state.offset - 20);
    loadCards();
  });
  const next = el("button", "Next");
  next.disabled = state.offset + data.cards.length >= data.total;
  next.addEventListener("click", () => {
    state.offset += 20;
    loadCards();
  });
  pager.append(prev, el("span", (data.total || 0) + " cards", "meta"), next);
}

function note(text) {
  const node = document.getElementById("notice");
  if (node) node.textContent = text || "";
}

async function act(body, confirmText) {
  if (confirmText && !window.confirm(confirmText)) return;
  const res = await fetch("/api/act", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    note(payload.error || "request failed");
    return;
  }
  note((payload.changed || 0) + " changed");
  await loadSummary();
  await loadCards();
}

document.getElementById("status").addEventListener("change", (ev) => {
  state.status = ev.target.value;
  state.offset = 0;
  loadCards();
});
let searchTimer = 0;
document.getElementById("q").addEventListener("input", (ev) => {
  window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(() => {
    state.q = ev.target.value.trim();
    state.offset = 0;
    loadCards();
  }, 200);
});
document.getElementById("group-q").addEventListener("input", () => renderGroups());
loadSummary();
</script>
</body>
</html>
"""


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


def list_cards(
    corpus: Corpus,
    *,
    status: str = "",
    source: str = "",
    lens: str | None = None,
    kind: str | None = None,
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
                "snippet": snippets.get(citations[0], "") if citations else "",
            }
        )
    return {"total": total, "cards": cards}


def apply_action(corpus: Corpus, body: dict) -> int:
    """Approve, refuse, or reopen cards by id, or by source and optional lens/kind."""
    action = str(body.get("action") or "").strip()
    if action not in ("approve", "refuse", "reopen"):
        raise ValueError("action must be approve, refuse, or reopen")
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
    if action == "approve":
        return corpus.approve_pending(sources=sources, lens=lens, kind=kind, ids=ids)
    if action == "refuse":
        return corpus.refuse_pending(sources=sources, lens=lens, kind=kind, ids=ids)
    return corpus.reopen_filtered(sources=sources, lens=lens, kind=kind, ids=ids)


def make_server(corpus: Corpus, port: int) -> HTTPServer:
    handler = _handler(corpus)
    return HTTPServer(("127.0.0.1", port), handler)


def serve(corpus: Corpus, port: int) -> None:
    httpd = make_server(corpus, port)
    httpd.serve_forever()


def _optional_facet(body: dict, key: str) -> str | None:
    if key not in body or body[key] is None:
        return None
    return str(body[key])


def _list_filter(
    *,
    status: str,
    source: str,
    lens: str | None,
    kind: str | None,
    q: str = "",
) -> tuple[str, list]:
    clauses = ["1 = 1"]
    params: list = []
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


def _handler(corpus: Corpus) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/":
                body = _PAGE.encode("utf-8")
                self._send(200, "text/html; charset=utf-8", body)
                return
            if parsed.path == "/api/summary":
                self._json(200, summary(corpus))
                return
            if parsed.path == "/api/cards":
                query = parse_qs(parsed.query)
                lens = query.get("lens", [None])[0]
                kind = query.get("kind", [None])[0]
                try:
                    offset = int(query.get("offset", ["0"])[0])
                    limit = int(query.get("limit", [str(PAGE_SIZE)])[0])
                    payload = list_cards(
                        corpus,
                        status=query.get("status", [""])[0],
                        source=query.get("source", [""])[0],
                        lens=lens,
                        kind=kind,
                        q=query.get("q", [""])[0],
                        offset=offset,
                        limit=limit,
                    )
                except ValueError as exc:
                    self._json(400, {"error": str(exc)})
                    return
                self._json(200, payload)
                return
            self._json(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/api/act":
                self._json(404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length") or "0")
            except ValueError:
                self._json(400, {"error": "bad length"})
                return
            if length < 1 or length > 1_000_000:
                self._json(400, {"error": "body is empty or too large"})
                return
            try:
                body = json.loads(self.rfile.read(length))
            except json.JSONDecodeError:
                self._json(400, {"error": "body is not JSON"})
                return
            if not isinstance(body, dict):
                self._json(400, {"error": "body must be an object"})
                return
            try:
                changed = apply_action(corpus, body)
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
                return
            self._json(200, {"changed": changed})

        def log_message(self, fmt: str, *args) -> None:
            return

        def _json(self, code: int, payload: dict) -> None:
            self._send(code, "application/json", json.dumps(payload).encode("utf-8"))

        def _send(self, code: int, content_type: str, body: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler
