"""
Tests for custom CLI exceptions module.

These tests define the expected behavior of the exception hierarchy,
including categorization, severity levels, suggestions, and recovery strategies.
"""

import pytest
from pathlib import Path


class TestCLIExceptionHierarchy:
    """Test the exception class hierarchy and inheritance."""

    @pytest.mark.unit
    def test_cli_error_is_base_exception(self):
        """CLIError should be the base for all CLI exceptions."""
        from src.cli.exceptions import CLIError

        error = CLIError("Test error")
        assert isinstance(error, Exception)
        assert str(error) == "Test error"

    @pytest.mark.unit

    @pytest.mark.unit
    def test_exceptions_can_be_caught_as_cli_error(self):
        """All custom exceptions should be catchable as CLIError."""
        from src.cli.exceptions import CLIError, ValidationError

        try:
            raise ValidationError("Invalid input")
        except CLIError as e:
            assert "Invalid input" in str(e)


class TestCLIErrorAttributes:
    """Test that CLIError has required attributes for error handling."""

    @pytest.mark.unit
    def test_cli_error_has_category(self):
        """CLIError should have a category attribute."""
        from src.cli.exceptions import CLIError
        from src.cli.utils.error_handler import ErrorCategory

        error = CLIError("Test error", category=ErrorCategory.SYSTEM)
        assert error.category == ErrorCategory.SYSTEM

    @pytest.mark.unit
    def test_cli_error_has_severity(self):
        """CLIError should have a severity attribute."""
        from src.cli.exceptions import CLIError
        from src.cli.utils.error_handler import ErrorSeverity

        error = CLIError("Test error", severity=ErrorSeverity.ERROR)
        assert error.severity == ErrorSeverity.ERROR

    @pytest.mark.unit
    def test_cli_error_default_severity_is_error(self):
        """CLIError should default to ERROR severity."""
        from src.cli.exceptions import CLIError
        from src.cli.utils.error_handler import ErrorSeverity

        error = CLIError("Test error")
        assert error.severity == ErrorSeverity.ERROR

    @pytest.mark.unit
    def test_cli_error_stores_context(self):
        """CLIError should store additional context."""
        from src.cli.exceptions import CLIError

        error = CLIError("Test error", context={"operation": "save", "file": "test.txt"})
        assert error.context == {"operation": "save", "file": "test.txt"}

    @pytest.mark.unit
    def test_cli_error_suggestion_property(self):
        """CLIError should provide actionable suggestions."""
        from src.cli.exceptions import CLIError

        error = CLIError("Test error", suggestion="Try again with valid input")
        assert error.suggestion == "Try again with valid input"


class TestValidationError:
    """Test ValidationError for input validation failures."""

    @pytest.mark.unit
    def test_validation_error_basic(self):
        """ValidationError should store message and field."""
        from src.cli.exceptions import ValidationError

        error = ValidationError("Invalid value", field="provider")
        assert "Invalid value" in str(error)
        assert error.field == "provider"

    @pytest.mark.unit
    def test_validation_error_with_invalid_value(self):
        """ValidationError should store the invalid value."""
        from src.cli.exceptions import ValidationError

        error = ValidationError("Invalid provider", field="provider", value="invalid_prov")
        assert error.value == "invalid_prov"
        assert error.field == "provider"

    @pytest.mark.unit
    def test_validation_error_has_validation_category(self):
        """ValidationError should have VALIDATION category."""
        from src.cli.exceptions import ValidationError
        from src.cli.utils.error_handler import ErrorCategory

        error = ValidationError("Test")
        assert error.category == ErrorCategory.VALIDATION

    @pytest.mark.unit
    def test_validation_error_formats_message_with_field(self):
        """ValidationError should format message to include field name."""
        from src.cli.exceptions import ValidationError

        error = ValidationError("must be a positive integer", field="timeout")
        assert "timeout" in str(error).lower() or error.field == "timeout"

    @pytest.mark.unit
    def test_validation_error_provides_suggestion(self):
        """ValidationError should provide helpful suggestions."""
        from src.cli.exceptions import ValidationError

        error = ValidationError("Invalid provider", field="provider", value="xyz")
        assert error.suggestion is not None
        assert len(error.suggestion) > 0


class TestProviderError:
    """Test ProviderError for API/provider failures."""

    @pytest.mark.unit
    def test_provider_error_stores_provider_name(self):
        """ProviderError should store the provider name."""
        from src.cli.exceptions import ProviderError

        error = ProviderError("Connection failed", provider="openai")
        assert error.provider == "openai"
        assert "Connection failed" in str(error)

    @pytest.mark.unit
    def test_provider_error_has_api_category(self):
        """ProviderError should have API category."""
        from src.cli.exceptions import ProviderError
        from src.cli.utils.error_handler import ErrorCategory

        error = ProviderError("Test", provider="test")
        assert error.category == ErrorCategory.API

    @pytest.mark.unit
    def test_provider_error_rate_limit(self):
        """ProviderError should indicate rate limiting."""
        from src.cli.exceptions import ProviderError

        error = ProviderError("Rate limit exceeded", provider="gemini", rate_limited=True)
        assert error.rate_limited is True

    @pytest.mark.unit
    def test_provider_error_timeout(self):
        """ProviderError should indicate timeouts."""
        from src.cli.exceptions import ProviderError

        error = ProviderError("Request timed out", provider="cerebras", is_timeout=True)
        assert error.is_timeout is True

    @pytest.mark.unit
    def test_provider_error_retryable(self):
        """ProviderError should indicate if retry is possible."""
        from src.cli.exceptions import ProviderError

        # Rate limits and timeouts are typically retryable
        error = ProviderError("Rate limit", provider="test", rate_limited=True)
        assert error.is_retryable is True

        # Auth errors are not retryable
        error2 = ProviderError("Invalid API key", provider="test", is_auth_error=True)
        assert error2.is_retryable is False

    @pytest.mark.unit
    def test_provider_error_stores_original_exception(self):
        """ProviderError should wrap original exception."""
        from src.cli.exceptions import ProviderError

        original = ConnectionError("Network unreachable")
        error = ProviderError("Connection failed", provider="test", original=original)
        assert error.original is original


class TestFileOperationError:
    """Test FileOperationError for file system failures."""

    @pytest.mark.unit
    def test_file_operation_error_stores_path(self):
        """FileOperationError should store the file path."""
        from src.cli.exceptions import FileOperationError

        path = Path("/test/file.txt")
        error = FileOperationError("File not found", path=path)
        assert error.path == path

    @pytest.mark.unit
    def test_file_operation_error_has_file_category(self):
        """FileOperationError should have FILE category."""
        from src.cli.exceptions import FileOperationError
        from src.cli.utils.error_handler import ErrorCategory

        error = FileOperationError("Test", path=Path("/test"))
        assert error.category == ErrorCategory.FILE

    @pytest.mark.unit
    def test_file_operation_error_operation_type(self):
        """FileOperationError should indicate the operation type."""
        from src.cli.exceptions import FileOperationError

        error = FileOperationError("Failed", path=Path("/test"), operation="read")
        assert error.operation == "read"

    @pytest.mark.unit
    def test_file_operation_error_from_os_error(self):
        """FileOperationError should wrap OS-level errors."""
        from src.cli.exceptions import FileOperationError

        original = FileNotFoundError("No such file")
        error = FileOperationError.from_os_error(original, Path("/test/file.txt"))
        assert error.path == Path("/test/file.txt")
        assert error.original is original

    @pytest.mark.unit
    def test_file_operation_error_permission_denied(self):
        """FileOperationError should indicate permission issues."""
        from src.cli.exceptions import FileOperationError

        original = PermissionError("Access denied")
        error = FileOperationError.from_os_error(original, Path("/test"))
        assert "permission" in error.suggestion.lower()


class TestSessionError:
    """Test SessionError for session management failures."""

    @pytest.mark.unit
    def test_session_error_stores_operation(self):
        """SessionError should store the session operation."""
        from src.cli.exceptions import SessionError

        error = SessionError("Save failed", operation="save")
        assert error.operation == "save"
        assert "Save failed" in str(error)

    @pytest.mark.unit
    def test_session_error_load_operation(self):
        """SessionError should handle load failures."""
        from src.cli.exceptions import SessionError

        error = SessionError("No session found", operation="load")
        assert error.operation == "load"

    @pytest.mark.unit
    def test_session_error_stores_session_path(self):
        """SessionError should store the session file path."""
        from src.cli.exceptions import SessionError

        error = SessionError("Corrupted", operation="load", session_path=Path("/test/.session"))
        assert error.session_path == Path("/test/.session")


class TestTaskExecutionError:
    """Test TaskExecutionError for task execution failures."""

    @pytest.mark.unit
    def test_task_execution_error_stores_task_name(self):
        """TaskExecutionError should store the task name."""
        from src.cli.exceptions import TaskExecutionError

        error = TaskExecutionError("Planning failed", task_name="planning")
        assert error.task_name == "planning"

    @pytest.mark.unit
    def test_task_execution_error_has_task_category(self):
        """TaskExecutionError should have TASK category."""
        from src.cli.exceptions import TaskExecutionError
        from src.cli.utils.error_handler import ErrorCategory

        error = TaskExecutionError("Test", task_name="test")
        assert error.category == ErrorCategory.TASK

    @pytest.mark.unit
    def test_task_execution_error_stores_partial_result(self):
        """TaskExecutionError should store partial results if available."""
        from src.cli.exceptions import TaskExecutionError

        partial = {"steps_completed": 3, "total_steps": 5}
        error = TaskExecutionError("Interrupted", task_name="analysis", partial_result=partial)
        assert error.partial_result == partial


class TestParseError:
    """Test ParseError for parsing failures."""

    @pytest.mark.unit
    def test_parse_error_stores_source(self):
        """ParseError should store the source being parsed."""
        from src.cli.exceptions import ParseError

        error = ParseError("Invalid JSON", source="response.json")
        assert error.source == "response.json"

    @pytest.mark.unit
    def test_parse_error_has_parse_category(self):
        """ParseError should have PARSE category."""
        from src.cli.exceptions import ParseError
        from src.cli.utils.error_handler import ErrorCategory

        error = ParseError("Test", source="test")
        assert error.category == ErrorCategory.PARSE

    @pytest.mark.unit
    def test_parse_error_stores_content_preview(self):
        """ParseError should store a preview of the problematic content."""
        from src.cli.exceptions import ParseError

        error = ParseError("Unexpected token", source="test.json", content_preview="{invalid")
        assert error.content_preview == "{invalid"

    @pytest.mark.unit
    def test_parse_error_from_json_error(self):
        """ParseError should wrap JSON decode errors."""
        import json
        from src.cli.exceptions import ParseError

        try:
            json.loads("{invalid")
        except json.JSONDecodeError as e:
            error = ParseError.from_json_error(e, source="api_response")
            assert error.source == "api_response"
            assert error.original is e


class TestUserInputError:
    """Test UserInputError for user input failures."""

    @pytest.mark.unit
    def test_user_input_error_basic(self):
        """UserInputError should store the error message."""
        from src.cli.exceptions import UserInputError

        error = UserInputError("Input cancelled")
        assert "Input cancelled" in str(error)

    @pytest.mark.unit
    def test_user_input_error_has_user_input_category(self):
        """UserInputError should have USER_INPUT category."""
        from src.cli.exceptions import UserInputError
        from src.cli.utils.error_handler import ErrorCategory

        error = UserInputError("Test")
        assert error.category == ErrorCategory.USER_INPUT

    @pytest.mark.unit
    def test_user_input_error_interrupted(self):
        """UserInputError should indicate keyboard interrupt."""
        from src.cli.exceptions import UserInputError

        error = UserInputError("Cancelled by user", interrupted=True)
        assert error.interrupted is True

    @pytest.mark.unit
    def test_user_input_error_eof(self):
        """UserInputError should indicate EOF."""
        from src.cli.exceptions import UserInputError

        error = UserInputError("End of input", eof=True)
        assert error.eof is True


class TestExceptionFormatting:
    """Test exception message formatting."""

    @pytest.mark.unit
    def test_exception_str_includes_message(self):
        """Exception string should include the main message."""
        from src.cli.exceptions import CLIError

        error = CLIError("Something went wrong")
        assert "Something went wrong" in str(error)

    @pytest.mark.unit
    def test_exception_repr_includes_class_name(self):
        """Exception repr should include class name for debugging."""
        from src.cli.exceptions import ValidationError

        error = ValidationError("Invalid", field="test")
        assert "ValidationError" in repr(error)

    @pytest.mark.unit
    def test_exception_to_dict_for_logging(self):
        """Exceptions should be convertible to dict for structured logging."""
        from src.cli.exceptions import ProviderError
        from src.cli.utils.error_handler import ErrorCategory, ErrorSeverity

        error = ProviderError("Timeout", provider="openai", is_timeout=True)
        error_dict = error.to_dict()

        assert error_dict["message"] == "Timeout"
        assert error_dict["provider"] == "openai"
        assert error_dict["is_timeout"] is True
        assert "category" in error_dict
        assert "severity" in error_dict


class TestErrorRecoveryStrategies:
    """Test error recovery strategy support in exceptions."""

    @pytest.mark.unit
    def test_provider_error_suggests_retry_for_rate_limit(self):
        """Rate limited errors should suggest waiting and retrying."""
        from src.cli.exceptions import ProviderError

        error = ProviderError("Rate limited", provider="test", rate_limited=True)
        assert "retry" in error.suggestion.lower() or "wait" in error.suggestion.lower()

    @pytest.mark.unit
    def test_provider_error_suggests_fallback_provider(self):
        """Provider errors should suggest trying another provider."""
        from src.cli.exceptions import ProviderError

        error = ProviderError("Failed", provider="openai")
        assert "provider" in error.suggestion.lower() or "alternative" in error.suggestion.lower()

    @pytest.mark.unit
    def test_file_error_suggests_check_path(self):
        """File errors should suggest checking the path."""
        from src.cli.exceptions import FileOperationError

        error = FileOperationError("Not found", path=Path("/test/file.txt"))
        assert "path" in error.suggestion.lower() or "exist" in error.suggestion.lower()

    @pytest.mark.unit
    def test_validation_error_suggests_correct_format(self):
        """Validation errors should suggest the correct format."""
        from src.cli.exceptions import ValidationError

        error = ValidationError("Invalid", field="timeout", value="abc")
        assert error.suggestion is not None
        assert len(error.suggestion) > 0

    @pytest.mark.unit
    def test_exception_recovery_action_enum(self):
        """Exceptions should suggest recovery actions."""
        from src.cli.exceptions import ProviderError, RecoveryAction

        error = ProviderError("Timeout", provider="test", is_timeout=True)
        assert error.recovery_action == RecoveryAction.RETRY

    @pytest.mark.unit
    def test_exception_recovery_action_abort_for_auth(self):
        """Auth errors should suggest aborting."""
        from src.cli.exceptions import ProviderError, RecoveryAction

        error = ProviderError("Invalid key", provider="test", is_auth_error=True)
        assert error.recovery_action == RecoveryAction.ABORT


class TestExceptionLogging:
    """Test exception support for structured logging."""

    @pytest.mark.unit
    def test_exception_log_level_mapping(self):
        """Exceptions should map severity to log levels."""
        from src.cli.exceptions import CLIError
        from src.cli.utils.error_handler import ErrorSeverity
        import logging

        error = CLIError("Test", severity=ErrorSeverity.WARNING)
        assert error.log_level == logging.WARNING

        error2 = CLIError("Test", severity=ErrorSeverity.ERROR)
        assert error2.log_level == logging.ERROR

        error3 = CLIError("Test", severity=ErrorSeverity.CRITICAL)
        assert error3.log_level == logging.CRITICAL

    @pytest.mark.unit
    def test_exception_extra_for_logging(self):
        """Exceptions should provide extra dict for structured logging."""
        from src.cli.exceptions import ProviderError

        error = ProviderError("Failed", provider="openai", rate_limited=True)
        extra = error.logging_extra()

        assert extra["error_type"] == "ProviderError"
        assert extra["provider"] == "openai"
        assert extra["rate_limited"] is True
        assert "category" in extra


class TestRecoveryActionEnum:
    """Test RecoveryAction enumeration."""
    pass


class TestExceptionIntegrationWithErrorHandler:
    """Test that exceptions integrate with existing error_handler.py."""

    @pytest.mark.unit
    def test_exception_can_be_handled_by_handle_error(self):
        """Custom exceptions should work with handle_error function."""
        from src.cli.exceptions import ValidationError
        from src.cli.utils.error_handler import handle_error
        from tests.helpers import MockIO

        io = MockIO()
        error = ValidationError("Invalid provider", field="provider")

        handle_error(error, io)

        output = io.get_output()
        assert "Invalid provider" in output or "provider" in output

    @pytest.mark.unit
    def test_exception_uses_correct_severity_in_handler(self):
        """handle_error should use the exception's severity."""
        from src.cli.exceptions import CLIError
        from src.cli.utils.error_handler import handle_error, ErrorSeverity
        from tests.helpers import MockIO

        io = MockIO()
        error = CLIError("Critical failure", severity=ErrorSeverity.CRITICAL)

        handle_error(error, io, severity=error.severity)

        styled = io.get_styled_outputs()
        # Critical errors should be bold red
        assert any(s.get('bold') is True and s.get('fg') == 'red' for s in styled)


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.unit

    @pytest.mark.unit

    @pytest.mark.unit
    def test_exception_with_unicode_message(self):
        """Exception should handle unicode characters."""
        from src.cli.exceptions import CLIError

        error = CLIError("Error: invalid character")
        assert "invalid character" in str(error)


    @pytest.mark.unit
    def test_exception_context_with_non_serializable_value(self):
        """Exception context should handle non-serializable values in to_dict."""
        from src.cli.exceptions import CLIError

        # Create a non-serializable context
        error = CLIError("Test", context={"func": lambda x: x})

        # to_dict should handle this gracefully
        error_dict = error.to_dict()
        assert "context" in error_dict
