"""Единственное место выбора адаптеров и чтения окружения."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from fastapi import FastAPI

from ai_department.api.app import build_router
from ai_department.api.service import RunApi, ThreadApi
from ai_department.config import PlatformConfig, load_config, require_cloud_llm, require_local_llm
from ai_department.dialog.intake import Intake, RoleCard
from ai_department.dialog.reception import Reception
from ai_department.domain.errors import ConfigError
from ai_department.domain.role import RolePlugin
from ai_department.domain.task import ConstraintInput, resolve_constraints
from ai_department.evaluation.deterministic import DeterministicEvaluator
from ai_department.evaluation.port import Evaluator
from ai_department.evaluation.service import EvaluationCycle
from ai_department.events.broker import FileBroker
from ai_department.events.bus import EventBus
from ai_department.llm.catalog import (
    ModelCatalog,
    ReloadingCatalog,
    StaticCatalog,
    default_cloud_entries,
    default_local_entries,
    default_mock_entries,
    load_entries,
)
from ai_department.llm.cloud import CloudLlmProvider
from ai_department.llm.local import LocalLlmProvider
from ai_department.llm.mock import MockLlmProvider
from ai_department.llm.port import LlmProvider
from ai_department.llm.router import ModelRouter, ProviderDirectory
from ai_department.memory.in_memory import InMemoryStore
from ai_department.memory.port import MemoryStore
from ai_department.memory.shared import SharedDirectoryStore
from ai_department.memory.sqlite import SqliteStore
from ai_department.observability.counters import Counters
from ai_department.observability.feed import RunFeed, ThreadFeed
from ai_department.observability.stdout import stdout_subscriber
from ai_department.orchestrator.service import Orchestrator
from ai_department.runtime.loop import Runtime
from ai_department.tools.confirmations import ConfirmationBook, GrantStore
from ai_department.tools.gateway import ToolGateway
from ai_department.tools.registry import ToolRegistry


@dataclass
class Department:
    """Собранная платформа процесса."""

    config: PlatformConfig
    orchestrator: Orchestrator
    reception: Reception
    feed: RunFeed
    thread_feed: ThreadFeed
    counters: Counters
    app: FastAPI


def assemble(
    *,
    config: PlatformConfig,
    plugins: Sequence[RolePlugin],
    provider: LlmProvider,
    provider_id: str,
    catalog: ModelCatalog,
    evaluator: Evaluator,
    memory: MemoryStore,
    clock: Callable[[], datetime] | None = None,
    include_stdout: bool = False,
    ids: Callable[[], str] | None = None,
    broker_path: str | None = None,
) -> Department:
    """Собирает ядро на уже выбранных адаптерах. Роут адаптер не создаёт."""
    now = _now if clock is None else clock
    bus = EventBus(clock=now, debug=config.debug_events)
    feed = RunFeed()
    thread_feed = ThreadFeed()
    counters = Counters()
    bus.subscribe(feed)
    bus.subscribe(thread_feed)
    bus.subscribe(counters)
    if include_stdout:
        bus.subscribe(stdout_subscriber)
    if broker_path:
        broker = FileBroker(broker_path)
        bus.subscribe(broker.publish)
    grants = GrantStore()
    registry = ToolRegistry()
    confirmations = ConfirmationBook(_new_id if ids is None else ids)
    gateway = ToolGateway(registry, grants, confirmations)
    router = ModelRouter(catalog, ProviderDirectory({provider_id: provider}))
    runtime = Runtime(
        router=router,
        gateway=gateway,
        grants=grants,
        max_provider_retries=config.max_provider_retries,
    )
    orchestrator = Orchestrator(
        runtime=runtime,
        evaluation=EvaluationCycle(evaluator),
        tools=registry,
        confirmations=confirmations,
        bus=bus,
        memory=memory,
        platform_ceiling=config.platform_risk_ceiling,
        role_threshold=config.role_threshold,
        clock=now,
    )
    for plugin in plugins:
        orchestrator.register(plugin)
    api = RunApi(
        orchestrator,
        feed,
        default_steps=config.max_steps_default,
        max_steps=config.max_steps_max,
        default_revisions=config.max_revisions_default,
        max_revisions=config.max_revisions_max,
    )
    reception = Reception(
        orchestrator=orchestrator,
        intake=Intake(
            router,
            [RoleCard(plugin.role_id, plugin.description) for plugin in plugins],
            config.dialog_history_limit,
        ),
        bus=bus,
        default_constraints=resolve_constraints(
            ConstraintInput(),
            default_steps=config.max_steps_default,
            max_steps=config.max_steps_max,
            default_revisions=config.max_revisions_default,
            max_revisions=config.max_revisions_max,
        ),
        ids=_new_id if ids is None else ids,
    )
    app = FastAPI(title="AI Department")
    app.state.api = api
    app.state.threads = ThreadApi(reception, thread_feed)
    app.include_router(build_router())
    return Department(
        config=config,
        orchestrator=orchestrator,
        reception=reception,
        feed=feed,
        thread_feed=thread_feed,
        counters=counters,
        app=app,
    )


def build_from_environment(environ: Mapping[str, str] | None = None) -> Department:
    """Читает окружение и включает роли из конфигурации."""
    config = load_config(environ)
    env = environ if environ is not None else _process_env()
    if config.llm_adapter == "local":
        base_url, api_key = require_local_llm(config)
        provider: LlmProvider = LocalLlmProvider(base_url=base_url, api_key=api_key)
        provider_id = "local"
        entries = (
            load_entries(config.model_catalog_path)
            if config.model_catalog_path
            else default_local_entries(config.local_llm_model)
        )
    elif config.llm_adapter == "cloud":
        cloud_url, cloud_key = require_cloud_llm(config)
        provider = CloudLlmProvider(base_url=cloud_url, api_key=cloud_key)
        provider_id = "cloud"
        entries = (
            load_entries(config.model_catalog_path)
            if config.model_catalog_path
            else default_cloud_entries(config.cloud_llm_model)
        )
    else:
        provider = _mock_from_env(env)
        provider_id = "mock"
        entries = (
            load_entries(config.model_catalog_path)
            if config.model_catalog_path
            else default_mock_entries()
        )
    catalog: ModelCatalog
    if config.catalog_source == "live":
        if not config.model_catalog_path:
            raise ConfigError("MODEL_CATALOG_PATH")
        catalog = ReloadingCatalog(config.model_catalog_path)
    else:
        catalog = StaticCatalog(entries)
    memory: MemoryStore
    if config.memory_backend == "sqlite":
        memory = SqliteStore(config.sqlite_path)
    elif config.memory_backend == "shared":
        memory = SharedDirectoryStore(config.shared_path)
    else:
        memory = InMemoryStore()
    plugins = [_load_role(role_id, env) for role_id in config.enabled_roles]
    return assemble(
        config=config,
        plugins=plugins,
        provider=provider,
        provider_id=provider_id,
        catalog=catalog,
        evaluator=DeterministicEvaluator(),
        memory=memory,
        include_stdout=True,
        broker_path=config.broker_path,
    )


def _load_role(role_id: str, env: Mapping[str, str]) -> RolePlugin:
    module_name, separator, builder_name = {
        "clerk": "roles.clerk.plugin:build_clerk_role",
        "mail": "roles.mail.plugin:build_mail_role",
        "records": "roles.records.plugin:build_records_role",
    }.get(role_id, "").partition(":")
    if not module_name or not separator:
        raise ConfigError("ENABLED_ROLES", f"Неизвестная роль {role_id}")
    module = importlib.import_module(module_name)
    builder = getattr(module, builder_name)
    if not callable(builder):
        raise ConfigError("ENABLED_ROLES", f"У роли {role_id} нет сборщика")
    return cast(RolePlugin, builder(env))


def _mock_from_env(env: Mapping[str, str]) -> MockLlmProvider:
    script = env.get("MOCK_LLM_SCRIPT")
    if not script:
        return MockLlmProvider([])
    import json

    from ai_department.domain.tools import ToolCall
    from ai_department.llm.port import LlmResponse

    raw = json.loads(script)
    responses: list[LlmResponse] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            calls = []
            tool_calls = item.get("tool_calls")
            if isinstance(tool_calls, list):
                for index, call in enumerate(tool_calls):
                    if isinstance(call, dict) and isinstance(call.get("name"), str):
                        arguments = call.get("arguments")
                        calls.append(
                            ToolCall(
                                call_id=f"script-{index}",
                                name=call["name"],
                                arguments=arguments if isinstance(arguments, dict) else {},
                            )
                        )
            text = item.get("text")
            responses.append(
                LlmResponse(text=text if isinstance(text, str) else "", tool_calls=tuple(calls))
            )
    return MockLlmProvider(responses)


def _now() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    from uuid import uuid4

    return uuid4().hex


def _process_env() -> Mapping[str, str]:
    import os

    return os.environ
