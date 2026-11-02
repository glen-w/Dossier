"""Match, gaps, packet, prove, and referees."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from dossier.config import Config
from dossier.effort import EFFORT_NAMES
from dossier.jobs import RUNNER, Job, LockerBusy
from dossier.web.context import (
    _egress_notice,
    _kept_text,
    _open,
    _page,
    _posted_scope,
    _q,
    _scope_template,
    _start_match,
)

router = APIRouter()

@router.get("/match", response_class=HTMLResponse)
async def match_page(request: Request) -> HTMLResponse:
    cfg = Config.from_env()
    job_id = request.query_params.get("job", "")
    result = None
    job = RUNNER.get(job_id) if job_id else None
    if job is not None and job.status == "done" and isinstance(job.result, dict):
        result = job.result
    return _page(
        request,
        "match.html",
        "match",
        cfg=cfg,
        busy=RUNNER.busy(),
        result=result,
        spec_text=_kept_text(job, result, "spec"),
        job=job.snapshot() if job else None,
        notice=_egress_notice(cfg),
        efforts=EFFORT_NAMES,
        **_scope_template(cfg),
    )

@router.post("/match/run")
async def match_run(
    spec: str = Form(...),
    scope_form: str = Form(""),
    sources: list[str] = Form(default=[]),
    year_from: str = Form(""),
    year_to: str = Form(""),
    effort: str = Form(""),
) -> RedirectResponse:
    text = spec.strip()
    if not text:
        return RedirectResponse("/match?err=Paste+a+job+spec", status_code=303)
    try:
        scope = _posted_scope(scope_form, sources, year_from, year_to, effort)
        job = _start_match(text, scope)
    except LockerBusy:
        return RedirectResponse("/match?err=busy", status_code=303)
    except ValueError as exc:
        return RedirectResponse(f"/match?err={_q(str(exc))}", status_code=303)
    return RedirectResponse(f"/match?job={job.id}", status_code=303)

@router.get("/drift", response_class=HTMLResponse)
async def drift_page(request: Request) -> HTMLResponse:
    from dossier.drift import collect_drift, render_drift

    cfg, corpus = _open()
    try:
        report = collect_drift(corpus)
        return _page(
            request,
            "drift.html",
            "drift",
            cfg=cfg,
            report=report,
            body=render_drift(report),
        )
    finally:
        corpus.close()


@router.get("/gaps", response_class=HTMLResponse)
async def gaps_page(request: Request) -> HTMLResponse:
    from dossier.show import gap_report

    cfg, corpus = _open()
    try:
        return _page(
            request,
            "gaps.html",
            "gaps",
            cfg=cfg,
            report=gap_report(corpus),
            notice=_egress_notice(cfg),
        )
    finally:
        corpus.close()

@router.get("/packet", response_class=HTMLResponse)
async def packet_page(request: Request) -> HTMLResponse:
    cfg = Config.from_env()
    raw = Path(request.query_params.get("path", "")).name
    body = ""
    shown = ""
    if raw and raw not in {".", ".."}:
        root = (Path(cfg.data_dir) / "packets").resolve()
        resolved = (root / raw).resolve()
        if resolved.parent == root and resolved.is_file():
            shown = str(resolved)
            body = resolved.read_text(encoding="utf-8")
    return _page(
        request,
        "packet.html",
        "packet",
        cfg=cfg,
        path=shown,
        body=body,
        busy=RUNNER.busy(),
        notice=_egress_notice(cfg),
    )

@router.post("/packet/run")
async def packet_run() -> RedirectResponse:
    from dossier.show import write_packet

    if RUNNER.busy():
        return RedirectResponse("/packet?err=busy", status_code=303)
    cfg, corpus = _open()
    try:
        path = write_packet(corpus, Path(cfg.data_dir) / "packets")
    finally:
        corpus.close()
    return RedirectResponse(f"/packet?path={_q(path.name)}", status_code=303)

@router.get("/prove", response_class=HTMLResponse)
async def prove_page(request: Request) -> HTMLResponse:
    return _page(
        request,
        "prove.html",
        "prove",
        cfg=Config.from_env(),
        busy=RUNNER.busy(),
    )

@router.post("/prove/run")
async def prove_run() -> RedirectResponse:
    if RUNNER.busy():
        return RedirectResponse("/prove?err=busy", status_code=303)

    def run(job: Job) -> dict[str, Any]:
        from dossier.prove import DEFAULT_ADAPTERS, run_prove

        code = run_prove(adapters=DEFAULT_ADAPTERS, allow_overlap=True, with_llm=False)
        return {"code": code}

    job = RUNNER.start("prove", run)
    return RedirectResponse(f"/prove?job={job.id}", status_code=303)

@router.get("/referees", response_class=HTMLResponse)
async def referees_page(request: Request) -> HTMLResponse:
    return _page(
        request,
        "referees.html",
        "referees",
        cfg=Config.from_env(),
        busy=RUNNER.busy(),
    )
