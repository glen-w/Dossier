"""Ask and cited chat."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from dossier.ask import ASK_MODES
from dossier.config import Config
from dossier.effort import EFFORT_NAMES
from dossier.jobs import RUNNER, LockerBusy
from dossier.web.context import (
    _egress_notice,
    _kept_text,
    _page,
    _posted_scope,
    _q,
    _scope_template,
    _start_ask,
)

router = APIRouter()

@router.get("/ask", response_class=HTMLResponse)
async def ask_page(request: Request) -> HTMLResponse:
    cfg = Config.from_env()
    job_id = request.query_params.get("job", "")
    result = None
    job = RUNNER.get(job_id) if job_id else None
    if job is not None and job.status == "done" and isinstance(job.result, dict):
        result = job.result
    return _page(
        request,
        "ask.html",
        "ask",
        cfg=cfg,
        busy=RUNNER.busy(),
        result=result,
        question_text=_kept_text(job, result, "question"),
        job=job.snapshot() if job else None,
        notice=_egress_notice(cfg),
        modes=ASK_MODES,
        efforts=EFFORT_NAMES,
        **_scope_template(cfg),
    )

@router.post("/ask/run")
async def ask_run(
    question: str = Form(...),
    mode: str = Form(""),
    scope_form: str = Form(""),
    sources: list[str] = Form(default=[]),
    year_from: str = Form(""),
    year_to: str = Form(""),
    effort: str = Form(""),
) -> RedirectResponse:
    q = question.strip()
    if not q:
        return RedirectResponse("/ask?err=empty", status_code=303)
    try:
        scope = _posted_scope(scope_form, sources, year_from, year_to, effort)
        job = _start_ask(q, mode.strip() or None, scope)
    except LockerBusy:
        return RedirectResponse("/ask?err=busy", status_code=303)
    except ValueError as exc:
        return RedirectResponse(f"/ask?err={_q(str(exc))}", status_code=303)
    return RedirectResponse(f"/ask?job={job.id}", status_code=303)
