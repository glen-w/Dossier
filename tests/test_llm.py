from unittest.mock import patch

import httpx
import pytest

from dossier.config import Config
from dossier.llm import EGRESS_NOTICE, get_client, llm_egress_is_remote
from dossier.llm.client import CompletionRequest, LLMClientError, NullLLMClient, OllamaClient
from dossier.llm.validate import LlmConfigError, validate_ollama_url


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


def test_egress_status_names_the_only_way_text_leaves() -> None:
    from dossier.llm import egress_status

    local = Config(llm_enabled=True, llm_provider="ollama", llm_base_url="http://127.0.0.1:11434")
    assert egress_status(local).startswith("egress: no")
    remote = Config(
        llm_enabled=True,
        llm_provider="litellm",
        llm_allow_remote=False,
        llm_api_base="https://api.example/v1",
    )
    assert egress_status(remote).startswith("egress: yes")
    blocked = Config(
        llm_enabled=True,
        llm_provider="ollama",
        llm_base_url="http://example.invalid:11434",
        llm_allow_remote=False,
    )
    assert "blocked" in egress_status(blocked)
    assert not llm_egress_is_remote(blocked)


def test_blocked_remote_ollama_is_not_egress() -> None:
    cfg = Config(
        llm_enabled=True,
        llm_provider="ollama",
        llm_base_url="http://example.invalid:11434",
        llm_allow_remote=False,
    )
    assert not llm_egress_is_remote(cfg)


def test_ollama_think_flag_is_sent_only_when_set() -> None:
    client = OllamaClient(base_url="http://127.0.0.1:11434", allow_remote=False)
    captured: dict = {}

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"response": "ok"}

    def _post(url: str, json: dict) -> _Resp:  # noqa: A002
        captured["url"] = url
        captured["payload"] = json
        return _Resp()

    with patch("dossier.llm.client.httpx.Client") as mock_cls:
        mock_cls.return_value.__enter__.return_value.post.side_effect = _post
        client.complete(CompletionRequest(model="toy", prompt="hi", think=False))
        assert captured["payload"]["think"] is False
        client.complete(CompletionRequest(model="toy", prompt="hi"))
        assert "think" not in captured["payload"]


def test_ollama_timeout_is_llm_client_error() -> None:
    client = OllamaClient(base_url="http://127.0.0.1:11434", allow_remote=False)
    req = CompletionRequest(model="toy", prompt="hi", timeout_seconds=1.0)
    with patch("dossier.llm.client.httpx.Client") as mock_cls:
        mock_cls.return_value.__enter__.return_value.post.side_effect = httpx.ReadTimeout(
            "timed out"
        )
        with pytest.raises(LLMClientError, match="timed out"):
            client.complete(req)
