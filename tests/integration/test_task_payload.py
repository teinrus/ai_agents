"""Доменный payload задачи попадает в ленту и проходит редакцию."""

from tests.support.factory import final, make_department, task

from ai_department.domain.events import EventName


def test_task_payload_is_on_the_feed_and_redacted() -> None:
    department, _provider, _clerk = make_department([final("есть payload")])
    done = department.orchestrator.submit(
        task(payload={"role": "clerk", "api_key": "secret-value"})
    )
    received = next(
        event
        for event in department.feed.list(done.run_id)
        if event.event == EventName.TASK_RECEIVED.value
    )
    domain = received.payload["payload"]
    assert isinstance(domain, dict)
    assert domain["role"] == "clerk"
    assert domain["api_key"] == "***"
