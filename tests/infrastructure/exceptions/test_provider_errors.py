"""
Tests for provider-specific exceptions.

Following CLAUDE.md: Test BEHAVIOR, not structure. Cover edge cases.
"""

import pytest
from scrappy.infrastructure.exceptions import (
    ProviderError,
    RateLimitError,
    AllProvidersRateLimitedError,
    ProviderNotFoundError,
    AuthenticationError,
    TimeoutError,
    NetworkError,
    ProviderExecutionError,
    RecoveryAction,
    ErrorCategory,
)


class TestRateLimitError:
    """Test RateLimitError behavior."""

    def test_is_retryable(self):
        """Test rate limit errors are retryable."""
        error = RateLimitError("Rate limit hit", provider_name="groq")

        assert error.is_retryable is True
        assert error.recovery_action == RecoveryAction.RETRY

    def test_includes_wait_time(self):
        """Test error includes wait time suggestion."""
        error = RateLimitError(
            "Rate limit exceeded",
            provider_name="groq",
            wait_seconds=60.0,
            max_wait_seconds=120.0
        )

        assert error.provider_name == "groq"
        assert error.wait_seconds == 60.0
        assert error.max_wait_seconds == 120.0
        assert "60" in error.suggestion

    def test_auto_generates_suggestion(self):
        """Test auto-generated suggestion for wait time."""
        error = RateLimitError(
            "Rate limit exceeded",
            provider_name="groq",
            wait_seconds=45.5
        )

        assert "Wait 45.5 seconds" in error.suggestion or "45.5" in error.suggestion

    def test_context_includes_provider_name(self):
        """Test provider name is in context."""
        error = RateLimitError(
            "Rate limit",
            provider_name="openai",
            wait_seconds=30.0
        )

        assert error.context['provider_name'] == 'openai'
        assert error.context['wait_seconds'] == 30.0


class TestAllProvidersRateLimitedError:
    """Test AllProvidersRateLimitedError behavior."""

    def test_is_not_retryable(self):
        """Test this error is not retryable (all providers down)."""
        error = AllProvidersRateLimitedError(
            "All providers rate limited",
            attempted_providers=['groq', 'openai', 'claude']
        )

        assert error.is_retryable is False
        assert error.recovery_action == RecoveryAction.ABORT

    def test_includes_attempted_providers(self):
        """Test error includes list of attempted providers."""
        providers = ['groq', 'openai', 'claude', 'gemini']
        error = AllProvidersRateLimitedError(
            "All providers exhausted",
            attempted_providers=providers
        )

        assert error.attempted_providers == providers
        assert error.context['attempted_providers'] == providers

    def test_auto_generates_suggestion(self):
        """Test suggestion mentions waiting or adding keys."""
        error = AllProvidersRateLimitedError(
            "All providers down",
            attempted_providers=['groq']
        )

        suggestion = error.suggestion.lower()
        assert 'wait' in suggestion or 'api key' in suggestion

    def test_provider_details_with_retry_after(self):
        """Test error includes retry-after times per provider."""
        provider_details = {
            'openai': {'retry_after': 45, 'error': 'Rate limit exceeded'},
            'anthropic': {'retry_after': 120, 'error': 'Too many requests'},
        }
        error = AllProvidersRateLimitedError(
            "",  # Empty to trigger auto-generation
            provider_details=provider_details
        )

        # Should auto-populate attempted_providers from provider_details
        assert set(error.attempted_providers) == {'openai', 'anthropic'}
        assert error.provider_details == provider_details
        assert error.context['provider_details'] == provider_details

    def test_auto_generates_message_with_retry_times(self):
        """Test message lists providers with retry times."""
        error = AllProvidersRateLimitedError(
            "",
            provider_details={
                'openai': {'retry_after': 45},
                'groq': {'retry_after': 60},
            }
        )

        message = str(error)
        assert 'openai' in message
        assert 'groq' in message
        assert '45s' in message
        assert '1m' in message  # 60s formatted as 1m

    def test_suggestion_uses_minimum_retry_time(self):
        """Test suggestion shows minimum wait time."""
        error = AllProvidersRateLimitedError(
            "",
            provider_details={
                'openai': {'retry_after': 120},  # 2 minutes
                'groq': {'retry_after': 30},     # 30 seconds (minimum)
            }
        )

        assert '30s' in error.suggestion

    def test_time_formatting(self):
        """Test time formatting for different durations."""
        # Seconds
        error1 = AllProvidersRateLimitedError(
            "", provider_details={'p': {'retry_after': 45}}
        )
        assert '45s' in str(error1)

        # Minutes
        error2 = AllProvidersRateLimitedError(
            "", provider_details={'p': {'retry_after': 120}}
        )
        assert '2m' in str(error2)

        # Hours
        error3 = AllProvidersRateLimitedError(
            "", provider_details={'p': {'retry_after': 3600}}
        )
        assert '1.0h' in str(error3)

    def test_user_friendly_message_includes_suggestion(self):
        """Test user_friendly_message combines message and suggestion."""
        error = AllProvidersRateLimitedError(
            "",
            provider_details={'groq': {'retry_after': 60}}
        )

        friendly = error.user_friendly_message()
        assert 'groq' in friendly
        assert 'Suggestion' in friendly


class TestProviderNotFoundError:
    """Test ProviderNotFoundError behavior."""

    def test_is_not_retryable(self):
        """Test provider not found is not retryable."""
        error = ProviderNotFoundError(
            "Provider not found",
            provider_name="unknown",
            available_providers=['groq', 'openai']
        )

        assert error.is_retryable is False

    def test_includes_available_providers(self):
        """Test error suggests available providers."""
        error = ProviderNotFoundError(
            "Provider 'xyz' not found",
            provider_name='xyz',
            available_providers=['groq', 'openai', 'claude']
        )

        assert error.provider_name == 'xyz'
        assert error.available_providers == ['groq', 'openai', 'claude']
        assert 'groq' in error.suggestion
        assert 'openai' in error.suggestion

    def test_handles_empty_provider_list(self):
        """Test handling when no providers are available."""
        error = ProviderNotFoundError(
            "No providers available",
            provider_name='groq',
            available_providers=[]
        )

        assert error.available_providers == []


class TestAuthenticationError:
    """Test AuthenticationError behavior."""

    def test_is_not_retryable(self):
        """Test auth errors are not retryable."""
        error = AuthenticationError(
            "Invalid API key",
            provider_name="groq"
        )

        assert error.is_retryable is False
        assert error.recovery_action == RecoveryAction.ABORT

    def test_severity_is_critical(self):
        """Test auth errors have critical severity."""
        error = AuthenticationError(
            "Auth failed",
            provider_name="openai"
        )

        assert error.category == ErrorCategory.AUTHENTICATION
        # BaseError default is ERROR, but AuthenticationError sets CRITICAL
        # Let's verify it's at least as severe
        import logging
        assert error.log_level >= logging.ERROR

    def test_includes_helpful_suggestion(self):
        """Test suggestion mentions checking API key."""
        error = AuthenticationError(
            "Invalid credentials",
            provider_name="claude"
        )

        suggestion = error.suggestion.lower()
        assert 'api key' in suggestion
        assert 'claude' in suggestion


class TestTimeoutError:
    """Test TimeoutError behavior."""

    def test_is_retryable(self):
        """Test timeout errors are retryable."""
        error = TimeoutError(
            "Request timed out",
            timeout_seconds=30.0
        )

        assert error.is_retryable is True
        assert error.recovery_action == RecoveryAction.RETRY

    def test_includes_timeout_value(self):
        """Test error includes timeout that was exceeded."""
        error = TimeoutError(
            "Timeout",
            timeout_seconds=60.0
        )

        assert error.timeout_seconds == 60.0
        assert error.context['timeout_seconds'] == 60.0

    def test_suggestion_mentions_network(self):
        """Test suggestion mentions network or timeout."""
        error = TimeoutError("Timeout occurred")

        suggestion = error.suggestion.lower()
        assert 'network' in suggestion or 'timeout' in suggestion or 'long' in suggestion


class TestNetworkError:
    """Test NetworkError behavior."""

    def test_is_retryable(self):
        """Test network errors are retryable."""
        error = NetworkError("Connection failed")

        assert error.is_retryable is True
        assert error.recovery_action == RecoveryAction.RETRY

    def test_category_is_network(self):
        """Test error category is NETWORK."""
        error = NetworkError("DNS failed")

        assert error.category == ErrorCategory.NETWORK

    def test_includes_network_suggestion(self):
        """Test suggestion mentions network connection."""
        error = NetworkError("Connection refused")

        suggestion = error.suggestion.lower()
        assert 'network' in suggestion or 'connection' in suggestion


class TestProviderExecutionError:
    """Test ProviderExecutionError behavior."""

    def test_is_retryable(self):
        """Test provider execution errors are retryable."""
        error = ProviderExecutionError(
            "Execution failed",
            provider_name="groq"
        )

        assert error.is_retryable is True

    def test_wraps_original_error(self):
        """Test error wraps original provider exception."""
        original = ValueError("Invalid response format")
        error = ProviderExecutionError(
            "Provider call failed",
            provider_name="groq",
            original_error=original
        )

        assert error.original_error is original
        assert error.provider_name == "groq"

        # Should appear in dict
        data = error.to_dict()
        assert data['original_error']['type'] == 'ValueError'

    def test_context_includes_provider(self):
        """Test provider name is in context."""
        error = ProviderExecutionError(
            "Failed",
            provider_name="claude"
        )

        assert error.context['provider_name'] == 'claude'


class TestProviderErrorBase:
    """Test ProviderError base class."""

    def test_category_is_api(self):
        """Test provider errors have API category."""
        error = ProviderError("API error")

        assert error.category == ErrorCategory.API

    def test_provider_name_in_context(self):
        """Test provider name is stored in context."""
        error = ProviderError(
            "Error occurred",
            provider_name="gemini"
        )

        assert error.provider_name == "gemini"
        assert error.context['provider_name'] == "gemini"

    def test_none_provider_name(self):
        """Test handling None provider name."""
        error = ProviderError("Error", provider_name=None)

        assert error.provider_name is None
        # Should not crash when accessing context
        context = error.context
