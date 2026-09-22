"""Runtime config. Ollama on loopback unless the user opts into egress.

A gitignored ``$DOSSIER_DATA/dossier.toml`` overrides code defaults.
Environment variables override the file.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from dossier.effort import DEFAULT_EFFORT, apply_effort, normalize_effort
from dossier.paths import data_dir, pubs_url, warehouse_db

ASK_MODES = ("exact", "auto", "rich")
DECOMPOSE_MODES = ("off", "auto", "on")
PLANNER_MODES = ("off", "rich")


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
    extract_chunk_chars: int = 4000
    extract_max_chunks: int = 4
    run_adapters: tuple[str, ...] = ()
    run_pack: str = "career"
    run_posting: str = ""
    lexicon: tuple[str, ...] | None = None
    llm_max_calls: int = 0
    llm_timeout_seconds: float = 300.0
    ask_cards_first: bool = True
    ask_passages: bool = True
    ask_hops: int = 1
    ask_decompose: str = "auto"
    ask_planner: str = "off"
    embed_model: str = "nomic-embed-text"
    ask_embed: bool = True
    ask_pubs: bool = False
    cv_name: str = ""
    referee_pubs: bool = True
    employer_filter: bool = True
    employer_filter_llm: bool = True
    employer_filter_llm_calls: int = 4
    effort: str = DEFAULT_EFFORT

    @classmethod
    def from_env(cls) -> Config:
        root = data_dir()
        file_cfg = _load_toml(root / "dossier.toml")
        llm = file_cfg.get("llm") if isinstance(file_cfg.get("llm"), dict) else {}
        ask = file_cfg.get("ask") if isinstance(file_cfg.get("ask"), dict) else {}
        extract = file_cfg.get("extract") if isinstance(file_cfg.get("extract"), dict) else {}
        run = file_cfg.get("run") if isinstance(file_cfg.get("run"), dict) else {}
        tailor = file_cfg.get("tailor") if isinstance(file_cfg.get("tailor"), dict) else {}
        employer = file_cfg.get("employer") if isinstance(file_cfg.get("employer"), dict) else {}

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
        effort = normalize_effort(
            _env_str(
                "DOSSIER_EFFORT",
                str(file_cfg.get("effort") or DEFAULT_EFFORT),
            )
        )
        cfg = cls(
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
            extract_chunk_chars=max(
                500,
                _env_int(
                    "DOSSIER_EXTRACT_CHUNK_CHARS",
                    _as_int(extract.get("chunk_chars"), 4000),
                ),
            ),
            extract_max_chunks=max(
                1,
                _env_int(
                    "DOSSIER_EXTRACT_MAX_CHUNKS",
                    _as_int(extract.get("max_chunks"), 4),
                ),
            ),
            run_adapters=adapters,
            run_pack=_env_str("DOSSIER_RUN_PACK", str(run.get("pack") or "career")).strip()
            or "career",
            run_posting=_env_str(
                "DOSSIER_RUN_POSTING",
                str(run.get("posting") or ""),
            ).strip(),
            lexicon=lexicon,
            llm_max_calls=max(
                0,
                _env_int("DOSSIER_LLM_MAX_CALLS", _as_int(llm.get("max_calls"), 0)),
            ),
            llm_timeout_seconds=max(
                30.0,
                _env_float(
                    "DOSSIER_LLM_TIMEOUT",
                    _as_float(llm.get("timeout"), 300.0),
                ),
            ),
            ask_cards_first=_env_bool(
                "DOSSIER_ASK_CARDS_FIRST",
                bool(ask.get("cards_first", True)),
            ),
            ask_passages=_env_bool(
                "DOSSIER_ASK_PASSAGES",
                bool(ask.get("passages", True)),
            ),
            ask_hops=max(0, _env_int("DOSSIER_ASK_HOPS", _as_int(ask.get("hops"), 1))),
            ask_decompose=_choice(
                _env_str("DOSSIER_ASK_DECOMPOSE", str(ask.get("decompose") or "auto")),
                DECOMPOSE_MODES,
                "auto",
            ),
            ask_planner=_choice(
                _env_str("DOSSIER_ASK_PLANNER", str(ask.get("planner") or "off")),
                PLANNER_MODES,
                "off",
            ),
            embed_model=_env_str(
                "DOSSIER_EMBED_MODEL",
                str(llm.get("embed_model") or "nomic-embed-text"),
            ).strip()
            or "nomic-embed-text",
            ask_embed=_env_bool("DOSSIER_ASK_EMBED", bool(ask.get("embed", True))),
            ask_pubs=_env_bool("DOSSIER_ASK_PUBS", bool(ask.get("pubs", False))),
            cv_name=_env_str("DOSSIER_CV_NAME", str(tailor.get("name") or "")).strip(),
            referee_pubs=_env_bool("DOSSIER_REFEREE_PUBS", True),
            employer_filter=_env_bool(
                "DOSSIER_EMPLOYER_FILTER",
                bool(employer.get("filter", True)),
            ),
            employer_filter_llm=_env_bool(
                "DOSSIER_EMPLOYER_FILTER_LLM",
                bool(employer.get("filter_llm", True)),
            ),
            employer_filter_llm_calls=max(
                0,
                _env_int(
                    "DOSSIER_EMPLOYER_FILTER_LLM_CALLS",
                    _as_int(employer.get("filter_llm_calls"), 4),
                ),
            ),
            effort=effort,
        )
        return apply_effort(cfg)


def _choice(value: str, allowed: tuple[str, ...], default: str) -> str:
    cleaned = value.strip().lower()
    if cleaned in allowed:
        return cleaned
    return default


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


def _as_float(value: object, default: float) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return default
    try:
        return float(value)
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


def _env_float(name: str, default: float) -> float:
    if name not in os.environ or not os.environ.get(name, "").strip():
        return default
    return _as_float(os.environ.get(name), default)
