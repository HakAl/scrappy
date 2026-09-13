"""Tests for the containment env key set and the CONFLICT RULE (plan 3b, 3c)."""

import re
from pathlib import Path

import pytest

from tests.containment.env import (
    CONTAINMENT_ENV_KEYS,
    ContainmentConflictError,
    assert_no_containment_conflict,
    forward_env,
)


LAUNCHER = Path(__file__).resolve().parents[2] / "scripts" / "contained-pytest.sh"


def launcher_exported_keys() -> set[str]:
    """Return the variables scripts/contained-pytest.sh actually exports (STEP D)."""
    return set(re.findall(r"(?m)^export ([A-Za-z_][A-Za-z0-9_]*)=", LAUNCHER.read_text()))


def test_key_set_matches_launcher_assignment():
    """The forwarded key set is exactly what scripts/contained-pytest.sh assigns (3b).

    READ FROM THE LAUNCHER, not restated here. A hand-copied list drifts silently: it
    would still pass after someone added an export to the launcher, and the macOS and
    tmux harnesses would then stop forwarding a key the launcher owns, which is exactly
    the S-5 failure this constant exists to prevent.
    """
    exported = launcher_exported_keys()
    assert exported, f"no export lines found in {LAUNCHER}; the parser has drifted"
    assert set(CONTAINMENT_ENV_KEYS) == exported, (
        f"launcher exports {sorted(exported - set(CONTAINMENT_ENV_KEYS))} not in the key set; "
        f"key set has {sorted(set(CONTAINMENT_ENV_KEYS) - exported)} the launcher does not export"
    )


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
