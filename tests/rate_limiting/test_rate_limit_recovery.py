"""
Tests for rate limit error detection and exception classes.

After LiteLLM integration (Phase 3):
- Rate limit recovery is handled by LiteLLM Router internally
- These tests verify the utility functions for error detection
- Recovery/fallback tests are now in test_litellm_escalation.py
"""

import pytest

from scrappy.infrastructure.utils import is_rate_limit_error
from scrappy.infrastructure.exceptions import RateLimitError, AllProvidersRateLimitedError


class TestRateLimitErrorDetection:
    """Test that rate limit errors are properly detected."""

    def test_detects_429_status_code(self):
        error = Exception("Error 429: Too Many Requests")
        assert is_rate_limit_error(error) is True

    def test_detects_rate_limit_message(self):
        error = Exception("Rate limit exceeded for this API")
        assert is_rate_limit_error(error) is True

    def test_detects_quota_exceeded(self):
        error = Exception("Quota exceeded. Please try again later.")
        assert is_rate_limit_error(error) is True

    def test_detects_resource_exhausted(self):
        error = Exception("RESOURCE_EXHAUSTED: Request quota exhausted")
        assert is_rate_limit_error(error) is True

    def test_detects_throttling(self):
        error = Exception("Request throttled due to high traffic")
        assert is_rate_limit_error(error) is True

    def test_detects_too_many_requests(self):
        error = Exception("Too many requests. Please slow down.")
        assert is_rate_limit_error(error) is True

    def test_ignores_regular_errors(self):
        error = Exception("Connection timeout")
        assert is_rate_limit_error(error) is False

    def test_ignores_auth_errors(self):
        error = Exception("Invalid API key")
        assert is_rate_limit_error(error) is False

    def test_ignores_server_errors(self):
        error = Exception("Internal server error")
        assert is_rate_limit_error(error) is False

    def test_detects_custom_rate_limit_error(self):
        error = RateLimitError("Rate limit hit for groq", provider_name="groq")
        assert is_rate_limit_error(error) is True


# NOTE: TestRateLimitRecovery class was removed in Phase 3 of LiteLLM integration.
# Rate limit recovery and fallback is now handled by LiteLLM Router internally.
# See test_litellm_escalation.py for the new fallback behavior tests.


class TestRateLimitExceptions:
    """Test the infrastructure rate limit exception classes."""

    def test_rate_limit_error_message(self):
        error = RateLimitError(
            "Rate limit exceeded for groq (tokens)",
            provider_name="groq",
            wait_seconds=30.0
        )
        assert "groq" in str(error)
        assert error.provider_name == "groq"
        assert error.wait_seconds == 30.0

    def test_rate_limit_error_custom_message(self):
        error = RateLimitError("Custom rate limit message")
        assert str(error) == "Custom rate limit message"

    def test_all_providers_error_lists_attempted(self):
        error = AllProvidersRateLimitedError(
            "All providers rate limited",
            attempted_providers=['groq', 'cerebras', 'gemini']
        )
        assert 'groq' in error.attempted_providers
        assert 'cerebras' in error.attempted_providers
        assert 'gemini' in error.attempted_providers
        assert error.attempted_providers == ['groq', 'cerebras', 'gemini']
