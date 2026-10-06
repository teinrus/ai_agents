"""Ответ клиенту по снимку прогона. Модель не вызывается."""

from __future__ import annotations

import json
from dataclasses import dataclass

from ai_department.domain.run import RunSnapshot
from ai_department.domain.states import EmployeeState, RunStatus
from ai_department.domain.thread import ReplyKind


@dataclass(frozen=True)
class ReplyText:
    """Вид и текст ответа."""

    kind: ReplyKind
    text: str


def compose_reply(snapshot: RunSnapshot) -> ReplyText:
    """Таблица раздела 19.3 контракта."""
    role = snapshot.role_id or "сотрудник"
    if snapshot.status is RunStatus.NO_ROLE:
        if snapshot.failure_reason == "busy":
            return ReplyText(
                ReplyKind.NO_ROLE,
                "Подходящий сотрудник сейчас занят другой задачей или ждёт решения "
                "в другом диалоге. Повторите чуть позже.",
            )
        return ReplyText(ReplyKind.NO_ROLE, "Ни один сотрудник не взял эту задачу.")
    if snapshot.state is EmployeeState.WAITING_CONFIRMATION:
        return ReplyText(ReplyKind.WAITING_CONFIRMATION, _confirmation_text(snapshot, role))
    summary = _summary(snapshot.output)
    if snapshot.status is RunStatus.COMPLETED:
        text = summary if summary else f"Сотрудник {role} выполнил задачу."
        return ReplyText(ReplyKind.COMPLETED, text)
    if snapshot.status is RunStatus.REJECTED:
        text = f"Результат сотрудника {role} не прошёл проверку."
        if summary:
            text = f"{text} Последний вариант: {summary}"
        return ReplyText(ReplyKind.REJECTED, text)
    if snapshot.status is RunStatus.FAILED:
        reason = snapshot.failure_reason or "внутренняя ошибка"
        return ReplyText(ReplyKind.FAILED, f"Сотрудник {role} не справился: {reason}.")
    return ReplyText(ReplyKind.ANSWER, f"Задача принята, сотрудник {role} работает.")


def _confirmation_text(snapshot: RunSnapshot, role: str) -> str:
    pending = snapshot.pending_confirmation
    if pending is None:
        return f"Сотрудник {role} ждёт подтверждения. Разрешить или отклонить?"
    arguments = json.dumps(pending.arguments, ensure_ascii=False, default=str)
    return (
        f"Сотрудник {role} просит разрешение на действие {pending.tool} "
        f"с аргументами {arguments}. Разрешить или отклонить?"
    )


def _summary(output: object) -> str:
    if not isinstance(output, dict):
        return ""
    raw = output.get("summary")
    return raw.strip() if isinstance(raw, str) else ""
