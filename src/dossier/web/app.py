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
from dossier.lists import PHRASE_LISTS, phrase_list_groups, phrase_list_patch
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

    @app.get("/match", response_class=HTMLResponse)
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
            job=job.snapshot() if job else None,
            notice=_egress_notice(cfg),
        )

    @app.post("/match/run")
    async def match_run(spec: str = Form(...)) -> RedirectResponse:
        text = spec.strip()
        if not text:
            return RedirectResponse("/match?err=Paste+a+job+spec", status_code=303)
        try:
            job = _start_match(text)
        except LockerBusy:
            return RedirectResponse("/match?err=busy", status_code=303)
        return RedirectResponse(f"/match?job={job.id}", status_code=303)

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

    @app.get("/settings/lists", response_class=HTMLResponse)
    async def lists_page(request: Request) -> HTMLResponse:
        cfg = Config.from_env()
        root = Path(cfg.data_dir)
        return _page(
            request,
            "lists.html",
            "settings",
            groups=phrase_list_groups(),
            toml_path=str(root / "dossier.toml"),
            saved=request.query_params.get("saved") == "1",
        )

    @app.post("/settings/lists")
    async def lists_save(request: Request) -> RedirectResponse:
        form = await request.form()
        checked: set[tuple[str, str, str]] = set()
        for raw in form.getlist("on"):
            parts = str(raw).split("|", 2)
            if len(parts) == 3 and parts[0] and parts[1]:
                checked.add((parts[0], parts[1], parts[2]))
        extras = {
            (spec.section, spec.key): str(form.get(f"extra_{spec.section}_{spec.key}") or "")
            for spec in PHRASE_LISTS
        }
        path = Path(Config.from_env().data_dir) / "dossier.toml"
        save_common_settings(path, phrase_list_patch(checked, extras))
        return RedirectResponse("/settings/lists?saved=1", status_code=303)

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

    @app.get("/index", response_class=HTMLResponse)
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

    @app.post("/index/run")
    async def index_run() -> RedirectResponse:
        try:
            job = _start_index()
        except LockerBusy:
            return RedirectResponse("/index?err=busy", status_code=303)
        return RedirectResponse(f"/index?job={job.id}", status_code=303)

    @app.get("/brief", response_class=HTMLResponse)
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
            notice=_egress_notice(cfg),
            modes=ASK_MODES,
        )

    @app.post("/brief/run")
    async def brief_run(
        pack: str = Form("career"),
        posting: str = Form(""),
        mode: str = Form(""),
    ) -> RedirectResponse:
        try:
            job = _start_brief(pack.strip() or "career", posting.strip(), mode.strip() or None)
        except LockerBusy:
            return RedirectResponse("/brief?err=busy", status_code=303)
        except ValueError as exc:
            return RedirectResponse(f"/brief?err={_q(str(exc))}", status_code=303)
        return RedirectResponse(f"/brief?job={job.id}", status_code=303)

    @app.get("/run", response_class=HTMLResponse)
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
            notice=_egress_notice(cfg),
        )

    @app.post("/run/start")
    async def run_start() -> RedirectResponse:
        try:
            job = _start_run()
        except LockerBusy:
            return RedirectResponse("/run?err=busy", status_code=303)
        return RedirectResponse(f"/run?job={job.id}", status_code=303)

    @app.get("/settings/prompts", response_class=HTMLResponse)
    async def prompts_page(request: Request) -> HTMLResponse:
        from dossier.prompts import FAMILIES, ROLES, active_map, dry_run, list_catalogue, resolve

        cfg = Config.from_env()
        root = Path(cfg.data_dir)
        catalogue = list_catalogue(root)
        selected_id = request.query_params.get("id") or (catalogue[0].prompt_id if catalogue else "extract")
        try:
            selected = resolve(selected_id, root)
        except KeyError:
            selected = catalogue[0]
        rendered = ""
        if request.query_params.get("dry") == "1":
            rendered = dry_run(selected)
        return _page(
            request,
            "prompts.html",
            "settings",
            cfg=cfg,
            catalogue=catalogue,
            selected=selected,
            families=FAMILIES,
            roles=ROLES,
            prompt_roles=active_map(root),
            rendered=rendered,
            notice=_egress_notice(cfg),
            saved=request.query_params.get("saved") == "1",
        )

    @app.post("/settings/prompts/override")
    async def prompts_override(
        prompt_id: str = Form(...),
        system_prompt: str = Form(""),
        user_template: str = Form(""),
    ) -> RedirectResponse:
        from dossier.prompts import save_override

        cfg = Config.from_env()
        try:
            save_override(
                prompt_id.strip(),
                system_prompt=system_prompt,
                user_template=user_template,
                root=Path(cfg.data_dir),
            )
        except (OSError, ValueError) as exc:
            return RedirectResponse(
                f"/settings/prompts?id={_q(prompt_id)}&err={_q(str(exc))}",
                status_code=303,
            )
        return RedirectResponse(f"/settings/prompts?id={prompt_id}&saved=1", status_code=303)

    @app.post("/settings/prompts/restore")
    async def prompts_restore(prompt_id: str = Form(...)) -> RedirectResponse:
        from dossier.prompts import restore_builtin

        cfg = Config.from_env()
        restore_builtin(prompt_id.strip(), Path(cfg.data_dir))
        return RedirectResponse(f"/settings/prompts?id={prompt_id}&saved=1", status_code=303)

    @app.post("/settings/prompts/custom")
    async def prompts_custom(
        prompt_id: str = Form(...),
        title: str = Form(""),
        family: str = Form("ask"),
        system_prompt: str = Form(""),
        user_template: str = Form(""),
    ) -> RedirectResponse:
        from dossier.prompts import save_custom

        cfg = Config.from_env()
        try:
            saved = save_custom(
                prompt_id,
                title=title,
                family=family,
                system_prompt=system_prompt,
                user_template=user_template,
                root=Path(cfg.data_dir),
            )
        except (OSError, ValueError) as exc:
            return RedirectResponse(f"/settings/prompts?err={_q(str(exc))}", status_code=303)
        return RedirectResponse(f"/settings/prompts?id={saved.prompt_id}&saved=1", status_code=303)

    @app.post("/settings/prompts/activate")
    async def prompts_activate(role: str = Form(...), prompt_id: str = Form(...)) -> RedirectResponse:
        from dossier.prompts import set_active

        cfg = Config.from_env()
        try:
            set_active(role.strip(), prompt_id.strip(), Path(cfg.data_dir))
        except (OSError, ValueError, KeyError) as exc:
            return RedirectResponse(f"/settings/prompts?err={_q(str(exc))}", status_code=303)
        return RedirectResponse("/settings/prompts?saved=1", status_code=303)

    @app.get("/settings/packs", response_class=HTMLResponse)
    async def packs_page(request: Request) -> HTMLResponse:
        import json as _json

        from dossier.packs import CAREER, list_saved_packs, questions_payload, resolve_pack

        cfg = Config.from_env()
        root = Path(cfg.data_dir)
        selected = request.query_params.get("pack") or "career"
        try:
            questions = resolve_pack(selected, root) if selected != "career" else list(CAREER)
            body = _json.dumps(questions_payload(questions), indent=2)
        except (OSError, ValueError):
            selected = "career"
            body = _json.dumps(questions_payload(list(CAREER)), indent=2)
        return _page(
            request,
            "packs.html",
            "settings",
            cfg=cfg,
            pack_name=selected,
            pack_body=body,
            saved_packs=list_saved_packs(root),
            notice=_egress_notice(cfg),
            saved=request.query_params.get("saved") == "1",
        )

    @app.post("/settings/packs/save")
    async def packs_save(name: str = Form(...), body: str = Form(...)) -> RedirectResponse:
        from dossier.packs import save_named_pack

        cfg = Config.from_env()
        try:
            save_named_pack(name, body, Path(cfg.data_dir))
        except (OSError, ValueError) as exc:
            return RedirectResponse(f"/settings/packs?err={_q(str(exc))}", status_code=303)
        return RedirectResponse(f"/settings/packs?pack={name.strip().lower()}&saved=1", status_code=303)

    @app.post("/settings/packs/delete")
    async def packs_delete(name: str = Form(...)) -> RedirectResponse:
        from dossier.packs import delete_named_pack

        cfg = Config.from_env()
        try:
            delete_named_pack(name, Path(cfg.data_dir))
        except ValueError as exc:
            return RedirectResponse(f"/settings/packs?err={_q(str(exc))}", status_code=303)
        return RedirectResponse("/settings/packs?saved=1", status_code=303)

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
                max_num_ctx=cfg.llm_max_num_ctx,
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


def _start_match(spec: str) -> Job:
    def run(job: Job) -> dict[str, Any]:
        from dossier.cli import _query_embedder
        from dossier.match import match_posting, write_match

        cfg = Config.from_env()
        corpus = Corpus(evidence_db(Path(cfg.data_dir)))
        try:
            report = match_posting(
                corpus,
                spec,
                cfg,
                embedder=_query_embedder(cfg, corpus),
            )
            path = write_match(report, Path(cfg.data_dir) / "matches")
            data = report.as_dict()
            data["path"] = str(path)
            return data
        finally:
            corpus.close()

    return RUNNER.start("match", run)


def _job_from_query(request: Request) -> Job | None:
    job_id = request.query_params.get("job", "")
    return RUNNER.get(job_id) if job_id else None


def _start_index() -> Job:
    def run(job: Job) -> dict[str, Any]:
        from dossier.embed import EmbedError, OllamaEmbedder, index_passages
        from dossier.llm.validate import LlmConfigError, validate_ollama_url
        from dossier.ui import Progress

        cfg = Config.from_env()
        if not cfg.llm_enabled:
            note("index: skipped (provider off)")
            return {"skipped": "provider off", "vectors": 0}
        remote = False
        try:
            validate_ollama_url(cfg.llm_base_url, False)
        except LlmConfigError:
            if not cfg.llm_allow_remote:
                note("index: skipped (remote embeddings are not allowed)")
                return {"skipped": "remote embeddings are not allowed", "vectors": 0}
            remote = True
        if remote and llm_egress_is_remote(cfg):
            note("index: remote embeddings")
        embedder = OllamaEmbedder(cfg.llm_base_url, cfg.llm_allow_remote, cfg.embed_model)
        ready, msg = embedder.check()
        if not ready:
            note(f"index: skipped ({msg})")
            return {"skipped": msg, "vectors": 0}
        corpus = Corpus(evidence_db(Path(cfg.data_dir)))
        try:
            stage("index", cfg.embed_model)
            bar: Progress | None = None

            def on_batch(done: int, total: int) -> None:
                nonlocal bar
                if bar is None:
                    bar = Progress(total, label="index")
                    bar.__enter__()
                bar.done = done
                bar.tick(0)
                if total and done >= total:
                    bar.finish()
                    bar.__exit__(None, None, None)

            try:
                count = index_passages(corpus, embedder, on_batch=on_batch)
            except (EmbedError, LlmConfigError) as exc:
                note(f"index: skipped ({exc})")
                return {"skipped": str(exc), "vectors": 0}
            return {"vectors": count, "skipped": ""}
        finally:
            corpus.close()

    return RUNNER.start("index", run)


def _start_brief(pack: str, posting: str, mode: str | None) -> Job:
    def run(job: Job) -> dict[str, Any]:
        from dossier.brief import run_pack, write_brief
        from dossier.cli import _LazyClient, _client_for_mode, _query_embedder
        from dossier.packs import posting_pack, resolve_pack
        from dossier.prompts import start_prompt_log, stop_prompt_log
        from dossier.ui import Progress

        cfg = Config.from_env()
        chosen = mode or cfg.ask_mode
        if chosen not in ASK_MODES:
            chosen = cfg.ask_mode
        if pack == "posting" or posting:
            if not posting:
                raise ValueError("posting pack needs a posting path")
            questions = posting_pack(Path(posting).expanduser().read_text(encoding="utf-8"))
        else:
            questions = resolve_pack(pack, Path(cfg.data_dir))
        corpus = Corpus(evidence_db(Path(cfg.data_dir)))
        try:
            budget = CallBudget(cfg.llm_max_calls)
            if chosen == "exact" or not cfg.llm_enabled:
                client: LLMClient = NullLLMClient()
            elif chosen == "auto":
                client = budget.wrap(_LazyClient(cfg))
            else:
                client, code = _client_for_mode(cfg, chosen)
                if code is not None:
                    raise LLMClientError("model not ready for rich brief")
                client = budget.wrap(client)
            stage("brief", f"{len(questions)} questions · mode={chosen}")
            cited = 0
            refused = 0
            token = start_prompt_log()
            try:
                with Progress(len(questions), label="brief") as bar:

                    def on_progress(done: int, total: int, item, result) -> None:  # noqa: ANN001
                        nonlocal cited, refused
                        bar.set_total(total)
                        if result.refused:
                            refused += 1
                        else:
                            cited += 1
                        bar.tick(cited=cited, refused=refused)
                        bar.status(item.question[:40])

                    items = run_pack(
                        corpus,
                        questions,
                        cfg,
                        client,
                        mode=chosen,
                        on_progress=on_progress,
                        embedder=_query_embedder(cfg, corpus),
                    )
                    bar.finish(cited=cited, refused=refused)
                prompt_stamp = stop_prompt_log(token, empty="ask=none")
            except Exception:
                stop_prompt_log(token, empty="ask=none")
                raise
            path = write_brief(
                items,
                Path(cfg.data_dir) / "briefs",
                prompt_stamp=prompt_stamp,
            )
            return {
                "path": str(path),
                "cited": cited,
                "refused": refused,
                "stamp": prompt_stamp,
            }
        finally:
            corpus.close()

    return RUNNER.start("brief", run)


def _start_run() -> Job:
    def run(job: Job) -> dict[str, Any]:
        from dossier.cli import _brief, _detected_targets, _extract_cards
        from dossier.ingest_run import run_ingest_targets

        cfg = Config.from_env()
        corpus = Corpus(evidence_db(Path(cfg.data_dir)))
        try:
            targets, skipped = _detected_targets(cfg.run_adapters)
            if targets:
                stage("ingest", f"{len(targets)} source{'s' if len(targets) != 1 else ''}")
                run_ingest_targets(targets, corpus)
            extract_budget = CallBudget(cfg.llm_max_calls)
            _extract_cards(
                cfg,
                corpus,
                source=None,
                limit=None,
                strict_llm=False,
                budget=extract_budget,
            )
            brief_budget = CallBudget(cfg.llm_max_calls)
            from argparse import Namespace

            code = 0
            try:
                code = _brief(
                    Namespace(mode=None, pack=None, posting=None),
                    cfg,
                    corpus,
                    budget=brief_budget,
                )
            except Exception as exc:  # noqa: BLE001
                note(str(exc))
                code = 1
            calls = extract_budget.calls + brief_budget.calls
            ledger = (
                f"records={len(corpus.records())} "
                f"adapters_skipped={len(skipped)} "
                f"model_calls={calls} "
                f"egress={'yes' if llm_egress_is_remote(cfg) else 'no'} "
                f"brief_exit={code}"
            )
            note(ledger)
            return {"ledger": ledger, "code": code}
        finally:
            corpus.close()

    return RUNNER.start("run", run)
