"""Порт перевода состояний. Таблицу применяет оркестратор."""

from __future__ import annotations

from typing import Protocol

from ai_department.domain.states import EmployeeState


class EmployeeControl(Protocol):
    """Запрос перехода. Допустимость проверяет оркестратор."""

    @property
    def state(self) -> EmployeeState:
        """Текущее состояние сотрудника."""

    def move(self, target: EmployeeState, reason: str) -> None:
        """Переводит автомат, если ребро есть в контракте."""
