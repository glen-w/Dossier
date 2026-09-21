"""Runtime config. Ollama on loopback unless the user opts into egress.

A gitignored ``$DOSSIER_DATA/dossier.toml`` overrides code defaults.
Environment variables override the file.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from dossier.paths import data_dir, pubs_url, warehouse_db

ASK_MODES = ("exact", "auto", "rich")


@dataclass(frozen=True)
class Config:
    llm_enabled: bool = True
    llm_provider: str = "ollama"
    llm_base_url: str = "http://127.0.0.1:11434"
    llm_allow_remote: bool = False
    llm_api_base: str | None = None
    llm_model: str = "qwen3.8:latest"
    data_dir: str = ""
    warehouse: str = ""
    pubs_url: str = ""
    ask_mode: str = "auto"
    ask_limit: int = 5
    ask_fts: bool = True
    extract_llm: bool = True
    run_adapters: tuple[str, ...] = ()
    run_pack: str = "career"
    lexicon: tuple[str, ...] | None = None

    @classmethod
    def from_env(cls) -> Config:
        root = data_dir()
        file_cfg = _load_toml(root / "dossier.toml")
        llm = file_cfg.get("llm") if isinstance(file_cfg.get("llm"), dict) else {}
        ask = file_cfg.get("ask") if isinstance(file_cfg.get("ask"), dict) else {}
        extract = file_cfg.get("extract") if isinstance(file_cfg.get("extract"), dict) else {}
        run = file_cfg.get("run") if isinstance(file_cfg.get("run"), dict) else {}

        provider = _env_str(
            "DOSSIER_LLM_PROVIDER",
            str(llm.get("provider") or "ollama"),
        ).strip().lower()
        enabled = provider not in {"off", "none", "null", "disabled"}
        allow_remote = _env_bool(
            "DOSSIER_LLM_ALLOW_REMOTE",
            bool(llm.get("allow_remote", False)),
        )
        api_base = _env_str(
            "DOSSIER_LLM_API_BASE",
            str(llm.get("api_base") or ""),
        ).strip()
        mode = _env_str("DOSSIER_ASK_MODE", str(ask.get("mode") or "auto")).strip().lower()
        if mode not in ASK_MODES:
            mode = "auto"
        adapters = _name_list(
            _env_str("DOSSIER_RUN_ADAPTERS", _join_list(run.get("adapters")))
        )
        lexicon = _lexicon(file_cfg)
        if "DOSSIER_LEXICON" in os.environ:
            lexicon = tuple(_name_list(os.environ.get("DOSSIER_LEXICON", "")))
        return cls(
            llm_enabled=enabled,
            llm_provider="ollama" if not enabled else provider,
            llm_base_url=_env_str(
                "DOSSIER_LLM_BASE_URL",
                str(llm.get("base_url") or "http://127.0.0.1:11434"),
            ),
            llm_allow_remote=allow_remote,
            llm_api_base=api_base or None,
            llm_model=_env_str(
                "DOSSIER_LLM_MODEL",
                str(llm.get("model") or "qwen3.8:latest"),
            ),
            data_dir=str(root),
            warehouse=str(warehouse_db()),
            pubs_url=pubs_url(),
            ask_mode=mode,
            ask_limit=_env_int("DOSSIER_ASK_LIMIT", _as_int(ask.get("limit"), 5)),
            ask_fts=_env_bool("DOSSIER_ASK_FTS", bool(ask.get("fts", True))),
            extract_llm=_env_bool("DOSSIER_EXTRACT_LLM", bool(extract.get("llm", True))),
            run_adapters=adapters,
            run_pack=_env_str("DOSSIER_RUN_PACK", str(run.get("pack") or "career")).strip()
            or "career",
            lexicon=lexicon,
        )


def _load_toml(path: Path) -> dict:
    if not path.is_file():
        return {}
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    return data if isinstance(data, dict) else {}


def _lexicon(file_cfg: dict) -> tuple[str, ...] | None:
    if "lexicon" not in file_cfg:
        return None
    return tuple(_name_list(_join_list(file_cfg.get("lexicon"))))


def _join_list(value: object) -> str:
    if isinstance(value, list):
        return ",".join(str(item) for item in value if str(item).strip())
    if value is None:
        return ""
    return str(value)


def _name_list(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def _as_int(value: object, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int | str):
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_str(name: str, default: str) -> str:
    if name not in os.environ:
        return default
    return os.environ.get(name, "")


def _env_bool(name: str, default: bool) -> bool:
    if name not in os.environ:
        return default
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}


def _env_int(name: str, default: int) -> int:
    if name not in os.environ or not os.environ.get(name, "").strip():
        return default
    return _as_int(os.environ.get(name), default)
