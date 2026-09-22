"""FastAPI workbench: server-rendered pages + SSE job progress."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse

from dossier.ask import ASK_MODES
from dossier.cards import STATUS_APPROVED, STATUS_PENDING, STATUS_REFUSED
from dossier.config import Config
from dossier.effort import DEFAULT_EFFORT, EFFORT_NAMES, effort_blurb, normalize_effort
from dossier.extract import ExtractProgress, extract_corpus
from dossier.ingest_run import run_ingest_targets
from dossier.interview import conduct
from dossier.jobs import LockerBusy, RUNNER, Job
from dossier.llm import EGRESS_NOTICE, get_client, llm_egress_is_remote
from dossier.llm.budget import CallBudget
from dossier.llm.client import LLMClient, LLMClientError, NullLLMClient
from dossier.ops import detected_targets, locker_snapshot, source_rows
from dossier.paths import evidence_db
from dossier.profiles import (
    VIRTUAL_DEFAULT,
    activate_profile,
    delete_profile,
    list_profiles,
    save_profile,
)
from dossier.review import apply_action, list_cards, summary
from dossier.settings_io import common_settings_patch, save_common_settings
from dossier.store import Corpus
from dossier.ui import Progress, note, stage
from dossier.vocab import BLURBS, NAV, label

_PKG = Path(__file__).resolve().parent
_TEMPLATES = Jinja2Templates(directory=str(_PKG / "templates"))
_STATIC = _PKG / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="Dossier", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

    @app.middleware("http")
    async def loopback_only(request: Request, call_next):  # noqa: ANN001
        client = request.client.host if request.client else ""
        if client not in {"127.0.0.1", "::1", "testclient", "localhost"}:
            return HTMLResponse("loopback only", status_code=403)
        return await call_next(request)

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request) -> HTMLResponse:
        return RedirectResponse("/locker")

    @app.get("/locker", response_class=HTMLResponse)
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

    @app.get("/sources", response_class=HTMLResponse)
    async def sources_page(request: Request) -> HTMLResponse:
        cfg = Config.from_env()
        return _page(
            request,
            "sources.html",
            "sources",
            cfg=cfg,
            rows=source_rows(),
            busy=RUNNER.busy(),
            notice=_egress_notice(cfg),
        )

    @app.post("/sources/ingest")
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

    @app.get("/extract", response_class=HTMLResponse)
    async def extract_page(request: Request) -> HTMLResponse:
        cfg = Config.from_env()
        return _page(
            request,
            "extract.html",
            "extract",
            cfg=cfg,
            rows=source_rows(),
            busy=RUNNER.busy(),
            notice=_egress_notice(cfg),
        )

    @app.post("/extract/run")
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

    @app.get("/review", response_class=HTMLResponse)
    async def review_page(
        request: Request,
        status: str = "pending",
        source: str = "",
        lens: str = "",
        kind: str = "",
        q: str = "",
        offset: int = 0,
    ) -> HTMLResponse:
        cfg, corpus = _open()
        try:
            status_key = status if status in {"", "pending", "approved", "refused"} else "pending"
            start = max(0, offset)
            payload = list_cards(
                corpus,
                status=status_key,
                source=source,
                lens=lens or None,
                kind=kind or None,
                q=q,
                offset=start,
            )
            payload["offset"] = start
            payload["has_more"] = start + len(payload["cards"]) < payload["total"]
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
                q=q,
                busy=RUNNER.busy(),
                notice=_egress_notice(cfg),
            )
        finally:
            corpus.close()

    @app.post("/review/act")
    async def review_act(
        action: str = Form(...),
        ids: str = Form(""),
        source: str = Form(""),
        lens: str = Form(""),
        kind: str = Form(""),
        status: str = Form("pending"),
        q: str = Form(""),
    ) -> RedirectResponse:
        if RUNNER.busy():
            return RedirectResponse("/review?err=busy", status_code=303)
        cfg, corpus = _open()
        try:
            body: dict[str, Any] = {"action": action}
            id_list = [part.strip() for part in ids.split(",") if part.strip()]
            if id_list:
                body["ids"] = id_list
            if source:
                body["source"] = source
            if lens:
                body["lens"] = lens
            if kind:
                body["kind"] = kind
            apply_action(corpus, body)
        finally:
            corpus.close()
        params = f"status={status}&source={source}&lens={lens}&kind={kind}&q={_q(q)}"
        return RedirectResponse(f"/review?{params}", status_code=303)

    @app.get("/ask", response_class=HTMLResponse)
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
            job=job.snapshot() if job else None,
            notice=_egress_notice(cfg),
            modes=ASK_MODES,
        )

    @app.post("/ask/run")
    async def ask_run(
        question: str = Form(...),
        mode: str = Form(""),
    ) -> RedirectResponse:
        q = question.strip()
        if not q:
            return RedirectResponse("/ask?err=empty", status_code=303)
        try:
            job = _start_ask(q, mode.strip() or None)
        except LockerBusy:
            return RedirectResponse("/ask?err=busy", status_code=303)
        return RedirectResponse(f"/ask?job={job.id}", status_code=303)

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(request: Request) -> HTMLResponse:
        cfg = Config.from_env()
        root = Path(cfg.data_dir)
        return _page(
            request,
            "settings.html",
            "settings",
            cfg=cfg,
            efforts=EFFORT_NAMES,
            effort_blurbs={name: effort_blurb(name) for name in EFFORT_NAMES},
            profiles=list_profiles(root),
            modes=ASK_MODES,
            toml_path=str(root / "dossier.toml"),
            notice=_egress_notice(cfg),
            saved=request.query_params.get("saved") == "1",
            err=request.query_params.get("err", ""),
        )

    @app.post("/settings/save")
    async def settings_save(
        effort: str = Form(DEFAULT_EFFORT),
        model: str = Form(""),
        max_calls: str = Form("0"),
        ask_mode: str = Form("auto"),
        extract_llm: str = Form(""),
        ask_planner: str = Form("off"),
    ) -> RedirectResponse:
        cfg = Config.from_env()
        path = Path(cfg.data_dir) / "dossier.toml"
        try:
            calls = max(0, int(max_calls.strip() or "0"))
        except ValueError:
            return RedirectResponse("/settings?err=max_calls", status_code=303)
        mode = ask_mode if ask_mode in ASK_MODES else "auto"
        planner = ask_planner if ask_planner in {"off", "rich"} else "off"
        patch = common_settings_patch(
            effort=normalize_effort(effort),
            model=model.strip() or cfg.llm_model,
            max_calls=calls,
            ask_mode=mode,
            extract_llm=extract_llm in {"1", "true", "on", "yes"},
            ask_planner=planner,
        )
        save_common_settings(path, patch)
        return RedirectResponse("/settings?saved=1", status_code=303)

    @app.post("/settings/profile/save")
    async def profile_save(
        name: str = Form(...),
        description: str = Form(""),
    ) -> RedirectResponse:
        cfg = Config.from_env()
        root = Path(cfg.data_dir)
        cleaned = name.strip().lower()
        if cleaned == VIRTUAL_DEFAULT:
            return RedirectResponse("/settings?err=default", status_code=303)
        try:
            save_profile(
                cleaned,
                description=description,
                config={
                    "effort": cfg.effort,
                    "llm": {"model": cfg.llm_model, "max_calls": cfg.llm_max_calls},
                    "ask": {"mode": cfg.ask_mode, "planner": cfg.ask_planner},
                    "extract": {"llm": cfg.extract_llm},
                },
                root=root,
            )
        except ValueError as exc:
            return RedirectResponse(f"/settings?err={_q(str(exc))}", status_code=303)
        return RedirectResponse("/settings?saved=1", status_code=303)

    @app.post("/settings/profile/activate")
    async def profile_activate(name: str = Form(...)) -> RedirectResponse:
        cfg = Config.from_env()
        try:
            activate_profile(name.strip(), Path(cfg.data_dir))
        except (OSError, ValueError, FileNotFoundError) as exc:
            return RedirectResponse(f"/settings?err={_q(str(exc))}", status_code=303)
        return RedirectResponse("/settings?saved=1", status_code=303)

    @app.post("/settings/profile/delete")
    async def profile_delete(name: str = Form(...)) -> RedirectResponse:
        cfg = Config.from_env()
        try:
            delete_profile(name.strip(), Path(cfg.data_dir))
        except ValueError as exc:
            return RedirectResponse(f"/settings?err={_q(str(exc))}", status_code=303)
        return RedirectResponse("/settings?saved=1", status_code=303)

    @app.get("/api/jobs/current")
    async def job_current() -> JSONResponse:
        job = RUNNER.current
        if job is None:
            return JSONResponse({"job": None})
        return JSONResponse({"job": job.snapshot()})

    @app.get("/api/jobs/{job_id}")
    async def job_get(job_id: str) -> JSONResponse:
        job = RUNNER.get(job_id)
        if job is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"job": job.snapshot()})

    @app.get("/api/jobs/{job_id}/events")
    async def job_events(job_id: str, after: int = 0) -> EventSourceResponse:
        job = RUNNER.get(job_id)
        if job is None:
            return EventSourceResponse(_missing_job())

        async def gen():
            cursor = max(0, after)
            while True:
                batch = job.wait_events(cursor, timeout=0.8)
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

    @app.get("/partials/job-strip", response_class=HTMLResponse)
    async def job_strip(request: Request) -> HTMLResponse:
        job = RUNNER.current
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/job_strip.html",
            {"job": job.snapshot() if job else None, "busy": RUNNER.busy()},
        )

    return app


def serve(*, host: str = "127.0.0.1", port: int = 8766) -> None:
    import uvicorn

    uvicorn.run(create_app(), host=host, port=port, log_level="warning")


def _page(
    request: Request,
    template: str,
    active: str,
    **ctx: Any,
) -> HTMLResponse:
    job = RUNNER.current
    base = {
        "request": request,
        "nav": NAV,
        "active": active,
        "label": label,
        "blurbs": BLURBS,
        "job": job.snapshot() if job else None,
        "busy": RUNNER.busy(),
        "err": request.query_params.get("err", ""),
        "job_id": request.query_params.get("job", ""),
        "statuses": (STATUS_PENDING, STATUS_APPROVED, STATUS_REFUSED),
    }
    base.update(ctx)
    return _TEMPLATES.TemplateResponse(request, template, base)


def _open() -> tuple[Config, Corpus]:
    cfg = Config.from_env()
    return cfg, Corpus(evidence_db(Path(cfg.data_dir)))


def _egress_notice(cfg: Config) -> str:
    if llm_egress_is_remote(cfg):
        return EGRESS_NOTICE
    return ""


def _q(text: str) -> str:
    from urllib.parse import quote

    return quote(text[:120], safe="")


async def _missing_job():
    yield {"event": "message", "data": json.dumps({"kind": "error", "error": "not found"})}


def _start_ingest(adapter: str | None) -> Job:
    if adapter:
        targets = detected_targets((adapter,))
        if not targets:
            raise ValueError(f"{adapter}: not detected")
    else:
        targets = detected_targets()
        if not targets:
            raise ValueError("nothing to ingest")

    def run(job: Job) -> dict[str, Any]:
        cfg = Config.from_env()
        corpus = Corpus(evidence_db(Path(cfg.data_dir)))
        try:
            stage("ingest", f"{len(targets)} source{'s' if len(targets) != 1 else ''}")
            before, after = run_ingest_targets(targets, corpus)
            return {"records_before": before, "records_after": after}
        finally:
            corpus.close()

    return RUNNER.start("ingest", run)


def _start_extract(source: str | None, limit: int | None) -> Job:
    def run(job: Job) -> dict[str, Any]:
        cfg = Config.from_env()
        corpus = Corpus(evidence_db(Path(cfg.data_dir)))
        try:
            use_llm = cfg.extract_llm and cfg.llm_enabled
            client: LLMClient = NullLLMClient()
            if use_llm:
                client = get_client(cfg)
                ok_cfg, msg = client.check_config(cfg.llm_model)
                if not ok_cfg:
                    note(msg)
                    use_llm = False
                    client = NullLLMClient()
                else:
                    client = CallBudget(cfg.llm_max_calls).wrap(client)
            bar: Progress | None = None
            drafted = 0
            cards_n = 0

            def on_progress(ev: ExtractProgress) -> None:
                nonlocal bar, drafted, cards_n
                if ev.phase == "start":
                    mode = f"llm={cfg.llm_model}" if use_llm else "llm=off (drafts only)"
                    stage("extract", f"{mode} · {ev.total} to draft")
                    if ev.total:
                        bar = Progress(ev.total, label="extract")
                        bar.__enter__()
                    return
                if ev.phase == "draft":
                    drafted += 1
                    cards_n += ev.cards_added
                    if bar is not None:
                        bar.tick(drafted=drafted, cards=cards_n)
                elif ev.phase == "done" and bar is not None:
                    bar.finish(drafted=drafted, cards=cards_n)
                    bar.__exit__(None, None, None)

            cards = extract_corpus(
                corpus,
                client,
                cfg.llm_model,
                source=source,
                limit=limit,
                use_llm=use_llm,
                timeout_seconds=min(cfg.llm_timeout_seconds, 60.0),
                chunk_chars=cfg.extract_chunk_chars,
                max_chunks=cfg.extract_max_chunks,
                on_progress=on_progress,
            )
            return {"cards": len(cards), "use_llm": use_llm}
        finally:
            corpus.close()

    return RUNNER.start("extract", run)


def _start_ask(question: str, mode: str | None) -> Job:
    def run(job: Job) -> dict[str, Any]:
        from dossier.cli import _LazyClient, _client_for_mode, _query_embedder
        from dossier.sources.pubs import optional_pubs_hits

        cfg = Config.from_env()
        corpus = Corpus(evidence_db(Path(cfg.data_dir)))
        try:
            chosen = mode or cfg.ask_mode
            if chosen not in ASK_MODES:
                chosen = cfg.ask_mode
            budget = CallBudget(cfg.llm_max_calls)
            if chosen == "exact" or not cfg.llm_enabled:
                client: LLMClient = NullLLMClient()
            elif chosen == "auto":
                client = budget.wrap(_LazyClient(cfg))
            else:
                client, code = _client_for_mode(cfg, chosen)
                if code is not None:
                    raise LLMClientError("model not ready for rich ask")
                client = budget.wrap(client)
            stage("ask", chosen)
            extra = optional_pubs_hits(question, enabled=cfg.ask_pubs, limit=cfg.ask_limit)
            result = conduct(
                corpus,
                question,
                cfg,
                client,
                mode=chosen,
                limit=cfg.ask_limit,
                embedder=_query_embedder(cfg, corpus),
                extra_hits=extra or None,
            )
            corpus.add_answer(
                question=question,
                mode=chosen,
                text=result.text,
                citations=result.citations,
                refused=result.refused,
                reason=result.reason,
            )
            return {
                "question": question,
                "mode": chosen,
                "text": result.text,
                "citations": result.citations,
                "refused": result.refused,
                "reason": result.reason,
            }
        finally:
            corpus.close()

    return RUNNER.start("ask", run)
