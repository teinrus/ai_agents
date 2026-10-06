"""Оценщик с заданным вердиктом для тестов ядра."""

from __future__ import annotations

from ai_department.domain.evaluation import CheckResult, Trace, Verdict
from ai_department.domain.states import VerdictKind
from ai_department.domain.task import Task


class MockEvaluator:
    """Очередь вердиктов. Инструменты и модель не вызывает."""

    def __init__(self, verdicts: list[Verdict] | None = None) -> None:
        self._verdicts = list(verdicts or [])

    def evaluate(self, task: Task, output: object, trace: Trace) -> Verdict:
        del task, output, trace
        if not self._verdicts:
            return Verdict(kind=VerdictKind.PASSED, checks=(CheckResult("mock", True, ""),))
        return self._verdicts.pop(0)
