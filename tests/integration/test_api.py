"""Четыре операции HTTP на моках."""

from fastapi.testclient import TestClient
from tests.support.factory import calls, final, make_department

from ai_department.domain.errors import ProviderError


def test_health_reports_roles_without_secrets_or_model_calls() -> None:
    department, provider, _clerk = make_department([final("не должно вызываться")])
    client = TestClient(department.app)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["llm_adapter"] == "mock"
    assert body["threads_backend"] == "memory"
    assert body["catalog_models"] >= 1
    assert body["roles"] == [
        {"role_id": "clerk", "description": body["roles"][0]["description"], "state": "Idle"}
    ]
    assert body["roles"][0]["description"]
    assert provider.calls == []
    flat = str(body).lower()
    for forbidden in ("password", "api_key", "reasoner-small", "coder-large"):
        assert forbidden not in flat


def test_api_covers_completion_confirmation_and_missing_role() -> None:
    department, _provider, clerk = make_department(
        [
            calls("read_note", {"key": "a"}, "c1"),
            calls("commit_note", {"key": "a", "text": "текст"}, "c2"),
            final("текст"),
        ]
    )
    client = TestClient(department.app)
    created = client.post("/tasks", json={"goal": "заметка", "payload": {"role": "clerk"}})
    assert created.status_code == 201
    body = created.json()
    run_id = body["run_id"]
    waiting = client.get(f"/runs/{run_id}")
    assert waiting.status_code == 200
    assert waiting.json()["state"] == "WaitingConfirmation"
    confirmation = waiting.json()["pending_confirmation"]["confirmation_id"]
    events = client.get(f"/runs/{run_id}/events")
    assert events.status_code == 200
    assert events.json()[0]["seq"] == 1
    approved = client.post(
        f"/runs/{run_id}/confirmations",
        json={"confirmation_id": confirmation, "decision": "approve"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "completed"
    assert approved.json()["state"] == "Idle"
    assert clerk.committed == ["a"]

    missing = client.post("/tasks", json={"goal": "никому", "payload": {}})
    assert missing.status_code == 201
    foreign = client.get(f"/runs/{missing.json()['run_id']}")
    assert foreign.json()["status"] == "no_role"

    invalid = client.post(
        "/tasks",
        json={"goal": "много", "payload": {"role": "clerk"}, "constraints": {"max_steps": 1000}},
    )
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["kind"] == "validation"


def test_api_exposes_no_model_as_failed_run() -> None:
    from ai_department.composition import assemble
    from ai_department.config import PlatformConfig
    from ai_department.evaluation.deterministic import DeterministicEvaluator
    from ai_department.llm.catalog import StaticCatalog
    from ai_department.llm.mock import MockLlmProvider
    from ai_department.memory.mock import MockMemory
    from roles.clerk.plugin import build_clerk_role

    department = assemble(
        config=PlatformConfig(enabled_roles=()),
        plugins=[build_clerk_role()],
        provider=MockLlmProvider([ProviderError("auth", "нет ключа")]),
        provider_id="mock",
        catalog=StaticCatalog([]),
        evaluator=DeterministicEvaluator(),
        memory=MockMemory(),
        include_stdout=False,
    )
    client = TestClient(department.app)
    created = client.post("/tasks", json={"goal": "заметка", "payload": {"role": "clerk"}})
    assert created.status_code == 201
    run = client.get(f"/runs/{created.json()['run_id']}")
    assert run.json()["status"] == "failed"
    assert run.json()["failure_reason"] == "no_model"
    assert run.status_code == 200
