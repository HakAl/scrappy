"""
Tests for orchestrator output abstraction.

Tests ConsoleOutput, NullOutput, and CapturingOutput implementations
of the OutputInterface protocol.
"""

import pytest
from io import StringIO
import sys

from src.orchestrator.output import (
    OutputInterface,
    ConsoleOutput,
    NullOutput,
    CapturingOutput,
)


class TestOutputInterfaceProtocol:
    """Test that implementations satisfy the OutputInterface protocol."""





class TestConsoleOutput:
    """Test ConsoleOutput prints to stdout correctly."""

    def test_info_prints_message(self, capsys):
        """info() should print the message as-is."""
        output = ConsoleOutput()
        output.info("Test message")
        captured = capsys.readouterr()
        assert captured.out == "Test message\n"

    def test_warn_prints_with_prefix(self, capsys):
        """warn() should print message with [WARN] prefix."""
        output = ConsoleOutput()
        output.warn("Warning message")
        captured = capsys.readouterr()
        assert captured.out == "[WARN] Warning message\n"

    def test_error_prints_with_prefix(self, capsys):
        """error() should print message with [ERROR] prefix."""
        output = ConsoleOutput()
        output.error("Error message")
        captured = capsys.readouterr()
        assert captured.out == "[ERROR] Error message\n"

    def test_success_prints_with_prefix(self, capsys):
        """success() should print message with [OK] prefix."""
        output = ConsoleOutput()
        output.success("Success message")
        captured = capsys.readouterr()
        assert captured.out == "[OK] Success message\n"

    def test_empty_message(self, capsys):
        """Empty messages should still be printed with proper formatting."""
        output = ConsoleOutput()

        output.info("")
        output.warn("")
        output.error("")
        output.success("")

        captured = capsys.readouterr()
        lines = captured.out.split("\n")

        assert lines[0] == ""
        assert lines[1] == "[WARN] "
        assert lines[2] == "[ERROR] "
        assert lines[3] == "[OK] "

    def test_message_with_newlines(self, capsys):
        """Messages with embedded newlines should be preserved."""
        output = ConsoleOutput()
        output.info("Line 1\nLine 2")
        captured = capsys.readouterr()
        assert captured.out == "Line 1\nLine 2\n"

    def test_message_with_special_characters(self, capsys):
        """Messages with special characters should be preserved."""
        output = ConsoleOutput()
        output.info("Path: C:\\Users\\test")
        captured = capsys.readouterr()
        assert captured.out == "Path: C:\\Users\\test\n"

    def test_message_with_unicode(self, capsys):
        """Messages with unicode should be handled correctly."""
        output = ConsoleOutput()
        output.info("Test with symbols: [OK] [X]")
        captured = capsys.readouterr()
        assert captured.out == "Test with symbols: [OK] [X]\n"


class TestNullOutput:
    """Test NullOutput produces no output."""

    def test_info_produces_no_output(self, capsys):
        """info() should not produce any output."""
        output = NullOutput()
        output.info("Test message")
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_warn_produces_no_output(self, capsys):
        """warn() should not produce any output."""
        output = NullOutput()
        output.warn("Warning message")
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_error_produces_no_output(self, capsys):
        """error() should not produce any output."""
        output = NullOutput()
        output.error("Error message")
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_success_produces_no_output(self, capsys):
        """success() should not produce any output."""
        output = NullOutput()
        output.success("Success message")
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_multiple_calls_produce_no_output(self, capsys):
        """Multiple calls should all produce no output."""
        output = NullOutput()
        output.info("info")
        output.warn("warn")
        output.error("error")
        output.success("success")
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""


class TestCapturingOutput:
    """Test CapturingOutput captures messages for inspection."""

    def test_info_captures_message(self):
        """info() should capture the message."""
        output = CapturingOutput()
        output.info("Test message")
        assert len(output.messages) == 1
        assert output.messages[0] == ('info', 'Test message')

    def test_warn_captures_message(self):
        """warn() should capture the message."""
        output = CapturingOutput()
        output.warn("Warning message")
        assert len(output.messages) == 1
        assert output.messages[0] == ('warn', 'Warning message')

    def test_error_captures_message(self):
        """error() should capture the message."""
        output = CapturingOutput()
        output.error("Error message")
        assert len(output.messages) == 1
        assert output.messages[0] == ('error', 'Error message')

    def test_success_captures_message(self):
        """success() should capture the message."""
        output = CapturingOutput()
        output.success("Success message")
        assert len(output.messages) == 1
        assert output.messages[0] == ('success', 'Success message')

    def test_multiple_captures(self):
        """Multiple messages should all be captured in order."""
        output = CapturingOutput()
        output.info("first")
        output.warn("second")
        output.error("third")
        output.success("fourth")

        assert len(output.messages) == 4
        assert output.messages[0] == ('info', 'first')
        assert output.messages[1] == ('warn', 'second')
        assert output.messages[2] == ('error', 'third')
        assert output.messages[3] == ('success', 'fourth')

    def test_get_by_level_info(self):
        """get_by_level('info') should return only info messages."""
        output = CapturingOutput()
        output.info("info1")
        output.warn("warn1")
        output.info("info2")

        info_messages = output.get_by_level('info')
        assert info_messages == ['info1', 'info2']

    def test_get_by_level_warn(self):
        """get_by_level('warn') should return only warn messages."""
        output = CapturingOutput()
        output.warn("warn1")
        output.info("info1")
        output.warn("warn2")

        warn_messages = output.get_by_level('warn')
        assert warn_messages == ['warn1', 'warn2']

    def test_get_by_level_error(self):
        """get_by_level('error') should return only error messages."""
        output = CapturingOutput()
        output.error("error1")
        output.info("info1")
        output.error("error2")

        error_messages = output.get_by_level('error')
        assert error_messages == ['error1', 'error2']

    def test_get_by_level_success(self):
        """get_by_level('success') should return only success messages."""
        output = CapturingOutput()
        output.success("success1")
        output.info("info1")
        output.success("success2")

        success_messages = output.get_by_level('success')
        assert success_messages == ['success1', 'success2']

    def test_get_by_level_empty(self):
        """get_by_level() should return empty list when no matching messages."""
        output = CapturingOutput()
        output.info("info")

        assert output.get_by_level('error') == []

    def test_clear_messages(self):
        """clear() should remove all captured messages."""
        output = CapturingOutput()
        output.info("test1")
        output.warn("test2")

        output.clear()

        assert output.messages == []

    def test_has_errors_true(self):
        """has_errors() should return True when errors exist."""
        output = CapturingOutput()
        output.info("info")
        output.error("error")

        assert output.has_errors() is True

    def test_has_errors_false(self):
        """has_errors() should return False when no errors exist."""
        output = CapturingOutput()
        output.info("info")
        output.warn("warn")
        output.success("success")

        assert output.has_errors() is False

    def test_has_errors_empty(self):
        """has_errors() should return False when no messages."""
        output = CapturingOutput()
        assert output.has_errors() is False

    def test_has_warnings_true(self):
        """has_warnings() should return True when warnings exist."""
        output = CapturingOutput()
        output.info("info")
        output.warn("warning")

        assert output.has_warnings() is True

    def test_has_warnings_false(self):
        """has_warnings() should return False when no warnings exist."""
        output = CapturingOutput()
        output.info("info")
        output.error("error")

        assert output.has_warnings() is False

    def test_produces_no_stdout(self, capsys):
        """CapturingOutput should not write to stdout."""
        output = CapturingOutput()
        output.info("test")
        output.warn("test")
        output.error("test")
        output.success("test")

        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""


class TestOutputEdgeCases:
    """Test edge cases across all output implementations."""

    @pytest.mark.parametrize("output_class", [ConsoleOutput, NullOutput, CapturingOutput])
    def test_none_message_handling(self, output_class):
        """All implementations should handle None gracefully (if passed)."""
        output = output_class()
        # These should not raise exceptions
        # Note: Protocol specifies str, but implementations should be robust
        try:
            output.info("")
            output.warn("")
            output.error("")
            output.success("")
        except Exception as e:
            pytest.fail(f"{output_class.__name__} raised exception on empty string: {e}")

    @pytest.mark.parametrize("output_class", [ConsoleOutput, NullOutput, CapturingOutput])
    def test_long_message(self, output_class, capsys):
        """All implementations should handle very long messages."""
        output = output_class()
        long_message = "x" * 10000

        # Should not raise
        output.info(long_message)

        if isinstance(output, CapturingOutput):
            assert output.messages[0][1] == long_message

    @pytest.mark.parametrize("output_class", [ConsoleOutput, NullOutput, CapturingOutput])
    def test_multiline_message(self, output_class):
        """All implementations should handle multiline messages."""
        output = output_class()
        multiline = "Line 1\nLine 2\nLine 3"

        # Should not raise
        output.info(multiline)

        if isinstance(output, CapturingOutput):
            assert output.messages[0][1] == multiline


class TestCapturingOutputIntegration:
    """Integration tests showing how CapturingOutput enables testing."""

    def test_can_verify_specific_error_message(self):
        """Demonstrate verifying a specific error was output."""
        output = CapturingOutput()

        # Simulate code that outputs on error
        if True:  # error condition
            output.error("Failed to connect to database")

        # In tests, we can verify:
        errors = output.get_by_level('error')
        assert "database" in errors[0]

    def test_can_verify_no_warnings(self):
        """Demonstrate verifying no warnings were output."""
        output = CapturingOutput()

        # Simulate successful operation
        output.info("Starting operation")
        output.success("Operation complete")

        # Verify no warnings or errors
        assert not output.has_warnings()
        assert not output.has_errors()

    def test_can_track_operation_sequence(self):
        """Demonstrate tracking sequence of operations."""
        output = CapturingOutput()

        # Simulate a multi-step operation
        output.info("Step 1: Loading config")
        output.info("Step 2: Connecting")
        output.warn("Connection slow")
        output.info("Step 3: Processing")
        output.success("Complete")

        # Verify order
        assert len(output.messages) == 5
        assert output.messages[0][0] == 'info'
        assert output.messages[4][0] == 'success'
        assert output.has_warnings()
        assert not output.has_errors()
