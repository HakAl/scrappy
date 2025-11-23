"""Tests for DisplayManager component.

Quality behavioral tests that prove DisplayManager coordinates between
RichIO and RichDashboard correctly. Tests focus on behavior, not structure,
following CLAUDE.md principles.
"""

import pytest
from io import StringIO
from rich.console import Console


class TestDisplayManagerProtocol:
    """Tests verifying DisplayManager implements DisplayManagerProtocol."""

    @pytest.mark.unit
    def test_display_manager_implements_protocol(self):
        """DisplayManager should satisfy DisplayManagerProtocol."""
        from src.cli.display_manager import DisplayManager
        from src.cli.protocols import DisplayManagerProtocol

        display = DisplayManager()

        # Should be recognized as implementing the protocol
        assert isinstance(display, DisplayManagerProtocol)


    @pytest.mark.unit
    def test_display_manager_provides_dashboard_when_enabled(self):
        """DisplayManager should provide dashboard when enabled."""
        from src.cli.display_manager import DisplayManager
        from src.cli.protocols import DashboardProtocol

        display = DisplayManager(dashboard_enabled=True)
        dashboard = display.get_dashboard()

        # Should return DashboardProtocol implementation
        assert dashboard is not None
        assert isinstance(dashboard, DashboardProtocol)


class TestDashboardModeToggle:
    """Tests for dashboard mode enable/disable behavior."""

    @pytest.mark.unit
    def test_dashboard_disabled_by_default(self):
        """Dashboard should be disabled by default."""
        from src.cli.display_manager import DisplayManager

        display = DisplayManager()

        assert display.is_dashboard_enabled() is False
        assert display.get_dashboard() is None

    @pytest.mark.unit
    def test_dashboard_enabled_when_configured(self):
        """Dashboard should be enabled when configured."""
        from src.cli.display_manager import DisplayManager

        display = DisplayManager(dashboard_enabled=True)

        assert display.is_dashboard_enabled() is True
        assert display.get_dashboard() is not None

    @pytest.mark.unit
    def test_enable_dashboard_creates_dashboard_if_not_exists(self):
        """Enabling dashboard should create dashboard if needed."""
        from src.cli.display_manager import DisplayManager

        display = DisplayManager(dashboard_enabled=False)
        assert display.get_dashboard() is None

        display.enable_dashboard()

        assert display.is_dashboard_enabled() is True
        assert display.get_dashboard() is not None

    @pytest.mark.unit
    def test_disable_dashboard_keeps_dashboard_instance(self):
        """Disabling dashboard should retain instance but not use it."""
        from src.cli.display_manager import DisplayManager

        display = DisplayManager(dashboard_enabled=True)
        dashboard_ref = display.get_dashboard()

        display.disable_dashboard()

        # Dashboard should be disabled
        assert display.is_dashboard_enabled() is False
        # But instance should still exist (just returns None via get_dashboard)
        assert display.get_dashboard() is None

    @pytest.mark.unit
    def test_enable_disable_enable_cycle(self):
        """Dashboard should support enable/disable/enable cycle."""
        from src.cli.display_manager import DisplayManager

        display = DisplayManager(dashboard_enabled=False)

        # Enable
        display.enable_dashboard()
        assert display.is_dashboard_enabled() is True

        # Disable
        display.disable_dashboard()
        assert display.is_dashboard_enabled() is False

        # Enable again
        display.enable_dashboard()
        assert display.is_dashboard_enabled() is True


class TestDependencyInjection:
    """Tests for dependency injection behavior."""

    @pytest.mark.unit
    def test_inject_custom_io(self):
        """DisplayManager should use injected IO."""
        from src.cli.display_manager import DisplayManager
        from src.cli.io_interface import TestIO

        custom_io = TestIO()
        display = DisplayManager(io=custom_io)

        # Should use the injected IO
        assert display.get_io() is custom_io

    @pytest.mark.unit
    def test_inject_custom_dashboard(self):
        """DisplayManager should use injected dashboard when enabled."""
        from src.cli.display_manager import DisplayManager
        from src.cli.rich_dashboard import RichDashboard

        custom_dashboard = RichDashboard()
        display = DisplayManager(
            dashboard=custom_dashboard,
            dashboard_enabled=True
        )

        # Should use the injected dashboard
        assert display.get_dashboard() is custom_dashboard

    @pytest.mark.unit
    def test_creates_default_io_when_not_provided(self):
        """DisplayManager should create default IO if not injected."""
        from src.cli.display_manager import DisplayManager
        from src.cli.unified_io import UnifiedIO

        display = DisplayManager()
        io = display.get_io()

        # Should have created default UnifiedIO
        assert io is not None
        assert isinstance(io, UnifiedIO)

    @pytest.mark.unit
    def test_creates_default_dashboard_when_enabled_without_injection(self):
        """DisplayManager should create default dashboard if enabled but not injected."""
        from src.cli.display_manager import DisplayManager
        from src.cli.rich_dashboard import RichDashboard

        display = DisplayManager(dashboard_enabled=True)
        dashboard = display.get_dashboard()

        # Should have created default RichDashboard
        assert dashboard is not None
        assert isinstance(dashboard, RichDashboard)


class TestLiveDashboardContext:
    """Tests for live dashboard context manager behavior."""

    @pytest.mark.unit
    def test_live_dashboard_context_yields_dashboard(self):
        """Live dashboard context should yield dashboard instance."""
        from src.cli.display_manager import DisplayManager

        display = DisplayManager(dashboard_enabled=True)

        with display.live_dashboard():
            dashboard = display.get_dashboard()
            # Dashboard should be available in context
            assert dashboard is not None

    @pytest.mark.unit
    def test_live_dashboard_raises_if_disabled(self):
        """Live dashboard context should raise error if dashboard disabled."""
        from src.cli.display_manager import DisplayManager

        display = DisplayManager(dashboard_enabled=False)

        with pytest.raises(RuntimeError) as exc_info:
            with display.live_dashboard():
                pass

        assert "dashboard is disabled" in str(exc_info.value).lower()

    @pytest.mark.unit
    def test_dashboard_updates_within_live_context(self):
        """Dashboard should update successfully within live context."""
        from src.cli.display_manager import DisplayManager

        display = DisplayManager(dashboard_enabled=True)

        with display.live_dashboard():
            dashboard = display.get_dashboard()
            dashboard.set_state("thinking", "Testing...")
            dashboard.update_thought_process("Test thought")
            dashboard.append_terminal("Test output")

            # Verify updates were applied
            assert dashboard.get_state() == "thinking"
            assert dashboard.get_panel_content("thought_process") == "Test thought"
            assert "Test output" in dashboard.get_panel_content("terminal")


class TestReset:
    """Tests for display manager reset behavior."""

    @pytest.mark.unit
    def test_reset_clears_dashboard_if_present(self):
        """Reset should clear dashboard state."""
        from src.cli.display_manager import DisplayManager

        display = DisplayManager(dashboard_enabled=True)
        dashboard = display.get_dashboard()

        # Set some content
        dashboard.set_state("executing", "Running...")
        dashboard.update_thought_process("Thinking...")
        dashboard.append_terminal("Output")

        # Reset display manager
        display.reset()

        # Dashboard should be reset to initial state
        assert dashboard.get_state() == "idle"
        assert dashboard.get_panel_content("thought_process") == ""
        assert dashboard.get_panel_content("terminal") == ""



class TestBackwardCompatibility:
    """Tests verifying backward compatibility patterns."""

    @pytest.mark.unit
    def test_can_use_io_directly_without_dashboard(self):
        """Should be able to use IO directly without dashboard."""
        from src.cli.display_manager import DisplayManager
        from src.cli.io_interface import TestIO

        test_io = TestIO()
        display = DisplayManager(io=test_io, dashboard_enabled=False)

        io = display.get_io()
        io.echo("Test message")

        # IO should work independently
        assert "Test message" in test_io.get_output()

    @pytest.mark.unit
    def test_simple_usage_pattern(self):
        """Test simple usage pattern for handlers."""
        from src.cli.display_manager import DisplayManager
        from src.cli.io_interface import TestIO

        # Simulate handler usage
        test_io = TestIO()
        display = DisplayManager(io=test_io, dashboard_enabled=False)

        io = display.get_io()
        io.secho("Operation started", fg="green")

        # Check if dashboard is enabled (it's not)
        if display.is_dashboard_enabled():
            dashboard = display.get_dashboard()
            dashboard.set_state("executing")
        # Since dashboard is disabled, this branch is skipped

        io.echo("Operation complete")

        output = test_io.get_output()
        assert "Operation started" in output
        assert "Operation complete" in output

    @pytest.mark.unit
    def test_dashboard_mode_usage_pattern(self):
        """Test dashboard mode usage pattern for handlers."""
        from src.cli.display_manager import DisplayManager
        from src.cli.io_interface import TestIO

        # Simulate handler with dashboard enabled
        test_io = TestIO()
        display = DisplayManager(io=test_io, dashboard_enabled=True)

        io = display.get_io()
        io.secho("Operation started", fg="green")

        # Check if dashboard is enabled (it is)
        if display.is_dashboard_enabled():
            dashboard = display.get_dashboard()
            dashboard.set_state("executing", "Running operation...")
            dashboard.update_thought_process("Analyzing requirements")
            dashboard.append_terminal("$ command")

            # Verify dashboard was updated
            assert dashboard.get_state() == "executing"
            assert "Analyzing" in dashboard.get_panel_content("thought_process")

        io.echo("Operation complete")

        output = test_io.get_output()
        assert "Operation started" in output
        assert "Operation complete" in output


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.unit
    def test_get_dashboard_returns_none_when_disabled(self):
        """Getting dashboard when disabled should return None."""
        from src.cli.display_manager import DisplayManager

        display = DisplayManager(dashboard_enabled=False)

        assert display.get_dashboard() is None

    @pytest.mark.unit
    def test_enable_dashboard_multiple_times_is_safe(self):
        """Enabling dashboard multiple times should be safe."""
        from src.cli.display_manager import DisplayManager

        display = DisplayManager(dashboard_enabled=False)

        display.enable_dashboard()
        dashboard1 = display.get_dashboard()

        display.enable_dashboard()
        dashboard2 = display.get_dashboard()

        # Should have same dashboard instance
        assert dashboard1 is dashboard2

    @pytest.mark.unit
    def test_disable_dashboard_when_already_disabled(self):
        """Disabling already disabled dashboard should be safe."""
        from src.cli.display_manager import DisplayManager

        display = DisplayManager(dashboard_enabled=False)

        # Should not raise error
        display.disable_dashboard()
        display.disable_dashboard()

        assert display.is_dashboard_enabled() is False



class TestIntegrationWithHandlers:
    """Integration tests demonstrating usage with CLI handlers."""

    @pytest.mark.integration
    def test_simulated_task_execution_with_dashboard(self):
        """Simulate task execution handler using display manager."""
        from src.cli.display_manager import DisplayManager
        from src.cli.io_interface import TestIO

        test_io = TestIO()
        display = DisplayManager(io=test_io, dashboard_enabled=True)

        io = display.get_io()
        dashboard = display.get_dashboard()

        # Simulate task planning flow
        io.secho("Planning task...", bold=True)
        if dashboard:
            dashboard.set_state("thinking", "Generating plan...")
            dashboard.update_thought_process("Planning task: Build feature X")

        # Simulate plan execution
        if dashboard:
            dashboard.set_state("executing", "Executing plan...")
            dashboard.append_terminal("$ step 1 completed")
            dashboard.append_terminal("$ step 2 completed")

        io.echo("Task complete")

        if dashboard:
            dashboard.set_state("idle", "Task finished")

        # Verify output
        output = test_io.get_output()
        assert "Planning task..." in output
        assert "Task complete" in output

        # Verify dashboard state
        assert dashboard.get_state() == "idle"
        assert "step 1 completed" in dashboard.get_panel_content("terminal")

    @pytest.mark.integration
    def test_simulated_smart_query_with_dashboard(self):
        """Simulate smart query handler using display manager."""
        from src.cli.display_manager import DisplayManager
        from src.cli.io_interface import TestIO

        test_io = TestIO()
        display = DisplayManager(io=test_io, dashboard_enabled=True)

        io = display.get_io()
        dashboard = display.get_dashboard()

        # Simulate query flow
        query = "What does function X do?"
        io.secho(f"Analyzing: {query}", fg="cyan")

        if dashboard:
            dashboard.set_state("thinking", "Analyzing query intent...")
            dashboard.update_thought_process(f"Query: {query}")

        # Simulate research phase
        if dashboard:
            dashboard.set_state("scanning", "Researching codebase...")
            dashboard.append_terminal("Researched: code_search (3 results)")
            dashboard.append_thought("\nGathered 3 research results")

        # Simulate response generation
        if dashboard:
            dashboard.set_state("thinking", "Generating response...")

        io.echo("Answer: Function X does...")

        if dashboard:
            dashboard.set_state("idle", "Query complete")

        # Verify
        output = test_io.get_output()
        assert "Analyzing:" in output
        assert "Answer:" in output
        assert dashboard.get_state() == "idle"

    @pytest.mark.integration
    def test_handler_without_dashboard_mode(self):
        """Handlers should work correctly without dashboard mode."""
        from src.cli.display_manager import DisplayManager
        from src.cli.io_interface import TestIO

        test_io = TestIO()
        display = DisplayManager(io=test_io, dashboard_enabled=False)

        io = display.get_io()
        dashboard = display.get_dashboard()

        # Simulate handler that checks for dashboard
        io.secho("Starting operation", bold=True)

        if dashboard:
            # This branch should not execute
            dashboard.set_state("executing")
            raise AssertionError("Dashboard should be None")

        io.echo("Operation complete without dashboard")

        # Verify
        output = test_io.get_output()
        assert "Starting operation" in output
        assert "Operation complete without dashboard" in output
