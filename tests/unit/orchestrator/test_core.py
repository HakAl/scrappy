"""
Unit tests for orchestrator core helpers.
"""

from scrappy.orchestrator.core import _format_trace_chain
from scrappy.orchestrator.provider_types import ProviderAttempt


class TestFormatTraceChain:
    """Tests for formatting provider fallback chains."""

    def test_empty_attempts_returns_none(self):
        """Empty attempts list should return None."""
        assert _format_trace_chain([]) is None

    def test_single_failed_attempt_returns_none(self):
        """Single attempt should not yield a chain."""
        attempts = [
            ProviderAttempt(
                provider="cerebras",
                model="cerebras/llama-3.3-70b",
                success=False,
                error="429",
            )
        ]
        assert _format_trace_chain(attempts) is None

    def test_formats_failed_then_success_with_model_prefix(self):
        """Formats failures and strips provider prefix on success."""
        attempts = [
            ProviderAttempt(
                provider="cerebras",
                model="cerebras/llama-3.3-70b",
                success=False,
                error="429",
            ),
            ProviderAttempt(
                provider="groq",
                model="groq/llama-3.1-8b-instant",
                success=True,
            ),
        ]
        assert _format_trace_chain(attempts) == "cerebras(429)->groq: llama-3.1-8b-instant"

    def test_formats_success_without_provider_prefix(self):
        """Formats success when model name has no provider prefix."""
        attempts = [
            ProviderAttempt(
                provider="local",
                model="custom-model",
                success=False,
                error="timeout",
            ),
            ProviderAttempt(
                provider="local",
                model="custom-model",
                success=True,
            ),
        ]
        assert _format_trace_chain(attempts) == "local(timeout)->local: custom-model"
