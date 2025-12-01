"""
Tests for base exception classes.

Following CLAUDE.md: Test BEHAVIOR, not structure. Prove features work.
"""

import pytest
import logging
from scrappy.infrastructure.exceptions import (
    BaseError,
    RetryableError,
    NonRetryableError,
    RecoveryAction,
    ErrorSeverity,
    ErrorCategory,
)


class TestBaseError:
    """Test BaseError behavior."""

    def test_basic_error_creation(self):
        """Test creating error with minimal parameters."""
        error = BaseError("Something went wrong")

        assert str(error) == "Something went wrong"
        assert error.message == "Something went wrong"
        assert error.category == ErrorCategory.SYSTEM
        assert error.severity == ErrorSeverity.ERROR

    def test_error_with_all_metadata(self):
        """Test error with complete metadata."""
        original = ValueError("bad value")

        error = BaseError(
            "Operation failed",
            category=ErrorCategory.API,
            severity=ErrorSeverity.CRITICAL,
            context={'provider': 'groq', 'attempt': 3},
            suggestion="Try a different provider",
            original_error=original,
            recovery_action=RecoveryAction.FALLBACK
        )

        assert error.message == "Operation failed"
        assert error.category == ErrorCategory.API
        assert error.severity == ErrorSeverity.CRITICAL
        assert error.context['provider'] == 'groq'
        assert error.context['attempt'] == 3
        assert error.suggestion == "Try a different provider"
        assert error.original_error is original
        assert error.recovery_action == RecoveryAction.FALLBACK

    def test_recovery_action_auto_determination(self):
        """Test that recovery action is auto-determined from error properties."""
        # Retryable error should default to RETRY
        class TestRetryable(BaseError):
            @property
            def is_retryable(self):
                return True

        error = TestRetryable("retryable error")
        assert error.recovery_action == RecoveryAction.RETRY

        # Critical error should default to ABORT
        error = BaseError("critical", severity=ErrorSeverity.CRITICAL)
        assert error.recovery_action == RecoveryAction.ABORT

        # User input error should default to ASK_USER
        error = BaseError("bad input", category=ErrorCategory.USER_INPUT)
        assert error.recovery_action == RecoveryAction.ASK_USER

    def test_log_level_from_severity(self):
        """Test log level mapping from severity."""
        assert BaseError("info", severity=ErrorSeverity.INFO).log_level == logging.INFO
        assert BaseError("warn", severity=ErrorSeverity.WARNING).log_level == logging.WARNING
        assert BaseError("error", severity=ErrorSeverity.ERROR).log_level == logging.ERROR
        assert BaseError("critical", severity=ErrorSeverity.CRITICAL).log_level == logging.CRITICAL

    def test_to_dict_serialization(self):
        """Test converting error to dictionary."""
        error = BaseError(
            "test error",
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.WARNING,
            context={'field': 'email', 'value': 'invalid'},
            suggestion="Provide valid email"
        )

        data = error.to_dict()

        assert data['type'] == 'BaseError'
        assert data['message'] == 'test error'
        assert data['category'] == 'validation'
        assert data['severity'] == ErrorSeverity.WARNING.value
        assert data['recovery_action'] == RecoveryAction.ABORT.value
        assert data['context']['field'] == 'email'
        assert data['suggestion'] == "Provide valid email"

    def test_to_dict_with_original_error(self):
        """Test serialization includes original error."""
        original = ValueError("bad value")
        error = BaseError("wrapped error", original_error=original)

        data = error.to_dict()

        assert 'original_error' in data
        assert data['original_error']['type'] == 'ValueError'
        assert data['original_error']['message'] == 'bad value'

    def test_logging_extra_fields(self):
        """Test structured logging extra fields."""
        error = BaseError(
            "log test",
            category=ErrorCategory.API,
            context={'provider': 'groq', 'tokens': 500}
        )

        extra = error.logging_extra()

        assert extra['error_type'] == 'BaseError'
        assert extra['error_category'] == 'api'
        assert extra['error_severity'] == ErrorSeverity.ERROR.value
        assert extra['error_context_provider'] == 'groq'
        assert extra['error_context_tokens'] == 500

    def test_str_representation(self):
        """Test string representation includes message and suggestion."""
        error = BaseError(
            "File not found",
            suggestion="Check the file path"
        )

        str_repr = str(error)
        assert "File not found" in str_repr
        assert "Suggestion: Check the file path" in str_repr

    def test_str_with_original_error(self):
        """Test string representation includes original error."""
        original = OSError("disk full")  # Python 3: IOError is OSError
        error = BaseError("Write failed", original_error=original)

        str_repr = str(error)
        assert "Write failed" in str_repr
        assert "Caused by: OSError: disk full" in str_repr

    def test_repr_shows_key_attributes(self):
        """Test repr shows key error attributes."""
        error = BaseError(
            "test",
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.WARNING
        )

        repr_str = repr(error)
        assert "BaseError" in repr_str
        assert "test" in repr_str
        assert "ErrorCategory.NETWORK" in repr_str or "NETWORK" in repr_str
        assert "ErrorSeverity.WARNING" in repr_str or "WARNING" in repr_str


class TestRetryableError:
    """Test RetryableError behavior."""

    def test_is_retryable_always_true(self):
        """Test RetryableError is always retryable."""
        error = RetryableError("temporary failure")

        assert error.is_retryable is True
        assert error.recovery_action == RecoveryAction.RETRY

    def test_inherits_base_error_features(self):
        """Test RetryableError has all BaseError features."""
        error = RetryableError(
            "timeout",
            category=ErrorCategory.NETWORK,
            context={'timeout': 30}
        )

        assert error.category == ErrorCategory.NETWORK
        assert error.context['timeout'] == 30
        assert error.is_retryable is True

        # Should serialize correctly
        data = error.to_dict()
        assert data['recovery_action'] == 'retry'


class TestNonRetryableError:
    """Test NonRetryableError behavior."""

    def test_is_retryable_always_false(self):
        """Test NonRetryableError is never retryable."""
        error = NonRetryableError("permanent failure")

        assert error.is_retryable is False
        assert error.recovery_action == RecoveryAction.ABORT

    def test_inherits_base_error_features(self):
        """Test NonRetryableError has all BaseError features."""
        error = NonRetryableError(
            "auth failed",
            category=ErrorCategory.AUTHENTICATION,
            suggestion="Check API key"
        )

        assert error.category == ErrorCategory.AUTHENTICATION
        assert error.suggestion == "Check API key"
        assert error.is_retryable is False


class TestErrorCategories:
    """Test error category enumeration."""

    def test_all_categories_exist(self):
        """Test all expected categories are defined."""
        categories = {c.value for c in ErrorCategory}

        assert 'validation' in categories
        assert 'api' in categories
        assert 'file' in categories
        assert 'system' in categories
        assert 'parse' in categories
        assert 'task' in categories
        assert 'user_input' in categories
        assert 'network' in categories
        assert 'rate_limit' in categories
        assert 'authentication' in categories


class TestRecoveryActions:
    """Test recovery action enumeration."""

    def test_all_actions_exist(self):
        """Test all expected actions are defined."""
        actions = {a.value for a in RecoveryAction}

        assert 'retry' in actions
        assert 'fallback' in actions
        assert 'abort' in actions
        assert 'skip' in actions
        assert 'ask_user' in actions
