"""Сборка ядра на моках для тестов."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import datetime

from ai_department.composition import Department, assemble
from ai_department.config import PlatformConfig
from ai_department.dialog.store import ThreadStore
from ai_department.domain.evaluation import Verdict
from ai_department.domain.role import RolePlugin
from ai_department.domain.task import ConstraintInput, Task, resolve_constraints
from ai_department.domain.tools import ToolCall
from ai_department.evaluation.deterministic import DeterministicEvaluator
from ai_department.evaluation.mock import MockEvaluator
from ai_department.llm.catalog import StaticCatalog, default_mock_entries
from ai_department.llm.mock import MockLlmProvider
from ai_department.llm.port import LlmResponse
from ai_department.memory.mock import MockMemory
from roles.clerk.plugin import ClerkRole, build_clerk_role


def make_department(
    responses: list[LlmResponse | object] | None = None,
    *,
    plugins: Sequence[RolePlugin] | None = None,
    verdicts: list[Verdict] | None = None,
    clock: Callable[[], datetime] | None = None,
    config: PlatformConfig | None = None,
    memory: MockMemory | None = None,
    threads: ThreadStore | None = None,
) -> tuple[Department, MockLlmProvider, ClerkRole]:
    """Платформа с ролью clerk и очередью ответов модели."""
    clerk = build_clerk_role()
    provider = MockLlmProvider(_responses(list(responses or [])))
    department = assemble(
        config=config or PlatformConfig(enabled_roles=()),
        plugins=list(plugins) if plugins is not None else [clerk],
        provider=provider,
        provider_id="mock",
        catalog=StaticCatalog(default_mock_entries()),
        evaluator=MockEvaluator(verdicts) if verdicts is not None else DeterministicEvaluator(),
        memory=memory or MockMemory(),
        clock=clock,
        include_stdout=False,
        threads=threads,
    )
    return department, provider, clerk


def _responses(items: list[object]) -> list[LlmResponse | object]:
    from ai_department.domain.errors import ProviderError

    cleaned: list[LlmResponse | ProviderError] = []
    for item in items:
        if isinstance(item, LlmResponse):
            cleaned.append(item)
        elif isinstance(item, ProviderError):
            cleaned.append(item)
    return cleaned


def task(
    *,
    role: str | None = "clerk",
    goal: str = "Сделать заметку",
    max_steps: int | None = None,
    max_revisions: int | None = None,
    deadline: datetime | None = None,
    payload: dict[str, object] | None = None,
) -> Task:
    """Задача с платформенными пределами."""
    body = {"role": role} if role is not None else {}
    if payload is not None:
        body = payload
    return Task(
        goal=goal,
        constraints=resolve_constraints(
            ConstraintInput(max_steps=max_steps, max_revisions=max_revisions, deadline=deadline),
            default_steps=20,
            max_steps=100,
            default_revisions=1,
            max_revisions=3,
        ),
        payload=body,
        correlation_id="corr-1",
    )


def calls(name: str, arguments: dict[str, object], call_id: str = "call-1") -> LlmResponse:
    """Ответ модели с одним tool-call."""
    return LlmResponse(
        text="",
        tool_calls=(ToolCall(call_id=call_id, name=name, arguments=arguments),),
    )


def final(summary: str = "готово") -> LlmResponse:
    """Итоговый JSON по схеме clerk."""
    return LlmResponse(text=json.dumps({"summary": summary}, ensure_ascii=False))
