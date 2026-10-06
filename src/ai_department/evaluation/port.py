"""Порт оценщика."""

from __future__ import annotations

from typing import Protocol

from ai_department.domain.evaluation import Trace, Verdict
from ai_department.domain.task import Task


class Evaluator(Protocol):
    """Оценка без инструментов и без выбора модели."""

    def evaluate(self, task: Task, output: object, trace: Trace) -> Verdict:
        """Возвращает passed или rejected и список проверок."""
