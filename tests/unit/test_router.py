"""Роутер: разные требования, выключенная модель, пустой список."""

from datetime import UTC, datetime

from ai_department.domain.errors import NoModelError
from ai_department.domain.events import EventName
from ai_department.domain.model import Capability, ModelEntry, ModelRequirements, Preference
from ai_department.events.bus import EventBus, RunLogger
from ai_department.llm.catalog import StaticCatalog, default_mock_entries
from ai_department.llm.mock import MockLlmProvider
from ai_department.llm.port import LlmRequest
from ai_department.llm.router import ModelRouter, ProviderDirectory


def _router() -> tuple[ModelRouter, MockLlmProvider, RunLogger, list[object]]:
    seen: list[object] = []
    bus = EventBus(clock=lambda: datetime(2026, 1, 1, tzinfo=UTC), debug=False)
    bus.subscribe(seen.append)
    provider = MockLlmProvider([])
    router = ModelRouter(
        StaticCatalog(default_mock_entries()), ProviderDirectory({"mock": provider})
    )
    log = RunLogger(bus=bus, run_id="run-1", correlation_id="corr")
    return router, provider, log, seen


def test_two_requirements_select_different_models_without_stdout() -> None:
    router, provider, log, _seen = _router()
    cheap = router.route(
        ModelRequirements(
            frozenset({Capability.REASONING, Capability.TOOLS}),
            (Preference.CHEAP,),
            1000,
            "inspect",
        ),
        log,
    )
    coder = router.route(
        ModelRequirements(frozenset({Capability.CODING}), (Preference.CHEAP,), 1000, "publish"),
        log,
    )
    assert cheap.model_id == "cheap-reasoner"
    assert coder.model_id == "coder"
    assert cheap.provider_model_name != coder.provider_model_name
    router.invoke(cheap, LlmRequest(messages=(), tools=()), log, purpose="inspect")
    router.invoke(coder, LlmRequest(messages=(), tools=()), log, purpose="publish")
    assert provider.calls == ["reasoner-small", "coder-large"]


def test_disabled_model_is_not_selected() -> None:
    router, _provider, log, seen = _router()
    selected = router.route(
        ModelRequirements(frozenset({Capability.REASONING}), (Preference.CHEAP,), 1000, "inspect"),
        log,
    )
    assert selected.model_id != "disabled-cheap"
    routed = next(
        item for item in seen if getattr(item, "event", None) == EventName.MODEL_ROUTED.value
    )
    rejected = routed.payload["rejected"]
    assert any(
        row["model_id"] == "disabled-cheap" and row["reason"] == "disabled" for row in rejected
    )


def test_empty_catalog_match_raises_no_model_error() -> None:
    router, provider, log, _seen = _router()
    try:
        router.route(
            ModelRequirements(
                frozenset({Capability.REASONING}), (Preference.CHEAP,), 10**9, "too-big"
            ),
            log,
        )
    except NoModelError as exc:
        assert exc.message
    else:
        raise AssertionError("ожидался NoModelError")
    assert provider.calls == []


def test_equal_rank_keeps_catalog_order() -> None:
    first = ModelEntry(
        "a",
        "mock",
        "a-model",
        frozenset({Capability.REASONING}),
        1000,
        1,
        1,
        True,
    )
    second = ModelEntry(
        "b",
        "mock",
        "b-model",
        frozenset({Capability.REASONING}),
        1000,
        1,
        1,
        True,
    )
    bus = EventBus(clock=lambda: datetime(2026, 1, 1, tzinfo=UTC), debug=False)
    log = RunLogger(bus=bus, run_id="run", correlation_id="corr")
    router = ModelRouter(
        StaticCatalog((first, second)), ProviderDirectory({"mock": MockLlmProvider([])})
    )
    selected = router.route(
        ModelRequirements(
            frozenset({Capability.REASONING}), (Preference.CHEAP, Preference.FAST), 100, "x"
        ),
        log,
    )
    assert selected.model_id == "a"
