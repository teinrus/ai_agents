"""Редакция секретов до публикации."""

from __future__ import annotations

import re
from typing import Any

_EXACT = frozenset(
    {
        "password",
        "secret",
        "api_key",
        "apikey",
        "authorization",
        "token",
        "credential",
        "access_key",
    }
)
_BEARER = re.compile(r"^bearer\s+\S+", re.IGNORECASE)


def sensitive_key(key: str) -> bool:
    """Пароли, ключи и Authorization. Поле tokens не считается секретом."""
    normalized = key.lower().replace("-", "_")
    if normalized in _EXACT:
        return True
    return any(
        normalized.endswith("_" + fragment) or normalized.startswith(fragment + "_")
        for fragment in _EXACT
    )


def redact(value: object) -> object:
    """Возвращает копию значения без секретов."""
    if isinstance(value, dict):
        cleaned: dict[str, object] = {}
        for key, item in value.items():
            name = str(key)
            cleaned[name] = "***" if sensitive_key(name) else redact(item)
        return cleaned
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str) and _BEARER.match(value):
        return "***"
    return value


def redact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Редакция словаря payload конверта."""
    cleaned = redact(payload)
    if isinstance(cleaned, dict):
        return cleaned
    return {}
