"""
Tests for OutputModeContext.

Tests the context-aware output mode tracking system that determines
whether output should route through TUI or CLI.
"""

import pytest
from unittest.mock import MagicMock

from src.infrastructure.output_mode import OutputModeContext


class TestOutputModeContextDefaults:
    """Tests for default state behavior."""

    def test_default_is_cli_mode(self):
        """OutputModeContext defaults to CLI mode (not TUI)."""
        OutputModeContext.reset()
        assert OutputModeContext.is_tui_mode() is False

    def test_default_output_sink_is_none(self):
        """OutputModeContext has no sink by default."""
        OutputModeContext.reset()
        assert OutputModeContext.get_output_sink() is None


class TestOutputModeContextSetTuiMode:
    """Tests for set_tui_mode behavior."""

    def test_set_tui_mode_true_enables_tui_mode(self):
        """Setting TUI mode to True enables TUI mode."""
        OutputModeContext.reset()
        mock_sink = MagicMock()

        OutputModeContext.set_tui_mode(True, mock_sink)

        assert OutputModeContext.is_tui_mode() is True

    def test_set_tui_mode_true_stores_sink(self):
        """Setting TUI mode stores the output sink."""
        OutputModeContext.reset()
        mock_sink = MagicMock()

        OutputModeContext.set_tui_mode(True, mock_sink)

        assert OutputModeContext.get_output_sink() is mock_sink

    def test_set_tui_mode_false_disables_tui_mode(self):
        """Setting TUI mode to False returns to CLI mode."""
        OutputModeContext.reset()
        mock_sink = MagicMock()
        OutputModeContext.set_tui_mode(True, mock_sink)

        OutputModeContext.set_tui_mode(False)

        assert OutputModeContext.is_tui_mode() is False

    def test_set_tui_mode_false_clears_sink(self):
        """Setting TUI mode to False clears the output sink."""
        OutputModeContext.reset()
        mock_sink = MagicMock()
        OutputModeContext.set_tui_mode(True, mock_sink)

        OutputModeContext.set_tui_mode(False)

        assert OutputModeContext.get_output_sink() is None

    def test_set_tui_mode_without_sink_still_enables(self):
        """TUI mode can be enabled without providing a sink."""
        OutputModeContext.reset()

        OutputModeContext.set_tui_mode(True)

        assert OutputModeContext.is_tui_mode() is True
        assert OutputModeContext.get_output_sink() is None


class TestOutputModeContextReset:
    """Tests for reset behavior."""

    def test_reset_clears_tui_mode(self):
        """Reset returns to CLI mode."""
        OutputModeContext.set_tui_mode(True, MagicMock())

        OutputModeContext.reset()

        assert OutputModeContext.is_tui_mode() is False

    def test_reset_clears_sink(self):
        """Reset clears the output sink."""
        OutputModeContext.set_tui_mode(True, MagicMock())

        OutputModeContext.reset()

        assert OutputModeContext.get_output_sink() is None


class TestOutputModeContextStateTransitions:
    """Tests for state transitions."""

    def test_can_toggle_tui_mode_multiple_times(self):
        """TUI mode can be toggled on and off repeatedly."""
        OutputModeContext.reset()
        mock_sink1 = MagicMock()
        mock_sink2 = MagicMock()

        # Enable
        OutputModeContext.set_tui_mode(True, mock_sink1)
        assert OutputModeContext.is_tui_mode() is True
        assert OutputModeContext.get_output_sink() is mock_sink1

        # Disable
        OutputModeContext.set_tui_mode(False)
        assert OutputModeContext.is_tui_mode() is False
        assert OutputModeContext.get_output_sink() is None

        # Re-enable with different sink
        OutputModeContext.set_tui_mode(True, mock_sink2)
        assert OutputModeContext.is_tui_mode() is True
        assert OutputModeContext.get_output_sink() is mock_sink2

    def test_replacing_sink_while_tui_mode_active(self):
        """Sink can be replaced while TUI mode remains active."""
        OutputModeContext.reset()
        mock_sink1 = MagicMock()
        mock_sink2 = MagicMock()

        OutputModeContext.set_tui_mode(True, mock_sink1)
        OutputModeContext.set_tui_mode(True, mock_sink2)

        assert OutputModeContext.is_tui_mode() is True
        assert OutputModeContext.get_output_sink() is mock_sink2


@pytest.fixture(autouse=True)
def reset_output_mode_context():
    """Ensure clean state before and after each test."""
    OutputModeContext.reset()
    yield
    OutputModeContext.reset()
