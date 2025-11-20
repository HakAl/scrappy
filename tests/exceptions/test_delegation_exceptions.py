"""
Tests for domain exception hierarchy.

Verifies that the delegation exceptions follow the proper hierarchy
and maintain backward compatibility with existing code.
"""

import pytest
from src.exceptions.delegation import (
    DelegationError,
    RetryExhaustedError,
    CacheError,
    ProviderNotFoundError,
    RateLimitExceededError,
    InvalidRequestError,
    PromptAugmentationError,
    BatchSchedulingError,
    ProviderExecutionError,
)
from src.utils.errors import (
    RateLimitError,
    AllProvidersRateLimitedError,
)


class TestExceptionHierarchy:
    """Test that exceptions follow the proper inheritance hierarchy."""

    def test_all_exceptions_inherit_from_delegation_error(self):
        """Verify all domain exceptions inherit from DelegationError."""
        exceptions = [
            RetryExhaustedError([], Exception("test"), 0),
            CacheError("test"),
            ProviderNotFoundError("test", []),
            RateLimitExceededError("test", 1.0),
            InvalidRequestError("param", "value", "message"),
            PromptAugmentationError("test"),
            BatchSchedulingError("test"),
            ProviderExecutionError("test", Exception("test")),
        ]

        for exc in exceptions:
            assert isinstance(exc, DelegationError)
            assert isinstance(exc, Exception)

    def test_legacy_exceptions_inherit_from_domain_exceptions(self):
        """Verify legacy exceptions now inherit from domain exceptions."""
        # RateLimitError should inherit from RateLimitExceededError
        rate_limit_exc = RateLimitError("test_provider")
        assert isinstance(rate_limit_exc, RateLimitExceededError)
        assert isinstance(rate_limit_exc, DelegationError)

        # AllProvidersRateLimitedError should inherit from RetryExhaustedError
        all_providers_exc = AllProvidersRateLimitedError(["provider1", "provider2"])
        assert isinstance(all_providers_exc, RetryExhaustedError)
        assert isinstance(all_providers_exc, DelegationError)


class TestRetryExhaustedError:
    """Test RetryExhaustedError functionality."""

    def test_stores_all_attributes(self):
        """Verify exception stores all required attributes."""
        providers = ["provider1", "provider2"]
        last_error = ValueError("test error")
        attempts = 5

        exc = RetryExhaustedError(
            attempted_providers=providers,
            last_error=last_error,
            total_attempts=attempts
        )

        assert exc.attempted_providers == providers
        assert exc.last_error == last_error
        assert exc.total_attempts == attempts

    def test_message_includes_details(self):
        """Verify exception message includes useful details."""
        providers = ["provider1", "provider2"]
        last_error = ValueError("test error")
        attempts = 5

        exc = RetryExhaustedError(
            attempted_providers=providers,
            last_error=last_error,
            total_attempts=attempts
        )

        message = str(exc)
        assert "5 attempts" in message
        assert "provider1" in message
        assert "provider2" in message
        assert "test error" in message


class TestProviderNotFoundError:
    """Test ProviderNotFoundError functionality."""

    def test_stores_provider_info(self):
        """Verify exception stores provider information."""
        provider = "unknown_provider"
        available = ["provider1", "provider2"]

        exc = ProviderNotFoundError(provider, available)

        assert exc.provider_name == provider
        assert exc.available_providers == available

    def test_message_includes_available_providers(self):
        """Verify exception message lists available providers."""
        provider = "unknown_provider"
        available = ["provider1", "provider2"]

        exc = ProviderNotFoundError(provider, available)

        message = str(exc)
        assert "unknown_provider" in message
        assert "provider1" in message
        assert "provider2" in message


class TestRateLimitExceededError:
    """Test RateLimitExceededError functionality."""

    def test_stores_rate_limit_info(self):
        """Verify exception stores rate limit information."""
        provider = "test_provider"
        wait_time = 30.5
        max_wait = 60.0

        exc = RateLimitExceededError(provider, wait_time, max_wait)

        assert exc.provider_name == provider
        assert exc.wait_seconds == wait_time
        assert exc.max_wait_seconds == max_wait

    def test_message_with_max_wait(self):
        """Verify exception message includes wait times when max_wait provided."""
        exc = RateLimitExceededError("test_provider", 30.5, 60.0)
        message = str(exc)

        assert "test_provider" in message
        assert "30.5" in message
        assert "60.0" in message

    def test_message_without_max_wait(self):
        """Verify exception message works when max_wait is None."""
        exc = RateLimitExceededError("test_provider", 30.5)
        message = str(exc)

        assert "test_provider" in message
        assert "30.5" in message


class TestInvalidRequestError:
    """Test InvalidRequestError functionality."""

    def test_stores_validation_info(self):
        """Verify exception stores parameter validation information."""
        param = "max_tokens"
        value = -100
        validation_msg = "must be positive"

        exc = InvalidRequestError(param, value, validation_msg)

        assert exc.parameter_name == param
        assert exc.parameter_value == value
        assert exc.validation_message == validation_msg

    def test_message_includes_all_details(self):
        """Verify exception message includes all validation details."""
        exc = InvalidRequestError("max_tokens", -100, "must be positive")
        message = str(exc)

        assert "max_tokens" in message
        assert "-100" in message
        assert "must be positive" in message


class TestProviderExecutionError:
    """Test ProviderExecutionError functionality."""

    def test_wraps_original_error(self):
        """Verify exception wraps the original provider error."""
        provider = "test_provider"
        original = ValueError("API error")

        exc = ProviderExecutionError(provider, original)

        assert exc.provider_name == provider
        assert exc.original_error == original

    def test_message_includes_provider_and_error(self):
        """Verify exception message includes provider name and original error."""
        original = ValueError("API error")
        exc = ProviderExecutionError("test_provider", original)

        message = str(exc)
        assert "test_provider" in message
        assert "API error" in message


class TestBackwardCompatibility:
    """Test backward compatibility with legacy exception handling."""

    def test_can_catch_legacy_rate_limit_error(self):
        """Verify legacy RateLimitError can still be caught."""
        exc = RateLimitError("test_provider", "Daily quota exceeded")

        # Should be catchable as RateLimitError (legacy)
        with pytest.raises(RateLimitError):
            raise exc

        # Should be catchable as RateLimitExceededError (new)
        with pytest.raises(RateLimitExceededError):
            raise exc

        # Should be catchable as DelegationError (base)
        with pytest.raises(DelegationError):
            raise exc

    def test_can_catch_legacy_all_providers_error(self):
        """Verify legacy AllProvidersRateLimitedError can still be caught."""
        exc = AllProvidersRateLimitedError(["provider1", "provider2"])

        # Should be catchable as AllProvidersRateLimitedError (legacy)
        with pytest.raises(AllProvidersRateLimitedError):
            raise exc

        # Should be catchable as RetryExhaustedError (new)
        with pytest.raises(RetryExhaustedError):
            raise exc

        # Should be catchable as DelegationError (base)
        with pytest.raises(DelegationError):
            raise exc

    def test_legacy_exceptions_preserve_attributes(self):
        """Verify legacy exceptions preserve their original attributes."""
        # RateLimitError preserves limit_type and message
        rate_exc = RateLimitError("test_provider", "Custom message", "tokens")
        assert rate_exc.provider == "test_provider"
        assert rate_exc.limit_type == "tokens"
        assert rate_exc.message == "Custom message"

        # AllProvidersRateLimitedError preserves attempted_providers and message
        all_exc = AllProvidersRateLimitedError(["p1", "p2"])
        assert all_exc.attempted_providers == ["p1", "p2"]
        assert hasattr(all_exc, 'message')
