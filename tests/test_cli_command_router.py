"""
Tests for CLI command router module.

TDD: Tests written first for the command_router.py module which handles
routing slash commands to appropriate handlers.
"""

import pytest
from unittest.mock import MagicMock, patch
from tests.helpers import MockIO, ConfigurableTestOrchestrator


class TestCommandRouter:
    """Tests for CommandRouter class."""

    def setup_method(self):
        """Set up test fixtures."""
        from src.cli.command_router import CommandRouter
        self.CommandRouter = CommandRouter
        self.orchestrator = ConfigurableTestOrchestrator()

    # =========================================================================
    # Initialization Tests
    # =========================================================================

    def test_initializes_with_handlers(self):
        """Should initialize with handler registry."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)

        assert router is not None

    def test_accepts_state_manager(self):
        """Should accept optional state manager."""
        from src.cli.state_manager import PlanStateManager
        io = MockIO()
        state_mgr = PlanStateManager()
        router = self.CommandRouter(io, self.orchestrator, state_manager=state_mgr)

        assert router.state_manager is state_mgr

    # =========================================================================
    # Command Routing Tests
    # =========================================================================

    def test_route_help_command(self):
        """Should route /help to display handler."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)
        router.display = MagicMock()

        result = router.route("/help", "")

        router.display.show_help.assert_called_once()
        assert result is True  # Continue loop

    def test_route_status_command(self):
        """Should route /status to display handler."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)
        router.display = MagicMock()

        result = router.route("/status", "")

        router.display.show_status.assert_called_once()
        assert result is True

    def test_route_providers_command(self):
        """Should route /providers to display handler."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)
        router.display = MagicMock()

        result = router.route("/providers", "")

        router.display.list_providers.assert_called_once()

    def test_route_brain_command(self):
        """Should route /brain to display handler."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)
        router.display = MagicMock()

        result = router.route("/brain", "claude")

        router.display.switch_brain.assert_called_once_with("claude")

    def test_route_usage_command(self):
        """Should route /usage to display handler."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)
        router.display = MagicMock()

        result = router.route("/usage", "")

        router.display.show_usage.assert_called_once()

    def test_route_models_command(self):
        """Should route /models to display handler."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)
        router.display = MagicMock()

        result = router.route("/models", "openai")

        router.display.list_models.assert_called_once_with("openai")

    # =========================================================================
    # Session Command Tests
    # =========================================================================

    def test_route_context_command(self):
        """Should route /context to session manager."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)
        router.session_mgr = MagicMock()

        result = router.route("/context", "explore")

        router.session_mgr.manage_context.assert_called_once()

    def test_route_cache_command(self):
        """Should route /cache to session manager."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)
        router.session_mgr = MagicMock()

        result = router.route("/cache", "stats")

        router.session_mgr.manage_cache.assert_called_once()

    def test_route_session_command(self):
        """Should route /session to session manager."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)
        router.session_mgr = MagicMock()
        router.session_mgr.manage_session.return_value = {}

        result = router.route("/session", "save")

        router.session_mgr.manage_session.assert_called_once()

    def test_route_limits_command(self):
        """Should route /limits to session manager."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)
        router.session_mgr = MagicMock()

        result = router.route("/limits", "")

        router.session_mgr.show_rate_limits.assert_called_once()

    # =========================================================================
    # Task Command Tests
    # =========================================================================

    def test_route_plan_command_with_args(self):
        """Should route /plan to tasks handler."""
        io = MockIO(confirmations=[False])  # Don't start plan
        router = self.CommandRouter(io, self.orchestrator)
        router.tasks = MagicMock()
        router.tasks.plan_task.return_value = []

        result = router.route("/plan", "create a feature")

        router.tasks.plan_task.assert_called_once_with("create a feature")

    def test_route_plan_command_no_args_shows_usage(self):
        """Should show usage when /plan called without args."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)

        result = router.route("/plan", "")

        output = io.get_output()
        assert "Usage:" in output

    def test_route_reason_command(self):
        """Should route /reason to tasks handler."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)
        router.tasks = MagicMock()

        result = router.route("/reason", "why is the sky blue")

        router.tasks.reason.assert_called_once_with("why is the sky blue")

    def test_route_agent_command(self):
        """Should route /agent to agent manager."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)
        router.agent_mgr = MagicMock()

        result = router.route("/agent", "implement feature")

        router.agent_mgr.run_agent.assert_called_once()

    def test_route_agent_no_args_shows_usage(self):
        """Should show usage when /agent called without args."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)

        result = router.route("/agent", "")

        output = io.get_output()
        assert "Usage:" in output

    # =========================================================================
    # Multi-Provider Command Tests
    # =========================================================================

    def test_route_synthesize_command(self):
        """Should route /synthesize to multiprovider."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)
        router.multiprovider = MagicMock()

        result = router.route("/synthesize", "")

        router.multiprovider.synthesize_mode.assert_called_once()

    def test_route_delegate_command(self):
        """Should route /delegate to multiprovider."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)
        router.multiprovider = MagicMock()

        result = router.route("/delegate", "openai test")

        router.multiprovider.delegate_mode.assert_called_once()

    # =========================================================================
    # Smart Query Command Tests
    # =========================================================================

    def test_route_smart_command_with_query(self):
        """Should route /smart with query to smart handler."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)
        router.smart = MagicMock()

        result = router.route("/smart", "search for something")

        router.smart.smart_query.assert_called_once_with("search for something")

    def test_route_smart_toggle(self):
        """Should toggle smart mode when /smart toggle."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)
        router.smart_mode = False

        result = router.route("/smart", "toggle")

        assert router.smart_mode is True

    def test_route_smart_no_args_shows_status(self):
        """Should show status when /smart called without args."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)
        router.smart_mode = True

        result = router.route("/smart", "")

        output = io.get_output()
        assert "Smart" in output or "smart" in output

    # =========================================================================
    # Codebase Command Tests
    # =========================================================================

    def test_route_explore_command(self):
        """Should route /explore to codebase handler."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)
        router.codebase = MagicMock()

        result = router.route("/explore", "/path/to/dir")

        router.codebase.explore_codebase.assert_called_once()

    # =========================================================================
    # Task Router Command Tests
    # =========================================================================

    def test_route_classify_command(self):
        """Should route /classify to task router."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)
        router.task_router = MagicMock()

        result = router.route("/classify", "write a function")

        router.task_router.handle_classify_only.assert_called_once_with("write a function")

    def test_route_classify_no_args_shows_usage(self):
        """Should show usage when /classify without args."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)

        result = router.route("/classify", "")

        output = io.get_output()
        assert "Usage:" in output

    # =========================================================================
    # State Command Tests
    # =========================================================================

    def test_route_clear_command(self):
        """Should clear conversation history on /clear."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)
        router.conversation_history = [{"role": "user", "content": "test"}]

        result = router.route("/clear", "")

        assert router.conversation_history == []
        output = io.get_output()
        assert "cleared" in output.lower()

    def test_route_autoexec_toggle(self):
        """Should toggle auto_execute_tasks on /autoexec."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)
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
        router = self.CommandRouter(io, self.orchestrator)
        router.multiline_mode = True

        result = router.route("/ml", "")

        assert router.multiline_mode is False
        output = io.get_output()
        assert "Multiline" in output

    def test_route_auto_toggle(self):
        """Should toggle auto_route_mode on /auto."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)
        router.auto_route_mode = False

        result = router.route("/auto", "")

        assert router.auto_route_mode is True
        output = io.get_output()
        assert "Auto-routing" in output or "routing" in output.lower()

    def test_route_auto_status(self):
        """Should show routing status on /auto status."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)
        router.task_router = MagicMock()

        result = router.route("/auto", "status")

        router.task_router.handle_route_status.assert_called_once()

    def test_route_auto_history(self):
        """Should show routing history on /auto history."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)
        router.task_router = MagicMock()

        result = router.route("/auto", "history")

        router.task_router.handle_route_history.assert_called_once()

    # =========================================================================
    # Tasks List Command Tests
    # =========================================================================

    def test_route_tasks_shows_plan(self):
        """Should show task list when plan active."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)
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
        router = self.CommandRouter(io, self.orchestrator)
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
        router = self.CommandRouter(io, self.orchestrator)
        router.display = MagicMock()
        router.auto_save = False

        result = router.route("/quit", "")

        assert result is False

    def test_route_exit_returns_false(self):
        """Should return False on /exit to exit loop."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)
        router.display = MagicMock()
        router.auto_save = False

        result = router.route("/exit", "")

        assert result is False

    def test_route_q_returns_false(self):
        """Should return False on /q to exit loop."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)
        router.display = MagicMock()
        router.auto_save = False

        result = router.route("/q", "")

        assert result is False

    def test_quit_auto_saves_session(self):
        """Should auto-save session on quit when enabled."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)
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
        router = self.CommandRouter(io, self.orchestrator)
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
        router = self.CommandRouter(io, self.orchestrator)

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
        router = self.CommandRouter(io, self.orchestrator)

        result = router.route("/xyz", "")

        assert result is True

    def test_unknown_command_suggests_help(self):
        """Should suggest /help for unknown command."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)

        result = router.route("/badcmd", "")

        output = io.get_output()
        assert "/help" in output

    # =========================================================================
    # Command Alias Tests
    # =========================================================================

    def test_multiline_aliases(self):
        """Should accept /paste and /multiline as /ml aliases."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)
        router.multiline_mode = True

        router.route("/paste", "")
        assert router.multiline_mode is False

        router.route("/multiline", "")
        assert router.multiline_mode is True

    def test_auto_aliases(self):
        """Should accept /route and /autoroute as /auto aliases."""
        io = MockIO()
        router = self.CommandRouter(io, self.orchestrator)
        router.auto_route_mode = False

        router.route("/route", "")
        assert router.auto_route_mode is True

        router.route("/autoroute", "")
        assert router.auto_route_mode is False


class TestCommandRouterModuleStructure:
    """Tests for command_router module structure."""

    def test_module_imports_successfully(self):
        """Module should import without errors."""
        from src.cli import command_router
        assert command_router is not None

    def test_command_router_class_exists(self):
        """CommandRouter class should exist."""
        from src.cli.command_router import CommandRouter
        assert CommandRouter is not None

    def test_has_route_method(self):
        """CommandRouter should have route method."""
        from src.cli.command_router import CommandRouter
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        router = CommandRouter(io, orchestrator)

        assert hasattr(router, 'route')
        assert callable(router.route)

    def test_route_method_signature(self):
        """route() should accept command and args parameters."""
        import inspect
        from src.cli.command_router import CommandRouter

        sig = inspect.signature(CommandRouter.route)
        params = list(sig.parameters.keys())

        assert 'cmd' in params or 'command' in params
        assert 'args' in params

    def test_has_required_state_attributes(self):
        """Should have required state attributes."""
        from src.cli.command_router import CommandRouter
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        router = CommandRouter(io, orchestrator)

        # State that router manages
        assert hasattr(router, 'conversation_history')
        assert hasattr(router, 'multiline_mode')
        assert hasattr(router, 'auto_route_mode')
        assert hasattr(router, 'smart_mode')
        assert hasattr(router, 'auto_save')
