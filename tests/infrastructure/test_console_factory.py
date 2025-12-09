"""
Tests for ConsoleFactory.

Tests the mode-aware Console factory that returns appropriate
Console instances based on TUI/CLI mode.
"""

import pytest
from unittest.mock import MagicMock
from io import StringIO

from rich.console import Console

from scrappy.infrastructure.console_factory import ConsoleFactory
from scrappy.infrastructure.output_mode import OutputModeContext


class TestConsoleFactoryInCliMode:
    """Tests for ConsoleFactory behavior in CLI mode."""

    def test_get_console_returns_fallback_in_cli_mode(self):
        """In CLI mode, get_console returns the fallback console."""
        OutputModeContext.reset()
        fallback = Console()
        factory = ConsoleFactory(fallback_console=fallback)

        result = factory.get_console()

        assert result is fallback


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




        # Nothing should happen - no sink to call


class TestConsoleFactoryProtocolCompliance:
    """Tests that ConsoleFactory satisfies ConsoleFactoryProtocol."""




@pytest.fixture(autouse=True)
def reset_output_mode_context():
    """Ensure clean state before and after each test."""
    OutputModeContext.reset()
    yield
    OutputModeContext.reset()
