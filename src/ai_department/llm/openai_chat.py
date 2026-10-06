"""Общий разбор OpenAI-совместимого chat completions. Имена SDK наружу не выходят."""

from __future__ import annotations

import json
from typing import Any

import httpx

from ai_department.domain.errors import ProviderError
from ai_department.domain.tools import ToolCall
from ai_department.llm.port import ChatMessage, LlmRequest, LlmResponse, ToolSchema


def complete_openai_chat(
    *,
    client: httpx.Client,
    base_url: str,
    api_key: str,
    provider_model_name: str,
    request: LlmRequest,
    subject: str,
    title: str,
) -> LlmResponse:
    """Один POST. Ключ уходит только в заголовок Authorization."""
    body: dict[str, object] = {
        "model": provider_model_name,
        "messages": [_message(item) for item in request.messages],
        "tools": [_tool(item) for item in request.tools],
    }
    if request.temperature is not None:
        body["temperature"] = request.temperature
    try:
        response = client.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=body,
        )
    except httpx.TimeoutException as exc:
        raise ProviderError("timeout", f"Таймаут {subject} endpoint") from exc
    except httpx.HTTPError as exc:
        raise ProviderError("unavailable", f"{title} endpoint недоступен") from exc
    if response.status_code in {401, 403}:
        raise ProviderError("auth", f"{title} endpoint отклонил ключ")
    if response.status_code == 429:
        raise ProviderError("rate_limit", f"{title} endpoint ограничил частоту")
    if response.status_code >= 500:
        raise ProviderError("unavailable", f"{title} endpoint вернул ошибку")
    if response.status_code >= 400:
        raise ProviderError("invalid_response", f"{title} endpoint отклонил запрос")
    try:
        payload: object = response.json()
    except json.JSONDecodeError as exc:
        raise ProviderError("invalid_response", f"Ответ {subject} endpoint не JSON") from exc
    return _lift_textual_call(_parse(payload), request)


def _message(message: ChatMessage) -> dict[str, object]:
    body: dict[str, object] = {"role": message.role, "content": message.content}
    if message.tool_call_id is not None:
        body["tool_call_id"] = message.tool_call_id
    if message.tool_calls:
        body["tool_calls"] = [
            {
                "id": call.call_id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(call.arguments, ensure_ascii=False),
                },
            }
            for call in message.tool_calls
        ]
    return body


def _tool(schema: ToolSchema) -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": schema.name,
            "description": schema.description,
            "parameters": schema.parameters,
        },
    }


def _parse(payload: object) -> LlmResponse:
    if not isinstance(payload, dict):
        raise ProviderError("invalid_response", "В ответе нет объекта")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderError("invalid_response", "В ответе нет choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise ProviderError("invalid_response", "choice не объект")
    message = first.get("message")
    if not isinstance(message, dict):
        raise ProviderError("invalid_response", "В ответе нет message")
    text = message.get("content")
    content = text if isinstance(text, str) else ""
    tool_calls = _tool_calls(message.get("tool_calls"))
    usage = payload.get("usage")
    tokens: int | None = None
    if isinstance(usage, dict) and isinstance(usage.get("total_tokens"), int):
        tokens = usage["total_tokens"]
    return LlmResponse(text=content, tool_calls=tool_calls, token_count=tokens)


def _lift_textual_call(response: LlmResponse, request: LlmRequest) -> LlmResponse:
    """Модели вроде локального Ollama кладут вызов в текст, а не в tool_calls."""
    if response.tool_calls:
        return response
    text = _strip_fence(response.text.strip())
    try:
        loaded: object = json.loads(text)
    except json.JSONDecodeError:
        return response
    if not isinstance(loaded, dict):
        return response
    name = loaded.get("name")
    known = {tool.name for tool in request.tools}
    if not isinstance(name, str) or name not in known:
        return response
    arguments = loaded.get("arguments", {})
    if not isinstance(arguments, dict):
        return response
    return LlmResponse(
        text="",
        tool_calls=(
            ToolCall(
                call_id=name,
                name=name,
                arguments={str(key): value for key, value in arguments.items()},
            ),
        ),
        token_count=response.token_count,
    )


def _strip_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    body = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
    return "\n".join(body).strip()


def _tool_calls(raw: object) -> tuple[ToolCall, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ProviderError("invalid_response", "tool_calls не список")
    calls: list[ToolCall] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ProviderError("invalid_response", "tool_call не объект")
        function = item.get("function")
        if not isinstance(function, dict):
            raise ProviderError("invalid_response", "У tool_call нет function")
        name = function.get("name")
        if not isinstance(name, str):
            raise ProviderError("invalid_response", "У tool_call нет имени")
        arguments = _arguments(function.get("arguments"))
        call_id = item.get("id")
        calls.append(
            ToolCall(
                call_id=call_id if isinstance(call_id, str) else name,
                name=name,
                arguments=arguments,
            )
        )
    return tuple(calls)


def _arguments(raw: object) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return {str(key): value for key, value in raw.items()}
    if not isinstance(raw, str):
        raise ProviderError("invalid_response", "Аргументы tool_call не читаются")
    try:
        loaded: object = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProviderError("invalid_response", "Аргументы tool_call не JSON") from exc
    if not isinstance(loaded, dict):
        raise ProviderError("invalid_response", "Аргументы tool_call не объект")
    return {str(key): value for key, value in loaded.items()}
