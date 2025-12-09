"""
Tests for CLI theme integration (Phase 4).

Verifies that CLI components properly accept and use theme parameters.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from io import StringIO
from rich.console import Console

from scrappy.infrastructure.theme import (
    ThemeProtocol,
    ScrappyTheme,
    LightTheme,
    NoColorTheme,
    DEFAULT_THEME,
)
from scrappy.cli.display_rich import (
    show_help_table,
    show_status_rich,
    show_rate_limits_rich,
    show_plan_tree,
)
from scrappy.cli.interactive_banner import display_banner, render_welcome_banner
from scrappy.cli.rich_dashboard import RichDashboard
from scrappy.cli.task_router_handler import CLITaskRouterHandler
from scrappy.cli.output_bridge import (
    OutputBridge,
    ConsoleOutputBridge,
    create_output_bridge,
)
from scrappy.cli.unified_io import UnifiedIO


class TestDisplayRichThemeIntegration:
    """Tests for display_rich.py theme integration."""

    def setup_method(self):
        """Create test fixtures."""
        self.io = Mock()
        self.io.secho = Mock()
        self.io.echo = Mock()
        self.io.table = Mock()
        self.io.panel = Mock()
        self.theme = ScrappyTheme()
        self.light_theme = LightTheme()
        self.io.theme = self.theme  # Functions access theme via io.theme



    def test_show_status_rich_uses_theme_primary(self):
        """show_status_rich uses theme.primary for panel border."""
        orchestrator = Mock()
        orchestrator.status.return_value = {
            "orchestrator_brain": "anthropic",
            "available_providers": ["anthropic", "openai"],
            "tasks_executed": 5,
        }
        from datetime import datetime

        show_status_rich(self.io, orchestrator, datetime.now())
        self.io.panel.assert_called_once()
        _, kwargs = self.io.panel.call_args
        assert kwargs["border_style"] == self.theme.primary

    def test_show_status_rich_with_light_theme(self):
        """show_status_rich uses light theme colors correctly."""
        orchestrator = Mock()
        orchestrator.status.return_value = {
            "orchestrator_brain": "anthropic",
            "available_providers": ["anthropic"],
            "tasks_executed": 0,
        }
        from datetime import datetime

        self.io.theme = self.light_theme  # Switch to light theme
        show_status_rich(self.io, orchestrator, datetime.now())
        _, kwargs = self.io.panel.call_args
        assert kwargs["border_style"] == self.light_theme.primary

    def test_show_rate_limits_rich_uses_theme_warning(self):
        """show_rate_limits_rich uses theme.warning for empty data message."""
        show_rate_limits_rich(self.io, {})
        self.io.secho.assert_called_once()
        _, kwargs = self.io.secho.call_args
        assert kwargs["fg"] == self.theme.warning

    def test_show_plan_tree_uses_theme_warning_for_empty(self):
        """show_plan_tree uses theme.warning when no plan exists."""
        show_plan_tree(self.io, {})
        self.io.secho.assert_called_once()
        _, kwargs = self.io.secho.call_args
        assert kwargs["fg"] == self.theme.warning


class TestInteractiveBannerThemeIntegration:
    """Tests for interactive_banner.py theme integration."""

    def setup_method(self):
        """Create test fixtures."""
        self.mock_sink = Mock()
        self.mock_sink.post_output = Mock()
        self.mock_sink.post_renderable = Mock()
        self.theme = ScrappyTheme()

        # Should not raise



class TestRichDashboardThemeIntegration:
    """Tests for rich_dashboard.py theme integration."""

    def test_accepts_theme_parameter(self):
        """RichDashboard accepts theme parameter in constructor."""
        theme = ScrappyTheme()
        dashboard = RichDashboard(theme=theme)
        assert dashboard._theme == theme

    def test_uses_default_theme_when_not_provided(self):
        """RichDashboard uses DEFAULT_THEME when theme not provided."""
        dashboard = RichDashboard()
        assert dashboard._theme == DEFAULT_THEME

    def test_state_styles_use_theme_colors(self):
        """Dashboard state styles use theme colors."""
        theme = ScrappyTheme()
        dashboard = RichDashboard(theme=theme)

        assert dashboard._state_styles["thinking"] == theme.accent
        assert dashboard._state_styles["executing"] == theme.success
        assert dashboard._state_styles["scanning"] == theme.primary

    def test_state_styles_with_light_theme(self):
        """Dashboard state styles use light theme colors correctly."""
        theme = LightTheme()
        dashboard = RichDashboard(theme=theme)

        assert dashboard._state_styles["thinking"] == theme.accent
        assert dashboard._state_styles["executing"] == theme.success
        assert dashboard._state_styles["scanning"] == theme.primary


class TestTaskRouterHandlerThemeIntegration:
    """Tests for task_router_handler.py theme integration."""

    def setup_method(self):
        """Create test fixtures."""
        self.orchestrator = Mock()
        self.io = Mock()
        self.io.secho = Mock()
        self.io.echo = Mock()
        self.io.style = Mock(return_value="styled")
        self.theme = ScrappyTheme()

    def test_accepts_theme_parameter(self):
        """CLITaskRouterHandler accepts theme parameter."""
        handler = CLITaskRouterHandler(
            orchestrator=self.orchestrator,
            io=self.io,
            theme=self.theme,
        )
        assert handler._theme == self.theme

    def test_uses_default_theme_when_not_provided(self):
        """CLITaskRouterHandler uses DEFAULT_THEME when not provided."""
        handler = CLITaskRouterHandler(
            orchestrator=self.orchestrator,
            io=self.io,
        )
        assert handler._theme == DEFAULT_THEME

    def test_task_colors_use_theme(self):
        """Task type colors use theme values."""
        handler = CLITaskRouterHandler(
            orchestrator=self.orchestrator,
            io=self.io,
            theme=self.theme,
        )

        assert handler._task_colors["direct_command"] == self.theme.success
        assert handler._task_colors["code_generation"] == self.theme.accent
        assert handler._task_colors["research"] == self.theme.primary
        assert handler._task_colors["conversation"] == self.theme.info

    def test_handle_route_history_empty_uses_theme_warning(self):
        """handle_route_history uses theme.warning for empty history."""
        handler = CLITaskRouterHandler(
            orchestrator=self.orchestrator,
            io=self.io,
            theme=self.theme,
        )

        handler.handle_route_history()
        self.io.secho.assert_called_once()
        _, kwargs = self.io.secho.call_args
        assert kwargs["fg"] == self.theme.warning


class TestOutputBridgeThemeIntegration:
    """Tests for output_bridge.py theme integration."""

    def setup_method(self):
        """Create test fixtures."""
        self.theme = ScrappyTheme()
        self.light_theme = LightTheme()

    def test_output_bridge_accepts_theme(self):
        """OutputBridge accepts theme parameter."""
        sink = Mock()
        bridge = OutputBridge(sink, theme=self.theme)
        assert bridge._theme == self.theme

    def test_output_bridge_uses_default_theme(self):
        """OutputBridge uses DEFAULT_THEME when not provided."""
        sink = Mock()
        bridge = OutputBridge(sink)
        assert bridge._theme == DEFAULT_THEME

    def test_console_output_bridge_accepts_theme(self):
        """ConsoleOutputBridge accepts theme parameter."""
        bridge = ConsoleOutputBridge(theme=self.theme)
        assert bridge._theme == self.theme

    def test_console_output_bridge_uses_default_theme(self):
        """ConsoleOutputBridge uses DEFAULT_THEME when not provided."""
        bridge = ConsoleOutputBridge()
        assert bridge._theme == DEFAULT_THEME

    def test_create_output_bridge_passes_theme(self):
        """create_output_bridge passes theme to created bridge."""
        # TUI mode
        sink = Mock()
        bridge = create_output_bridge(output_sink=sink, theme=self.theme)
        assert bridge._theme == self.theme

        # CLI mode
        bridge = create_output_bridge(theme=self.light_theme)
        assert bridge._theme == self.light_theme

    def test_output_bridge_warn_uses_theme_warning(self):
        """OutputBridge.warn uses theme.warning color."""
        sink = Mock()
        sink.post_renderable = Mock()
        bridge = OutputBridge(sink, theme=self.theme)

        bridge.warn("test warning")

        sink.post_renderable.assert_called_once()
        text = sink.post_renderable.call_args[0][0]
        assert text.style == self.theme.warning

    def test_output_bridge_error_uses_theme_error(self):
        """OutputBridge.error uses theme.error color."""
        sink = Mock()
        sink.post_renderable = Mock()
        bridge = OutputBridge(sink, theme=self.theme)

        bridge.error("test error")

        sink.post_renderable.assert_called_once()
        text = sink.post_renderable.call_args[0][0]
        assert self.theme.error in text.style

    def test_output_bridge_success_uses_theme_success(self):
        """OutputBridge.success uses theme.success color."""
        sink = Mock()
        sink.post_renderable = Mock()
        bridge = OutputBridge(sink, theme=self.theme)

        bridge.success("test success")

        sink.post_renderable.assert_called_once()
        text = sink.post_renderable.call_args[0][0]
        assert text.style == self.theme.success


class TestUnifiedIOThemeIntegration:
    """Tests for unified_io.py theme integration."""

    def setup_method(self):
        """Create test fixtures."""
        self.theme = ScrappyTheme()
        self.light_theme = LightTheme()

    def test_accepts_theme_parameter(self):
        """UnifiedIO accepts theme parameter."""
        io = UnifiedIO(theme=self.theme)
        assert io._theme == self.theme

    def test_uses_default_theme_when_not_provided(self):
        """UnifiedIO uses DEFAULT_THEME when not provided."""
        io = UnifiedIO()
        assert io._theme == DEFAULT_THEME

    def test_theme_property_returns_theme(self):
        """UnifiedIO.theme property returns the theme."""
        io = UnifiedIO(theme=self.theme)
        assert io.theme == self.theme




class TestNoColorThemeIntegration:
    """Tests that NoColorTheme works with CLI components."""

    def setup_method(self):
        """Create test fixtures."""
        self.theme = NoColorTheme()

    def test_unified_io_with_no_color_theme(self):
        """UnifiedIO works with NoColorTheme."""
        io = UnifiedIO(theme=self.theme)
        assert io.theme == self.theme
        assert io.theme.primary == ""

    def test_rich_dashboard_with_no_color_theme(self):
        """RichDashboard works with NoColorTheme."""
        dashboard = RichDashboard(theme=self.theme)
        assert dashboard._theme == self.theme
        # State styles should have empty string for scanning
        assert dashboard._state_styles["scanning"] == ""

    def test_output_bridge_with_no_color_theme(self):
        """OutputBridge works with NoColorTheme."""
        sink = Mock()
        sink.post_renderable = Mock()
        bridge = OutputBridge(sink, theme=self.theme)

        bridge.warn("test")
        text = sink.post_renderable.call_args[0][0]
        assert text.style == ""  # Empty style for NoColorTheme


class TestThemePropagation:
    """Tests that theme is properly propagated through component creation."""

    def test_task_router_handler_propagates_theme_to_task_colors(self):
        """Theme is propagated to task type color mapping."""
        theme = LightTheme()
        orchestrator = Mock()
        io = Mock()
        io.secho = Mock()
        io.echo = Mock()
        io.style = Mock(return_value="styled")

        handler = CLITaskRouterHandler(
            orchestrator=orchestrator,
            io=io,
            theme=theme,
        )

        # Verify task colors match light theme (hex codes)
        assert handler._task_colors["direct_command"] == "#00ff00"  # theme.success
        assert handler._task_colors["code_generation"] == "#ff00ff"  # theme.accent
        assert handler._task_colors["research"] == "#0000ff"  # theme.primary
        assert handler._task_colors["conversation"] == "#00ffff"  # theme.info
