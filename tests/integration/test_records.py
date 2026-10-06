"""Вторая роль на моках: тот же цикл, без правки ядра."""

import json
from pathlib import Path

from ai_department.composition import assemble, build_from_environment
from ai_department.config import PlatformConfig
from ai_department.domain.events import EventName
from ai_department.domain.model import Capability, ModelEntry
from ai_department.domain.states import EmployeeState, RunStatus
from ai_department.domain.task import ConstraintInput, Task, resolve_constraints
from ai_department.domain.tools import ToolCall
from ai_department.evaluation.deterministic import DeterministicEvaluator
from ai_department.llm.catalog import StaticCatalog, default_mock_entries
from ai_department.llm.mock import MockLlmProvider
from ai_department.llm.port import LlmResponse
from ai_department.memory.in_memory import InMemoryStore
from roles.mail.mailbox import InMemoryMailbox
from roles.mail.plugin import MailRole
from roles.records.plugin import RecordsRole


def test_records_run_follows_the_same_cycle() -> None:
    role = RecordsRole()
    department, _provider = _department(
        role,
        [
            _call("list_records", {"limit": 5}),
            _call("write_record", {"title": "Карточка", "body": "Текст"}),
            _final("запись сохранена", "record-1"),
        ],
    )
    done = department.orchestrator.submit(_task({"channel": "records"}))
    events = department.feed.list(done.run_id)
    names = [event.event for event in events]
    invoked = [
        event.payload["tool"] for event in events if event.event == EventName.TOOL_INVOKED.value
    ]
    assert done.status is RunStatus.COMPLETED
    assert done.state is EmployeeState.IDLE
    assert done.role_id == "records"
    assert invoked == ["list_records", "write_record"]
    assert role.records[0]["record_id"] == "record-1"
    assert EventName.TOOL_CONFIRMATION_REQUIRED.value not in names
    assert names.index(EventName.EVALUATION_COMPLETED.value) < names.index(
        EventName.TASK_FINISHED.value
    )


def test_mail_model_changes_with_catalog_not_role_code() -> None:
    catalog = StaticCatalog(
        (
            ModelEntry(
                model_id="standin-reasoner",
                provider_id="mock",
                provider_model_name="standin-small",
                capabilities=frozenset({Capability.REASONING, Capability.TOOLS}),
                context_window=8_000,
                cost_tier=1,
                latency_tier=1,
                enabled=True,
            ),
        )
    )
    department, provider = _department(
        MailRole(InMemoryMailbox()),
        [_call("list_unread", {"limit": 5}), _final("без писем")],
        catalog,
    )
    done = department.orchestrator.submit(_task({"channel": "mail"}))
    routed = next(
        event
        for event in department.feed.list(done.run_id)
        if event.event == EventName.MODEL_ROUTED.value
    )
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in Path("src/roles/mail").rglob("*.py")
    )
    assert routed.payload["model_id"] == "standin-reasoner"
    assert provider.calls == ["standin-small", "standin-small"]
    assert "standin-reasoner" not in source
    assert "standin-small" not in source


def test_shared_task_goes_to_higher_score_and_miss_is_no_role() -> None:
    records = RecordsRole()
    mail = MailRole(InMemoryMailbox())
    department, provider = _department(
        records,
        [_final("берёт картотека")],
        plugins=(records, mail),
    )
    chosen = department.orchestrator.submit(
        _task({"channels": ["mail", "records"]}, "both"),
    )
    selected = next(
        event
        for event in department.feed.list(chosen.run_id)
        if event.event == EventName.AGENT_SELECTED.value
    )
    assert chosen.role_id == "records"
    assert selected.payload["score"] == 0.75
    assert selected.payload["rejected"] == [{"role_id": "mail", "score": 0.5}]
    calls_after_choice = list(provider.calls)
    missed = department.orchestrator.submit(_task({}, "none"))
    assert missed.status is RunStatus.NO_ROLE
    assert missed.role_id is None
    assert provider.calls == calls_after_choice


def test_other_role_skill_is_denied() -> None:
    mailbox = InMemoryMailbox()
    records = RecordsRole()
    department, _provider = _department(
        records,
        [
            LlmResponse(
                text="",
                tool_calls=(
                    ToolCall("c1", "send_message", {"to": "a@b.c", "subject": "s", "body": "b"}),
                ),
            ),
            _final("чужой инструмент закрыт"),
        ],
        plugins=(records, MailRole(mailbox)),
    )
    done = department.orchestrator.submit(_task({"channel": "records"}))
    denied = [
        event
        for event in department.feed.list(done.run_id)
        if event.event == EventName.TOOL_DENIED.value
    ]
    assert done.status is RunStatus.COMPLETED
    assert denied[0].payload["tool"] == "send_message"
    assert denied[0].payload["rule"] == 1
    assert mailbox.sent == []
    assert records.records == []


def test_agent_memory_of_two_roles_stays_separate() -> None:
    store = InMemoryStore()
    records = RecordsRole()
    mail = MailRole(InMemoryMailbox())
    department, _provider = _department(
        records,
        [
            _call("list_records", {"limit": 1}),
            _final("карточка"),
            _call("list_unread", {"limit": 1}),
            _final("ящик"),
        ],
        plugins=(records, mail),
        memory=store,
    )
    first = department.orchestrator.submit(_task({"channel": "records"}, "records-run"))
    assert store.get("agent", "mail", "last_run") is None
    second = department.orchestrator.submit(_task({"channel": "mail"}, "mail-run"))
    assert json.loads(store.get("agent", "records", "last_run") or "")["status"] == "completed"
    assert json.loads(store.get("agent", "mail", "last_run") or "")["status"] == "completed"
    assert store.get("run", first.run_id, "outcome") is not None
    assert store.get("run", second.run_id, "outcome") is not None
    assert first.run_id != second.run_id


def test_records_role_loads_from_configuration() -> None:
    script = json.dumps(
        [
            {"text": "", "tool_calls": [{"name": "list_records", "arguments": {"limit": 3}}]},
            {"text": json.dumps({"summary": "из конфигурации"}, ensure_ascii=False)},
        ],
        ensure_ascii=False,
    )
    department = build_from_environment(
        {
            "LLM_ADAPTER": "mock",
            "MEMORY_BACKEND": "memory",
            "ENABLED_ROLES": "records",
            "MOCK_LLM_SCRIPT": script,
        }
    )
    done = department.orchestrator.submit(_task({"channel": "records"}, "configured"))
    assert done.role_id == "records"
    assert done.status is RunStatus.COMPLETED


def _department(
    role: RecordsRole | MailRole,
    responses: list[LlmResponse],
    catalog: StaticCatalog | None = None,
    plugins: tuple[RecordsRole | MailRole, ...] | None = None,
    memory: InMemoryStore | None = None,
) -> tuple[object, MockLlmProvider]:
    provider = MockLlmProvider(responses)
    department = assemble(
        config=PlatformConfig(enabled_roles=()),
        plugins=list(plugins) if plugins is not None else [role],
        provider=provider,
        provider_id="mock",
        catalog=catalog or StaticCatalog(default_mock_entries()),
        evaluator=DeterministicEvaluator(),
        memory=memory or InMemoryStore(),
        include_stdout=False,
    )
    return department, provider


def _task(payload: dict[str, object], correlation_id: str = "records-1") -> Task:
    return Task(
        goal="Положить запись в картотеку",
        constraints=resolve_constraints(
            ConstraintInput(),
            default_steps=20,
            max_steps=100,
            default_revisions=1,
            max_revisions=3,
        ),
        payload=payload,
        correlation_id=correlation_id,
    )


def _call(name: str, arguments: dict[str, object]) -> LlmResponse:
    return LlmResponse(text="", tool_calls=(ToolCall("c1", name, arguments),))


def _final(summary: str, record_id: str | None = None) -> LlmResponse:
    body: dict[str, str] = {"summary": summary}
    if record_id is not None:
        body["record_id"] = record_id
    return LlmResponse(text=json.dumps(body, ensure_ascii=False))
