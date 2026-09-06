"""Tests for the containment env key set and the CONFLICT RULE (plan 3b, 3c)."""

import pytest

from tests.containment.env import (
    CONTAINMENT_ENV_KEYS,
    ContainmentConflictError,
    assert_no_containment_conflict,
    forward_env,
)


def test_key_set_matches_launcher_assignment():
    """The forwarded key set is exactly what scripts/contained-pytest.sh assigns (3b)."""
    assert CONTAINMENT_ENV_KEYS == {
        "HOME",
        "XDG_DATA_HOME",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "HF_HOME",
        "HUGGINGFACE_HUB_CACHE",
        "HF_HUB_CACHE",
        "HF_ASSETS_CACHE",
        "FASTEMBED_CACHE_PATH",
        "PYTHON_DOTENV_DISABLED",
        "TMPDIR",
        "TEMP",
        "TMP",
        "SCRAPPY_TEST_TEMP",
        "SCRAPPY_TEST_SESSION_ID",
        "CLI_CONFIG_PATH",
    }


def test_forward_env_selects_only_containment_keys():
    source = {"HOME": "/x", "CLI_CONFIG_PATH": "/y", "SCRAPPY_MOCK_LLM": "1", "PATH": "/bin"}
    assert forward_env(source) == {"HOME": "/x", "CLI_CONFIG_PATH": "/y"}


def test_conflict_rule_raises_on_a_containment_key():
    with pytest.raises(ContainmentConflictError) as excinfo:
        assert_no_containment_conflict({"HOME": "/outside/hostile"}, channel="extra_env")
    assert "HOME" in str(excinfo.value)
    assert "extra_env" in str(excinfo.value)


def test_conflict_rule_allows_non_containment_keys():
    # SCRAPPY_MOCK_LLM and CUSTOM_FLAG are the only keys current callers supply.
    assert_no_containment_conflict({"SCRAPPY_MOCK_LLM": "1", "CUSTOM_FLAG": "x"}, channel="session.env")


def test_conflict_rule_accepts_empty_or_none():
    assert_no_containment_conflict(None, channel="session.env")
    assert_no_containment_conflict({}, channel="extra_env")
