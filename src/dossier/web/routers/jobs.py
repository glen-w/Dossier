"""Job status, SSE, cancel, and the job strip."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sse_starlette.sse import EventSourceResponse

from dossier.jobs import RUNNER
from dossier.web.context import TEMPLATES, _missing_job

router = APIRouter()

@router.get("/api/jobs/current")
async def job_current() -> JSONResponse:
    job = RUNNER.current
    if job is None:
        return JSONResponse({"job": None})
    return JSONResponse({"job": job.snapshot()})

@router.get("/api/jobs/{job_id}")
async def job_get(job_id: str) -> JSONResponse:
    job = RUNNER.get(job_id)
    if job is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse({"job": job.snapshot()})

@router.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str, after: int = 0) -> EventSourceResponse:
    job = RUNNER.get(job_id)
    if job is None:
        return EventSourceResponse(_missing_job())

    async def gen():
        cursor = max(0, after)
        while True:
            batch = await asyncio.to_thread(job.wait_events, cursor, 0.8)
            for ev in batch:
                cursor = ev.index + 1
                yield {"event": "message", "data": json.dumps(ev.as_dict())}
            if job.status in {"done", "error"} and not job.events_after(cursor):
                yield {
                    "event": "message",
                    "data": json.dumps({"kind": "eof", "status": job.status}),
                }
                break

    return EventSourceResponse(gen())


@router.post("/api/jobs/{job_id}/cancel")
async def job_cancel(job_id: str) -> RedirectResponse:
    RUNNER.cancel(job_id)
    return RedirectResponse(f"/locker?job={job_id}", status_code=303)


@router.get("/partials/job-strip", response_class=HTMLResponse)
async def job_strip(request: Request) -> HTMLResponse:
    job = RUNNER.current
    return TEMPLATES.TemplateResponse(
        request,
        "partials/job_strip.html",
        {
            "job": job.snapshot() if job else None,
            "busy": RUNNER.busy(),
            "csrf_token": "",
        },
    )
