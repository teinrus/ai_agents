"""Адаптер OpenAI-совместимого локального endpoint. По умолчанию выключен."""

from __future__ import annotations

import httpx

from ai_department.llm.openai_chat import complete_openai_chat
from ai_department.llm.port import LlmRequest, LlmResponse


class LocalLlmProvider:
    """HTTP-адаптер. Ключ и URL приходят из корня сборки, в события не пишутся."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = client if client is not None else httpx.Client(timeout=60.0)
        self._owns_client = client is None

    def close(self) -> None:
        """Закрывает собственный HTTP-клиент."""
        if self._owns_client:
            self._client.close()

    def complete(self, provider_model_name: str, request: LlmRequest) -> LlmResponse:
        return complete_openai_chat(
            client=self._client,
            base_url=self._base_url,
            api_key=self._api_key,
            provider_model_name=provider_model_name,
            request=request,
            subject="локального",
            title="Локальный",
        )
