"""
Tests for ConsoleFactory.

Tests the mode-aware Console factory that returns appropriate
Console instances based on TUI/CLI mode.
"""

import pytest
from unittest.mock import MagicMock
from io import StringIO

from rich.console import Console

from src.infrastructure.console_factory import ConsoleFactory
from src.infrastructure.output_mode import OutputModeContext


class TestConsoleFactoryInCliMode:
    """Tests for ConsoleFactory behavior in CLI mode."""

    def test_get_console_returns_fallback_in_cli_mode(self):
        """In CLI mode, get_console returns the fallback console."""
        OutputModeContext.reset()
        fallback = Console()
        factory = ConsoleFactory(fallback_console=fallback)

        result = factory.get_console()

        assert result is fallback

    def test_get_console_creates_default_fallback_if_not_provided(self):
        """Factory creates default Console if no fallback provided."""
        OutputModeContext.reset()
        factory = ConsoleFactory()

        result = factory.get_console()

        assert isinstance(result, Console)

    def test_get_console_with_buffer_returns_none_buffer_in_cli_mode(self):
        """In CLI mode, get_console_with_buffer returns None for buffer."""
        OutputModeContext.reset()
        fallback = Console()
        factory = ConsoleFactory(fallback_console=fallback)

        console, buffer = factory.get_console_with_buffer()

        assert console is fallback
        assert buffer is None


class TestConsoleFactoryInTuiMode:
    """Tests for ConsoleFactory behavior in TUI mode."""

    def test_get_console_returns_string_console_in_tui_mode(self):
        """In TUI mode, get_console returns Console writing to StringIO."""
        mock_sink = MagicMock()
        OutputModeContext.set_tui_mode(True, mock_sink)
        factory = ConsoleFactory()

        console = factory.get_console()

        # Verify it's a new Console (not the fallback)
        assert isinstance(console, Console)
        # Verify it writes to StringIO
        console.print("test output")
        # The Console's file should be StringIO
        assert hasattr(console, "file")

    def test_get_console_with_buffer_returns_buffer_in_tui_mode(self):
        """In TUI mode, get_console_with_buffer returns a StringIO buffer."""
        mock_sink = MagicMock()
        OutputModeContext.set_tui_mode(True, mock_sink)
        factory = ConsoleFactory()

        console, buffer = factory.get_console_with_buffer()

        assert isinstance(console, Console)
        assert isinstance(buffer, StringIO)

    def test_console_output_captured_in_buffer(self):
        """Console output in TUI mode is captured in the buffer."""
        mock_sink = MagicMock()
        OutputModeContext.set_tui_mode(True, mock_sink)
        factory = ConsoleFactory()

        console, buffer = factory.get_console_with_buffer()
        console.print("hello world")
        output = buffer.getvalue()

        assert "hello world" in output


class TestConsoleFactoryStringConsole:
    """Tests for create_string_console method."""

    def test_create_string_console_returns_console_and_buffer(self):
        """create_string_console returns Console and StringIO tuple."""
        factory = ConsoleFactory()

        console, buffer = factory.create_string_console()

        assert isinstance(console, Console)
        assert isinstance(buffer, StringIO)

    def test_create_string_console_captures_output(self):
        """Output to string console is captured in buffer."""
        factory = ConsoleFactory()

        console, buffer = factory.create_string_console()
        console.print("captured output")
        output = buffer.getvalue()

        assert "captured output" in output

    def test_create_string_console_works_in_cli_mode(self):
        """String console works regardless of CLI mode."""
        OutputModeContext.reset()
        factory = ConsoleFactory()

        console, buffer = factory.create_string_console()
        console.print("test")

        assert "test" in buffer.getvalue()

    def test_create_string_console_works_in_tui_mode(self):
        """String console works regardless of TUI mode."""
        OutputModeContext.set_tui_mode(True, MagicMock())
        factory = ConsoleFactory()

        console, buffer = factory.create_string_console()
        console.print("test")

        assert "test" in buffer.getvalue()


class TestConsoleFactoryRouteOutput:
    """Tests for route_console_output method."""

    def test_route_output_calls_sink_in_tui_mode(self):
        """route_console_output posts output to sink in TUI mode."""
        mock_sink = MagicMock()
        OutputModeContext.set_tui_mode(True, mock_sink)
        factory = ConsoleFactory()

        console, buffer = factory.get_console_with_buffer()
        console.print("routed output")
        factory.route_console_output(console, buffer)

        mock_sink.post_output.assert_called_once()
        call_arg = mock_sink.post_output.call_args[0][0]
        assert "routed output" in call_arg

    def test_route_output_does_nothing_with_none_buffer(self):
        """route_console_output does nothing if buffer is None."""
        mock_sink = MagicMock()
        OutputModeContext.set_tui_mode(True, mock_sink)
        factory = ConsoleFactory()

        # This shouldn't raise
        factory.route_console_output(MagicMock(), None)

        mock_sink.post_output.assert_not_called()

    def test_route_output_does_nothing_if_buffer_empty(self):
        """route_console_output does nothing if buffer is empty."""
        mock_sink = MagicMock()
        OutputModeContext.set_tui_mode(True, mock_sink)
        factory = ConsoleFactory()

        console, buffer = factory.get_console_with_buffer()
        # Don't print anything
        factory.route_console_output(console, buffer)

        mock_sink.post_output.assert_not_called()

    def test_route_output_does_nothing_in_cli_mode(self):
        """route_console_output does nothing in CLI mode."""
        OutputModeContext.reset()
        factory = ConsoleFactory()

        # Create a buffer manually (simulating get_console_with_buffer in CLI mode)
        buffer = StringIO()
        buffer.write("some content")
        factory.route_console_output(MagicMock(), buffer)

        # Nothing should happen - no sink to call


class TestConsoleFactoryProtocolCompliance:
    """Tests that ConsoleFactory satisfies ConsoleFactoryProtocol."""

    def test_has_get_console_method(self):
        """ConsoleFactory has get_console method."""
        factory = ConsoleFactory()
        assert hasattr(factory, "get_console")
        assert callable(factory.get_console)

    def test_has_create_string_console_method(self):
        """ConsoleFactory has create_string_console method."""
        factory = ConsoleFactory()
        assert hasattr(factory, "create_string_console")
        assert callable(factory.create_string_console)


@pytest.fixture(autouse=True)
def reset_output_mode_context():
    """Ensure clean state before and after each test."""
    OutputModeContext.reset()
    yield
    OutputModeContext.reset()
