"""Счётчики прогонов, ролей, инструментов, маршрутов и вердиктов."""

from __future__ import annotations

from ai_department.domain.events import Envelope, EventName


class Counters:
    """Подписчик метрик. Отключение не меняет маршруты и политику."""

    def __init__(self) -> None:
        self.runs: dict[str, int] = {}
        self.roles: dict[str, int] = {}
        self.tools: dict[str, int] = {}
        self.routes: dict[str, int] = {}
        self.verdicts: dict[str, int] = {}

    def __call__(self, event: Envelope) -> None:
        name = event.event
        if name == EventName.TASK_FINISHED.value:
            self._bump(self.runs, str(event.payload.get("status", "")))
        elif name == EventName.AGENT_SELECTED.value:
            self._bump(self.roles, str(event.payload.get("role_id", "")))
        elif name == EventName.TOOL_INVOKED.value:
            self._bump(self.tools, "invoked")
        elif name == EventName.TOOL_DENIED.value:
            self._bump(self.tools, "denied")
        elif name == EventName.TOOL_CONFIRMATION_REQUIRED.value:
            self._bump(self.tools, "confirm")
        elif name == EventName.TOOL_FAILED.value:
            self._bump(self.tools, "failed")
        elif name == EventName.MODEL_ROUTED.value:
            model_id = event.payload.get("model_id")
            if isinstance(model_id, str):
                self._bump(self.routes, model_id)
        elif name == EventName.EVALUATION_COMPLETED.value:
            self._bump(self.verdicts, str(event.payload.get("verdict", "")))

    @staticmethod
    def _bump(bucket: dict[str, int], key: str) -> None:
        bucket[key] = bucket.get(key, 0) + 1
