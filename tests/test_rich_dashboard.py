"""Tests for Rich dashboard component.

TDD tests for the live dashboard that displays:
- Agent state (Scanning, Thinking, Executing)
- Thought process (LLM reasoning)
- Terminal output (command output)
- Context info (active files, tokens)
"""

import pytest
from unittest.mock import MagicMock, patch
from rich.console import Console
from rich.layout import 
from rich.panel import 


class TestDashboardCreation:
    """Tests for dashboard layout creation."""

    @pytest.mark.unit
    def test_dashboard_creates_layout_with_required_panels(self):
        """Dashboard should create layout with all four required panels."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()
        # Should have main layout with all panel names accessible
        panel_names = dashboard.get_panel_names()
        assert "agent_state" in panel_names
        assert "thought_process" in panel_names
        assert "terminal" in panel_names
        assert "context" in panel_names

    @pytest.mark.unit

    @pytest.mark.unit
    def test_dashboard_initializes_with_idle_state(self):
        """Dashboard should start in idle state."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        assert dashboard.get_state() == "idle"

    @pytest.mark.unit
    def test_dashboard_accepts_custom_console(self):
        """Dashboard should accept a custom Console for testing."""
        from src.cli.rich_dashboard import RichDashboard

        custom_console = Console(force_terminal=True, width=80)
        dashboard = RichDashboard(console=custom_console)

        assert dashboard.console is custom_console

    @pytest.mark.unit

    @pytest.mark.unit
    def test_dashboard_panels_have_correct_titles(self):
        """Each panel should have its designated title."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        assert dashboard.get_panel_title("agent_state") == "Agent State"
        assert dashboard.get_panel_title("thought_process") == "Thought Process"
        assert dashboard.get_panel_title("terminal") == "Terminal"
        assert dashboard.get_panel_title("context") == "Context"
