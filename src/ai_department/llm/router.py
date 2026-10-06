"""Роутер выбирает модель по требованиям шага и вызывает её провайдера."""

from __future__ import annotations

from collections.abc import Mapping

from ai_department.domain.errors import NoModelError, ProviderError
from ai_department.domain.events import EventLog, EventName
from ai_department.domain.model import (
    ModelEntry,
    ModelRequirements,
    Preference,
    requirements_payload,
)
from ai_department.llm.catalog import ModelCatalog
from ai_department.llm.port import LlmProvider, LlmRequest, LlmResponse


class ProviderDirectory:
    """Адаптеры по provider_id. Роутер не подменяет модель молча."""

    def __init__(self, providers: Mapping[str, LlmProvider]) -> None:
        self._providers = dict(providers)

    def complete(self, provider_id: str, model_name: str, request: LlmRequest) -> LlmResponse:
        provider = self._providers.get(provider_id)
        if provider is None:
            raise ProviderError("unavailable", f"Провайдер {provider_id} не подключён")
        return provider.complete(model_name, request)


class ModelRouter:
    """Фильтр, сортировка и один вызов выбранной записи."""

    def __init__(self, catalog: ModelCatalog, providers: ProviderDirectory) -> None:
        self._catalog = catalog
        self._providers = providers

    def route(self, requirements: ModelRequirements, log: EventLog) -> ModelEntry:
        """Публикует model.routed. Пустой список — NoModelError."""
        matched: list[ModelEntry] = []
        rejected: list[dict[str, str]] = []
        for entry in self._catalog.list():
            reason = _reject_reason(entry, requirements)
            if reason is None:
                matched.append(entry)
            else:
                rejected.append({"model_id": entry.model_id, "reason": reason})
        matched.sort(key=lambda entry: _sort_key(entry, requirements.preferences))
        selected = matched[0] if matched else None
        if selected is not None:
            for entry in matched[1:]:
                rejected.append({"model_id": entry.model_id, "reason": "lower_rank"})
        log.emit(
            EventName.MODEL_ROUTED,
            "Модель выбрана" if selected is not None else "Модель не найдена",
            {
                "requirements": requirements_payload(requirements),
                "model_id": None if selected is None else selected.model_id,
                "rejected": rejected,
            },
        )
        if selected is None:
            raise NoModelError()
        return selected

    def invoke(
        self,
        entry: ModelEntry,
        request: LlmRequest,
        log: EventLog,
        *,
        purpose: str,
    ) -> LlmResponse:
        """Вызывает провайдера выбранной записи и публикует model.called."""
        response = self._providers.complete(entry.provider_id, entry.provider_model_name, request)
        payload: dict[str, object] = {"model_id": entry.model_id, "purpose": purpose}
        if response.token_count is not None:
            payload["tokens"] = response.token_count
        log.emit(EventName.MODEL_CALLED, "Модель вызвана", payload)
        return response


def _reject_reason(entry: ModelEntry, requirements: ModelRequirements) -> str | None:
    if not entry.enabled:
        return "disabled"
    if not requirements.capabilities <= entry.capabilities:
        return "missing_capability"
    if entry.context_window < requirements.min_context_window:
        return "context_window"
    return None


def _sort_key(entry: ModelEntry, preferences: tuple[Preference, ...]) -> tuple[int, ...]:
    parts: list[int] = []
    for preference in preferences:
        if preference is Preference.CHEAP:
            parts.append(entry.cost_tier)
        elif preference is Preference.FAST:
            parts.append(entry.latency_tier)
        elif preference is Preference.LONG_CONTEXT:
            parts.append(-entry.context_window)
    return tuple(parts)
