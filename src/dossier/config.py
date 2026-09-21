"""Runtime config. Ollama on loopback unless the user opts into egress."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dossier.paths import data_dir, pubs_url, warehouse_db


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

    @classmethod
    def from_env(cls) -> Config:
        provider = os.environ.get("DOSSIER_LLM_PROVIDER", "ollama").strip().lower()
        enabled = provider not in {"off", "none", "null", "disabled"}
        allow_remote = os.environ.get("DOSSIER_LLM_ALLOW_REMOTE", "").lower() in {
            "1",
            "true",
            "yes",
        }
        return cls(
            llm_enabled=enabled,
            llm_provider="ollama" if provider in {"off", "none", "null", "disabled"} else provider,
            llm_base_url=os.environ.get("DOSSIER_LLM_BASE_URL", "http://127.0.0.1:11434"),
            llm_allow_remote=allow_remote,
            llm_api_base=os.environ.get("DOSSIER_LLM_API_BASE") or None,
            llm_model=os.environ.get("DOSSIER_LLM_MODEL", "qwen3.8:latest"),
            data_dir=str(data_dir()),
            warehouse=str(warehouse_db()),
            pubs_url=pubs_url(),
        )
