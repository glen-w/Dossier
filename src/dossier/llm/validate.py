"""Plan-time LLM config validation. Shape copied from Paperful."""

from __future__ import annotations

from urllib.parse import urlparse

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

EGRESS_NOTICE = (
    "Remote LLM is on — the prompt for this call may leave this machine. "
    "The corpus file stays local. This stays off unless the provider is litellm "
    "or DOSSIER_LLM_ALLOW_REMOTE is set."
)


class LlmConfigError(Exception):
    """Invalid or incomplete LLM configuration."""


class LlmExtraMissingError(LlmConfigError):
    """LiteLLM path selected but dossier[llm] is not installed."""


def validate_ollama_url(url: str, allow_remote: bool) -> None:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise LlmConfigError(
            f"Ollama URL scheme {parsed.scheme!r} is not supported; use http or https."
        )
    host = parsed.hostname
    if not host:
        raise LlmConfigError("Ollama URL must include a hostname.")
    if host not in LOCAL_HOSTS and not allow_remote:
        raise LlmConfigError(
            f"Ollama URL host {host!r} is not local. "
            "Set DOSSIER_LLM_ALLOW_REMOTE=true to permit non-loopback endpoints."
        )


def reject_litellm_ollama_model(model: str) -> None:
    low = model.strip().lower()
    if low.startswith(("ollama/", "ollama:")):
        raise LlmConfigError(
            f"model {model!r} must use DOSSIER_LLM_PROVIDER=ollama, not litellm."
        )


def validate_llm_api_base(url: str | None) -> None:
    if not url or not str(url).strip():
        return
    parsed = urlparse(str(url).strip())
    if parsed.scheme not in {"http", "https"}:
        raise LlmConfigError("llm.api_base must use http or https.")


def host_is_local(url: str) -> bool:
    """True for loopback hosts. Anything else can leave the machine."""
    host = urlparse((url or "").strip()).hostname
    return bool(host) and host in LOCAL_HOSTS


def llm_egress_is_remote(cfg) -> bool:
    """True when a model call is allowed to leave the machine.

    Off by default. On only for provider ``litellm``, or Ollama with
    ``allow_remote``. A non-loopback Ollama URL without that flag is
    refused by the client and reports False here (doctor says blocked;
    no egress notice).
    """
    if not cfg.llm_enabled:
        return False
    if cfg.llm_provider == "litellm":
        return True
    if cfg.llm_allow_remote:
        return True
    try:
        validate_ollama_url(cfg.llm_base_url, False)
    except LlmConfigError:
        return False
    return False


def egress_status(cfg) -> str:
    """One line for ``dossier doctor``. Records stay local unless remote LLM is on."""
    if not cfg.llm_enabled:
        return "egress: no (provider off; records stay on this machine)"
    if cfg.llm_provider == "litellm" or cfg.llm_allow_remote:
        return "egress: yes (remote LLM; the prompt may leave this machine)"
    try:
        validate_ollama_url(cfg.llm_base_url, False)
    except LlmConfigError:
        return (
            "egress: no (remote URL blocked; "
            "set DOSSIER_LLM_ALLOW_REMOTE to opt in)"
        )
    return "egress: no (Ollama on loopback; records stay on this machine)"
