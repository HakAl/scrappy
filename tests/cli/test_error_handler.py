"""
Tests for CLI error handler utility.

Tests for consistent error handling across the CLI modules.
"""

import pytest
import json
from pathlib import Path
from unittest.mock import Mock

from tests.helpers import MockIO


class TestErrorSeverity:
    """Tests for error severity classification."""


    def test_severity_ordering(self):
        """Severity levels have correct ordering (CRITICAL > ERROR > WARNING > INFO)."""
        from src.cli.utils.error_handler import ErrorSeverity

        assert ErrorSeverity.CRITICAL.value > ErrorSeverity.ERROR.value
        assert ErrorSeverity.ERROR.value > ErrorSeverity.WARNING.value
        assert ErrorSeverity.WARNING.value > ErrorSeverity.INFO.value


class TestErrorCategory:
    """Tests for error category classification."""



class TestFormatError:
    """Tests for error message formatting."""

    def test_format_error_basic(self):
        """format_error converts exception to user-friendly message."""
        from src.cli.utils.error_handler import format_error

        error = ValueError("Invalid input value")
        result = format_error(error)

        assert "Invalid input value" in result
        # Should not include traceback by default
        assert "Traceback" not in result

    def test_format_error_with_traceback(self):
        """format_error can include traceback when requested."""
        from src.cli.utils.error_handler import format_error

        try:
            raise ValueError("Test error")
        except ValueError as e:
            result = format_error(e, include_traceback=True)

        assert "Test error" in result
        assert "Traceback" in result or "ValueError" in result

    def test_format_error_file_not_found(self):
        """format_error handles FileNotFoundError with clear message."""
        from src.cli.utils.error_handler import format_error

        error = FileNotFoundError("config.json")
        result = format_error(error)

        assert "config.json" in result
        # Should be user-friendly, not raw exception
        assert len(result) < 200

    def test_format_error_permission_error(self):
        """format_error handles PermissionError with clear message."""
        from src.cli.utils.error_handler import format_error

        error = PermissionError("Access denied to /etc/passwd")
        result = format_error(error)

        assert "Access denied" in result or "permission" in result.lower()

    def test_format_error_json_decode_error(self):
        """format_error handles JSONDecodeError with clear message."""
        from src.cli.utils.error_handler import format_error

        try:
            json.loads("invalid json")
        except json.JSONDecodeError as e:
            result = format_error(e)

        assert len(result) < 300
        # Should not expose raw JSON error internals
        assert "Expecting value" in result or "JSON" in result or "parse" in result.lower()

    def test_format_error_connection_error(self):
        """format_error handles connection errors clearly."""
        from src.cli.utils.error_handler import format_error

        error = ConnectionError("Failed to connect to API")
        result = format_error(error)

        assert "connect" in result.lower() or "API" in result

    def test_format_error_strips_long_messages(self):
        """format_error truncates very long error messages."""
        from src.cli.utils.error_handler import format_error

        long_message = "x" * 1000
        error = Exception(long_message)
        result = format_error(error)

        # Should be truncated to reasonable length
        assert len(result) <= 500

    def test_format_error_empty_message(self):
        """format_error handles exceptions with empty messages."""
        from src.cli.utils.error_handler import format_error

        error = Exception("")
        result = format_error(error)

        # Should provide some useful output
        assert len(result) > 0
        assert "Unknown error" in result or "Exception" in result


class TestHandleError:
    """Tests for main error handling function."""

    def test_handle_error_displays_message(self):
        """handle_error outputs error message to IO."""
        from src.cli.utils.error_handler import handle_error, ErrorSeverity

        io = MockIO()
        error = ValueError("Test error message")

        handle_error(error, io)

        output = io.get_output()
        assert "Test error message" in output




    def test_handle_error_bold_for_critical(self):
        """handle_error uses bold for CRITICAL severity."""
        from src.cli.utils.error_handler import handle_error, ErrorSeverity

        io = MockIO()
        error = ValueError("Critical error")

        handle_error(error, io, severity=ErrorSeverity.CRITICAL)

        styled = io.get_styled_outputs()
        assert len(styled) > 0
        assert any(s.get('bold') for s in styled)

    def test_handle_error_with_context(self):
        """handle_error includes context in output when provided."""
        from src.cli.utils.error_handler import handle_error

        io = MockIO()
        error = ValueError("Test error")

        handle_error(error, io, context="While loading configuration")

        output = io.get_output()
        assert "loading configuration" in output or "configuration" in output



class TestGetErrorSuggestion:
    """Tests for error suggestion generation."""

    def test_suggestion_for_file_not_found(self):
        """get_error_suggestion provides help for FileNotFoundError."""
        from src.cli.utils.error_handler import get_error_suggestion

        error = FileNotFoundError("config.json")
        suggestion = get_error_suggestion(error)

        assert suggestion is not None
        assert len(suggestion) > 0
        # Should suggest checking file path or similar
        assert "path" in suggestion.lower() or "exist" in suggestion.lower() or "check" in suggestion.lower()

    def test_suggestion_for_permission_error(self):
        """get_error_suggestion provides help for PermissionError."""
        from src.cli.utils.error_handler import get_error_suggestion

        error = PermissionError("Access denied")
        suggestion = get_error_suggestion(error)

        assert suggestion is not None
        assert "permission" in suggestion.lower() or "access" in suggestion.lower()

    def test_suggestion_for_connection_error(self):
        """get_error_suggestion provides help for ConnectionError."""
        from src.cli.utils.error_handler import get_error_suggestion

        error = ConnectionError("Failed to connect")
        suggestion = get_error_suggestion(error)

        assert suggestion is not None
        assert "network" in suggestion.lower() or "connection" in suggestion.lower() or "internet" in suggestion.lower()

    def test_suggestion_for_json_error(self):
        """get_error_suggestion provides help for JSON parsing errors."""
        from src.cli.utils.error_handler import get_error_suggestion

        try:
            json.loads("invalid")
        except json.JSONDecodeError as e:
            suggestion = get_error_suggestion(e)

        assert suggestion is not None
        assert "json" in suggestion.lower() or "format" in suggestion.lower() or "syntax" in suggestion.lower()

    def test_suggestion_for_unknown_error(self):
        """get_error_suggestion provides generic help for unknown errors."""
        from src.cli.utils.error_handler import get_error_suggestion

        error = Exception("Unknown error type")
        suggestion = get_error_suggestion(error)

        # Should return something useful even for unknown errors
        assert suggestion is not None
        assert len(suggestion) > 0

    def test_suggestion_with_context(self):
        """get_error_suggestion uses context for better suggestions."""
        from src.cli.utils.error_handler import get_error_suggestion

        error = FileNotFoundError("missing.py")
        suggestion = get_error_suggestion(error, context="loading project files")

        assert suggestion is not None
        assert len(suggestion) > 0


class TestSafeOperation:
    """Tests for safe operation wrapper."""


    def test_safe_operation_failure(self):
        """safe_operation returns failure and error for failed operations."""
        from src.cli.utils.error_handler import safe_operation

        def failing_func():
            raise ValueError("Test error")

        success, result = safe_operation(failing_func)

        assert success is False
        assert "Test error" in str(result) or isinstance(result, Exception)

    def test_safe_operation_with_default(self):
        """safe_operation returns default value on failure when provided."""
        from src.cli.utils.error_handler import safe_operation

        def failing_func():
            raise ValueError("Test error")

        success, result = safe_operation(failing_func, default_return="default")

        assert success is False
        assert result == "default"



    def test_safe_operation_with_io(self):
        """safe_operation can output errors to IO when provided."""
        from src.cli.utils.error_handler import safe_operation

        io = MockIO()

        def failing_func():
            raise ValueError("Test error")

        success, result = safe_operation(failing_func, io=io)

        assert success is False
        # Error should be output to IO
        output = io.get_output()
        assert "Test error" in output or "error" in output.lower()

    def test_safe_operation_suppresses_output_when_silent(self):
        """safe_operation can suppress error output when silent=True."""
        from src.cli.utils.error_handler import safe_operation

        io = MockIO()

        def failing_func():
            raise ValueError("Test error")

        success, result = safe_operation(failing_func, io=io, silent=True)

        assert success is False
        # No output when silent
        output = io.get_output()
        assert output == "" or len(output) == 0


class TestFileOperationError:
    """Tests for file operation error handler."""


    def test_permission_error(self):
        """file_operation_error handles PermissionError."""
        from src.cli.utils.error_handler import file_operation_error

        io = MockIO()
        error = PermissionError("Access denied")

        file_operation_error(io, error, Path("/etc/passwd"))

        output = io.get_output()
        assert "permission" in output.lower() or "access" in output.lower()

    def test_generic_io_error(self):
        """file_operation_error handles generic IOError."""
        from src.cli.utils.error_handler import file_operation_error

        io = MockIO()
        error = IOError("Disk full")

        file_operation_error(io, error, Path("output.txt"))

        output = io.get_output()
        assert "Disk full" in output or "output.txt" in output


class TestApiDelegationError:
    """Tests for API delegation error handler."""

    def test_api_error_display(self):
        """api_delegation_error displays error message."""
        from src.cli.utils.error_handler import api_delegation_error

        io = MockIO()
        error = Exception("API rate limit exceeded")

        api_delegation_error(io, error, "openai")

        output = io.get_output()
        assert "rate limit" in output.lower() or "API" in output

    def test_api_error_includes_provider(self):
        """api_delegation_error includes provider name in output."""
        from src.cli.utils.error_handler import api_delegation_error

        io = MockIO()
        error = Exception("Connection failed")

        api_delegation_error(io, error, "anthropic")

        output = io.get_output()
        assert "anthropic" in output.lower()

    def test_api_timeout_error(self):
        """api_delegation_error handles timeout errors."""
        from src.cli.utils.error_handler import api_delegation_error

        io = MockIO()
        error = TimeoutError("Request timed out")

        api_delegation_error(io, error, "gemini")

        output = io.get_output()
        assert "timeout" in output.lower() or "timed out" in output.lower()


class TestTaskExecutionError:
    """Tests for task execution error handler."""

    def test_task_error_display(self):
        """task_execution_error displays error message."""
        from src.cli.utils.error_handler import task_execution_error

        io = MockIO()
        error = Exception("Task failed")

        task_execution_error(io, error, "code analysis")

        output = io.get_output()
        assert "Task failed" in output or "code analysis" in output

    def test_task_error_includes_task_name(self):
        """task_execution_error includes task name in output."""
        from src.cli.utils.error_handler import task_execution_error

        io = MockIO()
        error = Exception("Error")

        task_execution_error(io, error, "planning")

        output = io.get_output()
        assert "planning" in output


class TestSessionError:
    """Tests for session error handler."""

    def test_session_save_error(self):
        """session_error handles save errors."""
        from src.cli.utils.error_handler import session_error

        io = MockIO()
        error = IOError("Could not write to disk")

        session_error(io, error, "save")

        output = io.get_output()
        assert "save" in output.lower() or "session" in output.lower()

    def test_session_load_error(self):
        """session_error handles load errors."""
        from src.cli.utils.error_handler import session_error

        io = MockIO()
        error = FileNotFoundError("session.json")

        session_error(io, error, "load")

        output = io.get_output()
        assert "load" in output.lower() or "session" in output.lower()


class TestParseError:
    """Tests for parse error handler."""

    def test_json_parse_error(self):
        """parse_error handles JSON parsing errors."""
        from src.cli.utils.error_handler import parse_error

        io = MockIO()
        try:
            json.loads("invalid")
        except json.JSONDecodeError as e:
            parse_error(io, e, "response.json")

        output = io.get_output()
        assert "response.json" in output or "parse" in output.lower() or "json" in output.lower()

    def test_parse_error_with_content_preview(self):
        """parse_error can show content preview for debugging."""
        from src.cli.utils.error_handler import parse_error

        io = MockIO()
        error = ValueError("Invalid format")

        parse_error(io, error, "data.txt", content_preview="first 50 chars...")

        output = io.get_output()
        # Should include some helpful context
        assert "data.txt" in output or "Invalid format" in output


class TestValidationError:
    """Tests for validation error handler."""

    def test_validation_error_display(self):
        """validation_error displays validation message."""
        from src.cli.utils.error_handler import validation_error

        io = MockIO()

        validation_error(io, "Invalid email format", field="email")

        output = io.get_output()
        assert "Invalid email format" in output or "email" in output

    def test_validation_error_with_value(self):
        """validation_error can include the invalid value."""
        from src.cli.utils.error_handler import validation_error

        io = MockIO()

        validation_error(io, "Must be positive", field="count", value=-5)

        output = io.get_output()
        assert "Must be positive" in output or "count" in output


class TestErrorHandlerIntegration:
    """Integration tests for error handler with CLI workflows."""

    def test_chained_error_handling(self):
        """Error handler works correctly with multiple sequential errors."""
        from src.cli.utils.error_handler import handle_error, ErrorSeverity

        io = MockIO()

        # Simulate multiple errors in a workflow
        handle_error(ValueError("Error 1"), io, severity=ErrorSeverity.WARNING)
        handle_error(IOError("Error 2"), io, severity=ErrorSeverity.ERROR)

        output = io.get_output()
        assert "Error 1" in output
        assert "Error 2" in output

        styled = io.get_styled_outputs()
        # Should have both yellow (warning) and red (error)
        colors = [s.get('fg') for s in styled]
        assert 'yellow' in colors
        assert 'red' in colors


    def test_safe_operation_with_real_file_operations(self):
        """safe_operation handles real file I/O errors correctly."""
        from src.cli.utils.error_handler import safe_operation

        def read_nonexistent():
            return Path("/nonexistent/file.txt").read_text()

        success, result = safe_operation(read_nonexistent)

        assert success is False

    def test_error_context_propagation(self):
        """Error context is properly propagated through handlers."""
        from src.cli.utils.error_handler import handle_error

        io = MockIO()

        # Nested context scenario
        try:
            try:
                raise ValueError("Inner error")
            except ValueError as e:
                raise IOError("Outer error") from e
        except IOError as e:
            handle_error(e, io, context="During nested operation")

        output = io.get_output()
        assert "Outer error" in output or "nested operation" in output


class TestErrorMessageQuality:
    """Tests ensuring error messages are user-friendly and actionable."""

    def test_no_raw_exception_types_exposed(self):
        """Error messages don't expose raw Python exception types to users."""
        from src.cli.utils.error_handler import format_error

        errors = [
            ValueError("test"),
            KeyError("missing_key"),
            AttributeError("no attribute"),
        ]

        for error in errors:
            result = format_error(error)
            # Should not just show the exception class name alone
            assert result != type(error).__name__
            # Should have meaningful content
            assert len(result) > 5

    def test_messages_are_sentence_like(self):
        """Error messages are formatted as readable sentences."""
        from src.cli.utils.error_handler import handle_error

        io = MockIO()
        handle_error(ValueError("Invalid input provided"), io)

        output = io.get_output()
        # Should be readable, not raw exception format
        assert "Invalid input provided" in output

    def test_suggestions_are_actionable(self):
        """Error suggestions provide actionable steps."""
        from src.cli.utils.error_handler import get_error_suggestion

        error = FileNotFoundError("config.json")
        suggestion = get_error_suggestion(error)

        # Should contain actionable words
        actionable_words = ['check', 'verify', 'ensure', 'try', 'make sure', 'confirm']
        assert any(word in suggestion.lower() for word in actionable_words)


class TestEdgeCases:
    """Tests for edge cases and error recovery."""


    def test_format_error_with_unicode(self):
        """format_error handles Unicode characters in error messages."""
        from src.cli.utils.error_handler import format_error

        error = Exception("Error with unicode: cafe, nino")
        result = format_error(error)

        assert "cafe" in result or "nino" in result


    def test_deeply_nested_exception_chain(self):
        """handle_error works with deeply nested exception chains."""
        from src.cli.utils.error_handler import handle_error

        io = MockIO()

        try:
            try:
                try:
                    raise ValueError("Deepest")
                except ValueError as e:
                    raise KeyError("Middle") from e
            except KeyError as e:
                raise IOError("Outermost") from e
        except IOError as e:
            handle_error(e, io)

        output = io.get_output()
        assert "Outermost" in output or len(output) > 0
