"""Цикл событий оценки. Состояния переводит оркестратор."""

from __future__ import annotations

from ai_department.domain.evaluation import Trace, Verdict, verdict_payload
from ai_department.domain.events import EventLog, EventName
from ai_department.domain.task import Task
from ai_department.evaluation.port import Evaluator


class EvaluationCycle:
    """Публикует evaluation.started и evaluation.completed вокруг порта."""

    def __init__(self, evaluator: Evaluator) -> None:
        self._evaluator = evaluator

    def run(
        self, task: Task, output: object, trace: Trace, log: EventLog, *, attempt: int
    ) -> Verdict:
        log.emit(EventName.EVALUATION_STARTED, "Оценка начата", {"attempt": attempt})
        verdict = self._evaluator.evaluate(task, output, trace)
        log.emit(EventName.EVALUATION_COMPLETED, "Оценка завершена", verdict_payload(verdict))
        return verdict
