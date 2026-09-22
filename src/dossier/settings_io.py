"""Read and write gitignored ``dossier.toml`` patches for settings and profiles.

Environment variables still win at load time via ``Config.from_env``. Saving
only updates the file; it does not change the process environment.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any


def read_toml_dict(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    return data if isinstance(data, dict) else {}


def merge_toml_patch(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Shallow-merge top-level keys; dict values merge one level deep."""
    out = dict(current)
    for key, value in patch.items():
        if isinstance(value, dict):
            existing = out.get(key)
            base = dict(existing) if isinstance(existing, dict) else {}
            base.update(value)
            out[key] = base
        else:
            out[key] = value
    return out


def write_toml_dict(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_dump_toml(data), encoding="utf-8")


def common_settings_patch(
    *,
    effort: str | None = None,
    model: str | None = None,
    max_calls: int | None = None,
    ask_mode: str | None = None,
    extract_llm: bool | None = None,
    ask_planner: str | None = None,
) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    if effort is not None:
        patch["effort"] = effort
    llm: dict[str, Any] = {}
    if model is not None:
        llm["model"] = model
    if max_calls is not None:
        llm["max_calls"] = int(max_calls)
    if llm:
        patch["llm"] = llm
    ask: dict[str, Any] = {}
    if ask_mode is not None:
        ask["mode"] = ask_mode
    if ask_planner is not None:
        ask["planner"] = ask_planner
    if ask:
        patch["ask"] = ask
    if extract_llm is not None:
        patch["extract"] = {"llm": bool(extract_llm)}
    return patch


def save_common_settings(path: Path, patch: dict[str, Any]) -> None:
    current = read_toml_dict(path)
    write_toml_dict(path, merge_toml_patch(current, patch))


def _dump_toml(data: dict[str, Any]) -> str:
    """Minimal TOML writer for Dossier settings tables and scalars."""
    lines: list[str] = [
        "# Written by the Dossier workbench. Environment variables still win at load time.",
        "",
    ]
    # Top-level scalars first (effort, lexicon, …).
    for key in sorted(k for k, v in data.items() if not isinstance(v, dict)):
        lines.append(f"{key} = {_toml_value(data[key])}")
    if any(not isinstance(v, dict) for v in data.values()):
        lines.append("")
    for key in sorted(k for k, v in data.items() if isinstance(v, dict)):
        block = data[key]
        if not isinstance(block, dict):
            continue
        # Nested tables like [identity.mail_accounts] are preserved as flat
        # dotted sections only when values are themselves dicts.
        plain = {k: v for k, v in block.items() if not isinstance(v, dict)}
        nested = {k: v for k, v in block.items() if isinstance(v, dict)}
        if plain or not nested:
            lines.append(f"[{key}]")
            for sub in sorted(plain):
                lines.append(f"{sub} = {_toml_value(plain[sub])}")
            lines.append("")
        for sub_key in sorted(nested):
            lines.append(f"[{key}.{sub_key}]")
            for leaf, value in sorted(nested[sub_key].items()):
                lines.append(f"{leaf} = {_toml_value(value)}")
            lines.append("")
    text = "\n".join(lines).rstrip() + "\n"
    return text


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, list):
        inner = ", ".join(_toml_value(item) for item in value)
        return f"[{inner}]"
    if value is None:
        return '""'
    return _toml_string(str(value))


def _toml_string(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'
