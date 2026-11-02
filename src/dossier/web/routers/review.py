"""Review queue."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from dossier.jobs import RUNNER
from dossier.lenses import KINDS, LENSES
from dossier.review import (
    PAGE_SIZE,
    PER_PAGE_CHOICES,
    apply_action,
    card_sources,
    card_years,
    list_cards,
    summary,
)
from dossier.web.context import _egress_notice, _open, _page, _q

router = APIRouter()

@router.get("/review", response_class=HTMLResponse)
async def review_page(
    request: Request,
    status: str = "pending",
    source: str = "",
    lens: str = "",
    kind: str = "",
    year_from: str = "",
    year_to: str = "",
    q: str = "",
    offset: int = 0,
    view: str = "list",
    per: int = PAGE_SIZE,
) -> HTMLResponse:
    cfg, corpus = _open()
    try:
        status_key = status if status in {"", "pending", "approved", "refused"} else "pending"
        shown = view if view in {"list", "queue"} else "list"
        start = max(0, offset)
        per = per if per in PER_PAGE_CHOICES else PAGE_SIZE
        payload = list_cards(
            corpus,
            status=status_key,
            source=source,
            lens=lens or None,
            kind=kind or None,
            year_from=year_from,
            year_to=year_to,
            q=q,
            offset=start,
            limit=1 if shown == "queue" else per,
        )
        payload["offset"] = start
        payload["has_more"] = start + len(payload["cards"]) < payload["total"]
        years = card_years(corpus)
        years = sorted({*years, *(y for y in (year_from, year_to) if y)}, reverse=True)
        sources = card_sources(corpus)
        if source and source not in sources:
            sources = [source, *sources]
        return _page(
            request,
            "review.html",
            "review",
            cfg=cfg,
            summary=summary(corpus),
            cards=payload,
            status=status_key,
            source=source,
            lens=lens,
            kind=kind,
            year_from=year_from,
            year_to=year_to,
            years=years,
            per=per,
            per_choices=PER_PAGE_CHOICES,
            q=q,
            view=shown,
            sources=sources,
            lenses=LENSES,
            kinds=KINDS,
            noted=request.query_params.get("noted", ""),
            busy=RUNNER.busy(),
            notice=_egress_notice(cfg),
        )
    finally:
        corpus.close()

@router.post("/review/act")
async def review_act(
    action: str = Form(...),
    ids: str = Form(""),
    pick: list[str] = Form([]),
    source: str = Form(""),
    lens: str = Form(""),
    kind: str = Form(""),
    year_from: str = Form(""),
    year_to: str = Form(""),
    status: str = Form("pending"),
    q: str = Form(""),
    view: str = Form("list"),
    offset: int = Form(0),
    per: int = Form(PAGE_SIZE),
) -> RedirectResponse:
    if RUNNER.busy():
        return RedirectResponse("/review?err=busy", status_code=303)
    shown = view if view == "queue" else "list"
    _cfg, corpus = _open()
    try:
        body: dict[str, Any] = {"action": action}
        id_list = [part.strip() for part in ids.split(",") if part.strip()]
        id_list += [item.strip() for item in pick if item.strip() and item.strip() not in id_list]
        if id_list:
            body["ids"] = id_list
        if source:
            body["source"] = source
        if lens:
            body["lens"] = lens
        if kind:
            body["kind"] = kind
        if year_from:
            body["year_from"] = year_from
        if year_to:
            body["year_to"] = year_to
        apply_action(corpus, body)
        next_offset = max(0, offset)
        if shown == "queue" and id_list:
            payload = list_cards(
                corpus,
                status=status if status in {"", "pending", "approved", "refused"} else "pending",
                source=source,
                lens=lens or None,
                kind=kind or None,
                year_from=year_from,
                year_to=year_to,
                q=q,
                offset=next_offset,
                limit=1,
            )
            if payload["cards"] and payload["cards"][0]["id"] == id_list[0]:
                next_offset += 1
    finally:
        corpus.close()
    params = f"status={status}&source={source}&lens={lens}&kind={kind}&year_from={year_from}&year_to={year_to}&per={per if per in PER_PAGE_CHOICES else PAGE_SIZE}&q={_q(q)}"
    if shown == "queue":
        params += f"&view=queue&offset={next_offset}"
        if action == "defend":
            params += "&noted=span"
    return RedirectResponse(f"/review?{params}", status_code=303)
