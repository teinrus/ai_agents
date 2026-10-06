"""Требования шага и запись каталога. Имя модели агенту неизвестно."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Capability(StrEnum):
    """Способность, которую шаг обязан закрыть."""

    CODING = "coding"
    REASONING = "reasoning"
    TOOLS = "tools"


class Preference(StrEnum):
    """Порядок предпочтений — порядок сортировки."""

    CHEAP = "cheap"
    FAST = "fast"
    LONG_CONTEXT = "long_context"


@dataclass(frozen=True)
class ModelRequirements:
    """Требования одного шага, не всего прогона."""

    capabilities: frozenset[Capability]
    preferences: tuple[Preference, ...]
    min_context_window: int
    purpose: str

    def __post_init__(self) -> None:
        if not self.capabilities:
            raise ValueError("capabilities должны быть непустыми")
        if self.min_context_window < 0:
            raise ValueError("min_context_window не может быть отрицательным")


@dataclass(frozen=True)
class ModelEntry:
    """Строка каталога. Соответствие роли и модели здесь не задаётся."""

    model_id: str
    provider_id: str
    provider_model_name: str
    capabilities: frozenset[Capability]
    context_window: int
    cost_tier: int
    latency_tier: int
    enabled: bool


def requirements_payload(requirements: ModelRequirements) -> dict[str, object]:
    """Поля требований для события model.routed."""
    return {
        "capabilities": sorted(item.value for item in requirements.capabilities),
        "preferences": [item.value for item in requirements.preferences],
        "min_context_window": requirements.min_context_window,
        "purpose": requirements.purpose,
    }
