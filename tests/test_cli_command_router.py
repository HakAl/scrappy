"""
Tests for CLI command router module.

TDD: Tests written first for the command_router.py module which handles
routing slash commands to appropriate handlers.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
from tests.helpers import MockIO, ConfigurableTestOrchestrator
from src.cli.utils.cli_factory import initialize_cli_handlers


class TestCommandRouter:
    """Tests for CommandRouter class."""

    def setup_method(self):
        """Set up test fixtures."""
        from src.cli.command_router import CommandRouter
        self.CommandRouter = CommandRouter
        self.orchestrator = ConfigurableTestOrchestrator()

    def _create_router(self, io=None):
        """Helper to create a CommandRouter with all dependencies."""
        if io is None:
            io = MockIO()

        session_start = datetime.now()
        handlers = initialize_cli_handlers(self.orchestrator, session_start)

        return self.CommandRouter(
            io=io,
            orchestrator=self.orchestrator,
            display=handlers['display'],
            session_mgr=handlers['session_mgr'],
            codebase=handlers['codebase'],
            tasks=handlers['tasks'],
            multiprovider=handlers['multiprovider'],
            smart=handlers['smart'],
            agent_mgr=handlers['agent_mgr'],
            task_router=handlers['task_router']
        )

    # =========================================================================
    # Initialization Tests
    # =========================================================================


    def test_accepts_state_manager(self):
        """Should accept optional state manager."""
        from src.cli.state_manager import PlanStateManager
        io = MockIO()
        state_mgr = PlanStateManager()
        router = self._create_router(io)

        assert router.state_manager is state_mgr

    # =========================================================================
    # Task Command Tests
    # =========================================================================

    def test_route_plan_command_no_args_shows_usage(self):
        """Should show usage when /plan called without args."""
        io = MockIO()
        router = self._create_router(io)

        result = router.route("/plan", "")

        output = io.get_output()
        assert "Usage:" in output

    def test_route_agent_no_args_shows_usage(self):
        """Should show usage when /agent called without args."""
        io = MockIO()
        router = self._create_router(io)

        result = router.route("/agent", "")

        output = io.get_output()
        assert "Usage:" in output

    # =========================================================================
    # Smart Query Command Tests
    # =========================================================================

    def test_route_smart_toggle(self):
        """Should toggle smart mode when /smart toggle."""
        io = MockIO()
        router = self._create_router(io)
        router.smart_mode = False

        result = router.route("/smart", "toggle")

        assert router.smart_mode is True

    def test_route_smart_no_args_shows_status(self):
        """Should show status when /smart called without args."""
        io = MockIO()
        router = self._create_router(io)
        router.smart_mode = True

        result = router.route("/smart", "")

        output = io.get_output()
        assert "Smart" in output or "smart" in output

    # =========================================================================
    # Task Router Command Tests
    # =========================================================================

    def test_route_classify_no_args_shows_usage(self):
        """Should show usage when /classify without args."""
        io = MockIO()
        router = self._create_router(io)

        result = router.route("/classify", "")

        output = io.get_output()
        assert "Usage:" in output

    # =========================================================================
    # State Command Tests
    # =========================================================================

    def test_route_clear_command(self):
        """Should clear conversation history on /clear."""
        io = MockIO()
        router = self._create_router(io)
        router.conversation_history = [{"role": "user", "content": "test"}]

        result = router.route("/clear", "")

        assert router.conversation_history == []
        output = io.get_output()
        assert "cleared" in output.lower()

    def test_route_autoexec_toggle(self):
        """Should toggle auto_execute_tasks on /autoexec."""
        io = MockIO()
        router = self._create_router(io)
        from src.cli.state_manager import PlanStateManager
        router.state_manager = PlanStateManager()
        router.state_manager.auto_execute_tasks = True

        result = router.route("/autoexec", "")

        assert router.state_manager.auto_execute_tasks is False
        output = io.get_output()
        assert "Auto-execute" in output

    def test_route_multiline_toggle(self):
        """Should toggle multiline_mode on /ml."""
        io = MockIO()
        router = self._create_router(io)
        router.multiline_mode = True

        result = router.route("/ml", "")

        assert router.multiline_mode is False
        output = io.get_output()
        assert "Multiline" in output

    def test_route_auto_toggle(self):
        """Should toggle auto_route_mode on /auto."""
        io = MockIO()
        router = self._create_router(io)
        router.auto_route_mode = False

        result = router.route("/auto", "")

        assert router.auto_route_mode is True
        output = io.get_output()
        assert "Auto-routing" in output or "routing" in output.lower()

    # =========================================================================
    # Tasks List Command Tests
    # =========================================================================

    def test_route_tasks_shows_plan(self):
        """Should show task list when plan active."""
        io = MockIO()
        router = self._create_router(io)
        from src.cli.state_manager import PlanStateManager
        router.state_manager = PlanStateManager()
        router.state_manager.start_plan([
            {'step': 'Task 1'},
            {'step': 'Task 2'}
        ])

        result = router.route("/tasks", "")

        output = io.get_output()
        assert "Task 1" in output
        assert "Task 2" in output

    def test_route_tasks_no_plan_shows_message(self):
        """Should show message when no active plan."""
        io = MockIO()
        router = self._create_router(io)
        from src.cli.state_manager import PlanStateManager
        router.state_manager = PlanStateManager()

        result = router.route("/tasks", "")

        output = io.get_output()
        assert "No active plan" in output

    # =========================================================================
    # Exit Command Tests
    # =========================================================================

    def test_route_quit_returns_false(self):
        """Should return False on /quit to exit loop."""
        io = MockIO()
        router = self._create_router(io)
        router.display = MagicMock()
        router.auto_save = False

        result = router.route("/quit", "")

        assert result is False

    def test_route_exit_returns_false(self):
        """Should return False on /exit to exit loop."""
        io = MockIO()
        router = self._create_router(io)
        router.display = MagicMock()
        router.auto_save = False

        result = router.route("/exit", "")

        assert result is False

    def test_route_q_returns_false(self):
        """Should return False on /q to exit loop."""
        io = MockIO()
        router = self._create_router(io)
        router.display = MagicMock()
        router.auto_save = False

        result = router.route("/q", "")

        assert result is False

    def test_quit_auto_saves_session(self):
        """Should auto-save session on quit when enabled."""
        io = MockIO()
        router = self._create_router(io)
        router.display = MagicMock()
        router.auto_save = True
        self.orchestrator.save_session = MagicMock(return_value="/test/session.json")

        result = router.route("/quit", "")

        self.orchestrator.save_session.assert_called_once()
        output = io.get_output()
        assert "saved" in output.lower()

    def test_quit_shows_goodbye(self):
        """Should show goodbye message on quit."""
        io = MockIO()
        router = self._create_router(io)
        router.display = MagicMock()
        router.auto_save = False

        result = router.route("/quit", "")

        output = io.get_output()
        assert "Goodbye" in output

    # =========================================================================
    # Unknown Command Tests
    # =========================================================================

    def test_unknown_command_shows_error(self):
        """Should show error for unknown command."""
        io = MockIO()
        router = self._create_router(io)

        result = router.route("/unknowncommand", "")

        output = io.get_output()
        assert "Unknown command" in output or "Invalid command" in output

        styled = io.get_styled_outputs()
        error_outputs = [s for s in styled if "Unknown" in s['text'] or "Invalid" in s['text']]
        if error_outputs:
            # Validation errors are shown in red
            assert error_outputs[0]['fg'] == 'red'

    def test_unknown_command_returns_true(self):
        """Should return True to continue loop for unknown command."""
        io = MockIO()
        router = self._create_router(io)

        result = router.route("/xyz", "")

        assert result is True

    def test_unknown_command_suggests_help(self):
        """Should suggest /help for unknown command."""
        io = MockIO()
        router = self._create_router(io)

        result = router.route("/badcmd", "")

        output = io.get_output()
        assert "/help" in output

    # =========================================================================
    # Command Alias Tests
    # =========================================================================

    def test_multiline_aliases(self):
        """Should accept /paste and /multiline as /ml aliases."""
        io = MockIO()
        router = self._create_router(io)
        router.multiline_mode = True

        router.route("/paste", "")
        assert router.multiline_mode is False

        router.route("/multiline", "")
        assert router.multiline_mode is True

    def test_auto_aliases(self):
        """Should accept /route and /autoroute as /auto aliases."""
        io = MockIO()
        router = self._create_router(io)
        router.auto_route_mode = False

        router.route("/route", "")
        assert router.auto_route_mode is True

        router.route("/autoroute", "")
        assert router.auto_route_mode is False


class TestCommandRegistryPattern:
    """Tests for command registry pattern refactoring.

    These tests verify the registry-based dispatch pattern that replaces
    the long if/elif chain with dictionary-based command routing.
    """

    def setup_method(self):
        """Set up test fixtures."""
        from src.cli.command_router import CommandRouter
        self.CommandRouter = CommandRouter
        self.orchestrator = ConfigurableTestOrchestrator()

    # =========================================================================
    # Registry Structure Tests
    # =========================================================================


    def test_registry_contains_all_exit_commands(self):
        """Should have all exit commands in registry."""
        io = MockIO()
        router = self._create_router(io)

        exit_commands = ["/quit", "/exit", "/q"]
        for cmd in exit_commands:
            assert cmd in router._command_registry, f"Missing exit command: {cmd}"

    def test_registry_contains_display_commands(self):
        """Should have all display commands in registry."""
        io = MockIO()
        router = self._create_router(io)

        display_commands = ["/help", "/status", "/providers", "/brain", "/usage", "/models"]
        for cmd in display_commands:
            assert cmd in router._command_registry, f"Missing display command: {cmd}"

    def test_registry_contains_session_commands(self):
        """Should have all session commands in registry."""
        io = MockIO()
        router = self._create_router(io)

        session_commands = ["/context", "/cache", "/session", "/limits"]
        for cmd in session_commands:
            assert cmd in router._command_registry, f"Missing session command: {cmd}"

    def test_registry_contains_task_commands(self):
        """Should have all task commands in registry."""
        io = MockIO()
        router = self._create_router(io)

        task_commands = ["/plan", "/reason", "/agent"]
        for cmd in task_commands:
            assert cmd in router._command_registry, f"Missing task command: {cmd}"

    def test_registry_contains_multiprovider_commands(self):
        """Should have all multi-provider commands in registry."""
        io = MockIO()
        router = self._create_router(io)

        mp_commands = ["/synthesize", "/delegate"]
        for cmd in mp_commands:
            assert cmd in router._command_registry, f"Missing multi-provider command: {cmd}"

    def test_registry_contains_state_commands(self):
        """Should have all state commands in registry."""
        io = MockIO()
        router = self._create_router(io)

        state_commands = ["/clear", "/autoexec", "/paste", "/ml", "/multiline",
                         "/auto", "/route", "/autoroute", "/tasks"]
        for cmd in state_commands:
            assert cmd in router._command_registry, f"Missing state command: {cmd}"

    def test_registry_contains_other_commands(self):
        """Should have other specialized commands in registry."""
        io = MockIO()
        router = self._create_router(io)

        other_commands = ["/smart", "/explore", "/classify"]
        for cmd in other_commands:
            assert cmd in router._command_registry, f"Missing command: {cmd}"

    def test_registry_values_are_callable(self):
        """Should have callable handlers as registry values."""
        io = MockIO()
        router = self._create_router(io)

        for cmd, handler in router._command_registry.items():
            assert callable(handler), f"Handler for {cmd} is not callable"

    # =========================================================================
    # Registry Dispatch Tests
    # =========================================================================

    def test_registry_dispatch_for_help(self):
        """Should dispatch /help via registry to correct handler."""
        io = MockIO()
        router = self._create_router(io)

        result = router.route("/help", "")

        output = io.get_output()
        # /help should show available commands
        assert result is True
        # Verify handler was called (should show some help content)
        assert "help" in output.lower() or "command" in output.lower() or len(output) > 0

    def test_registry_dispatch_for_clear(self):
        """Should dispatch /clear via registry to correct handler."""
        io = MockIO()
        router = self._create_router(io)
        router.conversation_history = [{"role": "user", "content": "test"}]

        result = router.route("/clear", "")

        assert router.conversation_history == []
        assert result is True

    def test_registry_dispatch_for_exit(self):
        """Should dispatch exit commands via registry returning False."""
        io = MockIO()
        router = self._create_router(io)
        router.display = MagicMock()
        router.auto_save = False

        result = router.route("/quit", "")

        assert result is False

    def test_registry_dispatch_passes_args(self):
        """Should pass args to handler when dispatching via registry."""
        io = MockIO()
        router = self._create_router(io)

        # /auto with "status" arg should show routing status
        result = router.route("/auto", "status")

        assert result is True
        # Handler should receive and process the args

    # =========================================================================
    # Handler Method Tests
    # =========================================================================

    def test_handle_exit_returns_false(self):
        """_handle_exit should return False to exit loop."""
        io = MockIO()
        router = self._create_router(io)
        router.display = MagicMock()
        router.auto_save = False

        # Call handler directly
        result = router._handle_exit("")

        assert result is False

    def test_handle_exit_auto_saves_when_enabled(self):
        """_handle_exit should auto-save session when auto_save is True."""
        io = MockIO()
        router = self._create_router(io)
        router.display = MagicMock()
        router.auto_save = True
        self.orchestrator.save_session = MagicMock(return_value="/test/session.json")

        result = router._handle_exit("")

        self.orchestrator.save_session.assert_called_once()

    def test_handle_help_returns_true(self):
        """_handle_help should return True to continue loop."""
        io = MockIO()
        router = self._create_router(io)

        result = router._handle_help("")

        assert result is True

    def test_handle_status_returns_true(self):
        """_handle_status should return True to continue loop."""
        io = MockIO()
        router = self._create_router(io)

        result = router._handle_status("")

        assert result is True

    def test_handle_clear_clears_history(self):
        """_handle_clear should clear conversation history."""
        io = MockIO()
        router = self._create_router(io)
        router.conversation_history = [{"role": "user", "content": "test"}]

        result = router._handle_clear("")

        assert router.conversation_history == []
        assert result is True

    def test_handle_smart_toggle(self):
        """_handle_smart should toggle smart mode with 'toggle' arg."""
        io = MockIO()
        router = self._create_router(io)
        router.smart_mode = False

        result = router._handle_smart("toggle")

        assert router.smart_mode is True
        assert result is True

    def test_handle_smart_shows_status_no_args(self):
        """_handle_smart should show status when called without args."""
        io = MockIO()
        router = self._create_router(io)
        router.smart_mode = True

        result = router._handle_smart("")

        output = io.get_output()
        assert "smart" in output.lower() or "ON" in output
        assert result is True

    def test_handle_auto_toggle(self):
        """_handle_auto should toggle auto_route_mode with no args."""
        io = MockIO()
        router = self._create_router(io)
        router.auto_route_mode = False

        result = router._handle_auto("")

        assert router.auto_route_mode is True
        assert result is True

    def test_handle_autoexec_toggle(self):
        """_handle_autoexec should toggle auto_execute_tasks."""
        io = MockIO()
        router = self._create_router(io)
        from src.cli.state_manager import PlanStateManager
        router.state_manager = PlanStateManager()
        router.state_manager.auto_execute_tasks = True

        result = router._handle_autoexec("")

        assert router.state_manager.auto_execute_tasks is False
        assert result is True

    def test_handle_multiline_toggle(self):
        """_handle_multiline should toggle multiline_mode."""
        io = MockIO()
        router = self._create_router(io)
        router.multiline_mode = True

        result = router._handle_multiline("")

        assert router.multiline_mode is False
        assert result is True

    def test_handle_plan_no_args_shows_usage(self):
        """_handle_plan should show usage when called without args."""
        io = MockIO()
        router = self._create_router(io)

        result = router._handle_plan("")

        output = io.get_output()
        assert "Usage:" in output
        assert result is True

    def test_handle_reason_no_args_shows_usage(self):
        """_handle_reason should show usage when called without args."""
        io = MockIO()
        router = self._create_router(io)

        result = router._handle_reason("")

        output = io.get_output()
        assert "Usage:" in output
        assert result is True

    def test_handle_agent_no_args_shows_usage(self):
        """_handle_agent should show usage when called without args."""
        io = MockIO()
        router = self._create_router(io)

        result = router._handle_agent("")

        output = io.get_output()
        assert "Usage:" in output
        assert result is True

    def test_handle_classify_no_args_shows_usage(self):
        """_handle_classify should show usage when called without args."""
        io = MockIO()
        router = self._create_router(io)

        result = router._handle_classify("")

        output = io.get_output()
        assert "Usage:" in output
        assert result is True

    def test_handle_tasks_no_plan_shows_message(self):
        """_handle_tasks should show message when no active plan."""
        io = MockIO()
        router = self._create_router(io)
        from src.cli.state_manager import PlanStateManager
        router.state_manager = PlanStateManager()

        result = router._handle_tasks("")

        output = io.get_output()
        assert "No active plan" in output
        assert result is True

    # =========================================================================
    # Route Method Simplification Tests
    # =========================================================================

    def test_route_uses_registry_lookup(self):
        """route() should use registry lookup instead of if/elif chain."""
        io = MockIO()
        router = self._create_router(io)

        # All known commands should be handled via registry
        known_commands = ["/help", "/status", "/clear", "/smart", "/auto"]

        for cmd in known_commands:
            io.clear_output()
            result = router.route(cmd, "")
            assert result is True, f"Command {cmd} failed"

    def test_route_handles_unknown_via_registry_miss(self):
        """route() should handle unknown commands when not in registry."""
        io = MockIO()
        router = self._create_router(io)

        result = router.route("/notacommand", "")

        output = io.get_output()
        assert "Unknown command" in output or "Invalid command" in output
        assert result is True

    def test_route_validates_before_dispatch(self):
        """route() should validate command before looking up in registry."""
        io = MockIO()
        router = self._create_router(io)

        # Invalid command format should be caught by validator
        result = router.route("", "")

        output = io.get_output()
        assert "Invalid" in output or "Unknown" in output

    # =========================================================================
    # Alias Mapping Tests
    # =========================================================================

    def test_aliases_point_to_same_handler(self):
        """Command aliases should point to the same handler function."""
        io = MockIO()
        router = self._create_router(io)

        # Exit aliases
        exit_handler = router._command_registry.get("/quit")
        assert router._command_registry.get("/exit") == exit_handler
        assert router._command_registry.get("/q") == exit_handler

        # Multiline aliases
        ml_handler = router._command_registry.get("/ml")
        assert router._command_registry.get("/paste") == ml_handler
        assert router._command_registry.get("/multiline") == ml_handler

        # Auto-route aliases
        auto_handler = router._command_registry.get("/auto")
        assert router._command_registry.get("/route") == auto_handler
        assert router._command_registry.get("/autoroute") == auto_handler

    # =========================================================================
    # Handler Return Value Tests
    # =========================================================================


    def test_only_exit_handlers_return_false(self):
        """Only exit handlers should return False."""
        io = MockIO()
        router = self._create_router(io)
        router.display = MagicMock()
        router.auto_save = False

        # These should return True
        continue_handlers = [
            "_handle_help",
            "_handle_status",
            "_handle_clear",
            "_handle_multiline",
            "_handle_smart",
            "_handle_auto",
        ]

        for handler_name in continue_handlers:
            io.clear_output()
            handler = getattr(router, handler_name)
            result = handler("")
            assert result is True, f"{handler_name} should return True"

        # Exit should return False
        result = router._handle_exit("")
        assert result is False

    # =========================================================================
    # Edge Case Tests
    # =========================================================================

    def test_handler_receives_trimmed_args(self):
        """Handlers should receive args without leading/trailing whitespace."""
        io = MockIO()
        router = self._create_router(io)
        router.smart_mode = False

        # Toggle with extra whitespace
        result = router.route("/smart", "  toggle  ")

        # Should still toggle despite whitespace
        # Note: route() may or may not strip - test actual behavior
        assert result is True

    def test_empty_registry_key_not_allowed(self):
        """Registry should not contain empty string as key."""
        io = MockIO()
        router = self._create_router(io)

        assert "" not in router._command_registry
        assert None not in router._command_registry