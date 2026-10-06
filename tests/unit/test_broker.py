"""Брокер восстанавливает порядок по seq, даже если строки пришли наоборот."""

import json
from pathlib import Path

from ai_department.events.broker import FileBroker


def test_broker_restores_evaluation_before_finished(tmp_path: Path) -> None:
    path = tmp_path / "bus.log"
    path.write_text(
        "\n".join(
            [
                json.dumps(_line(2, "task.finished")),
                json.dumps(_line(1, "evaluation.completed")),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    events = FileBroker(str(path)).read()
    names = [event.event for event in events]
    assert names.index("evaluation.completed") < names.index("task.finished")
    assert [event.seq for event in events] == [1, 2]


def _line(seq: int, event: str) -> dict[str, object]:
    return {
        "ts": "2026-01-01T00:00:00Z",
        "seq": seq,
        "level": "INFO",
        "correlation_id": "corr",
        "run_id": "run-1",
        "event": event,
        "role_id": "clerk",
        "step": None,
        "message": event,
        "payload": {},
    }
