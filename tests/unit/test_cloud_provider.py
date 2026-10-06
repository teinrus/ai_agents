"""Облачный адаптер на подменённом транспорте, без сети."""

import httpx

from ai_department.domain.errors import ProviderError
from ai_department.llm.cloud import CloudLlmProvider
from ai_department.llm.port import ChatMessage, LlmRequest


def test_cloud_adapter_rejects_auth_without_leaking_the_key() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "no"})

    provider = CloudLlmProvider(
        base_url="http://cloud.example/v1",
        api_key="cloud-secret",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    try:
        provider.complete(
            "cloud-model", LlmRequest(messages=(ChatMessage("user", "ping"),), tools=())
        )
    except ProviderError as exc:
        assert exc.kind == "auth"
        assert "Облачный" in exc.message
        assert "cloud-secret" not in exc.message
    else:
        raise AssertionError("ожидался отказ ключа")
    provider.close()
