"""Local-first LLM client. Ollama default; cloud is opt-in with an egress notice."""

from __future__ import annotations

from dossier.llm.client import (
    CompletionRequest,
    LiteLLMClient,
    LLMClient,
    LLMClientError,
    NullLLMClient,
    OllamaClient,
    ctx_tokens_for,
    get_client,
    get_client_impl,
)
from dossier.llm.validate import (
    EGRESS_NOTICE,
    LlmConfigError,
    LlmExtraMissingError,
    llm_egress_is_remote,
    reject_litellm_ollama_model,
)

__all__ = [
    "CompletionRequest",
    "EGRESS_NOTICE",
    "LLMClient",
    "LLMClientError",
    "LiteLLMClient",
    "LlmConfigError",
    "LlmExtraMissingError",
    "NullLLMClient",
    "OllamaClient",
    "ctx_tokens_for",
    "get_client",
    "get_client_impl",
    "llm_egress_is_remote",
    "reject_litellm_ollama_model",
]
