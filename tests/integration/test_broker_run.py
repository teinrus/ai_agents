"""Прогон пишет конверты в брокер, чтение держит порядок seq."""

import json
from pathlib import Path

from ai_department.composition import build_from_environment
from ai_department.domain.task import ConstraintInput, Task, resolve_constraints
from ai_department.events.broker import FileBroker


def test_finished_run_is_ordered_in_the_broker(tmp_path: Path) -> None:
    journal = tmp_path / "events.log"
    script = json.dumps(
        [{"text": json.dumps({"summary": "готово"}, ensure_ascii=False)}],
        ensure_ascii=False,
    )
    department = build_from_environment(
        {
            "LLM_ADAPTER": "mock",
            "ENABLED_ROLES": "clerk",
            "MEMORY_BACKEND": "memory",
            "MOCK_LLM_SCRIPT": script,
            "BROKER_PATH": str(journal),
        }
    )
    department.orchestrator.submit(
        Task(
            goal="Заметка",
            constraints=resolve_constraints(
                ConstraintInput(),
                default_steps=20,
                max_steps=100,
                default_revisions=1,
                max_revisions=3,
            ),
            payload={"role": "clerk"},
            correlation_id="broker-1",
        )
    )
    names = [event.event for event in FileBroker(str(journal)).read()]
    assert names.index("evaluation.completed") < names.index("task.finished")
