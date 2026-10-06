"""Разбор решения модели приёмной."""

from ai_department.dialog.intake import Dispatch, Reply, decision_from_calls, parse_decision
from ai_department.domain.tools import ToolCall


def test_structured_dispatch_and_reply_calls() -> None:
    dispatch = decision_from_calls(
        [ToolCall("c1", "dispatch", {"role_id": "mail", "goal": " прочитать почту "})]
    )
    assert dispatch == Dispatch(role_id="mail", goal="прочитать почту")
    reply = decision_from_calls([ToolCall("c2", "reply", {"text": "Привет"})])
    assert reply == Reply("Привет")
    assert decision_from_calls([ToolCall("c3", "other", {"x": 1})]) is None
    assert decision_from_calls([ToolCall("c4", "dispatch", {"role_id": "", "goal": "x"})]) is None


def test_dispatch_with_payload() -> None:
    decision = parse_decision(
        '{"action": "dispatch", "role_id": "clerk", "goal": " записать ", "payload": {"k": 1}}'
    )
    assert decision == Dispatch(role_id="clerk", goal="записать", payload={"k": 1})


def test_dispatch_without_payload_inside_fence() -> None:
    decision = parse_decision(
        '```json\n{"action": "dispatch", "role_id": "records", "goal": "список"}\n```'
    )
    assert decision == Dispatch(role_id="records", goal="список", payload={})


def test_reply_action() -> None:
    assert parse_decision('{"action": "reply", "text": "Привет"}') == Reply("Привет")


def test_plain_text_becomes_reply() -> None:
    assert parse_decision("Чем могу помочь?") == Reply("Чем могу помочь?")


def test_malformed_json_decision_hides_raw_json() -> None:
    for raw in ('{"action": "dispatch", "goal": "без роли"}', "{}", '{"summary": "x"}'):
        decision = parse_decision(raw)
        assert isinstance(decision, Reply)
        assert "{" not in decision.text


def test_broken_call_fragment_is_hidden_from_client() -> None:
    for raw in (
        '{"type": "function", "function": {reply {text: "Привет"',
        '```json\n{"action": "reply", "text": ',
        '<tool_call>{"name": "reply"}',
    ):
        decision = parse_decision(raw)
        assert isinstance(decision, Reply)
        assert "{" not in decision.text and "<" not in decision.text


def test_empty_text_gets_fallback_reply() -> None:
    decision = parse_decision("   ")
    assert isinstance(decision, Reply)
    assert decision.text
