"""Named config overlays under ``$DOSSIER_DATA/profiles/``.

A profile is not identity, not effort itself, and not a referee. Virtual
``default`` is code defaults and is never a file on disk.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dossier.effort import DEFAULT_EFFORT, normalize_effort
from dossier.paths import data_dir

VIRTUAL_DEFAULT = "default"
_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
_ALLOWED_TOP = frozenset({"effort", "llm", "ask", "extract", "scope"})
_ALLOWED_SCOPE = frozenset({"all_sources", "sources", "year_from", "year_to"})
_ALLOWED_LLM = frozenset({"model", "fast", "max_calls", "provider", "timeout", "embed_model"})
_ALLOWED_ASK = frozenset({"mode", "limit", "planner", "decompose", "hops"})
_ALLOWED_EXTRACT = frozenset({"llm", "chunk_chars", "max_chunks"})


@dataclass(frozen=True)
class Profile:
    name: str
    description: str
    config: dict[str, Any]
    path: Path | None = None

    @property
    def is_virtual(self) -> bool:
        return self.path is None and self.name == VIRTUAL_DEFAULT


def profiles_dir(root: Path | None = None) -> Path:
    return (root or data_dir()) / "profiles"


def list_profiles(root: Path | None = None) -> list[Profile]:
    items = [virtual_default()]
    folder = profiles_dir(root)
    if not folder.is_dir():
        return items
    for path in sorted(folder.glob("*.json")):
        try:
            items.append(load_profile(path.stem, root))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return items


def virtual_default() -> Profile:
    return Profile(
        name=VIRTUAL_DEFAULT,
        description="Built-in defaults. Not a file on disk.",
        config={},
        path=None,
    )


def load_profile(name: str, root: Path | None = None) -> Profile:
    cleaned = name.strip().lower()
    if cleaned == VIRTUAL_DEFAULT:
        return virtual_default()
    if not _SLUG.match(cleaned):
        raise ValueError(f"invalid profile name {name!r}")
    path = profiles_dir(root) / f"{cleaned}.json"
    if not path.is_file():
        raise FileNotFoundError(f"profile {cleaned!r} not found")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("profile must be a JSON object")
    config = _sanitize_config(data.get("config") if isinstance(data.get("config"), dict) else {})
    return Profile(
        name=str(data.get("name") or cleaned).strip() or cleaned,
        description=str(data.get("description") or "").strip(),
        config=config,
        path=path,
    )


def save_profile(
    name: str,
    *,
    description: str = "",
    config: dict[str, Any] | None = None,
    root: Path | None = None,
) -> Profile:
    cleaned = name.strip().lower()
    if cleaned == VIRTUAL_DEFAULT:
        raise ValueError("cannot overwrite the virtual default profile")
    if not _SLUG.match(cleaned):
        raise ValueError(f"invalid profile name {name!r}")
    folder = profiles_dir(root)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{cleaned}.json"
    payload = {
        "name": cleaned,
        "description": description.strip(),
        "config": _sanitize_config(config or {}),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return Profile(
        name=cleaned,
        description=payload["description"],
        config=payload["config"],
        path=path,
    )


def delete_profile(name: str, root: Path | None = None) -> None:
    cleaned = name.strip().lower()
    if cleaned == VIRTUAL_DEFAULT:
        raise ValueError("cannot delete the virtual default profile")
    path = profiles_dir(root) / f"{cleaned}.json"
    if path.is_file():
        path.unlink()


def activate_profile(name: str, root: Path | None = None) -> dict[str, Any]:
    """Merge the profile overlay into ``dossier.toml``. Returns the merged patch."""
    from dossier.settings_io import merge_toml_patch, read_toml_dict, write_toml_dict

    profile = load_profile(name, root)
    data_root = root or data_dir()
    path = data_root / "dossier.toml"
    current = read_toml_dict(path)
    patch = profile_to_toml_patch(profile)
    if profile.is_virtual:
        # Reset effort to balanced; leave other sections alone.
        patch = {"effort": DEFAULT_EFFORT}
    merged = merge_toml_patch(current, patch)
    write_toml_dict(path, merged)
    return patch


def profile_to_toml_patch(profile: Profile) -> dict[str, Any]:
    cfg = dict(profile.config)
    patch: dict[str, Any] = {}
    if "effort" in cfg:
        patch["effort"] = normalize_effort(str(cfg["effort"]))
    for section in ("llm", "ask", "extract"):
        block = cfg.get(section)
        if isinstance(block, dict) and block:
            patch[section] = dict(block)
    scope = cfg.get("scope")
    if isinstance(scope, dict):
        block: dict[str, Any] = {}
        if scope.get("all_sources"):
            block["all"] = True
            block["sources"] = []
        elif isinstance(scope.get("sources"), list):
            block["all"] = False
            block["sources"] = list(scope["sources"])
        for key in ("year_from", "year_to"):
            if key in scope:
                block[key] = int(scope[key])
        if block:
            patch["scope"] = block
    return patch


def _sanitize_scope(raw: dict[str, Any]) -> dict[str, Any]:
    raw = {key: value for key, value in raw.items() if key in _ALLOWED_SCOPE}
    cleaned: dict[str, Any] = {}
    if raw.get("all_sources") is True:
        cleaned["all_sources"] = True
    elif isinstance(raw.get("sources"), list):
        cleaned["sources"] = [str(item).strip() for item in raw["sources"] if str(item).strip()]
    for key in ("year_from", "year_to"):
        if key not in raw:
            continue
        try:
            cleaned[key] = int(raw[key])
        except (TypeError, ValueError):
            continue
    return cleaned


def _sanitize_config(raw: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if key not in _ALLOWED_TOP:
            continue
        if key == "effort":
            out["effort"] = normalize_effort(str(value))
            continue
        if key == "scope":
            if isinstance(value, dict):
                cleaned_scope = _sanitize_scope(value)
                if cleaned_scope:
                    out["scope"] = cleaned_scope
            continue
        if not isinstance(value, dict):
            continue
        allowed = {
            "llm": _ALLOWED_LLM,
            "ask": _ALLOWED_ASK,
            "extract": _ALLOWED_EXTRACT,
        }[key]
        cleaned = {k: value[k] for k in value if k in allowed}
        if cleaned:
            out[key] = cleaned
    return out
