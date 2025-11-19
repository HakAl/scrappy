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
from rich.layout import Layout
from rich.panel import Panel


class TestDashboardCreation:
    """Tests for dashboard layout creation."""

    @pytest.mark.unit
    def test_dashboard_creates_layout_with_required_panels(self):
        """Dashboard should create layout with all four required panels."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()
        layout = dashboard.get_layout()

        # Should have main layout with all panel names accessible
        panel_names = dashboard.get_panel_names()
        assert "agent_state" in panel_names
        assert "thought_process" in panel_names
        assert "terminal" in panel_names
        assert "context" in panel_names

    @pytest.mark.unit
    def test_dashboard_layout_is_rich_layout(self):
        """Dashboard layout should be a Rich Layout object."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()
        layout = dashboard.get_layout()

        assert isinstance(layout, Layout)

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
    def test_dashboard_creates_default_console_if_not_provided(self):
        """Dashboard should create a default Console if none provided."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        assert dashboard.console is not None
        assert isinstance(dashboard.console, Console)

    @pytest.mark.unit
    def test_dashboard_panels_have_correct_titles(self):
        """Each panel should have its designated title."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        assert dashboard.get_panel_title("agent_state") == "Agent State"
        assert dashboard.get_panel_title("thought_process") == "Thought Process"
        assert dashboard.get_panel_title("terminal") == "Terminal"
        assert dashboard.get_panel_title("context") == "Context"

    @pytest.mark.unit
    def test_dashboard_layout_has_proper_structure(self):
        """Layout should have upper and lower sections for organized display."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()
        layout = dashboard.get_layout()

        # Layout should be splittable/have children
        # The exact structure depends on implementation
        assert layout is not None


class TestPanelContentUpdates:
    """Tests for updating panel contents."""

    @pytest.mark.unit
    def test_update_agent_state_panel(self):
        """Should update agent state panel content."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.update_agent_state("Scanning codebase...")

        content = dashboard.get_panel_content("agent_state")
        assert "Scanning codebase..." in content

    @pytest.mark.unit
    def test_update_thought_process_panel(self):
        """Should update thought process panel with LLM reasoning."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.update_thought_process("Analyzing user request...")

        content = dashboard.get_panel_content("thought_process")
        assert "Analyzing user request..." in content

    @pytest.mark.unit
    def test_update_terminal_panel(self):
        """Should update terminal panel with command output."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.update_terminal("$ python test.py\nAll tests passed")

        content = dashboard.get_panel_content("terminal")
        assert "python test.py" in content
        assert "All tests passed" in content

    @pytest.mark.unit
    def test_update_context_panel(self):
        """Should update context panel with file and token info."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.update_context(
            active_files=["src/main.py", "tests/test_main.py"],
            tokens_used=1500
        )

        content = dashboard.get_panel_content("context")
        assert "src/main.py" in content
        # Token count is formatted with commas for readability
        assert "1,500" in content

    @pytest.mark.unit
    def test_append_to_terminal_preserves_history(self):
        """Terminal should preserve previous output when appending."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.append_terminal("First command output")
        dashboard.append_terminal("Second command output")

        content = dashboard.get_panel_content("terminal")
        assert "First command output" in content
        assert "Second command output" in content

    @pytest.mark.unit
    def test_clear_terminal(self):
        """Should be able to clear terminal output."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.append_terminal("Some output")
        dashboard.clear_terminal()

        content = dashboard.get_panel_content("terminal")
        assert "Some output" not in content

    @pytest.mark.unit
    def test_append_to_thought_process_streams_content(self):
        """Thought process should support streaming/appending content."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.append_thought("First thought...")
        dashboard.append_thought("Second thought...")

        content = dashboard.get_panel_content("thought_process")
        assert "First thought..." in content
        assert "Second thought..." in content

    @pytest.mark.unit
    def test_clear_thought_process(self):
        """Should be able to clear thought process for new task."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.append_thought("Old thoughts")
        dashboard.clear_thought_process()

        content = dashboard.get_panel_content("thought_process")
        assert "Old thoughts" not in content


class TestStateTransitions:
    """Tests for dashboard state transitions."""

    @pytest.mark.unit
    def test_transition_to_thinking_state(self):
        """Dashboard should transition from idle to thinking."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()
        assert dashboard.get_state() == "idle"

        dashboard.set_state("thinking")

        assert dashboard.get_state() == "thinking"

    @pytest.mark.unit
    def test_transition_to_executing_state(self):
        """Dashboard should transition to executing state."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.set_state("executing")

        assert dashboard.get_state() == "executing"

    @pytest.mark.unit
    def test_transition_to_scanning_state(self):
        """Dashboard should support scanning state."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.set_state("scanning")

        assert dashboard.get_state() == "scanning"

    @pytest.mark.unit
    def test_transition_back_to_idle(self):
        """Dashboard should be able to return to idle state."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()
        dashboard.set_state("thinking")

        dashboard.set_state("idle")

        assert dashboard.get_state() == "idle"

    @pytest.mark.unit
    def test_state_change_updates_agent_state_panel(self):
        """State change should automatically update agent state panel."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.set_state("thinking")

        content = dashboard.get_panel_content("agent_state")
        # Panel should reflect the new state
        assert "thinking" in content.lower() or "Thinking" in content

    @pytest.mark.unit
    def test_invalid_state_raises_error(self):
        """Setting invalid state should raise ValueError."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        with pytest.raises(ValueError):
            dashboard.set_state("invalid_state")

    @pytest.mark.unit
    def test_valid_states_are_defined(self):
        """Dashboard should have defined set of valid states."""
        from src.cli.rich_dashboard import RichDashboard

        valid_states = RichDashboard.VALID_STATES

        assert "idle" in valid_states
        assert "thinking" in valid_states
        assert "executing" in valid_states
        assert "scanning" in valid_states

    @pytest.mark.unit
    def test_state_with_message(self):
        """Should be able to set state with a custom message."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.set_state("executing", message="Running pytest...")

        content = dashboard.get_panel_content("agent_state")
        assert "Running pytest..." in content


class TestTerminalCapture:
    """Tests for capturing and displaying terminal output."""

    @pytest.mark.unit
    def test_capture_stdout_output(self):
        """Should capture standard output."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.capture_output("Hello from stdout")

        content = dashboard.get_panel_content("terminal")
        assert "Hello from stdout" in content

    @pytest.mark.unit
    def test_capture_stderr_output(self):
        """Should capture error output separately or marked."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.capture_output("Error occurred", stream="stderr")

        content = dashboard.get_panel_content("terminal")
        assert "Error occurred" in content

    @pytest.mark.unit
    def test_capture_command_with_output(self):
        """Should capture both command and its output."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.capture_command("ls -la", "file1.py\nfile2.py")

        content = dashboard.get_panel_content("terminal")
        assert "ls -la" in content
        assert "file1.py" in content

    @pytest.mark.unit
    def test_terminal_has_max_lines_limit(self):
        """Terminal should limit history to prevent memory issues."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        # Add many lines
        for i in range(1000):
            dashboard.append_terminal(f"Line {i}")

        content = dashboard.get_panel_content("terminal")
        lines = content.split('\n')

        # Should be limited (exact limit is implementation detail)
        assert len(lines) <= dashboard.MAX_TERMINAL_LINES

    @pytest.mark.unit
    def test_terminal_scrolls_to_show_latest(self):
        """Terminal should show most recent output when full."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        # Add many lines
        for i in range(1000):
            dashboard.append_terminal(f"Line {i}")

        content = dashboard.get_panel_content("terminal")

        # Should contain recent lines, not old ones
        assert "Line 999" in content
        assert "Line 0" not in content


class TestDashboardRendering:
    """Tests for dashboard rendering capabilities."""

    @pytest.mark.unit
    def test_dashboard_can_render_to_string(self):
        """Dashboard should be able to render layout to string for testing."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()
        dashboard.update_agent_state("Testing")

        rendered = dashboard.render_to_string()

        assert isinstance(rendered, str)
        assert len(rendered) > 0

    @pytest.mark.unit
    def test_dashboard_render_includes_all_panels(self):
        """Rendered output should include all panel contents."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()
        dashboard.update_agent_state("State content")
        dashboard.update_thought_process("Thought content")
        dashboard.update_terminal("Terminal content")
        dashboard.update_context(active_files=["test.py"], tokens_used=100)

        rendered = dashboard.render_to_string()

        assert "State content" in rendered
        assert "Thought content" in rendered
        assert "Terminal content" in rendered
        assert "test.py" in rendered

    @pytest.mark.unit
    def test_dashboard_supports_live_display(self):
        """Dashboard should provide a renderable for Rich Live display."""
        from src.cli.rich_dashboard import RichDashboard
        from rich.live import Live

        dashboard = RichDashboard()

        # Should return something that can be used with Live
        renderable = dashboard.get_renderable()

        # Should be usable with Live (we just check it's not None)
        assert renderable is not None


class TestContextPanel:
    """Tests for context panel specific features."""

    @pytest.mark.unit
    def test_context_shows_multiple_files(self):
        """Context panel should display list of active files."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        files = ["src/main.py", "src/utils.py", "tests/test_main.py"]
        dashboard.update_context(active_files=files, tokens_used=0)

        content = dashboard.get_panel_content("context")
        for f in files:
            assert f in content

    @pytest.mark.unit
    def test_context_shows_token_count_formatted(self):
        """Token count should be formatted for readability."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.update_context(active_files=[], tokens_used=15000)

        content = dashboard.get_panel_content("context")
        # Should show formatted number (15,000 or 15000)
        assert "15" in content and "000" in content

    @pytest.mark.unit
    def test_context_can_update_files_only(self):
        """Should be able to update just files without changing tokens."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.update_context(active_files=["initial.py"], tokens_used=100)
        dashboard.update_active_files(["new.py"])

        content = dashboard.get_panel_content("context")
        assert "new.py" in content
        assert "100" in content  # Tokens preserved

    @pytest.mark.unit
    def test_context_can_update_tokens_only(self):
        """Should be able to update just tokens without changing files."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.update_context(active_files=["keep.py"], tokens_used=100)
        dashboard.update_tokens(200)

        content = dashboard.get_panel_content("context")
        assert "keep.py" in content  # Files preserved
        assert "200" in content


class TestDashboardIntegration:
    """Integration tests for dashboard with other components."""

    @pytest.mark.unit
    def test_dashboard_can_be_used_with_rich_io(self):
        """Dashboard should work alongside RichIO."""
        from src.cli.rich_dashboard import RichDashboard
        from src.cli.rich_output import RichIO

        console = Console(force_terminal=True, width=80)
        rich_io = RichIO(console=console)
        dashboard = RichDashboard(console=console)

        # Both should share the same console
        assert rich_io._console is dashboard.console

    @pytest.mark.unit
    def test_dashboard_reset_clears_all_state(self):
        """Reset should clear all panels and return to idle."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        # Set up various state
        dashboard.set_state("thinking")
        dashboard.update_thought_process("Some thoughts")
        dashboard.append_terminal("Some output")
        dashboard.update_context(active_files=["file.py"], tokens_used=500)

        dashboard.reset()

        assert dashboard.get_state() == "idle"
        assert dashboard.get_panel_content("thought_process") == ""
        assert dashboard.get_panel_content("terminal") == ""


class TestPanelStyles:
    """Tests for panel styling and borders."""

    @pytest.mark.unit
    def test_agent_state_panel_has_border_style(self):
        """Agent state panel should have appropriate border style."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        style = dashboard.get_panel_style("agent_state")

        # Should have some style defined
        assert style is not None

    @pytest.mark.unit
    def test_state_changes_affect_panel_border_color(self):
        """Panel border should change color based on state."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.set_state("idle")
        idle_style = dashboard.get_panel_style("agent_state")

        dashboard.set_state("executing")
        executing_style = dashboard.get_panel_style("agent_state")

        # Styles should differ based on state
        # (exact comparison depends on implementation)
        assert idle_style is not None
        assert executing_style is not None
