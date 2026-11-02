"""Tailor drafts."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from dossier.config import Config
from dossier.jobs import RUNNER, LockerBusy
from dossier.web.context import (
    _egress_notice,
    _job_from_query,
    _kept_text,
    _match_spec,
    _page,
    _start_tailor,
)

router = APIRouter()

@router.get("/tailor", response_class=HTMLResponse)
async def tailor_page(request: Request) -> HTMLResponse:
    cfg = Config.from_env()
    job = _job_from_query(request)
    result = (
        job.result
        if job is not None and job.status == "done" and isinstance(job.result, dict)
        else None
    )
    posting_text = _kept_text(job, result, "posting") or _match_spec(request.query_params.get("from", ""))
    kind_value = _kept_text(job, result, "kind") or "cv"
    if kind_value not in {"cv", "letter"}:
        kind_value = "cv"
    return _page(
        request,
        "tailor.html",
        "tailor",
        cfg=cfg,
        busy=RUNNER.busy(),
        result=result,
        posting_text=posting_text,
        kind_value=kind_value,
        job=job.snapshot() if job else None,
        notice=_egress_notice(cfg),
    )

@router.post("/tailor/run")
async def tailor_run(
    posting: str = Form(...),
    kind: str = Form("cv"),
    arrange: str = Form(""),
) -> RedirectResponse:
    text = posting.strip()
    if not text:
        return RedirectResponse("/tailor?err=Paste+a+posting", status_code=303)
    chosen = kind if kind in {"cv", "letter"} else "cv"
    try:
        job = _start_tailor(text, chosen, arrange == "1")
    except LockerBusy:
        return RedirectResponse("/tailor?err=busy", status_code=303)
    return RedirectResponse(f"/tailor?job={job.id}", status_code=303)
