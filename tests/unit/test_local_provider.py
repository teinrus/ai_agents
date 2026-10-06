"""Локальный адаптер на подменённом транспорте, без сети."""

import json

import httpx

from ai_department.domain.errors import ProviderError
from ai_department.domain.tools import ToolCall
from ai_department.llm.local import LocalLlmProvider
from ai_department.llm.port import ChatMessage, LlmRequest, ToolSchema


def _provider(handler: httpx.MockTransport) -> LocalLlmProvider:
    return LocalLlmProvider(
        base_url="http://llm.local/v1",
        api_key="test-key",
        client=httpx.Client(transport=handler),
    )


def test_temperature_is_forwarded_only_when_set() -> None:
    import pytest

    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    provider = _provider(httpx.MockTransport(handler))
    provider.complete(
        "local-model",
        LlmRequest(messages=(ChatMessage(role="user", content="x"),), tools=(), temperature=0.0),
    )
    provider.close()
    body = seen["body"]
    assert isinstance(body, dict) and body["temperature"] == 0.0
    with pytest.raises(ValueError):
        LlmRequest(messages=(), tools=(), temperature=3.0)


def test_local_adapter_parses_tool_call_and_sends_key_only_in_header() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "c1",
                                    "type": "function",
                                    "function": {
                                        "name": "list_unread",
                                        "arguments": '{"limit": 1}',
                                    },
                                }
                            ],
                        }
                    }
                ],
                "usage": {"total_tokens": 12},
            },
        )

    provider = _provider(httpx.MockTransport(handler))
    response = provider.complete(
        "local-model",
        LlmRequest(
            messages=(ChatMessage(role="user", content="прочитай"),),
            tools=(
                ToolSchema(name="list_unread", description="список", parameters={"type": "object"}),
            ),
        ),
    )
    provider.close()
    assert seen["auth"] == "Bearer test-key"
    body = seen["body"]
    assert isinstance(body, dict)
    assert body["model"] == "local-model"
    assert "temperature" not in body
    assert response.token_count == 12
    assert response.tool_calls == (ToolCall("c1", "list_unread", {"limit": 1}),)


def test_local_adapter_reads_tool_call_from_text() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        content = '{"name": "list_unread", "arguments": {"limit": 2}}'
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    provider = _provider(httpx.MockTransport(handler))
    response = provider.complete(
        "local-model",
        LlmRequest(
            messages=(ChatMessage(role="user", content="прочитай"),),
            tools=(ToolSchema(name="list_unread", description="список", parameters={}),),
        ),
    )
    provider.close()
    assert response.tool_calls == (ToolCall("list_unread", "list_unread", {"limit": 2}),)
    assert response.text == ""


def test_local_adapter_maps_auth_and_timeout() -> None:
    denied = _provider(httpx.MockTransport(lambda _request: httpx.Response(401, json={})))
    try:
        denied.complete("local-model", LlmRequest(messages=(), tools=()))
    except ProviderError as exc:
        assert exc.kind == "auth"
    else:
        raise AssertionError("ожидался auth")
    finally:
        denied.close()

    def explode(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow")

    timing = _provider(httpx.MockTransport(explode))
    try:
        timing.complete("local-model", LlmRequest(messages=(), tools=()))
    except ProviderError as exc:
        assert exc.kind == "timeout"
    else:
        raise AssertionError("ожидался timeout")
    finally:
        timing.close()
