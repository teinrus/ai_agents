"""Старт процесса: моки без секретов, локальный адаптер без переменной не стартует."""

import pytest

from ai_department.composition import build_from_environment
from ai_department.domain.errors import ConfigError


def test_mock_process_starts_without_secrets() -> None:
    department = build_from_environment(
        {"LLM_ADAPTER": "mock", "ENABLED_ROLES": "clerk", "MEMORY_BACKEND": "memory"}
    )
    assert department.app.title == "AI Department"


def test_local_adapter_without_variable_names_it() -> None:
    with pytest.raises(ConfigError) as missing_url:
        build_from_environment({"LLM_ADAPTER": "local", "ENABLED_ROLES": "clerk"})
    assert missing_url.value.variable == "LOCAL_LLM_BASE_URL"
    with pytest.raises(ConfigError) as missing_key:
        build_from_environment(
            {
                "LLM_ADAPTER": "local",
                "ENABLED_ROLES": "clerk",
                "LOCAL_LLM_BASE_URL": "http://127.0.0.1:9/v1",
            }
        )
    assert missing_key.value.variable == "LOCAL_LLM_API_KEY"


def test_cloud_adapter_without_variable_names_it() -> None:
    with pytest.raises(ConfigError) as missing_url:
        build_from_environment({"LLM_ADAPTER": "cloud", "ENABLED_ROLES": "clerk"})
    assert missing_url.value.variable == "CLOUD_LLM_BASE_URL"
    with pytest.raises(ConfigError) as missing_key:
        build_from_environment(
            {
                "LLM_ADAPTER": "cloud",
                "ENABLED_ROLES": "clerk",
                "CLOUD_LLM_BASE_URL": "http://127.0.0.1:9/v1",
            }
        )
    assert missing_key.value.variable == "CLOUD_LLM_API_KEY"


def test_live_catalog_without_path_names_the_variable() -> None:
    with pytest.raises(ConfigError) as missing:
        build_from_environment(
            {
                "LLM_ADAPTER": "mock",
                "ENABLED_ROLES": "clerk",
                "MODEL_CATALOG_SOURCE": "live",
            }
        )
    assert missing.value.variable == "MODEL_CATALOG_PATH"


def test_shared_backend_starts(tmp_path: object) -> None:
    from pathlib import Path

    department = build_from_environment(
        {
            "LLM_ADAPTER": "mock",
            "ENABLED_ROLES": "clerk",
            "MEMORY_BACKEND": "shared",
            "MEMORY_SHARED_PATH": str(Path(str(tmp_path)) / "shared"),
        }
    )
    assert department.app.title == "AI Department"


def test_sqlite_backend_does_not_require_role_changes(tmp_path: object) -> None:
    from pathlib import Path

    path = Path(str(tmp_path)) / "memory.db"
    department = build_from_environment(
        {
            "LLM_ADAPTER": "mock",
            "ENABLED_ROLES": "clerk",
            "MEMORY_BACKEND": "sqlite",
            "MEMORY_SQLITE_PATH": str(path),
        }
    )
    created = department.app
    assert created is not None
