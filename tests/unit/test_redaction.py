"""Редакция до публикации."""

from datetime import UTC, datetime

from ai_department.domain.events import Envelope, EventLevel
from ai_department.events.bus import EventBus
from ai_department.events.redaction import redact_payload


def test_password_and_authorization_do_not_survive() -> None:
    cleaned = redact_payload(
        {
            "password": "hunter2",
            "Authorization": "Bearer sk-live",
            "tokens": 12,
            "goal": "обычная цель",
        }
    )
    assert cleaned["password"] == "***"
    assert cleaned["Authorization"] == "***"
    assert cleaned["tokens"] == 12
    assert "hunter2" not in str(cleaned)
    assert "sk-live" not in str(cleaned)


def test_bus_redacts_before_subscribers_see_the_event() -> None:
    seen: list[Envelope] = []
    bus = EventBus(clock=lambda: datetime(2026, 1, 1, tzinfo=UTC), debug=False)
    bus.subscribe(seen.append)
    bus.publish(
        Envelope(
            ts="",
            seq=0,
            level=EventLevel.INFO,
            correlation_id="c",
            run_id="run-1",
            event="task.received",
            role_id=None,
            step=None,
            message="Задача принята",
            payload={"goal": "hi", "api_key": "secret-key"},
        )
    )
    assert seen[0].seq == 1
    assert seen[0].payload["api_key"] == "***"
    assert "secret-key" not in str(seen[0].payload)
