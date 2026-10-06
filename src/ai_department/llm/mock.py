"""Провайдер с заранее заданными ответами. Тесты ядра ходят только сюда."""

from __future__ import annotations

from collections.abc import Sequence

from ai_department.domain.errors import ProviderError
from ai_department.llm.port import LlmRequest, LlmResponse


class MockLlmProvider:
    """Очередь ответов и ошибок. Сеть не открывает."""

    def __init__(self, responses: Sequence[LlmResponse | ProviderError] | None = None) -> None:
        self._responses: list[LlmResponse | ProviderError] = list(responses or [])
        self.calls: list[str] = []

    def complete(self, provider_model_name: str, request: LlmRequest) -> LlmResponse:
        self.calls.append(provider_model_name)
        del request
        if not self._responses:
            return LlmResponse(text="{}")
        item = self._responses.pop(0)
        if isinstance(item, ProviderError):
            raise item
        return item
