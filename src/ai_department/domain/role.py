"""Контракт плагина роли. Ядро импортирует только этот модуль, не плагин."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from ai_department.domain.model import ModelRequirements
from ai_department.domain.risk import RiskLevel
from ai_department.domain.task import Task
from ai_department.domain.tools import ToolDefinition


@dataclass(frozen=True)
class SkillSpec:
    """Скилл роли: инструкция, инструменты и типовые требования шага."""

    skill_id: str
    instruction: str
    tool_names: tuple[str, ...]
    requirements: ModelRequirements


class RolePlugin(Protocol):
    """Плагин роли. Зависит только от domain и регистрируется корнем сборки."""

    role_id: str
    description: str
    skills: Sequence[SkillSpec]
    risk_ceiling: RiskLevel
    output_schema: Mapping[str, object]

    def score(self, task: Task) -> float:
        """Оценка задачи в диапазоне [0, 1]. Модель не вызывается."""

    def tools(self) -> Sequence[ToolDefinition]:
        """Описания инструментов вместе с обработчиками."""
