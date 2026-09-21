from dossier.config import Config
from dossier.llm import EGRESS_NOTICE, get_client, llm_egress_is_remote
from dossier.llm.client import NullLLMClient, OllamaClient
from dossier.llm.validate import validate_ollama_url
from dossier.llm.validate import LlmConfigError
import pytest


def test_ollama_loopback_is_not_egress() -> None:
    cfg = Config(llm_enabled=True, llm_provider="ollama", llm_base_url="http://127.0.0.1:11434")
    assert not llm_egress_is_remote(cfg)
    client = get_client(cfg)
    assert isinstance(client, OllamaClient)


def test_litellm_is_egress() -> None:
    cfg = Config(llm_enabled=True, llm_provider="litellm", llm_api_base="https://api.example/v1")
    assert llm_egress_is_remote(cfg)
    assert "leave this machine" in EGRESS_NOTICE


def test_disabled_llm_is_null() -> None:
    cfg = Config(llm_enabled=False)
    assert not llm_egress_is_remote(cfg)
    assert isinstance(get_client(cfg), NullLLMClient)


def test_remote_ollama_rejected_without_flag() -> None:
    with pytest.raises(LlmConfigError):
        validate_ollama_url("http://example.invalid:11434", allow_remote=False)
