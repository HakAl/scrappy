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
        from scrappy.cli.exceptions import CLIError

        error = CLIError("Test error")
        assert isinstance(error, Exception)
        assert str(error) == "Test error"

    @pytest.mark.unit

    @pytest.mark.unit
    def test_exceptions_can_be_caught_as_cli_error(self):
        """All custom exceptions should be catchable as CLIError."""
        from scrappy.cli.exceptions import CLIError, ValidationError

        try:
            raise ValidationError("Invalid input")
        except CLIError as e:
            assert "Invalid input" in str(e)


class TestCLIErrorAttributes:
    """Test that CLIError has required attributes for error handling."""

    @pytest.mark.unit
    def test_cli_error_has_category(self):
        """CLIError should have a category attribute."""
        from scrappy.cli.exceptions import CLIError
        from scrappy.cli.utils.error_handler import ErrorCategory

        error = CLIError("Test error", category=ErrorCategory.SYSTEM)
        assert error.category == ErrorCategory.SYSTEM

    @pytest.mark.unit
    def test_cli_error_has_severity(self):
        """CLIError should have a severity attribute."""
        from scrappy.cli.exceptions import CLIError
        from scrappy.cli.utils.error_handler import ErrorSeverity

        error = CLIError("Test error", severity=ErrorSeverity.ERROR)
        assert error.severity == ErrorSeverity.ERROR

    @pytest.mark.unit
    def test_cli_error_default_severity_is_error(self):
        """CLIError should default to ERROR severity."""
        from scrappy.cli.exceptions import CLIError
        from scrappy.cli.utils.error_handler import ErrorSeverity

        error = CLIError("Test error")
        assert error.severity == ErrorSeverity.ERROR

    @pytest.mark.unit
    def test_cli_error_stores_context(self):
        """CLIError should store additional context."""
        from scrappy.cli.exceptions import CLIError

        error = CLIError("Test error", context={"operation": "save", "file": "test.txt"})
        assert error.context == {"operation": "save", "file": "test.txt"}

    @pytest.mark.unit
    def test_cli_error_suggestion_property(self):
        """CLIError should provide actionable suggestions."""
        from scrappy.cli.exceptions import CLIError

        error = CLIError("Test error", suggestion="Try again with valid input")
        assert error.suggestion == "Try again with valid input"


class TestValidationError:
    """Test ValidationError for input validation failures."""

    @pytest.mark.unit
    def test_validation_error_basic(self):
        """ValidationError should store message and field."""
        from scrappy.cli.exceptions import ValidationError

        error = ValidationError("Invalid value", field="provider")
        assert "Invalid value" in str(error)
        assert error.field == "provider"

    @pytest.mark.unit
    def test_validation_error_with_invalid_value(self):
        """ValidationError should store the invalid value."""
        from scrappy.cli.exceptions import ValidationError

        error = ValidationError("Invalid provider", field="provider", value="invalid_prov")
        assert error.value == "invalid_prov"
        assert error.field == "provider"

    @pytest.mark.unit
    def test_validation_error_has_validation_category(self):
        """ValidationError should have VALIDATION category."""
        from scrappy.cli.exceptions import ValidationError
        from scrappy.cli.utils.error_handler import ErrorCategory

        error = ValidationError("Test")
        assert error.category == ErrorCategory.VALIDATION

    @pytest.mark.unit
    def test_validation_error_formats_message_with_field(self):
        """ValidationError should format message to include field name."""
        from scrappy.cli.exceptions import ValidationError

        error = ValidationError("must be a positive integer", field="timeout")
        assert "timeout" in str(error).lower() or error.field == "timeout"

    @pytest.mark.unit
    def test_validation_error_provides_suggestion(self):
        """ValidationError should provide helpful suggestions."""
        from scrappy.cli.exceptions import ValidationError

        error = ValidationError("Invalid provider", field="provider", value="xyz")
        assert error.suggestion is not None
        assert len(error.suggestion) > 0


class TestFileOperationError:
    """Test FileOperationError for file system failures."""

    @pytest.mark.unit
    def test_file_operation_error_stores_path(self):
        """FileOperationError should store the file path."""
        from scrappy.cli.exceptions import FileOperationError

        path = Path("/test/file.txt")
        error = FileOperationError("File not found", path=path)
        assert error.path == path

    @pytest.mark.unit
    def test_file_operation_error_has_file_category(self):
        """FileOperationError should have FILE category."""
        from scrappy.cli.exceptions import FileOperationError
        from scrappy.cli.utils.error_handler import ErrorCategory

        error = FileOperationError("Test", path=Path("/test"))
        assert error.category == ErrorCategory.FILE

    @pytest.mark.unit
    def test_file_operation_error_operation_type(self):
        """FileOperationError should indicate the operation type."""
        from scrappy.cli.exceptions import FileOperationError

        error = FileOperationError("Failed", path=Path("/test"), operation="read")
        assert error.operation == "read"

    @pytest.mark.unit
    def test_file_operation_error_from_os_error(self):
        """FileOperationError should wrap OS-level errors."""
        from scrappy.cli.exceptions import FileOperationError

        original = FileNotFoundError("No such file")
        error = FileOperationError.from_os_error(original, Path("/test/file.txt"))
        assert error.path == Path("/test/file.txt")
        assert error.original is original

    @pytest.mark.unit
    def test_file_operation_error_permission_denied(self):
        """FileOperationError should indicate permission issues."""
        from scrappy.cli.exceptions import FileOperationError

        original = PermissionError("Access denied")
        error = FileOperationError.from_os_error(original, Path("/test"))
        assert "permission" in error.suggestion.lower()


class TestSessionError:
    """Test SessionError for session management failures."""

    @pytest.mark.unit
    def test_session_error_stores_operation(self):
        """SessionError should store the session operation."""
        from scrappy.cli.exceptions import SessionError

        error = SessionError("Save failed", operation="save")
        assert error.operation == "save"
        assert "Save failed" in str(error)

    @pytest.mark.unit
    def test_session_error_load_operation(self):
        """SessionError should handle load failures."""
        from scrappy.cli.exceptions import SessionError

        error = SessionError("No session found", operation="load")
        assert error.operation == "load"

    @pytest.mark.unit
    def test_session_error_stores_session_path(self):
        """SessionError should store the session file path."""
        from scrappy.cli.exceptions import SessionError

        error = SessionError("Corrupted", operation="load", session_path=Path("/test/.session"))
        assert error.session_path == Path("/test/.session")


class TestTaskExecutionError:
    """Test TaskExecutionError for task execution failures."""

    @pytest.mark.unit
    def test_task_execution_error_stores_task_name(self):
        """TaskExecutionError should store the task name."""
        from scrappy.cli.exceptions import TaskExecutionError

        error = TaskExecutionError("Planning failed", task_name="planning")
        assert error.task_name == "planning"

    @pytest.mark.unit
    def test_task_execution_error_has_task_category(self):
        """TaskExecutionError should have TASK category."""
        from scrappy.cli.exceptions import TaskExecutionError
        from scrappy.cli.utils.error_handler import ErrorCategory

        error = TaskExecutionError("Test", task_name="test")
        assert error.category == ErrorCategory.TASK

    @pytest.mark.unit
    def test_task_execution_error_stores_partial_result(self):
        """TaskExecutionError should store partial results if available."""
        from scrappy.cli.exceptions import TaskExecutionError

        partial = {"steps_completed": 3, "total_steps": 5}
        error = TaskExecutionError("Interrupted", task_name="analysis", partial_result=partial)
        assert error.partial_result == partial


class TestParseError:
    """Test ParseError for parsing failures."""

    @pytest.mark.unit
    def test_parse_error_stores_source(self):
        """ParseError should store the source being parsed."""
        from scrappy.cli.exceptions import ParseError

        error = ParseError("Invalid JSON", source="response.json")
        assert error.source == "response.json"

    @pytest.mark.unit
    def test_parse_error_has_parse_category(self):
        """ParseError should have PARSE category."""
        from scrappy.cli.exceptions import ParseError
        from scrappy.cli.utils.error_handler import ErrorCategory

        error = ParseError("Test", source="test")
        assert error.category == ErrorCategory.PARSE

    @pytest.mark.unit
    def test_parse_error_stores_content_preview(self):
        """ParseError should store a preview of the problematic content."""
        from scrappy.cli.exceptions import ParseError

        error = ParseError("Unexpected token", source="test.json", content_preview="{invalid")
        assert error.content_preview == "{invalid"

    @pytest.mark.unit
    def test_parse_error_from_json_error(self):
        """ParseError should wrap JSON decode errors."""
        import json
        from scrappy.cli.exceptions import ParseError

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
        from scrappy.cli.exceptions import UserInputError

        error = UserInputError("Input cancelled")
        assert "Input cancelled" in str(error)

    @pytest.mark.unit
    def test_user_input_error_has_user_input_category(self):
        """UserInputError should have USER_INPUT category."""
        from scrappy.cli.exceptions import UserInputError
        from scrappy.cli.utils.error_handler import ErrorCategory

        error = UserInputError("Test")
        assert error.category == ErrorCategory.USER_INPUT

    @pytest.mark.unit
    def test_user_input_error_interrupted(self):
        """UserInputError should indicate keyboard interrupt."""
        from scrappy.cli.exceptions import UserInputError

        error = UserInputError("Cancelled by user", interrupted=True)
        assert error.interrupted is True

    @pytest.mark.unit
    def test_user_input_error_eof(self):
        """UserInputError should indicate EOF."""
        from scrappy.cli.exceptions import UserInputError

        error = UserInputError("End of input", eof=True)
        assert error.eof is True


class TestExceptionFormatting:
    """Test exception message formatting."""

    @pytest.mark.unit
    def test_exception_str_includes_message(self):
        """Exception string should include the main message."""
        from scrappy.cli.exceptions import CLIError

        error = CLIError("Something went wrong")
        assert "Something went wrong" in str(error)

    @pytest.mark.unit
    def test_exception_repr_includes_class_name(self):
        """Exception repr should include class name for debugging."""
        from scrappy.cli.exceptions import ValidationError

        error = ValidationError("Invalid", field="test")
        assert "ValidationError" in repr(error)

    @pytest.mark.unit
    def test_exception_to_dict_for_logging(self):
        """Exceptions should be convertible to dict for structured logging."""
        from scrappy.cli.exceptions import ValidationError

        error = ValidationError("Invalid input", field="timeout")
        error_dict = error.to_dict()

        assert error_dict["message"] == "Invalid input"
        assert "category" in error_dict
        assert "severity" in error_dict


class TestErrorRecoveryStrategies:
    """Test error recovery strategy support in exceptions."""

    @pytest.mark.unit
    def test_file_error_suggests_check_path(self):
        """File errors should suggest checking the path."""
        from scrappy.cli.exceptions import FileOperationError

        error = FileOperationError("Not found", path=Path("/test/file.txt"))
        assert "path" in error.suggestion.lower() or "exist" in error.suggestion.lower()

    @pytest.mark.unit
    def test_validation_error_suggests_correct_format(self):
        """Validation errors should suggest the correct format."""
        from scrappy.cli.exceptions import ValidationError

        error = ValidationError("Invalid", field="timeout", value="abc")
        assert error.suggestion is not None
        assert len(error.suggestion) > 0


class TestExceptionLogging:
    """Test exception support for structured logging."""

    @pytest.mark.unit
    def test_exception_log_level_mapping(self):
        """Exceptions should map severity to log levels."""
        from scrappy.cli.exceptions import CLIError
        from scrappy.cli.utils.error_handler import ErrorSeverity
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
        from scrappy.cli.exceptions import ValidationError

        error = ValidationError("Invalid input", field="timeout")
        extra = error.logging_extra()

        assert extra["error_type"] == "ValidationError"
        assert "category" in extra


class TestRecoveryActionEnum:
    """Test RecoveryAction enumeration."""
    pass


class TestExceptionIntegrationWithErrorHandler:
    """Test that exceptions integrate with existing error_handler.py."""

    @pytest.mark.unit
    def test_exception_can_be_handled_by_handle_error(self):
        """Custom exceptions should work with handle_error function."""
        from scrappy.cli.exceptions import ValidationError
        from scrappy.cli.utils.error_handler import handle_error
        from tests.helpers import MockIO

        io = MockIO()
        error = ValidationError("Invalid provider", field="provider")

        handle_error(error, io)

        output = io.get_output()
        assert "Invalid provider" in output or "provider" in output



class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.unit

    @pytest.mark.unit

    @pytest.mark.unit
    def test_exception_with_unicode_message(self):
        """Exception should handle unicode characters."""
        from scrappy.cli.exceptions import CLIError

        error = CLIError("Error: invalid character")
        assert "invalid character" in str(error)


    @pytest.mark.unit
    def test_exception_context_with_non_serializable_value(self):
        """Exception context should handle non-serializable values in to_dict."""
        from scrappy.cli.exceptions import CLIError

        # Create a non-serializable context
        error = CLIError("Test", context={"func": lambda x: x})

        # to_dict should handle this gracefully
        error_dict = error.to_dict()
        assert "context" in error_dict
