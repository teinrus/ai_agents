"""Настройки процесса. Секреты читает только корень сборки."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from ai_department.domain.errors import ConfigError
from ai_department.domain.risk import RiskLevel, parse_risk


@dataclass(frozen=True)
class PlatformConfig:
    """Пределы и выбор адаптеров."""

    max_steps_default: int = 20
    max_steps_max: int = 100
    max_revisions_default: int = 1
    max_revisions_max: int = 3
    role_threshold: float = 0.5
    platform_risk_ceiling: RiskLevel = RiskLevel.ACT
    max_provider_retries: int = 1
    debug_events: bool = False
    llm_adapter: str = "mock"
    memory_backend: str = "memory"
    sqlite_path: str = "data/memory.db"
    enabled_roles: tuple[str, ...] = ()
    model_catalog_path: str | None = None
    local_llm_base_url: str | None = None
    local_llm_api_key: str | None = None
    local_llm_model: str = "local-model"
    cloud_llm_base_url: str | None = None
    cloud_llm_api_key: str | None = None
    cloud_llm_model: str = "cloud-model"
    catalog_source: str = "startup"
    broker_path: str | None = None
    shared_path: str = "data/shared"
    dialog_history_limit: int = 12


def load_config(environ: Mapping[str, str] | None = None) -> PlatformConfig:
    """Читает окружение. Пустой словарь не подменяет значения процессом."""
    env = os.environ if environ is None else environ
    ceiling = parse_risk(env.get("PLATFORM_RISK_CEILING", "act"))
    if ceiling is RiskLevel.DESTRUCTIVE:
        raise ConfigError("PLATFORM_RISK_CEILING", "Уровень destructive закрыт")
    adapter = env.get("LLM_ADAPTER", "mock")
    if adapter not in {"mock", "local", "cloud"}:
        raise ConfigError("LLM_ADAPTER", "LLM_ADAPTER должен быть mock, local или cloud")
    backend = env.get("MEMORY_BACKEND", "memory")
    if backend not in {"memory", "sqlite", "shared"}:
        raise ConfigError("MEMORY_BACKEND", "MEMORY_BACKEND должен быть memory, sqlite или shared")
    catalog_source = env.get("MODEL_CATALOG_SOURCE", "startup")
    if catalog_source not in {"startup", "live"}:
        raise ConfigError(
            "MODEL_CATALOG_SOURCE", "MODEL_CATALOG_SOURCE должен быть startup или live"
        )
    roles = tuple(part.strip() for part in env.get("ENABLED_ROLES", "").split(",") if part.strip())
    catalog = env.get("MODEL_CATALOG_PATH") or None
    return PlatformConfig(
        max_steps_default=_integer(env, "PLATFORM_MAX_STEPS_DEFAULT", 20),
        max_steps_max=_integer(env, "PLATFORM_MAX_STEPS_MAX", 100),
        max_revisions_default=_integer(env, "PLATFORM_MAX_REVISIONS_DEFAULT", 1),
        max_revisions_max=_integer(env, "PLATFORM_MAX_REVISIONS_MAX", 3),
        role_threshold=float(env.get("PLATFORM_ROLE_THRESHOLD", "0.5")),
        platform_risk_ceiling=ceiling,
        max_provider_retries=_integer(env, "PLATFORM_MAX_PROVIDER_RETRIES", 1),
        debug_events=env.get("PLATFORM_DEBUG_EVENTS", "false").lower() == "true",
        llm_adapter=adapter,
        memory_backend=backend,
        sqlite_path=env.get("MEMORY_SQLITE_PATH", "data/memory.db"),
        enabled_roles=roles,
        model_catalog_path=catalog,
        local_llm_base_url=env.get("LOCAL_LLM_BASE_URL") or None,
        local_llm_api_key=env.get("LOCAL_LLM_API_KEY") or None,
        local_llm_model=env.get("LOCAL_LLM_MODEL", "local-model"),
        cloud_llm_base_url=env.get("CLOUD_LLM_BASE_URL") or None,
        cloud_llm_api_key=env.get("CLOUD_LLM_API_KEY") or None,
        cloud_llm_model=env.get("CLOUD_LLM_MODEL", "cloud-model"),
        catalog_source=catalog_source,
        broker_path=env.get("BROKER_PATH") or None,
        shared_path=env.get("MEMORY_SHARED_PATH", "data/shared"),
        dialog_history_limit=_integer(env, "PLATFORM_DIALOG_HISTORY_LIMIT", 12),
    )


def require_local_llm(config: PlatformConfig) -> tuple[str, str]:
    """Отказывает старт, если включённому локальному адаптеру не хватает переменной."""
    if not config.local_llm_base_url:
        raise ConfigError("LOCAL_LLM_BASE_URL")
    if not config.local_llm_api_key:
        raise ConfigError("LOCAL_LLM_API_KEY")
    return config.local_llm_base_url, config.local_llm_api_key


def require_cloud_llm(config: PlatformConfig) -> tuple[str, str]:
    """Отказывает старт, если включённому облачному адаптеру не хватает переменной."""
    if not config.cloud_llm_base_url:
        raise ConfigError("CLOUD_LLM_BASE_URL")
    if not config.cloud_llm_api_key:
        raise ConfigError("CLOUD_LLM_API_KEY")
    return config.cloud_llm_base_url, config.cloud_llm_api_key


def _integer(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(name, f"{name} должно быть целым") from exc
