"""Containment environment key set and the CONFLICT RULE (plan 3b, 3c).

CONTAINMENT_ENV_KEYS is the single source of truth for which variables the launcher
owns. The independently-based children (macOS iTerm2, the tmux server) do NOT inherit
the pytest environment (plan S-5), so the harness fixes forward exactly these keys
into their command strings via forward_env().

THE CONFLICT RULE (plan 3c, decided rev 8 by input I2): a containment key supplied
through a caller channel is a HARD ERROR, not a silent override. A test that believes
it set HOME and did not is a worse failure than a loud refusal.
"""

from __future__ import annotations

from collections.abc import Mapping


# The exact set the launcher assigns (scripts/contained-pytest.sh STEP D, plan 3b).
CONTAINMENT_ENV_KEYS: frozenset[str] = frozenset(
    {
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
)


class ContainmentConflictError(RuntimeError):
    """Raised when a caller channel supplies a key the launcher must own."""


def forward_env(source: Mapping[str, str]) -> dict[str, str]:
    """Return the containment-keyed subset of ``source`` (typically os.environ).

    Used by the macOS and tmux harnesses to forward the launcher's assignments into a
    child whose base environment is the login session or the tmux server and would
    otherwise miss them entirely (plan S-5).
    """
    return {key: source[key] for key in CONTAINMENT_ENV_KEYS if key in source}


def assert_no_containment_conflict(caller_env: Mapping[str, str] | None, *, channel: str) -> None:
    """Enforce the CONFLICT RULE for a caller-supplied environment mapping.

    Raises ContainmentConflictError if ``caller_env`` carries any containment key.
    ``channel`` names the caller surface (for example ``extra_env`` or ``session.env``)
    so the failure points at the exact seam.
    """
    if not caller_env:
        return
    collisions = sorted(set(caller_env) & CONTAINMENT_ENV_KEYS)
    if collisions:
        raise ContainmentConflictError(
            f"caller supplied containment key(s) {collisions} through {channel}; "
            "refusing to launch. The launcher owns these; a test that believes it set "
            "them and did not is a worse failure than a loud refusal."
        )
