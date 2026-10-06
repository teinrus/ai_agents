"""Таблица переходов."""

import pytest

from ai_department.domain.automaton import ALLOWED, automatic_idle, ensure_transition
from ai_department.domain.errors import InvalidTransition
from ai_department.domain.states import EmployeeState


@pytest.mark.parametrize(
    ("source", "target"), sorted(ALLOWED, key=lambda item: (item[0].value, item[1].value))
)
def test_contract_edges_are_legal(source: EmployeeState, target: EmployeeState) -> None:
    ensure_transition(source, target)


def test_running_to_completed_is_illegal() -> None:
    with pytest.raises(InvalidTransition):
        ensure_transition(EmployeeState.RUNNING, EmployeeState.COMPLETED)


def test_completed_is_only_reached_from_evaluating() -> None:
    sources = {source for source, target in ALLOWED if target is EmployeeState.COMPLETED}
    assert sources == {EmployeeState.EVALUATING}


def test_terminal_states_return_to_idle() -> None:
    assert automatic_idle(EmployeeState.COMPLETED) is EmployeeState.IDLE
    assert automatic_idle(EmployeeState.FAILED) is EmployeeState.IDLE
    assert automatic_idle(EmployeeState.RUNNING) is None
