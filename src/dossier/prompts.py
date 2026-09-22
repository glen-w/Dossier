"""Versioned prompt catalogue. Builtins match the previous inline strings.

Overrides live in ``$DOSSIER_DATA/prompts/overrides/<id>.json``.
Custom prompts live in ``$DOSSIER_DATA/prompts/custom/<id>.json``.
Active ids are ``[prompts]`` keys in gitignored ``dossier.toml``.
"""

from __future__ import annotations

import json
import re
from contextvars import ContextVar, Token
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dossier.paths import data_dir

FAMILIES = ("extract", "ask", "tailor")
ROLES = ("extract", "extract_seeker", "ask", "ask_plan", "tailor_arrange")
_SLUG = re.compile(r"^[a-z][a-z0-9_]{0,62}$")

EXTRACT_BODY = """You extract professional claim sentences for a CV locker.
Return JSON only: {"claims": [{"claim": "...", "citations": ["@@URI@@"]}]}
Each claim MUST be supported by the record text. Use only this URI in citations.
If nothing is a sellable professional claim, return {"claims": []}.
Do not invent employers, titles, or dates that are not in the text.

URI: @@URI@@
Title: @@TITLE@@
Text:
@@TEXT@@
"""

SEEKER_TAIL = """
This record was sought as professional work evidence, not a full inbox dump.
Optional keys per claim: "lens" (delivered|skills|contributions), "kind",
"skills" (list of strings), "org", "period". Prefer the Lens/Kind/Org/Year
header when present. Still refuse anything the text will not carry.
"""

ASK_BODY = """You answer a question about someone's professional work.
Use only the records below. Return JSON only:
{"answer": "...", "citations": ["uri", ...]}
Every citation must be a URI from the records. If the records do not answer
the question, return {"answer": "", "citations": []}.
Do not invent employers, dates, or titles.
@@PRIOR@@
Question: @@QUESTION@@

Records:
@@RECORDS@@
"""

PLAN_BODY = """Split the question into at most 4 shorter questions a record search can answer.
Return JSON only: {"questions": ["...", ...]}
Do not invent employers, dates, or titles.
Question: @@QUESTION@@
"""

ARRANGE_BODY = """Arrange a short letter using only the sentences below.
You may include this sentence once: "I am applying for the role in the posting."
Return JSON only: {"sentences": ["...", ...]}
Do not invent employers, dates, or titles.

Sentences:
@@SPANS@@
"""

SAMPLE_SLOTS = {
    "URI": "file://example/note.md",
    "TITLE": "Example note",
    "TEXT": "Led a workshop on coastal governance.",
    "PRIOR": "",
    "QUESTION": "What did I deliver?",
    "RECORDS": "URI: file://example/note.md\nTitle: Example\nText:\nLed a workshop.",
    "SPANS": "- Led a workshop on coastal governance.",
}

_LOG: ContextVar[list[str] | None] = ContextVar("dossier_prompt_log", default=None)


@dataclass(frozen=True)
class PromptDefinition:
    prompt_id: str
    version: int
    title: str
    family: str
    system_prompt: str
    user_template: str
    source: str = "builtin"

    def tag(self) -> str:
        return f"{self.prompt_id}@{self.version}"


def _builtin(
    prompt_id: str,
    title: str,
    family: str,
    user_template: str,
) -> PromptDefinition:
    return PromptDefinition(
        prompt_id=prompt_id,
        version=1,
        title=title,
        family=family,
        system_prompt="",
        user_template=user_template,
        source="builtin",
    )


BUILTINS: dict[str, PromptDefinition] = {
    "extract": _builtin("extract", "Extract claims", "extract", EXTRACT_BODY),
    "extract_seeker": _builtin(
        "extract_seeker",
        "Extract sought evidence",
        "extract",
        EXTRACT_BODY + SEEKER_TAIL,
    ),
    "ask": _builtin("ask", "Ask the locker", "ask", ASK_BODY),
    "ask_plan": _builtin("ask_plan", "Plan sub-questions", "ask", PLAN_BODY),
    "tailor_arrange": _builtin("tailor_arrange", "Arrange a letter", "tailor", ARRANGE_BODY),
}


def render(
    prompt: PromptDefinition,
    slots: dict[str, str],
    *,
    record: bool = True,
) -> str:
    body = prompt.user_template
    for key, value in slots.items():
        body = body.replace(f"@@{key}@@", value)
    system = prompt.system_prompt.strip()
    text = f"{system}\n\n{body}" if system else body
    if record:
        _note(prompt)
    return text


def start_prompt_log() -> Token[list[str] | None]:
    return _LOG.set([])


def stop_prompt_log(token: Token[list[str] | None], *, empty: str) -> str:
    tags = list(_LOG.get() or [])
    _LOG.reset(token)
    if not tags:
        return f"prompts: {empty}"
    return "prompts: " + ", ".join(tags)


def prompts_dir(root: Path | None = None) -> Path:
    return (root or data_dir()) / "prompts"


def list_catalogue(root: Path | None = None) -> list[PromptDefinition]:
    found: dict[str, PromptDefinition] = {}
    for prompt_id in BUILTINS:
        found[prompt_id] = _resolve_id(prompt_id, root)
    custom_root = prompts_dir(root) / "custom"
    if custom_root.is_dir():
        for path in sorted(custom_root.glob("*.json")):
            try:
                found[path.stem] = _load_file(path, source="custom")
            except (OSError, ValueError, json.JSONDecodeError):
                continue
    return [found[key] for key in sorted(found)]


def resolve(prompt_id: str, root: Path | None = None) -> PromptDefinition:
    cleaned = prompt_id.strip()
    if not cleaned:
        raise KeyError("empty prompt id")
    return _resolve_id(cleaned, root)


def active_prompt(role: str, root: Path | None = None) -> PromptDefinition:
    if role not in ROLES:
        raise KeyError(role)
    chosen = _active_ids(root).get(role) or role
    return resolve(chosen, root)


def active_map(root: Path | None = None) -> dict[str, str]:
    chosen = _active_ids(root)
    return {role: chosen.get(role) or role for role in ROLES}


def save_override(
    prompt_id: str,
    *,
    system_prompt: str,
    user_template: str,
    root: Path | None = None,
) -> PromptDefinition:
    if prompt_id not in BUILTINS:
        raise ValueError(f"{prompt_id} is not a builtin; save it as a custom prompt")
    current = _resolve_id(prompt_id, root)
    builtin = BUILTINS[prompt_id]
    prompt = PromptDefinition(
        prompt_id=prompt_id,
        version=current.version + 1,
        title=builtin.title,
        family=builtin.family,
        system_prompt=system_prompt,
        user_template=user_template,
        source="override",
    )
    _write_json(prompts_dir(root) / "overrides" / f"{prompt_id}.json", prompt)
    return prompt


def restore_builtin(prompt_id: str, root: Path | None = None) -> None:
    path = prompts_dir(root) / "overrides" / f"{prompt_id}.json"
    if path.is_file():
        path.unlink()


def save_custom(
    prompt_id: str,
    *,
    title: str,
    family: str,
    system_prompt: str,
    user_template: str,
    root: Path | None = None,
) -> PromptDefinition:
    cleaned = prompt_id.strip().lower()
    if not _SLUG.match(cleaned):
        raise ValueError(f"invalid prompt id {prompt_id!r}")
    if cleaned in BUILTINS:
        raise ValueError("builtin ids are saved as overrides")
    if family not in FAMILIES:
        raise ValueError(f"family must be one of {', '.join(FAMILIES)}")
    existing = prompts_dir(root) / "custom" / f"{cleaned}.json"
    version = 1
    if existing.is_file():
        version = _load_file(existing, source="custom").version + 1
    prompt = PromptDefinition(
        prompt_id=cleaned,
        version=version,
        title=title.strip() or cleaned,
        family=family,
        system_prompt=system_prompt,
        user_template=user_template,
        source="custom",
    )
    _write_json(existing, prompt)
    return prompt


def delete_custom(prompt_id: str, root: Path | None = None) -> None:
    path = prompts_dir(root) / "custom" / f"{prompt_id.strip().lower()}.json"
    if path.is_file():
        path.unlink()


def set_active(role: str, prompt_id: str, root: Path | None = None) -> None:
    if role not in ROLES:
        raise ValueError(f"unknown role {role}")
    resolve(prompt_id, root)
    from dossier.settings_io import read_toml_dict, write_toml_dict

    folder = root or data_dir()
    path = folder / "dossier.toml"
    data = read_toml_dict(path)
    block = dict(data.get("prompts") or {}) if isinstance(data.get("prompts"), dict) else {}
    if prompt_id == role:
        block.pop(role, None)
    else:
        block[role] = prompt_id
    if block:
        data["prompts"] = block
    else:
        data.pop("prompts", None)
    write_toml_dict(path, data)


def dry_run(prompt: PromptDefinition) -> str:
    return render(prompt, SAMPLE_SLOTS, record=False)


def _note(prompt: PromptDefinition) -> None:
    log = _LOG.get()
    if log is None:
        return
    tag = prompt.tag()
    if tag not in log:
        log.append(tag)


def _active_ids(root: Path | None) -> dict[str, str]:
    from dossier.settings_io import read_toml_dict

    folder = root or data_dir()
    data = read_toml_dict(folder / "dossier.toml")
    block = data.get("prompts")
    if not isinstance(block, dict):
        return {}
    out: dict[str, str] = {}
    for role in ROLES:
        chosen = str(block.get(role) or "").strip()
        if chosen:
            out[role] = chosen
    return out


def _resolve_id(prompt_id: str, root: Path | None) -> PromptDefinition:
    custom = prompts_dir(root) / "custom" / f"{prompt_id}.json"
    if custom.is_file():
        return _load_file(custom, source="custom")
    override = prompts_dir(root) / "overrides" / f"{prompt_id}.json"
    if override.is_file():
        loaded = _load_file(override, source="override")
        if loaded.prompt_id != prompt_id:
            raise ValueError(f"override file {prompt_id} has id {loaded.prompt_id}")
        return loaded
    if prompt_id in BUILTINS:
        return BUILTINS[prompt_id]
    raise KeyError(prompt_id)


def _load_file(path: Path, *, source: str) -> PromptDefinition:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("prompt file must be a JSON object")
    family = str(data.get("family") or "")
    if family not in FAMILIES:
        raise ValueError("prompt family is missing")
    prompt_id = str(data.get("prompt_id") or path.stem)
    return PromptDefinition(
        prompt_id=prompt_id,
        version=max(1, int(data.get("version") or 1)),
        title=str(data.get("title") or prompt_id),
        family=family,
        system_prompt=str(data.get("system_prompt") or ""),
        user_template=str(data.get("user_template") or ""),
        source=source,
    )


def _write_json(path: Path, prompt: PromptDefinition) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "prompt_id": prompt.prompt_id,
        "version": prompt.version,
        "title": prompt.title,
        "family": prompt.family,
        "system_prompt": prompt.system_prompt,
        "user_template": prompt.user_template,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
