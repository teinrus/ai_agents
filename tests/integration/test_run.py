"""Прогон на моках через оркестратор."""

from datetime import UTC, datetime, timedelta

from tests.support.factory import calls, final, make_department, task

from ai_department.domain.errors import ProviderError
from ai_department.domain.events import EventName
from ai_department.domain.model import Capability, ModelRequirements, Preference
from ai_department.domain.role import SkillSpec
from ai_department.domain.states import EmployeeState, RunStatus


def _names(department: object, run_id: str) -> list[str]:
    from ai_department.composition import Department

    assert isinstance(department, Department)
    return [event.event for event in department.feed.list(run_id)]


def test_no_role_does_not_call_the_model() -> None:
    department, provider, _clerk = make_department([final()])
    snapshot = department.orchestrator.submit(task(role=None))
    assert snapshot.status is RunStatus.NO_ROLE
    assert snapshot.state is None
    assert provider.calls == []
    assert EventName.MODEL_ROUTED.value not in _names(department, snapshot.run_id)
    assert _names(department, snapshot.run_id)[-1] == EventName.TASK_FINISHED.value


def test_happy_path_confirms_act_and_returns_employee_to_idle() -> None:
    department, provider, clerk = make_department(
        [
            calls("read_note", {"key": "a"}, "c1"),
            calls("commit_note", {"key": "a", "text": "hello", "password": "hunter2"}, "c2"),
            final("hello"),
        ]
    )
    paused = department.orchestrator.submit(task())
    assert paused.state is EmployeeState.WAITING_CONFIRMATION
    assert paused.pending_confirmation is not None
    assert "hunter2" not in str(department.feed.list(paused.run_id))
    assert clerk.committed == []
    same = department.orchestrator.ignore_unsolicited_tool(paused.run_id)
    assert same is EmployeeState.WAITING_CONFIRMATION
    assert clerk.committed == []
    done = department.orchestrator.confirm(
        paused.run_id,
        paused.pending_confirmation.confirmation_id,
        "approve",
    )
    assert done.status is RunStatus.COMPLETED
    assert done.state is EmployeeState.IDLE
    assert clerk.committed == ["a"]
    names = _names(department, done.run_id)
    assert names.index(EventName.EVALUATION_COMPLETED.value) < names.index(
        EventName.TASK_FINISHED.value
    )
    seqs = [event.seq for event in department.feed.list(done.run_id)]
    assert seqs == list(range(1, len(seqs) + 1))
    assert provider.calls[0] == "reasoner-small"
    assert provider.calls[1] == "coder-large"
    assert department.counters.runs["completed"] == 1
    assert department.counters.verdicts["passed"] == 1


def test_repeat_act_requires_a_new_confirmation() -> None:
    department, _provider, clerk = make_department(
        [
            calls("commit_note", {"key": "a", "text": "one"}, "c1"),
            calls("commit_note", {"key": "a", "text": "two"}, "c2"),
            final("дважды"),
        ]
    )
    paused = department.orchestrator.submit(task())
    assert paused.pending_confirmation is not None
    again = department.orchestrator.confirm(
        paused.run_id, paused.pending_confirmation.confirmation_id, "approve"
    )
    assert again.state is EmployeeState.WAITING_CONFIRMATION
    assert again.pending_confirmation is not None
    assert again.pending_confirmation.confirmation_id != paused.pending_confirmation.confirmation_id
    done = department.orchestrator.confirm(
        again.run_id, again.pending_confirmation.confirmation_id, "approve"
    )
    assert done.status is RunStatus.COMPLETED
    assert clerk.committed == ["a", "a"]


def test_busy_employee_gives_no_role_with_busy_reason() -> None:
    department, _provider, _clerk = make_department(
        [calls("commit_note", {"key": "a", "text": "one"}, "c1"), final("после")]
    )
    paused = department.orchestrator.submit(task())
    assert paused.state is EmployeeState.WAITING_CONFIRMATION
    second = department.orchestrator.submit(task(goal="вторая"))
    assert second.status is RunStatus.NO_ROLE
    assert second.failure_reason == "busy"
    finished = [
        event
        for event in department.feed.list(second.run_id)
        if event.event == EventName.TASK_FINISHED.value
    ]
    assert finished[0].payload["reason"] == "busy"
    unrelated = department.orchestrator.submit(task(role=None, payload={}))
    assert unrelated.status is RunStatus.NO_ROLE
    assert unrelated.failure_reason is None


def test_concurrent_submits_are_serialized() -> None:
    import threading

    department, _provider, _clerk = make_department(
        [
            calls("read_note", {"key": "a"}, "c1"),
            final("первый"),
            calls("read_note", {"key": "a"}, "c2"),
            final("второй"),
        ]
    )
    results: list[RunStatus | None] = []
    barrier = threading.Barrier(2)

    def worker() -> None:
        barrier.wait()
        results.append(department.orchestrator.submit(task()).status)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for item in threads:
        item.start()
    for item in threads:
        item.join()
    assert results == [RunStatus.COMPLETED, RunStatus.COMPLETED]
    assert department.orchestrator.staff()[0][1] is EmployeeState.IDLE


def test_tool_evidence_sends_storytelling_to_revision() -> None:
    department, provider, _clerk = make_department(
        [final("всё сделано"), calls("read_note", {"key": "a"}, "c1"), final("теперь правда")]
    )
    done = department.orchestrator.submit(task())
    assert done.status is RunStatus.COMPLETED
    assert done.revision_count == 1
    revision = next(
        event
        for event in department.feed.list(done.run_id)
        if event.event == EventName.EVALUATION_REVISION_REQUESTED.value
    )
    assert any(item["name"] == "tool_evidence" for item in revision.payload["remarks"])
    assert len(provider.calls) == 3


def test_rejected_act_counts_as_tool_evidence_and_keeps_confirmation_check() -> None:
    department, _provider, clerk = make_department(
        [calls("commit_note", {"key": "a", "text": "one"}, "c1"), final("отклонено человеком")]
    )
    paused = department.orchestrator.submit(task())
    assert paused.pending_confirmation is not None
    done = department.orchestrator.confirm(
        paused.run_id, paused.pending_confirmation.confirmation_id, "reject"
    )
    assert done.status is RunStatus.COMPLETED
    assert done.revision_count == 0
    assert clerk.committed == []


def test_invalid_arguments_fail_the_step_before_confirmation() -> None:
    department, provider, clerk = make_department(
        [
            calls("commit_note", {"key": "a", "text": 7}, "c1"),
            calls("commit_note", {"key": "a", "text": "ok"}, "c2"),
            final("исправлено"),
        ]
    )
    paused = department.orchestrator.submit(task())
    events = department.feed.list(paused.run_id)
    failed = [event for event in events if event.event == EventName.TOOL_FAILED.value]
    assert len(failed) == 1
    assert failed[0].payload["kind"] == "arguments"
    assert "text" in str(failed[0].payload["message"])
    confirmations = [
        event for event in events if event.event == EventName.TOOL_CONFIRMATION_REQUIRED.value
    ]
    assert len(confirmations) == 1
    assert confirmations[0].payload["arguments"] == {"key": "a", "text": "ok"}
    assert paused.state is EmployeeState.WAITING_CONFIRMATION
    assert clerk.committed == []
    assert len(provider.calls) == 2


def test_reject_does_not_execute_act() -> None:
    department, _provider, clerk = make_department(
        [calls("commit_note", {"key": "a", "text": "one"}, "c1"), final("без фиксации")]
    )
    paused = department.orchestrator.submit(task())
    assert paused.pending_confirmation is not None
    done = department.orchestrator.confirm(
        paused.run_id, paused.pending_confirmation.confirmation_id, "reject"
    )
    assert done.status is RunStatus.COMPLETED
    assert clerk.committed == []


def test_revision_then_pass_and_exhausted_rejection() -> None:
    from ai_department.domain.evaluation import CheckResult, Verdict
    from ai_department.domain.states import VerdictKind

    rejected = Verdict(VerdictKind.REJECTED, (CheckResult("output_schema", False, "не та схема"),))
    passed = Verdict(VerdictKind.PASSED, (CheckResult("output_schema", True, ""),))
    department, _provider, _clerk = make_department(
        [final("черновик"), final("итог")], verdicts=[rejected, passed]
    )
    done = department.orchestrator.submit(task())
    assert done.status is RunStatus.COMPLETED
    assert done.revision_count == 1
    names = _names(department, done.run_id)
    assert EventName.EVALUATION_REVISION_REQUESTED.value in names
    assert names.count(EventName.EVALUATION_COMPLETED.value) == 2

    stuck, _provider, _clerk = make_department(
        [final("нет"), final("снова")],
        verdicts=[rejected, rejected],
    )
    failed = stuck.orchestrator.submit(task())
    assert failed.status is RunStatus.REJECTED
    assert failed.state is EmployeeState.IDLE
    finished = [
        event.payload["status"]
        for event in stuck.feed.list(failed.run_id)
        if event.event == "task.finished"
    ]
    assert finished == ["rejected"]


def test_no_model_finishes_failed() -> None:
    from ai_department.composition import assemble
    from ai_department.config import PlatformConfig
    from ai_department.evaluation.deterministic import DeterministicEvaluator
    from ai_department.llm.catalog import StaticCatalog, default_mock_entries
    from ai_department.llm.mock import MockLlmProvider
    from ai_department.memory.mock import MockMemory
    from roles.clerk.plugin import build_clerk_role

    narrow = tuple(entry for entry in default_mock_entries() if entry.model_id == "cheap-reasoner")
    provider = MockLlmProvider([calls("read_note", {"key": "a"}, "c1")])
    built = assemble(
        config=PlatformConfig(enabled_roles=()),
        plugins=[build_clerk_role()],
        provider=provider,
        provider_id="mock",
        catalog=StaticCatalog(narrow),
        evaluator=DeterministicEvaluator(),
        memory=MockMemory(),
        include_stdout=False,
    )
    snapshot = built.orchestrator.submit(task())
    assert snapshot.status is RunStatus.FAILED
    assert snapshot.failure_reason == "no_model"
    assert snapshot.state is EmployeeState.IDLE
    assert provider.calls == ["reasoner-small"]


def test_provider_retries_same_model_then_fails() -> None:
    from ai_department.composition import assemble
    from ai_department.config import PlatformConfig
    from ai_department.evaluation.deterministic import DeterministicEvaluator
    from ai_department.llm.catalog import StaticCatalog, default_mock_entries
    from ai_department.llm.mock import MockLlmProvider
    from ai_department.memory.mock import MockMemory
    from roles.clerk.plugin import build_clerk_role

    provider = MockLlmProvider(
        [
            ProviderError("timeout", "медленно"),
            ProviderError("timeout", "снова медленно"),
        ]
    )
    built = assemble(
        config=PlatformConfig(enabled_roles=(), max_provider_retries=1),
        plugins=[build_clerk_role()],
        provider=provider,
        provider_id="mock",
        catalog=StaticCatalog(default_mock_entries()),
        evaluator=DeterministicEvaluator(),
        memory=MockMemory(),
        include_stdout=False,
    )
    snapshot = built.orchestrator.submit(task())
    assert snapshot.status is RunStatus.FAILED
    assert snapshot.failure_reason == "timeout"
    assert provider.calls == ["reasoner-small", "reasoner-small"]
    failed = [
        event
        for event in built.feed.list(snapshot.run_id)
        if event.event == EventName.MODEL_FAILED.value
    ]
    assert len(failed) == 2
    assert [event.payload["attempt"] for event in failed] == [1, 2]


def test_deadline_during_confirmation_fails_without_tool() -> None:
    class Clock:
        def __init__(self) -> None:
            self.now = datetime(2026, 1, 1, tzinfo=UTC)

        def __call__(self) -> datetime:
            return self.now

    clock = Clock()
    department, _provider, clerk = make_department(
        [calls("commit_note", {"key": "a", "text": "late"}, "c1")],
        clock=clock,
    )
    paused = department.orchestrator.submit(task(deadline=clock.now + timedelta(minutes=5)))
    assert paused.state is EmployeeState.WAITING_CONFIRMATION
    assert paused.pending_confirmation is not None
    clock.now = clock.now + timedelta(minutes=10)
    done = department.orchestrator.confirm(
        paused.run_id,
        paused.pending_confirmation.confirmation_id,
        "approve",
    )
    assert done.status is RunStatus.FAILED
    assert done.failure_reason == "deadline"
    assert clerk.committed == []


def test_foreign_tool_is_denied_and_run_can_finish() -> None:
    department, _provider, _clerk = make_department(
        [calls("send_message", {"to": "a", "subject": "s", "body": "b"}, "c1"), final("мимо")]
    )
    done = department.orchestrator.submit(task())
    assert done.status is RunStatus.COMPLETED
    denied = [
        event
        for event in department.feed.list(done.run_id)
        if event.event == EventName.TOOL_DENIED.value
    ]
    assert denied
    assert denied[0].payload["rule"] == 1


def test_equal_score_follows_registry_order() -> None:
    from dataclasses import dataclass

    from ai_department.domain.risk import RiskLevel
    from ai_department.domain.task import Task
    from ai_department.domain.tools import ToolDefinition

    @dataclass
    class Ranked:
        role_id: str
        skills: tuple[SkillSpec, ...]
        risk_ceiling: RiskLevel
        output_schema: dict[str, object]
        tool: ToolDefinition
        description: str = "тестовая роль"

        def score(self, incoming: Task) -> float:
            del incoming
            return 0.8

        def tools(self) -> tuple[ToolDefinition, ...]:
            return (self.tool,)

    def role(role_id: str, tool_name: str) -> Ranked:
        return Ranked(
            role_id=role_id,
            risk_ceiling=RiskLevel.READ,
            output_schema={
                "type": "object",
                "required": ["summary"],
                "properties": {"summary": {"type": "string"}},
            },
            skills=(
                SkillSpec(
                    skill_id="look",
                    instruction="верни json",
                    tool_names=(tool_name,),
                    requirements=ModelRequirements(
                        frozenset({Capability.REASONING}),
                        (Preference.CHEAP,),
                        1000,
                        "look",
                    ),
                ),
            ),
            tool=ToolDefinition(
                name=tool_name,
                description="чтение",
                parameters_schema={"type": "object", "properties": {}},
                risk_level=RiskLevel.READ,
                handler=lambda _arguments: {"ok": True},
            ),
        )

    department, _provider, _clerk = make_department(
        [calls("read_alpha", {}, "c1"), final("первый")],
        plugins=[role("alpha", "read_alpha"), role("beta", "read_beta")],
    )
    done = department.orchestrator.submit(task(role=None, payload={}))
    assert done.role_id == "alpha"
    assert done.status is RunStatus.COMPLETED
