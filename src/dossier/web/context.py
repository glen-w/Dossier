"""Shared workbench helpers used by routers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from dossier.ask import ASK_MODES
from dossier.cards import STATUS_APPROVED, STATUS_PENDING, STATUS_REFUSED
from dossier.config import Config
from dossier.extract import ExtractProgress, extract_corpus
from dossier.ingest_run import run_ingest_targets
from dossier.interview import conduct
from dossier.jobs import RUNNER, Job, JobCancelled
from dossier.llm import EGRESS_NOTICE, get_client, llm_egress_is_remote
from dossier.llm.budget import CallBudget
from dossier.llm.client import (
    LLMClient,
    LLMClientError,
    NullLLMClient,
    select_fast_model,
)
from dossier.ops import (
    LazyClient,
    client_for_mode,
    detected_targets,
    detected_targets_report,
    query_embedder,
)
from dossier.paths import evidence_db
from dossier.scope import (
    RequestScope,
    apply_request_scope,
    known_sources,
    parse_year,
    scope_label,
    sources_for_request,
)
from dossier.store import Corpus
from dossier.ui import Progress, note, stage
from dossier.vocab import BLURBS, NAV, NAV_ROOMS, err_message, label

_PKG = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(_PKG / "templates"))
STATIC = _PKG / "static"
CSRF_COOKIE = "dossier_csrf"

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
        "nav_rooms": NAV_ROOMS,
        "active": active,
        "label": label,
        "blurbs": BLURBS,
        "job": job.snapshot() if job else None,
        "busy": RUNNER.busy(),
        "err": err_message(request.query_params.get("err", "")),
        "job_id": request.query_params.get("job", ""),
        "statuses": (STATUS_PENDING, STATUS_APPROVED, STATUS_REFUSED),
        "csrf_token": getattr(request.state, "csrf_token", "")
        or request.cookies.get(CSRF_COOKIE)
        or "",
    }
    base.update(ctx)
    return TEMPLATES.TemplateResponse(request, template, base)


def _open() -> tuple[Config, Corpus]:
    cfg = Config.from_env()
    return cfg, Corpus(evidence_db(Path(cfg.data_dir)))


def _scope_template(cfg: Config) -> dict[str, Any]:
    names = known_sources()
    selected = names if cfg.scope_sources is None else cfg.scope_sources
    return {
        "scope_names": names,
        "scope_selected": set(selected),
        "scope_year_from": cfg.scope_year_from or "",
        "scope_year_to": cfg.scope_year_to or "",
    }


def _default_scope() -> RequestScope:
    cfg = Config.from_env()
    return RequestScope(cfg.scope_sources, cfg.scope_year_from, cfg.scope_year_to, "")


def _posted_scope(
    scope_form: str,
    sources: list[str],
    year_from: str,
    year_to: str,
    effort: str,
) -> RequestScope:
    if scope_form != "1":
        return _default_scope()
    start = parse_year(year_from)
    end = parse_year(year_to)
    if start and end and start > end:
        raise ValueError("year range")
    return RequestScope(sources_for_request(sources), start, end, effort.strip().lower())


def _profile_scope(cfg: Config) -> dict[str, Any]:
    years = {"year_from": cfg.scope_year_from, "year_to": cfg.scope_year_to}
    if cfg.scope_sources is None:
        return {"all_sources": True, **years}
    return {"sources": list(cfg.scope_sources), **years}


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
            model = cfg.fast_model
            if use_llm:
                client = get_client(cfg)
                model, fast_note = select_fast_model(cfg, client)
                if fast_note:
                    note(fast_note)
                ok_cfg, msg = client.check_config(model)
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
                if job.cancel.is_set():
                    raise JobCancelled("cancelled")
                if ev.phase == "start":
                    mode = f"llm={model}" if use_llm else "llm=off (drafts only)"
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
                model,
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


def _start_ask(question: str, mode: str | None, scope: RequestScope | None = None) -> Job:
    def run(job: Job) -> dict[str, Any]:
        from dossier.sources.pubs import optional_pubs_hits

        cfg = apply_request_scope(Config.from_env(), scope or _default_scope())
        corpus = Corpus(evidence_db(Path(cfg.data_dir)))
        try:
            chosen = mode or cfg.ask_mode
            if chosen not in ASK_MODES:
                chosen = cfg.ask_mode
            budget = CallBudget(cfg.llm_max_calls)
            if chosen == "exact" or not cfg.llm_enabled:
                client: LLMClient = NullLLMClient()
            elif chosen == "auto":
                client = budget.wrap(LazyClient(cfg))
            else:
                client, code = client_for_mode(cfg, chosen)
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
                embedder=query_embedder(cfg, corpus),
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
            href, sentence = _loop_next(cfg, corpus, result.reason if result.refused else "")
            payload = {
                "question": question,
                "mode": chosen,
                "text": result.text,
                "citations": result.citations,
                "refused": result.refused,
                "reason": result.reason,
                "next": sentence if result.refused else "",
                "next_href": href if result.refused else "",
                "scope": scope_label(cfg),
            }
            job.push("answer", **payload)
            return payload
        finally:
            corpus.close()

    return RUNNER.start("ask", run, seed={"question": question})


def _start_match(spec: str, scope: RequestScope | None = None) -> Job:
    def run(job: Job) -> dict[str, Any]:
        from dossier.match import match_posting, write_match

        cfg = apply_request_scope(Config.from_env(), scope or _default_scope())
        corpus = Corpus(evidence_db(Path(cfg.data_dir)))
        try:
            report = match_posting(
                corpus,
                spec,
                cfg,
                embedder=query_embedder(cfg, corpus),
            )
            path = write_match(report, Path(cfg.data_dir) / "matches")
            data = report.as_dict()
            data["path"] = str(path)
            data["spec"] = spec
            data["scope"] = scope_label(cfg)
            reqs = data.get("requirements") or []
            data["met"] = sum(1 for req in reqs if req.get("evidence") and not req.get("gap"))
            data["gaps"] = sum(1 for req in reqs if req.get("gap"))
            for req in data.get("requirements") or []:
                gap = str(req.get("gap") or "")
                if not gap:
                    req["next"] = ""
                    req["next_href"] = ""
                    continue
                href, sentence = _loop_next(cfg, corpus, gap)
                req["next"] = sentence
                req["next_href"] = href
            return data
        finally:
            corpus.close()

    return RUNNER.start("match", run, seed={"spec": spec})


def _loop_next(cfg: Config, corpus: Corpus, reason: str) -> tuple[str, str]:
    from dossier.nextstep import next_step
    from dossier.ops import loop_counts

    counts = loop_counts(cfg, corpus)
    return next_step(
        records=counts["records"],
        pending=counts["pending"],
        approved=counts["approved"],
        spanned=counts["spanned"],
        vectors=counts["vectors"],
        detected=counts["detected"],
        reason=reason,
    )


def _start_tailor(posting: str, kind: str, arrange: bool) -> Job:
    def run(job: Job) -> dict[str, Any]:
        from dossier.llm import get_client, llm_egress_is_remote
        from dossier.ops import note_egress
        from dossier.prompts import start_prompt_log, stop_prompt_log
        from dossier.tailor import (
            CV_CAP,
            LETTER_CAP,
            arrange_letter,
            linkedin_subtitle,
            render_draft,
            select_cards,
            write_draft,
        )

        cfg = Config.from_env()
        corpus = Corpus(evidence_db(Path(cfg.data_dir)))
        try:
            limit = LETTER_CAP if kind == "letter" else CV_CAP
            picked, bare = select_cards(corpus, posting, limit=limit)
            paragraphs = None
            prompt_stamp = "prompts: none"
            if arrange and kind == "letter" and picked and cfg.llm_enabled:
                if llm_egress_is_remote(cfg):
                    note_egress(cfg)
                raw_client = get_client(cfg)
                arrange_model, arrange_note = select_fast_model(cfg, raw_client)
                if arrange_note:
                    note(arrange_note)
                client = CallBudget(cfg.llm_max_calls).wrap(raw_client)
                spans = [item.card.extras["span"] for item in picked]
                token = start_prompt_log()
                try:
                    paragraphs = arrange_letter(
                        spans,
                        client,
                        arrange_model,
                        max_num_ctx=cfg.llm_max_num_ctx,
                        timeout_seconds=cfg.llm_timeout_seconds,
                    )
                    prompt_stamp = stop_prompt_log(token, empty="none")
                except Exception:
                    stop_prompt_log(token, empty="none")
                    raise
            body = render_draft(
                kind=kind,
                posting=posting,
                picked=picked,
                bare=bare,
                name=cfg.cv_name,
                subtitle=linkedin_subtitle(corpus),
                paragraphs=paragraphs,
            )
            path = write_draft(body, Path(cfg.data_dir) / "drafts", prompt_stamp=prompt_stamp)
            return {"path": str(path), "body": body, "posting": posting, "kind": kind}
        finally:
            corpus.close()

    return RUNNER.start("tailor", run, seed={"posting": posting, "kind": kind})


def _kept_text(job: Job | None, result: dict[str, Any] | None, key: str) -> str:
    if isinstance(result, dict) and result.get(key):
        return str(result[key])
    if job is not None:
        return str(job.seed.get(key) or "")
    return ""


def _match_spec(job_id: str) -> str:
    """Posting text from a finished match job. Empty when the id is missing or not a match."""
    if not job_id:
        return ""
    job = RUNNER.get(job_id)
    if job is None or job.kind != "match" or job.status != "done" or not isinstance(job.result, dict):
        return ""
    return str(job.result.get("spec") or "")


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


def _brief_view(root: Path, request: Request, job: Job | None) -> dict[str, Any]:
    from dossier.brief import brief_blocks, list_briefs, read_brief

    directory = root / "briefs"
    names = list_briefs(directory)
    asked = request.query_params.get("file", "").strip()
    chosen = ""
    missing = False
    if asked:
        if asked in names:
            chosen = asked
        else:
            missing = True
    elif job and job.status == "done" and isinstance(job.result, dict):
        stem = Path(str(job.result.get("path") or "")).name
        if stem.endswith(".md"):
            stem = stem[: -len(".md")]
        if stem in names:
            chosen = stem
    if not chosen and not missing and names:
        chosen = names[0]
    text = read_brief(directory, chosen) if chosen else None
    return {
        "brief_names": names,
        "brief_name": chosen,
        "brief_blocks": brief_blocks(text) if text else [],
        "brief_missing": missing,
    }


def _start_brief(
    pack: str,
    posting: str,
    mode: str | None,
    scope: RequestScope | None = None,
) -> Job:
    def run(job: Job) -> dict[str, Any]:
        from dossier.brief import run_pack, write_brief
        from dossier.packs import posting_pack, resolve_pack
        from dossier.prompts import start_prompt_log, stop_prompt_log
        from dossier.ui import Progress

        cfg = apply_request_scope(Config.from_env(), scope or _default_scope())
        chosen = mode or cfg.ask_mode
        if chosen not in ASK_MODES:
            chosen = cfg.ask_mode
        if pack == "posting" or posting:
            if not posting:
                raise ValueError("posting pack needs posting text")
            questions = posting_pack(posting)
        else:
            questions = resolve_pack(pack, Path(cfg.data_dir))
        corpus = Corpus(evidence_db(Path(cfg.data_dir)))
        try:
            budget = CallBudget(cfg.llm_max_calls)
            if chosen == "exact" or not cfg.llm_enabled:
                client: LLMClient = NullLLMClient()
            elif chosen == "auto":
                client = budget.wrap(LazyClient(cfg))
            else:
                client, code = client_for_mode(cfg, chosen)
                if code is not None:
                    raise LLMClientError("model not ready for rich brief")
                client = budget.wrap(client)
            stage("brief", f"{len(questions)} questions · mode={chosen}")
            cited = 0
            refused = 0
            token = start_prompt_log()
            try:
                with Progress(len(questions), label="brief") as bar:

                    def on_progress(done: int, total: int, item, result) -> None:
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
                        embedder=query_embedder(cfg, corpus),
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
                "scope": scope_label(cfg),
            }
        finally:
            corpus.close()

    return RUNNER.start("brief", run)


def _start_run() -> Job:
    def run(job: Job) -> dict[str, Any]:
        from argparse import Namespace

        from dossier.cli import _brief, _extract_cards
        from dossier.ingest_run import run_ingest_targets

        cfg = Config.from_env()
        corpus = Corpus(evidence_db(Path(cfg.data_dir)))
        try:
            targets, skipped = detected_targets_report(cfg.run_adapters)
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
            code = 0
            try:
                code = _brief(
                    Namespace(mode=None, pack=None, posting=None),
                    cfg,
                    corpus,
                    budget=brief_budget,
                )
            except Exception as extra:
                note(str(extra))
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
