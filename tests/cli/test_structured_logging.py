"""
Tests for structured logging in CLI.

These tests define the behavior of a structured logging system that
provides both human-readable output and machine-parseable structured data.
"""

import pytest
import json
import logging
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from io import StringIO


class TestCLILogger:
    """Test the main CLI logger class."""

    @pytest.mark.unit
    def test_logger_creation(self):
        """CLILogger should be created with name and io interface."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO

        io = MockIO()
        logger = CLILogger("test_logger", io=io)

        assert logger.name == "test_logger"

    @pytest.mark.unit
    def test_logger_outputs_to_io(self):
        """Logger should output to IO interface."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO

        io = MockIO()
        logger = CLILogger("test", io=io)

        logger.info("Test message")

        output = io.get_output()
        assert "Test message" in output

    @pytest.mark.unit
    def test_logger_error_uses_red_color(self):
        """Error messages should use red color."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO

        io = MockIO()
        logger = CLILogger("test", io=io)

        logger.error("Error message")

        styled = io.get_styled_outputs()
        assert any(s.get('fg') == 'red' for s in styled)

    @pytest.mark.unit
    def test_logger_warning_uses_yellow_color(self):
        """Warning messages should use yellow color."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO

        io = MockIO()
        logger = CLILogger("test", io=io)

        logger.warning("Warning message")

        styled = io.get_styled_outputs()
        assert any(s.get('fg') == 'yellow' for s in styled)

    @pytest.mark.unit
    def test_logger_info_uses_default_color(self):
        """Info messages should use default or cyan color."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO

        io = MockIO()
        logger = CLILogger("test", io=io)

        logger.info("Info message")

        output = io.get_output()
        assert "Info message" in output

    @pytest.mark.unit
    def test_logger_debug_respects_level(self):
        """Debug messages should respect log level."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO
        import logging

        io = MockIO()
        logger = CLILogger("test", io=io, level=logging.INFO)

        logger.debug("Debug message")

        output = io.get_output()
        assert "Debug message" not in output

    @pytest.mark.unit
    def test_logger_critical_uses_bold_red(self):
        """Critical messages should use bold red."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO

        io = MockIO()
        logger = CLILogger("test", io=io)

        logger.critical("Critical message")

        styled = io.get_styled_outputs()
        assert any(s.get('fg') == 'red' and s.get('bold') for s in styled)


class TestStructuredOutput:
    """Test structured data output capabilities."""

    @pytest.mark.unit
    def test_logger_can_output_structured_data(self):
        """Logger should support structured data output."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO

        io = MockIO()
        logger = CLILogger("test", io=io)

        logger.info("Operation completed", extra={
            "operation": "save",
            "duration_ms": 150,
            "items": 5
        })

        # Structured data should be accessible
        records = logger.get_records()
        assert len(records) > 0
        assert records[-1]["extra"]["operation"] == "save"
        assert records[-1]["extra"]["duration_ms"] == 150

    @pytest.mark.unit
    def test_logger_records_timestamp(self):
        """Logger should record timestamp for each message."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO

        io = MockIO()
        logger = CLILogger("test", io=io)

        logger.info("Test")

        records = logger.get_records()
        assert "timestamp" in records[-1]

    @pytest.mark.unit
    def test_logger_records_level(self):
        """Logger should record log level for each message."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO

        io = MockIO()
        logger = CLILogger("test", io=io)

        logger.warning("Test")

        records = logger.get_records()
        assert records[-1]["level"] == "WARNING"

    @pytest.mark.unit
    def test_logger_records_location(self):
        """Logger should record source location."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO

        io = MockIO()
        logger = CLILogger("test", io=io)

        logger.info("Test")

        records = logger.get_records()
        # Should have file/line info
        assert "location" in records[-1] or "file" in records[-1]

    @pytest.mark.unit
    def test_logger_export_to_json(self):
        """Logger should export records as JSON."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO

        io = MockIO()
        logger = CLILogger("test", io=io)

        logger.info("Message 1", extra={"key": "value1"})
        logger.error("Message 2", extra={"key": "value2"})

        json_output = logger.export_json()
        data = json.loads(json_output)

        assert len(data) == 2
        assert data[0]["message"] == "Message 1"
        assert data[1]["level"] == "ERROR"


class TestExceptionLogging:
    """Test logging of exceptions with structured data."""

    @pytest.mark.unit
    def test_logger_exception_includes_traceback(self):
        """Logger should include traceback for exceptions."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO

        io = MockIO()
        logger = CLILogger("test", io=io)

        try:
            raise ValueError("Test error")
        except ValueError:
            logger.exception("Operation failed")

        records = logger.get_records()
        assert "traceback" in records[-1] or "exc_info" in records[-1]

    @pytest.mark.unit
    def test_logger_exception_includes_type(self):
        """Logger should include exception type."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO

        io = MockIO()
        logger = CLILogger("test", io=io)

        try:
            raise ValueError("Test")
        except ValueError:
            logger.exception("Failed")

        records = logger.get_records()
        assert "ValueError" in str(records[-1])

    @pytest.mark.unit
    def test_logger_cli_exception_includes_extra(self):
        """Logger should extract extra data from CLI exceptions."""
        from src.cli.logging import CLILogger
        from src.cli.exceptions import ProviderError
        from tests.helpers import MockIO

        io = MockIO()
        logger = CLILogger("test", io=io)

        try:
            raise ProviderError("Timeout", provider="openai", is_timeout=True)
        except ProviderError:
            logger.exception("Provider failed")

        records = logger.get_records()
        # Should include exception's extra data
        extra = records[-1].get("extra", {})
        assert extra.get("provider") == "openai" or "openai" in str(records[-1])


class TestLoggerConfiguration:
    """Test logger configuration options."""

    @pytest.mark.unit
    def test_logger_set_level(self):
        """Logger level should be configurable."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO
        import logging

        io = MockIO()
        logger = CLILogger("test", io=io, level=logging.WARNING)

        logger.info("Should not appear")
        logger.warning("Should appear")

        output = io.get_output()
        assert "Should not appear" not in output
        assert "Should appear" in output

    @pytest.mark.unit
    def test_logger_enable_structured_mode(self):
        """Logger should support structured-only mode for machine parsing."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO

        io = MockIO()
        logger = CLILogger("test", io=io, structured_only=True)

        logger.info("Test message")

        # In structured mode, output should be JSON
        output = io.get_output()
        # Should be valid JSON
        data = json.loads(output.strip())
        assert data["message"] == "Test message"

    @pytest.mark.unit
    def test_logger_format_string(self):
        """Logger should support custom format strings."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO

        io = MockIO()
        logger = CLILogger(
            "test",
            io=io,
            format="[{level}] {message}"
        )

        logger.info("Test message")

        output = io.get_output()
        assert "[INFO]" in output

    @pytest.mark.unit
    def test_logger_max_records(self):
        """Logger should limit stored records to prevent memory issues."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO

        io = MockIO()
        logger = CLILogger("test", io=io, max_records=10)

        for i in range(20):
            logger.info(f"Message {i}")

        records = logger.get_records()
        assert len(records) <= 10


class TestLoggerContextManagement:
    """Test context management for structured logging."""

    @pytest.mark.unit
    def test_logger_with_context(self):
        """Logger should support context that applies to all messages."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO

        io = MockIO()
        logger = CLILogger("test", io=io)

        with logger.context(operation="bulk_import", user="test_user"):
            logger.info("Step 1")
            logger.info("Step 2")

        records = logger.get_records()
        for record in records:
            assert record["extra"]["operation"] == "bulk_import"
            assert record["extra"]["user"] == "test_user"

    @pytest.mark.unit
    def test_logger_nested_context(self):
        """Logger should support nested contexts."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO

        io = MockIO()
        logger = CLILogger("test", io=io)

        with logger.context(operation="import"):
            logger.info("Outer")
            with logger.context(step="validation"):
                logger.info("Inner")

        records = logger.get_records()
        assert records[1]["extra"]["operation"] == "import"
        assert records[1]["extra"]["step"] == "validation"

    @pytest.mark.unit
    def test_logger_bind_returns_new_logger(self):
        """bind() should return logger with bound context."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO

        io = MockIO()
        logger = CLILogger("test", io=io)

        bound_logger = logger.bind(request_id="123")
        bound_logger.info("Test")

        records = logger.get_records()
        assert records[-1]["extra"]["request_id"] == "123"


class TestLoggerIntegration:
    """Test logger integration with other CLI components."""

    @pytest.mark.unit
    def test_logger_replaces_direct_secho(self):
        """Logger should provide equivalent functionality to direct secho."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO

        io = MockIO()
        logger = CLILogger("test", io=io)

        # These should produce equivalent output
        logger.error("Error message")

        styled = io.get_styled_outputs()
        assert len(styled) > 0
        assert styled[0]["fg"] == "red"

    @pytest.mark.unit
    def test_logger_integrates_with_error_handler(self):
        """Logger should integrate with existing error_handler functions."""
        from src.cli.logging import CLILogger
        from src.cli.utils.error_handler import ErrorSeverity
        from tests.helpers import MockIO

        io = MockIO()
        logger = CLILogger("test", io=io)

        # Should map severity to log level
        logger.log_with_severity(
            "Test message",
            severity=ErrorSeverity.WARNING
        )

        records = logger.get_records()
        assert records[-1]["level"] == "WARNING"


class TestFileHandler:
    """Test file-based logging output."""

    @pytest.mark.unit
    def test_logger_writes_to_file(self, tmp_path):
        """Logger should write to file when configured."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO

        log_file = tmp_path / "test.log"
        io = MockIO()
        logger = CLILogger("test", io=io, log_file=log_file)

        logger.info("Test message")
        logger.flush()

        assert log_file.exists()
        content = log_file.read_text()
        assert "Test message" in content

        logger.close()

    @pytest.mark.unit
    def test_file_output_is_structured(self, tmp_path):
        """File output should be structured JSON lines."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO

        log_file = tmp_path / "test.log"
        io = MockIO()
        logger = CLILogger("test", io=io, log_file=log_file)

        logger.info("Message 1", extra={"key": "value1"})
        logger.info("Message 2", extra={"key": "value2"})
        logger.flush()

        lines = log_file.read_text().strip().split('\n')
        for line in lines:
            # Each line should be valid JSON
            data = json.loads(line)
            assert "message" in data

        logger.close()


class TestLoggerFactory:
    """Test logger factory for creating configured loggers."""

    @pytest.mark.unit
    def test_get_logger_returns_configured_instance(self):
        """get_logger should return configured logger instance."""
        from src.cli.logging import get_logger
        from tests.helpers import MockIO

        io = MockIO()
        logger = get_logger("my_module", io=io)

        assert logger.name == "my_module"

    @pytest.mark.unit
    def test_get_logger_returns_same_instance(self):
        """get_logger should return same instance for same name."""
        from src.cli.logging import get_logger
        from tests.helpers import MockIO

        io = MockIO()
        logger1 = get_logger("shared", io=io)
        logger2 = get_logger("shared", io=io)

        assert logger1 is logger2

    @pytest.mark.unit
    def test_configure_all_loggers(self):
        """Should be able to configure all loggers at once."""
        from src.cli.logging import configure_logging, get_logger
        from tests.helpers import MockIO
        import logging

        io = MockIO()
        configure_logging(level=logging.DEBUG, io=io)

        logger = get_logger("test_module", io=io)
        assert logger.level <= logging.DEBUG


class TestPerformance:
    """Test logger performance considerations."""

    @pytest.mark.unit
    def test_logger_disabled_check_is_fast(self):
        """Logger should quickly skip disabled levels."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO
        import logging

        io = MockIO()
        logger = CLILogger("test", io=io, level=logging.ERROR)

        # This should be very fast (no formatting)
        for _ in range(1000):
            logger.debug("This should be skipped")

        # No output should be produced
        assert io.get_output() == ""

    @pytest.mark.unit
    def test_logger_lazy_formatting(self):
        """Logger should use lazy formatting for expensive operations."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO
        import logging

        io = MockIO()
        logger = CLILogger("test", io=io, level=logging.ERROR)

        expensive_called = []

        def expensive_operation():
            expensive_called.append(1)
            return "expensive result"

        # Debug is disabled, so expensive_operation should not be called
        logger.debug("Result: %s", expensive_operation)

        assert len(expensive_called) == 0


class TestLogRotation:
    """Test log file rotation support."""

    @pytest.mark.unit
    def test_logger_rotates_large_files(self, tmp_path):
        """Logger should rotate log files when they get too large."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO

        log_file = tmp_path / "test.log"
        io = MockIO()

        # 1KB max size
        logger = CLILogger(
            "test",
            io=io,
            log_file=log_file,
            max_bytes=1024,
            backup_count=3
        )

        # Write enough to trigger rotation
        for i in range(100):
            logger.info("X" * 50, extra={"i": i})

        logger.flush()

        # Should have created backup files
        log_files = list(tmp_path.glob("test.log*"))
        assert len(log_files) > 1

        logger.close()


class TestFilterAndSampling:
    """Test log filtering and sampling."""

    @pytest.mark.unit
    def test_logger_filter_by_category(self):
        """Logger should support filtering by category."""
        from src.cli.logging import CLILogger
        from src.cli.utils.error_handler import ErrorCategory
        from tests.helpers import MockIO

        io = MockIO()
        logger = CLILogger(
            "test",
            io=io,
            categories=[ErrorCategory.API, ErrorCategory.TASK]
        )

        logger.info("API message", extra={"category": ErrorCategory.API})
        logger.info("File message", extra={"category": ErrorCategory.FILE})

        records = logger.get_records()
        # Only API message should be recorded
        assert len(records) == 1
        assert records[0]["extra"]["category"] == ErrorCategory.API

    @pytest.mark.unit
    def test_logger_sampling(self):
        """Logger should support sampling for high-volume logs."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO

        io = MockIO()
        logger = CLILogger("test", io=io, sample_rate=0.5)

        # Log many messages
        for i in range(100):
            logger.debug(f"Message {i}")

        records = logger.get_records()
        # Should have approximately 50% (with some variance)
        assert 20 < len(records) < 80


class TestJSONSerializationSafety:
    """Test that json.dumps() handles non-serializable data gracefully."""

    @pytest.mark.unit
    def test_logger_handles_datetime_in_extra(self):
        """Logger should handle datetime objects in extra without crashing."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO
        from datetime import datetime

        io = MockIO()
        logger = CLILogger("test", io=io)

        # datetime is not JSON serializable by default
        logger.info("Test", extra={"timestamp": datetime.now()})

        # Should not crash, should have logged something
        records = logger.get_records()
        assert len(records) == 1
        # The datetime should be converted to a string representation
        assert "timestamp" in records[0]["extra"]

    @pytest.mark.unit
    def test_logger_handles_set_in_extra(self):
        """Logger should handle set objects in extra without crashing."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO

        io = MockIO()
        logger = CLILogger("test", io=io)

        # set is not JSON serializable
        logger.info("Test", extra={"items": {1, 2, 3}})

        records = logger.get_records()
        assert len(records) == 1
        assert "items" in records[0]["extra"]

    @pytest.mark.unit
    def test_logger_handles_custom_object_in_extra(self):
        """Logger should handle custom objects in extra without crashing."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO

        class CustomObject:
            def __init__(self):
                self.value = 42

        io = MockIO()
        logger = CLILogger("test", io=io)

        logger.info("Test", extra={"obj": CustomObject()})

        records = logger.get_records()
        assert len(records) == 1
        assert "obj" in records[0]["extra"]

    @pytest.mark.unit
    def test_logger_handles_bytes_in_extra(self):
        """Logger should handle bytes objects in extra without crashing."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO

        io = MockIO()
        logger = CLILogger("test", io=io)

        logger.info("Test", extra={"data": b"binary data"})

        records = logger.get_records()
        assert len(records) == 1
        assert "data" in records[0]["extra"]

    @pytest.mark.unit
    def test_file_output_handles_non_serializable(self, tmp_path):
        """File output should handle non-serializable data without crashing."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO
        from datetime import datetime

        log_file = tmp_path / "test.log"
        io = MockIO()
        logger = CLILogger("test", io=io, log_file=log_file)

        # This should not crash even with non-serializable data
        logger.info("Test", extra={"timestamp": datetime.now()})
        logger.flush()

        # File should exist and contain data
        assert log_file.exists()
        content = log_file.read_text()
        assert "Test" in content

        logger.close()

    @pytest.mark.unit
    def test_structured_output_handles_non_serializable(self):
        """Structured output mode should handle non-serializable data."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO
        from datetime import datetime

        io = MockIO()
        logger = CLILogger("test", io=io, structured_only=True)

        # This should not crash
        logger.info("Test", extra={"timestamp": datetime.now()})

        # Should have produced output
        output = io.get_output()
        assert len(output) > 0
        # Output should be valid JSON
        data = json.loads(output.strip())
        assert data["message"] == "Test"

    @pytest.mark.unit
    def test_export_json_handles_non_serializable(self):
        """export_json should handle non-serializable data without crashing."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO
        from datetime import datetime

        io = MockIO()
        logger = CLILogger("test", io=io)

        logger.info("Test 1", extra={"timestamp": datetime.now()})
        logger.info("Test 2", extra={"items": {1, 2, 3}})

        # This should not crash
        json_output = logger.export_json()

        # Should be valid JSON
        data = json.loads(json_output)
        assert len(data) == 2
        assert data[0]["message"] == "Test 1"

    @pytest.mark.unit
    def test_logger_handles_nested_non_serializable(self):
        """Logger should handle nested non-serializable objects."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO
        from datetime import datetime

        io = MockIO()
        logger = CLILogger("test", io=io)

        # Nested structure with non-serializable data
        logger.info("Test", extra={
            "metadata": {
                "created": datetime.now(),
                "tags": {"a", "b", "c"}
            }
        })

        records = logger.get_records()
        assert len(records) == 1

    @pytest.mark.unit
    def test_logger_handles_function_in_extra(self):
        """Logger should handle function objects in extra without crashing."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO

        def my_func():
            pass

        io = MockIO()
        logger = CLILogger("test", io=io)

        logger.info("Test", extra={"callback": my_func})

        records = logger.get_records()
        assert len(records) == 1
        assert "callback" in records[0]["extra"]

    @pytest.mark.unit
    def test_bound_context_with_non_serializable(self):
        """Bound context with non-serializable data should not crash."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO
        from datetime import datetime

        io = MockIO()
        logger = CLILogger("test", io=io)

        # Bind non-serializable context
        bound = logger.bind(start_time=datetime.now())
        bound.info("Test message")

        records = logger.get_records()
        assert len(records) == 1

    @pytest.mark.unit
    def test_context_manager_with_non_serializable(self):
        """Context manager with non-serializable data should not crash."""
        from src.cli.logging import CLILogger
        from tests.helpers import MockIO
        from datetime import datetime

        io = MockIO()
        logger = CLILogger("test", io=io)

        with logger.context(start_time=datetime.now()):
            logger.info("Test message")

        records = logger.get_records()
        assert len(records) == 1
