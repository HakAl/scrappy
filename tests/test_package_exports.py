"""Behavior tests for the scrappy package's public lazy exports.

Regression coverage for scrappy-3o7w: the lazy __getattr__ in
src/scrappy/__init__.py imported OrchestratorAdapter from a module that no
longer defines it, so accessing ANY of the five lazy exports raised
ImportError while `import scrappy` itself succeeded (the break was silent
until attribute access).
"""

import subprocess
import sys

import pytest

import scrappy


def test_every_public_export_resolves_in_fresh_interpreter():
    """Each name in scrappy.__all__ must be accessible on a fresh import.

    Runs in a subprocess so the lazy path is exercised from a cold cache,
    exactly as a downstream consumer would hit it. One interpreter checks
    all names; failure output names the attribute that broke.
    """
    script = (
        "import scrappy\n"
        "for name in scrappy.__all__:\n"
        "    try:\n"
        "        getattr(scrappy, name)\n"
        "    except Exception as exc:\n"
        "        raise SystemExit(f'{name}: {type(exc).__name__}: {exc}')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"public export failed to resolve: {result.stderr.strip()}"
    )


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
