"""Сессия шага. Требования задаёт runtime, имя модели сюда не попадает."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field

from ai_department.domain.evaluation import Trace, TraceStep
from ai_department.domain.events import EventLog
from ai_department.domain.model import ModelRequirements
from ai_department.domain.risk import RiskLevel
from ai_department.domain.role import SkillSpec
from ai_department.domain.task import Task
from ai_department.domain.tools import ToolCall, ToolDefinition
from ai_department.llm.port import ChatMessage, LlmRequest, ToolSchema
from ai_department.memory.scoped import ScopedMemory
from ai_department.runtime.control import EmployeeControl
from ai_department.tools.confirmations import PendingConfirmation


@dataclass
class AgentSession:
    """Память одного прогона для общего цикла."""

    task: Task
    role_id: str
    skills: tuple[SkillSpec, ...]
    output_schema: Mapping[str, object]
    risk_ceiling: RiskLevel
    platform_ceiling: RiskLevel
    tools: dict[str, ToolDefinition]
    control: EmployeeControl
    log: EventLog
    memory: ScopedMemory
    messages: list[ChatMessage] = field(default_factory=list)
    trace_steps: list[TraceStep] = field(default_factory=list)
    steps: int = 0
    model_calls: int = 0
    output: object | None = None
    pending: PendingConfirmation | None = None
    pending_call: ToolCall | None = None

    def __post_init__(self) -> None:
        schema = json.dumps(dict(self.output_schema), ensure_ascii=False)
        instructions = "\n\n".join(skill.instruction for skill in self.skills)
        system = (
            "Ты выполняешь задачу выбранной роли. "
            "Доступны только перечисленные инструменты. "
            "Вызов инструмента — только по именам из списка. "
            "Когда инструменты больше не нужны, верни ровно один JSON-объект по схеме: "
            "только её поля, без пояснений и без обёртки name/arguments.\n"
            f"Схема:\n{schema}\n\n{instructions}"
        )
        user = json.dumps(
            {"goal": self.task.goal, "payload": self.task.payload},
            ensure_ascii=False,
            default=str,
        )
        self.messages = [
            ChatMessage(role="system", content=system),
            ChatMessage(role="user", content=user),
        ]

    @property
    def bound_tools(self) -> frozenset[str]:
        return frozenset(name for skill in self.skills for name in skill.tool_names)

    def requirements(self) -> ModelRequirements:
        """Требования текущего шага берутся из скилла роли."""
        index = min(self.model_calls, len(self.skills) - 1)
        return self.skills[index].requirements

    def request(self) -> LlmRequest:
        schemas = tuple(
            ToolSchema(
                name=definition.name,
                description=definition.description,
                parameters=definition.parameters_schema,
            )
            for definition in self.tools.values()
            if definition.name in self.bound_tools
        )
        return LlmRequest(messages=tuple(self.messages), tools=schemas)

    def trace(self) -> Trace:
        return Trace(
            role_id=self.role_id,
            risk_ceiling=self.risk_ceiling,
            output_schema=self.output_schema,
            max_steps=self.task.constraints.max_steps,
            steps=tuple(self.trace_steps),
            bound_tools=frozenset(self.bound_tools),
        )

    def add_feedback(self, remarks: list[dict[str, str]]) -> None:
        lines = "\n".join(f"- {item['name']}: {item['remark']}" for item in remarks)
        self.messages.append(
            ChatMessage(
                role="user",
                content=(
                    "Проверка не прошла.\n"
                    f"{lines}\n"
                    "Верни ровно один JSON-объект по схеме. "
                    "Не вызывай инструмент и не оборачивай ответ в name и arguments."
                ),
            )
        )
