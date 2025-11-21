"""Tests for Rich dashboard component.

Quality behavioral tests that prove the dashboard actually works.
Tests focus on behavior, not structure, following CLAUDE.md principles.
"""

import pytest
from rich.console import Console
from io import StringIO


class TestStateManagement:
    """Tests for dashboard state management behavior."""

    @pytest.mark.unit
    def test_set_state_updates_agent_state_panel_with_custom_message(self):
        """When state is set with message, agent state panel should show that message."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()
        dashboard.set_state("thinking", "Analyzing user requirements...")

        # Verify state was set
        assert dashboard.get_state() == "thinking"
        # Verify custom message appears in agent state panel
        content = dashboard.get_panel_content("agent_state")
        assert content == "Analyzing user requirements..."

    @pytest.mark.unit
    def test_set_state_without_message_shows_capitalized_state(self):
        """When state is set without message, panel should show capitalized state name."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()
        dashboard.set_state("executing")

        assert dashboard.get_state() == "executing"
        content = dashboard.get_panel_content("agent_state")
        assert content == "Executing"

    @pytest.mark.unit
    def test_set_state_changes_panel_style_based_on_state(self):
        """Panel style should change when state changes."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        # Set to thinking state
        dashboard.set_state("thinking")
        assert dashboard.get_panel_style("agent_state") == "yellow"

        # Change to executing state
        dashboard.set_state("executing")
        assert dashboard.get_panel_style("agent_state") == "green"

        # Change to scanning state
        dashboard.set_state("scanning")
        assert dashboard.get_panel_style("agent_state") == "cyan"

    @pytest.mark.unit
    def test_set_state_raises_error_for_invalid_state(self):
        """Setting invalid state should raise ValueError."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        with pytest.raises(ValueError) as exc_info:
            dashboard.set_state("invalid_state")

        assert "Invalid state" in str(exc_info.value)
        assert "invalid_state" in str(exc_info.value)


class TestThoughtProcessPanel:
    """Tests for thought process panel behavior."""

    @pytest.mark.unit
    def test_update_thought_process_replaces_existing_content(self):
        """Updating thought process should replace old content."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.update_thought_process("First thought")
        assert dashboard.get_panel_content("thought_process") == "First thought"

        dashboard.update_thought_process("Second thought")
        assert dashboard.get_panel_content("thought_process") == "Second thought"

    @pytest.mark.unit
    def test_append_thought_accumulates_content(self):
        """Appending thoughts should preserve previous content."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.append_thought("Step 1: Analyze requirements")
        dashboard.append_thought("Step 2: Design solution")

        content = dashboard.get_panel_content("thought_process")
        assert "Step 1: Analyze requirements" in content
        assert "Step 2: Design solution" in content

    @pytest.mark.unit
    def test_clear_thought_process_removes_all_content(self):
        """Clearing thought process should remove all content."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.update_thought_process("Some thought content")
        assert dashboard.get_panel_content("thought_process") != ""

        dashboard.clear_thought_process()
        assert dashboard.get_panel_content("thought_process") == ""


class TestTerminalPanel:
    """Tests for terminal panel behavior."""

    @pytest.mark.unit
    def test_update_terminal_replaces_existing_output(self):
        """Updating terminal should replace old output."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.update_terminal("First output")
        assert dashboard.get_panel_content("terminal") == "First output"

        dashboard.update_terminal("Second output")
        assert dashboard.get_panel_content("terminal") == "Second output"

    @pytest.mark.unit
    def test_append_terminal_accumulates_output(self):
        """Appending to terminal should preserve previous output."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.append_terminal("Line 1")
        dashboard.append_terminal("Line 2")

        content = dashboard.get_panel_content("terminal")
        assert "Line 1" in content
        assert "Line 2" in content

    @pytest.mark.unit
    def test_terminal_enforces_max_line_limit(self):
        """Terminal should keep only most recent lines when limit exceeded."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        # Add more than MAX_TERMINAL_LINES (100)
        for i in range(150):
            dashboard.append_terminal(f"Line {i}")

        content = dashboard.get_panel_content("terminal")
        lines = content.split('\n')

        # Should have exactly MAX_TERMINAL_LINES
        assert len(lines) == RichDashboard.MAX_TERMINAL_LINES
        # Should have newest lines (50-149)
        assert "Line 149" in content
        assert "Line 50" in content
        # Should NOT have oldest lines (0-49)
        assert "Line 0" not in content
        assert "Line 49" not in content

    @pytest.mark.unit
    def test_capture_output_appends_to_terminal(self):
        """Capturing stdout should append to terminal."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.capture_output("Process started", "stdout")

        content = dashboard.get_panel_content("terminal")
        assert "Process started" in content

    @pytest.mark.unit
    def test_capture_output_marks_stderr_differently(self):
        """Capturing stderr should mark it as stderr."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.capture_output("Error occurred", "stderr")

        content = dashboard.get_panel_content("terminal")
        assert "[stderr]" in content
        assert "Error occurred" in content

    @pytest.mark.unit
    def test_capture_command_shows_command_and_output(self):
        """Capturing command should show both command and its output."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.capture_command("ls -la", "total 64\ndrwxr-xr-x")

        content = dashboard.get_panel_content("terminal")
        assert "$ ls -la" in content
        assert "total 64" in content
        assert "drwxr-xr-x" in content

    @pytest.mark.unit
    def test_capture_command_with_empty_output(self):
        """Capturing command with no output should only show command."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.capture_command("echo test", "")

        content = dashboard.get_panel_content("terminal")
        assert "$ echo test" in content

    @pytest.mark.unit
    def test_clear_terminal_removes_all_output(self):
        """Clearing terminal should remove all output."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.append_terminal("Some output")
        assert dashboard.get_panel_content("terminal") != ""

        dashboard.clear_terminal()
        assert dashboard.get_panel_content("terminal") == ""


class TestContextPanel:
    """Tests for context panel behavior."""

    @pytest.mark.unit
    def test_update_context_shows_files_and_tokens(self):
        """Updating context should display files and token count."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        files = ["src/main.py", "src/utils.py", "tests/test_main.py"]
        dashboard.update_context(files, 2500)

        content = dashboard.get_panel_content("context")

        # Should show all files
        assert "src/main.py" in content
        assert "src/utils.py" in content
        assert "tests/test_main.py" in content

        # Should show token count with comma separator
        assert "2,500" in content or "2500" in content

    @pytest.mark.unit
    def test_update_active_files_preserves_token_count(self):
        """Updating only files should keep existing token count."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        # Set initial context
        dashboard.update_context(["file1.py"], 1000)

        # Update only files
        dashboard.update_active_files(["file2.py", "file3.py"])

        content = dashboard.get_panel_content("context")

        # Should have new files
        assert "file2.py" in content
        assert "file3.py" in content
        # Should NOT have old file
        assert "file1.py" not in content
        # Should preserve token count
        assert "1,000" in content or "1000" in content

    @pytest.mark.unit
    def test_update_tokens_preserves_file_list(self):
        """Updating only tokens should keep existing files."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        # Set initial context
        dashboard.update_context(["main.py", "test.py"], 500)

        # Update only tokens
        dashboard.update_tokens(1500)

        content = dashboard.get_panel_content("context")

        # Should have same files
        assert "main.py" in content
        assert "test.py" in content
        # Should have new token count
        assert "1,500" in content or "1500" in content

    @pytest.mark.unit
    def test_context_panel_with_empty_file_list(self):
        """Context panel should handle empty file list."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.update_context([], 0)

        content = dashboard.get_panel_content("context")

        # Should still show tokens (even if 0)
        assert "Tokens:" in content or "0" in content


class TestReset:
    """Tests for dashboard reset behavior."""

    @pytest.mark.unit
    def test_reset_clears_all_panels_and_state(self):
        """Reset should clear all content and return to idle state."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        # Set various content
        dashboard.set_state("executing", "Running task")
        dashboard.update_thought_process("Thinking...")
        dashboard.append_terminal("Output line")
        dashboard.update_context(["file.py"], 1000)

        # Reset
        dashboard.reset()

        # State should be idle
        assert dashboard.get_state() == "idle"

        # All panels should be empty
        assert dashboard.get_panel_content("agent_state") == ""
        assert dashboard.get_panel_content("thought_process") == ""
        assert dashboard.get_panel_content("terminal") == ""

        # Context should be cleared
        content = dashboard.get_panel_content("context")
        assert "file.py" not in content
        assert "Tokens: 0" in content


class TestRendering:
    """Tests for dashboard rendering behavior."""

    @pytest.mark.unit
    def test_render_to_string_produces_output(self):
        """Rendering to string should produce non-empty output."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.set_state("thinking", "Planning...")
        dashboard.update_thought_process("Step 1: Analyze")
        dashboard.append_terminal("$ ls")

        output = dashboard.render_to_string()

        # Output should not be empty
        assert len(output) > 0
        # Output should contain panel content
        assert "Planning..." in output or "Analyze" in output

    @pytest.mark.unit
    def test_get_renderable_returns_layout(self):
        """Getting renderable should return a Layout object."""
        from src.cli.rich_dashboard import RichDashboard
        from rich.layout import Layout

        dashboard = RichDashboard()

        renderable = dashboard.get_renderable()

        # Should return a Layout
        assert isinstance(renderable, Layout)


class TestDashboardProtocolCompliance:
    """Tests verifying RichDashboard implements DashboardProtocol."""

    @pytest.mark.unit
    def test_rich_dashboard_implements_protocol(self):
        """RichDashboard should satisfy DashboardProtocol."""
        from src.cli.rich_dashboard import RichDashboard
        from src.cli.protocols import DashboardProtocol

        dashboard = RichDashboard()

        # Should be recognized as implementing the protocol
        assert isinstance(dashboard, DashboardProtocol)



class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.unit
    def test_append_terminal_on_empty_terminal(self):
        """Appending to empty terminal should not add extra newline."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.append_terminal("First line")

        content = dashboard.get_panel_content("terminal")
        # Should not start with newline
        assert content == "First line"

    @pytest.mark.unit
    def test_append_thought_on_empty_thought_process(self):
        """Appending to empty thought process should not add extra newline."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.append_thought("First thought")

        content = dashboard.get_panel_content("thought_process")
        # Should not start with newline
        assert content == "First thought"

    @pytest.mark.unit
    def test_get_panel_content_for_unknown_panel_returns_empty(self):
        """Getting content for unknown panel should return empty string."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        content = dashboard.get_panel_content("nonexistent_panel")

        assert content == ""

    @pytest.mark.unit
    def test_get_panel_title_for_unknown_panel_returns_empty(self):
        """Getting title for unknown panel should return empty string."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        title = dashboard.get_panel_title("nonexistent_panel")

        assert title == ""

    @pytest.mark.unit
    def test_get_panel_style_for_non_agent_state_panel(self):
        """Getting style for non-agent-state panel should return default style."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        # Non-agent-state panels should have default style
        assert dashboard.get_panel_style("terminal") == "dim"
        assert dashboard.get_panel_style("thought_process") == "dim"
        assert dashboard.get_panel_style("context") == "dim"

    @pytest.mark.unit
    def test_update_context_with_large_token_count(self):
        """Context should format large token counts with comma separator."""
        from src.cli.rich_dashboard import RichDashboard

        dashboard = RichDashboard()

        dashboard.update_context([], 1234567)

        content = dashboard.get_panel_content("context")

        # Should have comma-separated format
        assert "1,234,567" in content

    @pytest.mark.unit
    def test_custom_console_injection(self):
        """Dashboard should use injected console for testing."""
        from src.cli.rich_dashboard import RichDashboard

        # Create custom console with string buffer
        string_io = StringIO()
        custom_console = Console(file=string_io, width=80)

        dashboard = RichDashboard(console=custom_console)

        # Dashboard should use the injected console
        assert dashboard.console is custom_console
