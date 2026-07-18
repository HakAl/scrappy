"""Channel-contract tests for DefaultThinkErrorHandler.

PR-4 Option D: ThinkResult.error carries the message plus cause chain,
ThinkResult.suggestion carries the actionable copy. The error channel
never embeds owned "Suggestion:" text; that invariant is scoped to
BaseError rendering that this codebase authors.
"""

import pytest

from scrappy.graph.nodes.think_error_handler import DefaultThinkErrorHandler
from scrappy.infrastructure.exceptions import (
    AuthenticationError,
    NetworkError,
    ProviderError,
    ProviderExecutionError,
    RateLimitError,
    RecoveryAction,
    TimeoutError as InfraTimeoutError,
)
from scrappy.infrastructure.exceptions.provider_errors import (
    RouterGroupExhaustedError,
)
from scrappy.orchestrator.litellm_service import (
    NOT_CONFIGURED_SUGGESTION,
    NotConfiguredError,
)
from scrappy.orchestrator.model_selection import SelectionExhaustedError


@pytest.fixture
def handler():
    return DefaultThinkErrorHandler()


class TestChannelSeparation:
    """Suggestion travels only in ThinkResult.suggestion."""

    @pytest.mark.parametrize(
        "error",
        [
            AuthenticationError("Auth failed for groq", provider_name="groq"),
            RateLimitError("Rate limit exceeded for groq", retry_after=30.0),
            NetworkError("Could not connect to groq"),
            InfraTimeoutError("Request to groq timed out"),
            ProviderExecutionError(
                "Provider request failed",
                suggestion="Try again or use a different provider.",
            ),
            ProviderError(
                "Generic provider failure",
                suggestion="Configure another provider.",
            ),
        ],
        ids=[
            "auth",
            "rate_limit",
            "network",
            "timeout",
            "provider_execution",
            "generic_provider",
        ],
    )
    def test_suggestion_channel_populated_error_channel_clean(
        self, handler, error
    ):
        result = handler.handle(error)

        assert result.suggestion == error.suggestion
        assert error.message in result.error
        assert "Suggestion:" not in result.error

    def test_nested_base_error_cause_never_leaks_suggestion(self, handler):
        """A suggestion-bearing BaseError cause must not re-embed its copy."""
        inner = AuthenticationError("inner auth failed", provider_name="groq")
        assert inner.suggestion  # premise: the nested cause carries copy
        outer = ProviderExecutionError(
            "outer request failed",
            original_error=inner,
            suggestion="outer suggestion",
        )

        result = handler.handle(outer)

        assert "outer request failed" in result.error
        assert "inner auth failed" in result.error
        assert "Suggestion:" not in result.error
        assert result.suggestion == "outer suggestion"

    def test_router_group_exhausted_rich_message_and_suggestion(self, handler):
        error = RouterGroupExhaustedError(
            "",
            provider_details={"groq": {"retry_after": 30}},
        )

        result = handler.handle(error)

        assert result.error == (
            "Rate limited by all providers:\n  - groq: retry after 30s"
        )
        assert "Suggestion:" not in result.error
        assert result.suggestion == "Wait 30s or add another provider API key."
        assert result.recovery_action == RecoveryAction.FALLBACK.value
        assert result.is_fatal is False

    def test_selection_exhausted_keeps_explicit_suggestion_field(self, handler):
        error = SelectionExhaustedError("no models available")

        result = handler.handle(error)

        assert result.error == "no models available"
        assert result.suggestion == error.suggestion
        assert result.recovery_action == RecoveryAction.FALLBACK.value

    def test_not_configured_result_is_fatal_with_suggestion(self, handler):
        result = handler.handle(NotConfiguredError())

        assert result.is_fatal is True
        assert result.recovery_action == RecoveryAction.ABORT.value
        assert "/setup" in result.error
        assert result.suggestion == NOT_CONFIGURED_SUGGESTION

    def test_not_configured_carries_default_suggestion(self):
        error = NotConfiguredError()

        assert error.suggestion == "Run /setup to configure provider API keys."
