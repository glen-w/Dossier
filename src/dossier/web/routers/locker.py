"""Locker, sources, extract, index, brief, and run pages."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from dossier.ask import ASK_MODES
from dossier.config import Config
from dossier.effort import EFFORT_NAMES
from dossier.jobs import RUNNER, LockerBusy
from dossier.ops import locker_snapshot, source_rows
from dossier.web.context import (
    _brief_view,
    _egress_notice,
    _job_from_query,
    _open,
    _page,
    _posted_scope,
    _q,
    _scope_template,
    _start_brief,
    _start_extract,
    _start_index,
    _start_ingest,
    _start_run,
)

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def home(request: Request) -> RedirectResponse:
    return RedirectResponse("/locker")

@router.get("/locker", response_class=HTMLResponse)
async def locker_page(request: Request) -> HTMLResponse:
    cfg, corpus = _open()
    try:
        snap = locker_snapshot(cfg, corpus)
        return _page(
            request,
            "locker.html",
            "locker",
            cfg=cfg,
            snap=snap,
            notice=_egress_notice(cfg),
        )
    finally:
        corpus.close()

@router.get("/sources", response_class=HTMLResponse)
async def sources_page(request: Request) -> HTMLResponse:
    cfg = Config.from_env()
    job = _job_from_query(request)
    result = (
        job.result
        if job is not None and job.status == "done" and isinstance(job.result, dict)
        else None
    )
    return _page(
        request,
        "sources.html",
        "sources",
        cfg=cfg,
        rows=source_rows(),
        busy=RUNNER.busy(),
        result=result,
        job=job.snapshot() if job else None,
        notice=_egress_notice(cfg),
    )

@router.post("/sources/ingest")
async def sources_ingest(
    request: Request,
    adapter: str = Form(""),
) -> RedirectResponse:
    try:
        job = _start_ingest(adapter.strip() or None)
    except LockerBusy:
        return RedirectResponse("/sources?err=busy", status_code=303)
    except ValueError as exc:
        return RedirectResponse(f"/sources?err={_q(str(exc))}", status_code=303)
    return RedirectResponse(f"/sources?job={job.id}", status_code=303)

@router.get("/extract", response_class=HTMLResponse)
async def extract_page(request: Request) -> HTMLResponse:
    cfg = Config.from_env()
    job = _job_from_query(request)
    result = (
        job.result
        if job is not None and job.status == "done" and isinstance(job.result, dict)
        else None
    )
    return _page(
        request,
        "extract.html",
        "extract",
        cfg=cfg,
        rows=source_rows(),
        busy=RUNNER.busy(),
        result=result,
        job=job.snapshot() if job else None,
        notice=_egress_notice(cfg),
    )

@router.post("/extract/run")
async def extract_run(
    source: str = Form(""),
    limit: str = Form(""),
) -> RedirectResponse:
    lim: int | None = None
    if limit.strip():
        try:
            lim = max(1, int(limit.strip()))
        except ValueError:
            return RedirectResponse("/extract?err=limit", status_code=303)
    try:
        job = _start_extract(source.strip() or None, lim)
    except LockerBusy:
        return RedirectResponse("/extract?err=busy", status_code=303)
    return RedirectResponse(f"/extract?job={job.id}", status_code=303)

@router.get("/index", response_class=HTMLResponse)
async def index_page(request: Request) -> HTMLResponse:
    cfg = Config.from_env()
    job = _job_from_query(request)
    return _page(
        request,
        "index.html",
        "index",
        cfg=cfg,
        busy=RUNNER.busy(),
        result=job.result if job and job.status == "done" else None,
        notice=_egress_notice(cfg),
    )

@router.post("/index/run")
async def index_run() -> RedirectResponse:
    try:
        job = _start_index()
    except LockerBusy:
        return RedirectResponse("/index?err=busy", status_code=303)
    return RedirectResponse(f"/index?job={job.id}", status_code=303)

@router.get("/brief", response_class=HTMLResponse)
async def brief_page(request: Request) -> HTMLResponse:
    cfg = Config.from_env()
    root = Path(cfg.data_dir)
    from dossier.packs import list_saved_packs

    job = _job_from_query(request)
    return _page(
        request,
        "brief.html",
        "brief",
        cfg=cfg,
        packs=["career", "posting", *list_saved_packs(root)],
        busy=RUNNER.busy(),
        result=job.result if job and job.status == "done" else None,
        job=job.snapshot() if job else None,
        notice=_egress_notice(cfg),
        modes=ASK_MODES,
        efforts=EFFORT_NAMES,
        **_scope_template(cfg),
        **_brief_view(root, request, job),
    )

@router.post("/brief/run")
async def brief_run(
    pack: str = Form("career"),
    posting: str = Form(""),
    mode: str = Form(""),
    scope_form: str = Form(""),
    sources: list[str] = Form(default=[]),
    year_from: str = Form(""),
    year_to: str = Form(""),
    effort: str = Form(""),
) -> RedirectResponse:
    try:
        scope = _posted_scope(scope_form, sources, year_from, year_to, effort)
        job = _start_brief(pack.strip() or "career", posting.strip(), mode.strip() or None, scope)
    except LockerBusy:
        return RedirectResponse("/brief?err=busy", status_code=303)
    except ValueError as exc:
        return RedirectResponse(f"/brief?err={_q(str(exc))}", status_code=303)
    return RedirectResponse(f"/brief?job={job.id}", status_code=303)

@router.get("/run", response_class=HTMLResponse)
async def run_page(request: Request) -> HTMLResponse:
    cfg = Config.from_env()
    job = _job_from_query(request)
    return _page(
        request,
        "run.html",
        "run",
        cfg=cfg,
        busy=RUNNER.busy(),
        result=job.result if job and job.status == "done" else None,
        job=job.snapshot() if job else None,
        notice=_egress_notice(cfg),
    )

@router.post("/run/start")
async def run_start() -> RedirectResponse:
    try:
        job = _start_run()
    except LockerBusy:
        return RedirectResponse("/run?err=busy", status_code=303)
    return RedirectResponse(f"/run?job={job.id}", status_code=303)
