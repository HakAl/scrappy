"""
Tests for AgentUI theme integration.

Verifies that AgentUI correctly uses theme colors for display.
"""

from unittest.mock import Mock

from scrappy.agent.ui import AgentUI
from scrappy.infrastructure.theme import (
    DEFAULT_THEME,
    LightTheme,
    NoColorTheme,
)
from tests.helpers import MockIO


class TestAgentUIThemeIntegration:
    """Tests for AgentUI theme integration."""

    def test_default_theme_is_used_when_none_provided(self):
        """AgentUI uses DEFAULT_THEME when no theme provided."""
        io = MockIO()
        ui = AgentUI(io)
        assert ui._theme is DEFAULT_THEME

    def test_custom_theme_is_used_when_provided(self):
        """AgentUI uses provided theme instance."""
        io = MockIO()
        light_theme = LightTheme()
        ui = AgentUI(io, theme=light_theme)
        assert ui._theme is light_theme


class TestAgentUIShowThinking:
    """Tests for show_thinking theme colors."""

    def test_show_thinking_uses_theme_info_for_panel(self):
        """show_thinking uses theme.info for panel border (verbose mode)."""
        io = MockIO()
        ui = AgentUI(io, verbose=True)
        ui.show_thinking("Processing...")

        assert len(io.panel_calls) == 1
        content, title, border_style = io.panel_calls[0]
        assert content == "Processing..."
        assert title == "Thinking"
        assert border_style == DEFAULT_THEME.info

    def test_show_thinking_uses_theme_info_for_secho_fallback(self):
        """show_thinking uses theme.info for secho when panel not available (verbose mode)."""
        io = Mock()
        io.secho = Mock()
        # Remove panel attribute to trigger fallback
        del io.panel

        ui = AgentUI(io, verbose=True)
        ui.show_thinking("Processing...")

        io.secho.assert_called_once()
        call_args = io.secho.call_args
        assert call_args.kwargs.get("fg") == DEFAULT_THEME.info

    def test_show_thinking_with_light_theme(self):
        """show_thinking uses light theme info color (verbose mode)."""
        io = MockIO()
        light_theme = LightTheme()
        ui = AgentUI(io, theme=light_theme, verbose=True)
        ui.show_thinking("Processing...")

        assert len(io.panel_calls) == 1
        _, _, border_style = io.panel_calls[0]
        assert border_style == light_theme.info

    def test_show_thinking_skips_empty_text(self):
        """show_thinking does nothing for empty text."""
        io = MockIO()
        ui = AgentUI(io)
        ui.show_thinking("")
        ui.show_thinking("   ")

        assert len(io.panel_calls) == 0
        assert len(io.secho_calls) == 0


class TestAgentUIShowToolRequest:
    """Tests for show_tool_request theme colors."""

    def test_show_tool_request_uses_theme_primary_for_secho(self):
        """show_tool_request uses theme.primary when no table (verbose mode)."""
        io = Mock()
        io.secho = Mock()
        io.echo = Mock()
        # Remove table to trigger secho path
        del io.table

        ui = AgentUI(io, verbose=True)
        ui.show_tool_request("read_file", {"path": "test.py"})

        io.secho.assert_called_once()
        call_args = io.secho.call_args
        assert call_args.kwargs.get("fg") == DEFAULT_THEME.primary
        assert call_args.kwargs.get("bold") is True

    def test_show_tool_request_compact_mode(self):
        """show_tool_request shows one-line summary in compact mode."""
        io = Mock()
        io.secho = Mock()

        ui = AgentUI(io, verbose=False)
        ui.show_tool_request("read_file", {"file_path": "test.py"})

        io.secho.assert_called_once()
        call_args = io.secho.call_args
        assert "[Step 1]" in call_args.args[0]
        assert "read_file" in call_args.args[0]
        assert "test.py" in call_args.args[0]
        assert call_args.kwargs.get("fg") == DEFAULT_THEME.primary


class TestAgentUIShowCommand:
    """Tests for show_command theme colors."""

    def test_show_command_uses_theme_accent_for_secho(self):
        """show_command uses theme.accent when no syntax highlighting."""
        io = Mock()
        io.secho = Mock()
        # Remove syntax to trigger secho path
        del io.syntax

        ui = AgentUI(io)
        ui.show_command("ls -la")

        io.secho.assert_called_once()
        call_args = io.secho.call_args
        assert call_args.kwargs.get("fg") == DEFAULT_THEME.accent


class TestAgentUIShowError:
    """Tests for show_error theme colors."""

    def test_show_error_uses_theme_error_for_panel(self):
        """show_error uses theme.error for panel border."""
        io = MockIO()
        ui = AgentUI(io)
        ui.show_error("Something failed")

        assert len(io.panel_calls) == 1
        content, title, border_style = io.panel_calls[0]
        assert content == "Something failed"
        assert title == "Error"
        assert border_style == DEFAULT_THEME.error

    def test_show_error_uses_theme_error_for_secho_fallback(self):
        """show_error uses theme.error for secho when panel not available."""
        io = Mock()
        io.secho = Mock()
        del io.panel

        ui = AgentUI(io)
        ui.show_error("Something failed")

        io.secho.assert_called_once()
        call_args = io.secho.call_args
        assert call_args.kwargs.get("fg") == DEFAULT_THEME.error


class TestAgentUIShowResult:
    """Tests for show_result theme colors."""

    def test_show_result_uses_theme_success_for_panel(self):
        """show_result uses theme.success for success panel (verbose mode)."""
        io = MockIO()
        ui = AgentUI(io, verbose=True)
        ui.show_result("Operation completed", is_error=False)

        assert len(io.panel_calls) == 1
        _, _, border_style = io.panel_calls[0]
        assert border_style == DEFAULT_THEME.success

    def test_show_result_uses_theme_error_for_error_panel(self):
        """show_result uses theme.error for error panel (errors always shown)."""
        io = MockIO()
        ui = AgentUI(io)  # Compact mode, but errors always shown
        ui.show_result("Operation failed", is_error=True)

        assert len(io.panel_calls) == 1
        _, _, border_style = io.panel_calls[0]
        assert border_style == DEFAULT_THEME.error

    def test_show_result_uses_theme_colors_for_secho_fallback(self):
        """show_result uses theme colors for secho fallback (verbose mode)."""
        io = Mock()
        io.secho = Mock()
        del io.panel

        ui = AgentUI(io, verbose=True)
        ui.show_result("Success", is_error=False)

        call_args = io.secho.call_args
        assert call_args.kwargs.get("fg") == DEFAULT_THEME.success

    def test_show_result_compact_mode(self):
        """show_result shows compact summary in compact mode."""
        io = Mock()
        io.secho = Mock()

        ui = AgentUI(io, verbose=False)
        ui.show_result("Line 1\nLine 2\nLine 3", is_error=False)

        io.secho.assert_called_once()
        call_args = io.secho.call_args
        assert "done" in call_args.args[0]
        assert "3 lines" in call_args.args[0]


class TestAgentUIShowWarning:
    """Tests for show_warning theme colors."""

    def test_show_warning_uses_theme_warning_for_panel(self):
        """show_warning uses theme.warning for panel border (verbose mode)."""
        io = MockIO()
        ui = AgentUI(io, verbose=True)
        ui.show_warning("Be careful")

        assert len(io.panel_calls) == 1
        content, title, border_style = io.panel_calls[0]
        assert content == "Be careful"
        assert title == "Warning"
        assert border_style == DEFAULT_THEME.warning

    def test_show_warning_uses_theme_warning_for_secho_fallback(self):
        """show_warning uses theme.warning for secho in compact mode."""
        io = Mock()
        io.secho = Mock()

        ui = AgentUI(io, verbose=False)
        ui.show_warning("Be careful")

        io.secho.assert_called_once()
        call_args = io.secho.call_args
        assert call_args.kwargs.get("fg") == DEFAULT_THEME.warning

    def test_show_warning_compact_mode(self):
        """show_warning shows one-line summary in compact mode."""
        io = Mock()
        io.secho = Mock()

        ui = AgentUI(io, verbose=False)
        ui.show_warning("This is a warning message")

        io.secho.assert_called_once()
        call_args = io.secho.call_args
        assert "[!]" in call_args.args[0]
        assert "warning message" in call_args.args[0].lower()


class TestAgentUIShowProgress:
    """Tests for show_progress theme colors."""

    def test_show_progress_uses_theme_primary(self):
        """show_progress uses theme.primary for color."""
        io = MockIO()
        ui = AgentUI(io)
        ui.show_progress("Working...")

        assert len(io.secho_calls) == 1
        message, kwargs = io.secho_calls[0]
        assert message == "Working..."
        assert kwargs.get("fg") == DEFAULT_THEME.primary


class TestAgentUIShowProviderStatus:
    """Tests for show_provider_status theme colors."""

    def test_show_provider_status_uses_theme_primary_default(self):
        """show_provider_status uses theme.primary when no color specified."""
        io = MockIO()
        ui = AgentUI(io)
        ui.show_provider_status("openai", "Connected")

        assert len(io.secho_calls) == 1
        message, kwargs = io.secho_calls[0]
        assert "[openai] Connected" in message
        assert kwargs.get("fg") == DEFAULT_THEME.primary

    def test_show_provider_status_respects_custom_color(self):
        """show_provider_status uses provided color when specified."""
        io = MockIO()
        ui = AgentUI(io)
        ui.show_provider_status("openai", "Error", color="red")

        assert len(io.secho_calls) == 1
        _, kwargs = io.secho_calls[0]
        assert kwargs.get("fg") == "red"


class TestAgentUILightTheme:
    """Tests for AgentUI with LightTheme."""

    def test_all_methods_use_light_theme_colors(self):
        """All AgentUI methods use light theme colors correctly (verbose mode)."""
        io = MockIO()
        light_theme = LightTheme()
        ui = AgentUI(io, theme=light_theme, verbose=True)

        # Test thinking (uses info)
        ui.show_thinking("Thinking...")
        assert io.panel_calls[-1][2] == light_theme.info

        # Test error (uses error)
        ui.show_error("Error")
        assert io.panel_calls[-1][2] == light_theme.error

        # Test warning (uses warning)
        ui.show_warning("Warning")
        assert io.panel_calls[-1][2] == light_theme.warning

        # Test result success (uses success)
        ui.show_result("Success", is_error=False)
        assert io.panel_calls[-1][2] == light_theme.success

        # Test progress (uses primary)
        ui.show_progress("Progress...")
        assert io.secho_calls[-1][1].get("fg") == light_theme.primary


class TestAgentUINoColorTheme:
    """Tests for AgentUI with NoColorTheme."""

    def test_works_with_no_color_theme(self):
        """AgentUI works with NoColorTheme (verbose mode)."""
        io = MockIO()
        no_color = NoColorTheme()
        ui = AgentUI(io, theme=no_color, verbose=True)

        # Should not raise errors even with empty color strings
        ui.show_thinking("Thinking...")
        ui.show_error("Error")
        ui.show_warning("Warning")
        ui.show_result("Success", is_error=False)
        ui.show_progress("Progress...")
        ui.show_provider_status("test", "Message")

        # All calls should have gone through (verbose mode)
        assert len(io.panel_calls) == 4
        assert len(io.secho_calls) == 2
