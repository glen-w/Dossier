"""Cap model completions for one process. A spent budget does not open a socket."""

from __future__ import annotations

from typing import Any

from dossier.llm.client import CompletionRequest, LLMClient, LLMClientError


class CallBudget:
    def __init__(self, max_calls: int) -> None:
        self.max_calls = max(0, max_calls)
        self.calls = 0

    @property
    def remaining(self) -> bool:
        return self.calls < self.max_calls

    def wrap(self, inner: LLMClient) -> LLMClient:
        return _BudgetClient(inner, self)


class _BudgetClient:
    def __init__(self, inner: LLMClient, budget: CallBudget) -> None:
        self._inner = inner
        self._budget = budget
        self.provider = getattr(inner, "provider", "budget")

    def check_config(self, model: str) -> tuple[bool, str]:
        return self._inner.check_config(model)

    def complete(self, request: CompletionRequest) -> str:
        self._take()
        return self._inner.complete(request)

    def complete_json(self, request: CompletionRequest) -> dict[str, Any]:
        self._take()
        return self._inner.complete_json(request)

    def _take(self) -> None:
        if self._budget.calls >= self._budget.max_calls:
            raise LLMClientError("model call budget spent")
        self._budget.calls += 1
