"""Behavior tests for the scrappy package's public lazy exports.

Regression coverage for scrappy-3o7w: the lazy __getattr__ in
src/scrappy/__init__.py imported OrchestratorAdapter from a module that no
longer defines it, so accessing ANY of the five lazy exports raised
ImportError while `import scrappy` itself succeeded (the break was silent
until attribute access).
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

import scrappy

# The checkout under test, derived from THIS FILE's location rather than the working
# directory. A worktree run from anywhere must exercise its own source, and cwd does
# not identify the checkout: a child launched from a worktree inherits the ambient
# editable install and silently resolves whatever OTHER checkout that points at.
CHECKOUT_SRC = Path(__file__).resolve().parents[1] / "src"

# Reports the resolved origin first, then exercises every public lazy export from a
# cold cache exactly as a downstream consumer would.
_EXPORT_PROBE = (
    "import scrappy\n"
    "print(scrappy.__file__)\n"
    "print(','.join(scrappy.__all__))\n"
    "for name in scrappy.__all__:\n"
    "    try:\n"
    "        getattr(scrappy, name)\n"
    "    except Exception as exc:\n"
    "        raise SystemExit(f'{name}: {type(exc).__name__}: {exc}')\n"
)


def _checkout_bound_env(ambient_pythonpath: str | None = None) -> dict[str, str]:
    """Child environment with this checkout's src PREPENDED to PYTHONPATH.

    Prepending is the point: appending would lose to an ambient editable install or
    a stale PYTHONPATH entry inherited from the parent.
    """
    env = dict(os.environ)
    if ambient_pythonpath is not None:
        env["PYTHONPATH"] = ambient_pythonpath
    inherited = env.get("PYTHONPATH")
    env["PYTHONPATH"] = os.pathsep.join(
        [str(CHECKOUT_SRC), inherited] if inherited else [str(CHECKOUT_SRC)]
    )
    return env


def _run_export_probe(env: dict[str, str]) -> tuple[subprocess.CompletedProcess, Path, list[str]]:
    result = subprocess.run(
        [sys.executable, "-c", _EXPORT_PROBE],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    lines = result.stdout.strip().splitlines()
    origin = Path(lines[0]).resolve() if lines else Path()
    names = lines[1].split(",") if len(lines) > 1 else []
    return result, origin, names


def test_every_public_export_resolves_in_fresh_interpreter():
    """Each name in scrappy.__all__ must be accessible on a fresh import.

    Runs in a subprocess so the lazy path is exercised from a cold cache,
    exactly as a downstream consumer would hit it. One interpreter checks
    all names; failure output names the attribute that broke.
    """
    result, origin, names = _run_export_probe(_checkout_bound_env())

    assert result.returncode == 0, (
        f"public export failed to resolve: {result.stderr.strip()}"
    )
    # ORIGIN PROVED, not merely requested via env: the child reports the file it
    # actually imported, and it must live under THIS checkout.
    assert origin.is_relative_to(CHECKOUT_SRC), (
        f"child imported scrappy from {origin}, not from the checkout under test "
        f"at {CHECKOUT_SRC}"
    )
    # A vacuous pass with zero exports would otherwise satisfy the loop above.
    assert names == list(scrappy.__all__), (origin, names)


def test_lazy_exports_point_at_canonical_definitions():
    """The package-level names must be the same objects as their real homes.

    Guards against the export drifting to a stale copy or shim when the
    underlying class moves modules again.
    """
    from scrappy.orchestrator.protocols import ContextProvider, OrchestratorAdapter
    from scrappy.orchestrator.provider_types import LLMResponse
    from scrappy.orchestrator_adapter import AgentOrchestratorAdapter, NullContext

    assert scrappy.OrchestratorAdapter is OrchestratorAdapter
    assert scrappy.ContextProvider is ContextProvider
    assert scrappy.LLMResponse is LLMResponse
    assert scrappy.AgentOrchestratorAdapter is AgentOrchestratorAdapter
    assert scrappy.NullContext is NullContext


def test_unknown_attribute_raises_attribute_error():
    """__getattr__ must reject unknown names with AttributeError, not ImportError."""
    with pytest.raises(AttributeError, match="no attribute 'DoesNotExist'"):
        scrappy.DoesNotExist


def test_fresh_interpreter_ignores_a_misleading_ambient_scrappy(tmp_path):
    """A hostile ambient PYTHONPATH must not displace the checkout under test.

    Without the checkout binding this test fails loudly: the child resolves the
    decoy and reports its sentinel export instead of the real package. That is the
    same failure mode as the real defect, where an ambient editable install pointed
    a worktree's child at a DIFFERENT checkout's source and the suite passed while
    validating the wrong tree.
    """
    decoy_root = tmp_path / "decoy"
    (decoy_root / "scrappy").mkdir(parents=True)
    (decoy_root / "scrappy" / "__init__.py").write_text(
        '__all__ = ["SENTINEL_WRONG_CHECKOUT"]\nSENTINEL_WRONG_CHECKOUT = "decoy"\n',
        encoding="utf-8",
    )

    result, origin, names = _run_export_probe(
        _checkout_bound_env(ambient_pythonpath=str(decoy_root))
    )

    assert result.returncode == 0, result.stderr.strip()
    assert origin.is_relative_to(CHECKOUT_SRC), (
        f"a misleading ambient PYTHONPATH won: child imported {origin}"
    )
    assert "SENTINEL_WRONG_CHECKOUT" not in names, names
    assert names == list(scrappy.__all__), names
