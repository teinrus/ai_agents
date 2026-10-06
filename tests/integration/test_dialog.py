"""Приёмная на моках: ответ без прогона, задача, подтверждение через тред."""

import json

from fastapi.testclient import TestClient
from tests.support.factory import calls, final, make_department

from ai_department.domain.errors import ProviderError
from ai_department.domain.thread import ReplyKind
from ai_department.llm.port import LlmResponse


def intake(action: str, **fields: object) -> LlmResponse:
    return LlmResponse(text=json.dumps({"action": action, **fields}, ensure_ascii=False))


def test_unparsable_intake_answer_is_retried_once() -> None:
    department, provider, _clerk = make_department(
        [LlmResponse(text='{"type": "function", "function": {'), intake("reply", text="Да")]
    )
    thread = department.reception.open()
    answered = department.reception.say(thread.thread_id, "привет")
    assert answered.messages[-1].text == "Да"
    assert provider.calls == ["reasoner-small", "reasoner-small"]
    assert answered.run_ids == []


def test_reply_does_not_create_run() -> None:
    department, provider, _clerk = make_department([intake("reply", text="Здравствуйте")])
    thread = department.reception.open()
    answered = department.reception.say(thread.thread_id, "привет")
    assert [item.author for item in answered.messages] == ["user", "assistant"]
    assert answered.messages[-1].kind is ReplyKind.ANSWER
    assert answered.messages[-1].text == "Здравствуйте"
    assert answered.run_ids == []
    assert provider.calls == ["reasoner-small"]
    names = [event.event for event in department.thread_feed.list(thread.thread_id)]
    assert names == [
        "thread.message_received",
        "model.routed",
        "model.called",
        "thread.replied",
    ]


def test_dispatch_runs_task_and_returns_summary() -> None:
    department, _provider, _clerk = make_department(
        [
            intake("dispatch", role_id="clerk", goal="прочитать заметку a"),
            calls("read_note", {"key": "a"}, "c1"),
            final("в заметке пусто"),
        ]
    )
    thread = department.reception.open()
    answered = department.reception.say(thread.thread_id, "что в заметке a?")
    reply = answered.messages[-1]
    assert reply.kind is ReplyKind.COMPLETED
    assert reply.text == "в заметке пусто"
    assert reply.run_id is not None
    assert answered.run_ids == [reply.run_id]
    assert answered.pending is None
    run = department.orchestrator.snapshot(reply.run_id)
    assert run.correlation_id == thread.thread_id
    events = [event.event for event in department.feed.list(reply.run_id)]
    assert events[0] == "task.received"
    assert events[-1] == "task.finished"
    dispatched = [
        event
        for event in department.thread_feed.list(thread.thread_id)
        if event.event == "thread.task_dispatched"
    ]
    assert dispatched[0].payload["payload"] == {"channel": "clerk", "request": "что в заметке a?"}


def test_confirmation_flows_through_thread() -> None:
    department, provider, clerk = make_department(
        [
            intake("dispatch", role_id="clerk", goal="зафиксировать заметку a"),
            calls("commit_note", {"key": "a", "text": "текст"}, "c1"),
            final("зафиксировано"),
            intake("reply", text="не должно вызываться"),
        ]
    )
    thread = department.reception.open()
    waiting = department.reception.say(thread.thread_id, "зафиксируй заметку a")
    assert waiting.messages[-1].kind is ReplyKind.WAITING_CONFIRMATION
    assert waiting.pending is not None
    assert waiting.pending.tool == "commit_note"
    assert clerk.committed == []
    calls_before = list(provider.calls)

    reminded = department.reception.say(thread.thread_id, "а ещё сделай вот это")
    assert reminded.messages[-1].kind is ReplyKind.WAITING_CONFIRMATION
    assert reminded.run_ids == waiting.run_ids
    assert provider.calls == calls_before

    done = department.reception.confirm(
        thread.thread_id, waiting.pending.confirmation_id, "approve"
    )
    assert done.messages[-1].kind is ReplyKind.COMPLETED
    assert done.messages[-1].text == "зафиксировано"
    assert done.pending is None
    assert clerk.committed == ["a"]


def test_intake_failure_without_run() -> None:
    department, _provider, _clerk = make_department([ProviderError("auth", "нет ключа")])
    thread = department.reception.open()
    answered = department.reception.say(thread.thread_id, "привет")
    assert answered.messages[-1].kind is ReplyKind.FAILED
    assert answered.run_ids == []


def test_unknown_role_hint_falls_back_to_the_only_role() -> None:
    department, _provider, _clerk = make_department(
        [
            intake("dispatch", role_id="<id из списка>", goal="прочитать заметку a"),
            calls("read_note", {"key": "a"}, "c1"),
            final("ок"),
        ]
    )
    thread = department.reception.open()
    answered = department.reception.say(thread.thread_id, "сделай что-то")
    assert answered.messages[-1].kind is ReplyKind.COMPLETED
    run = department.orchestrator.snapshot(answered.run_ids[0])
    assert run.role_id == "clerk"


def test_unknown_role_with_several_roles_yields_no_role() -> None:
    from roles.clerk.plugin import build_clerk_role
    from roles.records.plugin import build_records_role

    department, _provider, _clerk = make_department(
        [intake("dispatch", role_id="ghost", goal="что-то")],
        plugins=[build_records_role(), build_clerk_role()],
    )
    thread = department.reception.open()
    answered = department.reception.say(thread.thread_id, "сделай что-то")
    assert answered.messages[-1].kind is ReplyKind.NO_ROLE
    assert len(answered.run_ids) == 1


def test_degenerate_goal_is_replaced_by_request_text() -> None:
    department, _provider, _clerk = make_department(
        [
            calls(
                "dispatch", {"role_id": "clerk", "goal": "Просьба человека своими словами"}, "d1"
            ),
            final("ок"),
        ]
    )
    thread = department.reception.open()
    department.reception.say(thread.thread_id, "прочитай заметку a и перескажи")
    dispatched = next(
        event
        for event in department.thread_feed.list(thread.thread_id)
        if event.event == "thread.task_dispatched"
    )
    assert dispatched.payload["goal"] == "прочитай заметку a и перескажи"


def test_structured_call_decision_is_preferred_over_text() -> None:
    department, _provider, _clerk = make_department(
        [
            calls("dispatch", {"role_id": "clerk", "goal": "прочитать заметку a"}, "d1"),
            calls("read_note", {"key": "a"}, "c1"),
            final("из вызова"),
        ]
    )
    thread = department.reception.open()
    answered = department.reception.say(thread.thread_id, "что в заметке a?")
    assert answered.messages[-1].kind is ReplyKind.COMPLETED
    assert answered.messages[-1].text == "из вызова"


def test_thread_api_covers_open_say_confirm_and_events() -> None:
    department, _provider, clerk = make_department(
        [
            intake("dispatch", role_id="clerk", goal="зафиксировать заметку b"),
            calls("commit_note", {"key": "b", "text": "т"}, "c1"),
            final("готово"),
        ]
    )
    client = TestClient(department.app)
    opened = client.post("/threads")
    assert opened.status_code == 201
    thread_id = opened.json()["thread_id"]

    said = client.post(f"/threads/{thread_id}/messages", json={"text": "зафиксируй b"})
    assert said.status_code == 200
    body = said.json()
    assert body["messages"][-1]["kind"] == "waiting_confirmation"
    assert body["pending"]["tool"] == "commit_note"

    confirmed = client.post(
        f"/threads/{thread_id}/confirmations",
        json={"confirmation_id": body["pending"]["confirmation_id"], "decision": "approve"},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["messages"][-1]["kind"] == "completed"
    assert confirmed.json()["pending"] is None
    assert clerk.committed == ["b"]

    again = client.post(
        f"/threads/{thread_id}/confirmations",
        json={"confirmation_id": body["pending"]["confirmation_id"], "decision": "approve"},
    )
    assert again.status_code == 409

    read = client.get(f"/threads/{thread_id}")
    assert read.status_code == 200
    assert len(read.json()["messages"]) == 3

    events = client.get(f"/threads/{thread_id}/events")
    assert events.status_code == 200
    assert events.json()[0]["event"] == "thread.message_received"
    assert all(event["run_id"] == "" for event in events.json())

    missing = client.get("/threads/none")
    assert missing.status_code == 404
    empty = client.post(f"/threads/{thread_id}/messages", json={"text": ""})
    assert empty.status_code == 422
