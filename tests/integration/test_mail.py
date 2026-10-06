"""Почтовый плагин на моковом ящике и моковой модели."""

from ai_department.composition import assemble
from ai_department.config import PlatformConfig
from ai_department.domain.states import EmployeeState, RunStatus
from ai_department.domain.tools import ToolCall
from ai_department.evaluation.deterministic import DeterministicEvaluator
from ai_department.llm.catalog import StaticCatalog, default_mock_entries
from ai_department.llm.mock import MockLlmProvider
from ai_department.llm.port import LlmResponse
from ai_department.memory.mock import MockMemory
from roles.mail.mailbox import ImapSmtpMailbox, InMemoryMailbox
from roles.mail.plugin import MailRole


def test_mail_run_drafts_and_stops_send_on_confirmation() -> None:
    mailbox = InMemoryMailbox()
    mailbox.unread.append({"id": "1", "from": "a@b.c", "subject": "s", "date": "", "snippet": ""})
    role = MailRole(mailbox)
    provider = MockLlmProvider(
        [
            LlmResponse(
                text="",
                tool_calls=(ToolCall("c1", "list_unread", {"limit": 5}),),
            ),
            LlmResponse(
                text="",
                tool_calls=(
                    ToolCall("c2", "create_draft", {"to": "a@b.c", "subject": "s", "body": "b"}),
                ),
            ),
            LlmResponse(
                text="",
                tool_calls=(
                    ToolCall("c3", "send_message", {"to": "a@b.c", "subject": "s", "body": "b"}),
                ),
            ),
            LlmResponse(text='{"summary": "черновик сохранён", "draft_id": "draft-1"}'),
        ]
    )
    department = assemble(
        config=PlatformConfig(enabled_roles=("mail",)),
        plugins=[role],
        provider=provider,
        provider_id="mock",
        catalog=StaticCatalog(default_mock_entries()),
        evaluator=DeterministicEvaluator(),
        memory=MockMemory(),
        include_stdout=False,
    )
    from ai_department.domain.task import ConstraintInput, Task, resolve_constraints

    paused = department.orchestrator.submit(
        Task(
            goal="Подготовить ответ",
            constraints=resolve_constraints(
                ConstraintInput(),
                default_steps=20,
                max_steps=100,
                default_revisions=1,
                max_revisions=3,
            ),
            payload={"channel": "mail"},
            correlation_id="mail-1",
        )
    )
    assert paused.state is EmployeeState.WAITING_CONFIRMATION
    assert paused.pending_confirmation is not None
    assert paused.pending_confirmation.tool == "send_message"
    assert mailbox.sent == []
    assert len(mailbox.drafts) == 1
    done = department.orchestrator.confirm(
        paused.run_id,
        paused.pending_confirmation.confirmation_id,
        "reject",
    )
    assert done.status is RunStatus.COMPLETED
    assert mailbox.sent == []


def test_mail_run_reads_letter_then_drafts_reply() -> None:
    mailbox = InMemoryMailbox()
    mailbox.unread.append(
        {
            "id": "42",
            "from": "a@b.c",
            "subject": "Вопрос",
            "date": "Tue, 6 Oct 2026 21:00:00 +0300",
            "snippet": "Можно ли встретиться?",
        }
    )
    mailbox.messages["42"] = {
        "id": "42",
        "from": "a@b.c",
        "to": "me@b.c",
        "subject": "Вопрос",
        "date": "Tue, 6 Oct 2026 21:00:00 +0300",
        "message_id_header": "<q@b.c>",
        "text": "Можно ли встретиться на этой неделе?",
    }
    role = MailRole(mailbox)
    provider = MockLlmProvider(
        [
            LlmResponse(
                text="",
                tool_calls=(ToolCall("c1", "list_unread", {"limit": 5}),),
            ),
            LlmResponse(
                text="",
                tool_calls=(ToolCall("c2", "read_message", {"message_id": "42"}),),
            ),
            LlmResponse(
                text="",
                tool_calls=(
                    ToolCall(
                        "c3",
                        "create_draft",
                        {
                            "to": "a@b.c",
                            "subject": "Re: Вопрос",
                            "body": "Да, давайте во вторник.",
                            "in_reply_to": "42",
                        },
                    ),
                ),
            ),
            LlmResponse(text='{"summary": "черновик ответа сохранён", "draft_id": "draft-1"}'),
        ]
    )
    department = assemble(
        config=PlatformConfig(enabled_roles=("mail",)),
        plugins=[role],
        provider=provider,
        provider_id="mock",
        catalog=StaticCatalog(default_mock_entries()),
        evaluator=DeterministicEvaluator(),
        memory=MockMemory(),
        include_stdout=False,
    )
    from ai_department.domain.task import ConstraintInput, Task, resolve_constraints

    done = department.orchestrator.submit(
        Task(
            goal="Подготовить ответ",
            constraints=resolve_constraints(
                ConstraintInput(),
                default_steps=20,
                max_steps=100,
                default_revisions=1,
                max_revisions=3,
            ),
            payload={"channel": "mail"},
            correlation_id="mail-2",
        )
    )
    assert done.status is RunStatus.COMPLETED
    assert mailbox.drafts[0]["in_reply_to"] == "42"
    assert isinstance(done.output, dict)
    assert "черновик ответа сохранён" in str(done.output.get("summary"))


def test_list_unread_accepts_numeric_string_limit_and_rejects_junk() -> None:
    import pytest

    mailbox = InMemoryMailbox()
    mailbox.unread.extend(
        {"id": str(i), "from": "a@b.c", "subject": "s", "date": "", "snippet": ""} for i in range(3)
    )
    role = MailRole(mailbox)
    list_unread = next(tool for tool in role.tools() if tool.name == "list_unread")
    result = list_unread.handler({"limit": "2"})
    assert isinstance(result, dict) and len(result["messages"]) == 2
    for junk in ("0", "много", True, 2.5):
        with pytest.raises(ValueError):
            list_unread.handler({"limit": junk})


def test_handle_mailbox_instruction_starts_with_box_address() -> None:
    role = MailRole(InMemoryMailbox(address_value="box@example.com"))
    instruction = role.skills[0].instruction
    assert role.skills[0].skill_id == "handle_mailbox"
    assert instruction.startswith("Ты ведёшь ящик")
    assert "box@example.com" in instruction
    assert "\n" not in instruction


def test_imap_mailbox_refuses_to_connect_without_host() -> None:
    mailbox = ImapSmtpMailbox({})
    try:
        mailbox.list_unread(1)
    except Exception as exc:
        assert getattr(exc, "variable", "") == "IMAP_HOST"
    else:
        raise AssertionError("ожидался отказ без IMAP_HOST")
