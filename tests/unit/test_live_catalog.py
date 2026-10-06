"""Живой каталог перечитывает файл на каждом list()."""

import json
from datetime import UTC, datetime
from pathlib import Path

from ai_department.domain.model import Capability, ModelRequirements, Preference
from ai_department.events.bus import EventBus, RunLogger
from ai_department.llm.catalog import ReloadingCatalog
from ai_department.llm.router import ModelRouter, ProviderDirectory


def test_live_catalog_picks_up_a_new_row(tmp_path: Path) -> None:
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps([_row("first-model")]), encoding="utf-8")
    catalog = ReloadingCatalog(str(path))
    router = ModelRouter(catalog, ProviderDirectory({}))
    log = RunLogger(
        bus=EventBus(clock=lambda: datetime(2026, 1, 1, tzinfo=UTC), debug=False),
        run_id="run",
        correlation_id="corr",
    )
    requirements = ModelRequirements(
        capabilities=frozenset({Capability.REASONING}),
        preferences=(Preference.CHEAP,),
        min_context_window=1000,
        purpose="check",
    )
    assert router.route(requirements, log).model_id == "first-model"
    path.write_text(json.dumps([_row("second-model")]), encoding="utf-8")
    assert catalog.list()[0].model_id == "second-model"
    assert router.route(requirements, log).model_id == "second-model"


def _row(model_id: str) -> dict[str, object]:
    return {
        "model_id": model_id,
        "provider_id": "mock",
        "provider_model_name": model_id,
        "capabilities": ["reasoning"],
        "context_window": 8000,
        "cost_tier": 1,
        "latency_tier": 1,
        "enabled": True,
    }
