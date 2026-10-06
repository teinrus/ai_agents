"""Каталог моделей. Первая реализация читает конфигурацию на старте."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from ai_department.domain.errors import ConfigError
from ai_department.domain.model import Capability, ModelEntry


class ModelCatalog(Protocol):
    """Порт каталога. Смена источника не меняет list()."""

    def list(self) -> Sequence[ModelEntry]:
        """Возвращает записи в порядке каталога."""


class StaticCatalog:
    """Каталог, собранный при старте процесса."""

    def __init__(self, entries: Sequence[ModelEntry]) -> None:
        self._entries = tuple(entries)

    def list(self) -> Sequence[ModelEntry]:
        return self._entries


class ReloadingCatalog:
    """Живой источник: каждый list() заново читает JSON."""

    def __init__(self, path: str) -> None:
        self._path = path

    def list(self) -> Sequence[ModelEntry]:
        return load_entries(self._path)


def default_mock_entries() -> tuple[ModelEntry, ...]:
    """Две включённые модели и одна выключенная для локального mock-запуска."""
    return (
        ModelEntry(
            model_id="cheap-reasoner",
            provider_id="mock",
            provider_model_name="reasoner-small",
            capabilities=frozenset({Capability.REASONING, Capability.TOOLS}),
            context_window=8_000,
            cost_tier=1,
            latency_tier=2,
            enabled=True,
        ),
        ModelEntry(
            model_id="coder",
            provider_id="mock",
            provider_model_name="coder-large",
            capabilities=frozenset({Capability.CODING, Capability.REASONING, Capability.TOOLS}),
            context_window=32_000,
            cost_tier=3,
            latency_tier=3,
            enabled=True,
        ),
        ModelEntry(
            model_id="disabled-cheap",
            provider_id="mock",
            provider_model_name="disabled",
            capabilities=frozenset({Capability.CODING, Capability.REASONING, Capability.TOOLS}),
            context_window=8_000,
            cost_tier=0,
            latency_tier=1,
            enabled=False,
        ),
    )


def default_local_entries(model_name: str) -> tuple[ModelEntry, ...]:
    """Одна локальная модель. Имя берётся из окружения, не из роли."""
    return (
        ModelEntry(
            model_id="local",
            provider_id="local",
            provider_model_name=model_name,
            capabilities=frozenset({Capability.CODING, Capability.REASONING, Capability.TOOLS}),
            context_window=32_000,
            cost_tier=1,
            latency_tier=1,
            enabled=True,
        ),
    )


def default_cloud_entries(model_name: str) -> tuple[ModelEntry, ...]:
    """Одна облачная модель. Имя берётся из окружения, не из роли."""
    return (
        ModelEntry(
            model_id="cloud",
            provider_id="cloud",
            provider_model_name=model_name,
            capabilities=frozenset({Capability.CODING, Capability.REASONING, Capability.TOOLS}),
            context_window=32_000,
            cost_tier=2,
            latency_tier=2,
            enabled=True,
        ),
    )


def load_entries(path: str) -> tuple[ModelEntry, ...]:
    """Читает JSON-каталог. Ошибка формата — отказ старта."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError("MODEL_CATALOG_PATH", f"Каталог моделей не читается: {exc}") from exc
    if not isinstance(raw, list):
        raise ConfigError("MODEL_CATALOG_PATH", "Каталог моделей должен быть списком")
    entries: list[ModelEntry] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ConfigError("MODEL_CATALOG_PATH", "Запись каталога должна быть объектом")
        entries.append(_entry(item))
    return tuple(entries)


def _entry(item: Mapping[str, object]) -> ModelEntry:
    capabilities_raw = item.get("capabilities")
    if not isinstance(capabilities_raw, list) or not capabilities_raw:
        raise ConfigError("MODEL_CATALOG_PATH", "У модели нет capabilities")
    capabilities: set[Capability] = set()
    for value in capabilities_raw:
        try:
            capabilities.add(Capability(str(value)))
        except ValueError as exc:
            raise ConfigError("MODEL_CATALOG_PATH", f"Неизвестная capability: {value}") from exc
    try:
        return ModelEntry(
            model_id=str(item["model_id"]),
            provider_id=str(item["provider_id"]),
            provider_model_name=str(item["provider_model_name"]),
            capabilities=frozenset(capabilities),
            context_window=int(str(item["context_window"])),
            cost_tier=int(str(item["cost_tier"])),
            latency_tier=int(str(item["latency_tier"])),
            enabled=bool(item.get("enabled", True)),
        )
    except KeyError as exc:
        raise ConfigError("MODEL_CATALOG_PATH", f"В записи каталога нет поля {exc}") from exc
