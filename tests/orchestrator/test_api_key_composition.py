"""
Behavior tests for the production API key service composition.

Exercises create_api_key_service() end to end at the filesystem boundary:
tmp config paths only, never the real user config dir.
"""

import json

import pytest

from scrappy.orchestrator.api_key_composition import create_api_key_service
from scrappy.orchestrator.provider_catalog import build_default_catalog

_CATALOG_ENV_VARS = build_default_catalog().known_provider_env_vars()


def _clear_provider_env(monkeypatch):
    """Isolate from any provider keys present in the real environment."""
    for env_var in _CATALOG_ENV_VARS:
        monkeypatch.delenv(env_var, raising=False)


def _persisted_api_keys(config_file):
    return json.loads(config_file.read_text())["api_keys"]


@pytest.mark.parametrize("env_var", _CATALOG_ENV_VARS)
def test_migrates_each_catalog_known_env_var(env_var, tmp_path, monkeypatch):
    """Every catalog-known provider env var migrates into the persisted file."""
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv(env_var, "gsk_test_key_1234567890")
    config_file = tmp_path / "config.json"

    service = create_api_key_service(config_file=config_file)
    service.load(migrate_env=True)

    assert _persisted_api_keys(config_file)[env_var] == "gsk_test_key_1234567890"


def test_does_not_migrate_non_catalog_env_var(tmp_path, monkeypatch):
    """An env var the catalog does not know stays out of the persisted file."""
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("NOT_A_PROVIDER_API_KEY", "gsk_test_key_1234567890")
    config_file = tmp_path / "config.json"

    service = create_api_key_service(config_file=config_file)
    service.load(migrate_env=True)

    persisted = _persisted_api_keys(config_file) if config_file.exists() else {}
    assert "NOT_A_PROVIDER_API_KEY" not in persisted


def test_persists_to_user_config_path_by_default(tmp_path, monkeypatch):
    """Without config_file, writes land at paths.USER_CONFIG_FILE.

    Patching at the source module works because the factory dereferences
    paths.USER_CONFIG_FILE at call time, never at import time.
    """
    _clear_provider_env(monkeypatch)
    target = tmp_path / "config.json"
    monkeypatch.setattr("scrappy.infrastructure.paths.USER_CONFIG_FILE", target)

    service = create_api_key_service()
    service.set_key("CEREBRAS_API_KEY", "csk_abc123xyz789")

    assert _persisted_api_keys(target)["CEREBRAS_API_KEY"] == "csk_abc123xyz789"
