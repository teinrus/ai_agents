"""Ответ клиенту строится из снимка прогона по таблице контракта."""

from ai_department.dialog.reply import compose_reply
from ai_department.domain.run import PendingView, RunSnapshot
from ai_department.domain.states import EmployeeState, RunStatus
from ai_department.domain.thread import ReplyKind


def snapshot(
    *,
    status: RunStatus | None,
    state: EmployeeState | None,
    output: object | None = None,
    pending: PendingView | None = None,
    reason: str | None = None,
) -> RunSnapshot:
    return RunSnapshot(
        run_id="run-1",
        correlation_id="thread-1",
        status=status,
        state=state,
        role_id="clerk",
        failure_reason=reason,
        pending_confirmation=pending,
        step_count=1,
        revision_count=0,
        output=output,
    )


def test_no_role_and_completed_and_failed() -> None:
    no_role = compose_reply(snapshot(status=RunStatus.NO_ROLE, state=None))
    assert no_role.kind is ReplyKind.NO_ROLE

    done = compose_reply(
        snapshot(status=RunStatus.COMPLETED, state=EmployeeState.IDLE, output={"summary": "ок"})
    )
    assert done.kind is ReplyKind.COMPLETED
    assert done.text == "ок"

    bare = compose_reply(snapshot(status=RunStatus.COMPLETED, state=EmployeeState.IDLE, output={}))
    assert bare.kind is ReplyKind.COMPLETED
    assert "clerk" in bare.text

    failed = compose_reply(
        snapshot(status=RunStatus.FAILED, state=EmployeeState.IDLE, reason="no_model")
    )
    assert failed.kind is ReplyKind.FAILED
    assert "no_model" in failed.text


def test_waiting_confirmation_names_tool_and_arguments() -> None:
    reply = compose_reply(
        snapshot(
            status=None,
            state=EmployeeState.WAITING_CONFIRMATION,
            pending=PendingView(confirmation_id="c1", tool="commit_note", arguments={"key": "a"}),
        )
    )
    assert reply.kind is ReplyKind.WAITING_CONFIRMATION
    assert "commit_note" in reply.text
    assert '"key": "a"' in reply.text


def test_rejected_keeps_last_summary() -> None:
    reply = compose_reply(
        snapshot(
            status=RunStatus.REJECTED,
            state=EmployeeState.IDLE,
            output={"summary": "черновик"},
        )
    )
    assert reply.kind is ReplyKind.REJECTED
    assert "черновик" in reply.text
