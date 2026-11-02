"""Settings, lists, prompts, packs, profiles."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from dossier.ask import ASK_MODES
from dossier.config import Config
from dossier.effort import DEFAULT_EFFORT, EFFORT_NAMES, effort_blurb, normalize_effort
from dossier.lists import PHRASE_LISTS, phrase_list_groups, phrase_list_patch
from dossier.profiles import (
    VIRTUAL_DEFAULT,
    activate_profile,
    delete_profile,
    list_profiles,
    save_profile,
)
from dossier.scope import scope_toml
from dossier.settings_io import common_settings_patch, save_common_settings
from dossier.web.context import (
    _egress_notice,
    _page,
    _posted_scope,
    _profile_scope,
    _q,
    _scope_template,
)

router = APIRouter()

@router.get("/settings", response_class=HTMLResponse)
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
        **_scope_template(cfg),
    )

@router.post("/settings/save")
async def settings_save(
    effort: str = Form(DEFAULT_EFFORT),
    model: str = Form(""),
    fast: str = Form(""),
    max_calls: str = Form("0"),
    ask_mode: str = Form("auto"),
    extract_llm: str = Form(""),
    ask_planner: str = Form("off"),
    scope_form: str = Form(""),
    sources: list[str] = Form(default=[]),
    year_from: str = Form(""),
    year_to: str = Form(""),
) -> RedirectResponse:
    cfg = Config.from_env()
    path = Path(cfg.data_dir) / "dossier.toml"
    try:
        calls = max(0, int(max_calls.strip() or "0"))
    except ValueError:
        return RedirectResponse("/settings?err=max_calls", status_code=303)
    mode = ask_mode if ask_mode in ASK_MODES else "auto"
    planner = ask_planner if ask_planner in {"off", "rich"} else "off"
    scope_patch = None
    if scope_form == "1":
        try:
            posted = _posted_scope("1", sources, year_from, year_to, "")
        except ValueError as exc:
            return RedirectResponse(f"/settings?err={_q(str(exc))}", status_code=303)
        scope_patch = scope_toml(posted.sources, posted.year_from, posted.year_to)
    patch = common_settings_patch(
        effort=normalize_effort(effort),
        model=model.strip() or cfg.llm_model,
        fast=fast.strip() or cfg.llm_fast,
        max_calls=calls,
        ask_mode=mode,
        extract_llm=extract_llm in {"1", "true", "on", "yes"},
        ask_planner=planner,
        scope=scope_patch,
    )
    save_common_settings(path, patch)
    return RedirectResponse("/settings?saved=1", status_code=303)

@router.get("/settings/lists", response_class=HTMLResponse)
async def lists_page(request: Request) -> HTMLResponse:
    cfg = Config.from_env()
    root = Path(cfg.data_dir)
    return _page(
        request,
        "lists.html",
        "lists",
        groups=phrase_list_groups(),
        toml_path=str(root / "dossier.toml"),
        saved=request.query_params.get("saved") == "1",
    )

@router.post("/settings/lists")
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

@router.post("/settings/profile/save")
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
                "llm": {
                    "model": cfg.llm_model,
                    "fast": cfg.llm_fast,
                    "max_calls": cfg.llm_max_calls,
                },
                "ask": {"mode": cfg.ask_mode, "planner": cfg.ask_planner},
                "extract": {"llm": cfg.extract_llm},
                "scope": _profile_scope(cfg),
            },
            root=root,
        )
    except ValueError as exc:
        return RedirectResponse(f"/settings?err={_q(str(exc))}", status_code=303)
    return RedirectResponse("/settings?saved=1", status_code=303)

@router.post("/settings/profile/activate")
async def profile_activate(name: str = Form(...)) -> RedirectResponse:
    cfg = Config.from_env()
    try:
        activate_profile(name.strip(), Path(cfg.data_dir))
    except (OSError, ValueError, FileNotFoundError) as exc:
        return RedirectResponse(f"/settings?err={_q(str(exc))}", status_code=303)
    return RedirectResponse("/settings?saved=1", status_code=303)

@router.post("/settings/profile/delete")
async def profile_delete(name: str = Form(...)) -> RedirectResponse:
    cfg = Config.from_env()
    try:
        delete_profile(name.strip(), Path(cfg.data_dir))
    except ValueError as exc:
        return RedirectResponse(f"/settings?err={_q(str(exc))}", status_code=303)
    return RedirectResponse("/settings?saved=1", status_code=303)

@router.get("/settings/prompts", response_class=HTMLResponse)
async def prompts_page(request: Request) -> HTMLResponse:
    from dossier.prompts import (
        FAMILIES,
        ROLES,
        active_map,
        dry_run,
        list_catalogue,
        resolve,
    )

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
        "prompts",
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

@router.post("/settings/prompts/override")
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

@router.post("/settings/prompts/restore")
async def prompts_restore(prompt_id: str = Form(...)) -> RedirectResponse:
    from dossier.prompts import restore_builtin

    cfg = Config.from_env()
    restore_builtin(prompt_id.strip(), Path(cfg.data_dir))
    return RedirectResponse(f"/settings/prompts?id={prompt_id}&saved=1", status_code=303)

@router.post("/settings/prompts/custom")
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

@router.post("/settings/prompts/activate")
async def prompts_activate(role: str = Form(...), prompt_id: str = Form(...)) -> RedirectResponse:
    from dossier.prompts import set_active

    cfg = Config.from_env()
    try:
        set_active(role.strip(), prompt_id.strip(), Path(cfg.data_dir))
    except (OSError, ValueError, KeyError) as exc:
        return RedirectResponse(f"/settings/prompts?err={_q(str(exc))}", status_code=303)
    return RedirectResponse("/settings/prompts?saved=1", status_code=303)

@router.get("/settings/packs", response_class=HTMLResponse)
async def packs_page(request: Request) -> HTMLResponse:
    import json as _json

    from dossier.packs import (
        CAREER,
        list_saved_packs,
        questions_payload,
        resolve_pack,
    )

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
        "packs",
        cfg=cfg,
        pack_name=selected,
        pack_body=body,
        saved_packs=list_saved_packs(root),
        notice=_egress_notice(cfg),
        saved=request.query_params.get("saved") == "1",
    )

@router.post("/settings/packs/save")
async def packs_save(name: str = Form(...), body: str = Form(...)) -> RedirectResponse:
    from dossier.packs import save_named_pack

    cfg = Config.from_env()
    try:
        save_named_pack(name, body, Path(cfg.data_dir))
    except (OSError, ValueError) as exc:
        return RedirectResponse(f"/settings/packs?err={_q(str(exc))}", status_code=303)
    return RedirectResponse(f"/settings/packs?pack={name.strip().lower()}&saved=1", status_code=303)

@router.post("/settings/packs/delete")
async def packs_delete(name: str = Form(...)) -> RedirectResponse:
    from dossier.packs import delete_named_pack

    cfg = Config.from_env()
    try:
        delete_named_pack(name, Path(cfg.data_dir))
    except ValueError as exc:
        return RedirectResponse(f"/settings/packs?err={_q(str(exc))}", status_code=303)
    return RedirectResponse("/settings/packs?saved=1", status_code=303)
