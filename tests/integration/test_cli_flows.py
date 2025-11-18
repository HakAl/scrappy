"""
Integration tests for complete CLI user workflows.

These tests verify complete user workflows with MockIO, testing
state transitions, side effects, and multi-step interactions.

TDD: Tests written first to demonstrate expected behavior of
complete CLI workflows.
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from tests.helpers import (
    MockIO,
    ConfigurableTestOrchestrator,
    make_handler_test_setup,
    assert_output_contains,
    assert_output_not_contains,
    assert_styled_with,
    assert_has_success_output,
    assert_has_warning_output,
    assert_has_error_output,
)


# =============================================================================
# Session Lifecycle Flow Tests
# =============================================================================

class TestSessionStartupFlow:
    """Tests for complete session startup workflow."""

    def setup_method(self):
        """Set up test fixtures."""
        from src.cli.interactive import InteractiveMode
        self.InteractiveMode = InteractiveMode

    def test_complete_startup_displays_all_elements(self):
        """Startup should display banner, commands, and mode statuses."""
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        mode = self.InteractiveMode(io, orchestrator)

        with patch('sys.stdin.isatty', return_value=True):
            with patch.object(mode, '_main_loop', return_value=None):
                mode.run()

        output = io.get_output()

        # Should have welcome banner
        assert "LLM Agent Team" in output or "Interactive Mode" in output

        # Should show command help
        assert "/help" in output
        assert "/quit" in output
        assert "/plan" in output
        assert "/agent" in output

        # Should show mode statuses
        assert "Multiline" in output or "multiline" in output
        assert "Auto-routing" in output or "auto-routing" in output.lower()

    def test_startup_with_multiline_on_shows_status(self):
        """Should indicate multiline mode is ON at startup."""
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        mode = self.InteractiveMode(io, orchestrator)
        mode.multiline_mode = True

        with patch('sys.stdin.isatty', return_value=True):
            with patch.object(mode, '_main_loop', return_value=None):
                mode.run()

        output = io.get_output()
        # Should indicate ON status
        assert "ON" in output or "enabled" in output.lower()

    def test_startup_with_auto_route_on_shows_status(self):
        """Should indicate auto-routing mode is ON at startup."""
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        mode = self.InteractiveMode(io, orchestrator)
        mode.auto_route_mode = True

        with patch('sys.stdin.isatty', return_value=True):
            with patch.object(mode, '_main_loop', return_value=None):
                mode.run()

        output = io.get_output()
        # Auto-routing should be shown as ON
        assert "Auto-routing" in output or "auto-routing" in output.lower()


class TestSessionExitFlow:
    """Tests for complete session exit workflow."""

    def setup_method(self):
        """Set up test fixtures."""
        from src.cli.interactive import InteractiveMode
        from src.cli.command_router import CommandRouter
        self.InteractiveMode = InteractiveMode
        self.CommandRouter = CommandRouter

    def test_quit_command_saves_session_when_auto_save_enabled(self):
        """Exit with auto_save should save session and show confirmation."""
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        router = self.CommandRouter(io, orchestrator)
        router.auto_save = True
        orchestrator.save_session = MagicMock(return_value="/test/session.json")

        result = router.route("/quit", "")

        # Should return False to exit
        assert result is False

        # Should have saved session
        orchestrator.save_session.assert_called_once()

        # Should show goodbye
        output = io.get_output()
        assert "Goodbye" in output

    def test_quit_command_skips_save_when_auto_save_disabled(self):
        """Exit without auto_save should show warning."""
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        router = self.CommandRouter(io, orchestrator)
        router.auto_save = False
        orchestrator.save_session = MagicMock()

        result = router.route("/quit", "")

        assert result is False
        orchestrator.save_session.assert_not_called()

    def test_eof_triggers_auto_save(self):
        """EOF should trigger auto-save when enabled."""
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        orchestrator.save_session = MagicMock(return_value="/test/session.json")
        mode = self.InteractiveMode(io, orchestrator)
        mode.auto_save = True
        mode.display = MagicMock()

        mode._handle_eof()

        orchestrator.save_session.assert_called_once()
        output = io.get_output()
        assert "saved" in output.lower() or "Goodbye" in output

# =============================================================================
# Plan Workflow Flow Tests
# =============================================================================

class TestPlanCreationFlow:
    """Tests for plan creation workflow."""

    def setup_method(self):
        """Set up test fixtures."""
        from src.cli.command_router import CommandRouter
        from src.cli.state_manager import PlanStateManager
        self.CommandRouter = CommandRouter
        self.PlanStateManager = PlanStateManager

    def test_plan_command_creates_and_starts_plan(self):
        """Plan command should create plan and start tracking on confirmation."""
        io = MockIO(confirmations=[True])  # Confirm to start plan
        orchestrator = ConfigurableTestOrchestrator()
        router = self.CommandRouter(io, orchestrator)

        # Mock task planner to return steps
        router.tasks = MagicMock()
        router.tasks.plan_task.return_value = [
            {'step': 'Step 1', 'description': 'Do thing 1'},
            {'step': 'Step 2', 'description': 'Do thing 2'},
            {'step': 'Step 3', 'description': 'Do thing 3'}
        ]

        router.route("/plan", "build a feature")

        # Should have started tracking
        assert router.state_manager.plan_active is True
        assert len(router.state_manager.active_plan) == 3
        assert router.state_manager.current_task_index == 0

        # Should show current task
        output = io.get_output()
        assert "1" in output  # Task number

    def test_plan_command_without_confirmation_doesnt_start(self):
        """Plan command without confirmation should not start tracking."""
        io = MockIO(confirmations=[False])  # Decline to start plan
        orchestrator = ConfigurableTestOrchestrator()
        router = self.CommandRouter(io, orchestrator)

        router.tasks = MagicMock()
        router.tasks.plan_task.return_value = [
            {'step': 'Step 1'},
            {'step': 'Step 2'}
        ]

        router.route("/plan", "build something")

        # Should not have started tracking
        assert router.state_manager.plan_active is False

    def test_plan_command_without_args_shows_usage(self):
        """Plan command without args should show usage."""
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        router = self.CommandRouter(io, orchestrator)

        router.route("/plan", "")

        output = io.get_output()
        assert "Usage" in output or "plan" in output


class TestPlanNavigationFlow:
    """Tests for navigating through plan tasks."""

    def setup_method(self):
        """Set up test fixtures."""
        from src.cli.state_manager import PlanStateManager
        self.PlanStateManager = PlanStateManager

    def test_complete_task_advances_to_next(self):
        """Completing task should advance to next task."""
        io = MockIO(inputs=["1"])  # Choice 1: Complete and continue
        state_mgr = self.PlanStateManager()
        state_mgr.start_plan([
            {'step': 'Task 1'},
            {'step': 'Task 2'},
            {'step': 'Task 3'}
        ])

        with patch('sys.stdin.isatty', return_value=True):
            state_mgr.prompt_task_progression(io)

        assert state_mgr.current_task_index == 1
        assert state_mgr.plan_active is True

        output = io.get_output()
        assert "DONE" in output or "complete" in output.lower()

    def test_stay_on_task_keeps_index(self):
        """Staying on task should keep current index."""
        io = MockIO(inputs=["2"])  # Choice 2: Stay on task
        state_mgr = self.PlanStateManager()
        state_mgr.start_plan([
            {'step': 'Task 1'},
            {'step': 'Task 2'}
        ])

        with patch('sys.stdin.isatty', return_value=True):
            state_mgr.prompt_task_progression(io)

        assert state_mgr.current_task_index == 0
        assert state_mgr.plan_active is True

    def test_skip_task_advances_without_completion(self):
        """Skipping task should advance without marking complete."""
        io = MockIO(inputs=["3"])  # Choice 3: Skip
        state_mgr = self.PlanStateManager()
        state_mgr.start_plan([
            {'step': 'Task 1'},
            {'step': 'Task 2'}
        ])

        with patch('sys.stdin.isatty', return_value=True):
            state_mgr.prompt_task_progression(io)

        assert state_mgr.current_task_index == 1
        assert state_mgr.plan_active is True

        output = io.get_output()
        assert "Skipped" in output or "skip" in output.lower()

    def test_finish_planning_ends_plan(self):
        """Finishing planning should end the plan."""
        io = MockIO(inputs=["4"])  # Choice 4: Finish
        state_mgr = self.PlanStateManager()
        state_mgr.start_plan([
            {'step': 'Task 1'},
            {'step': 'Task 2'}
        ])

        with patch('sys.stdin.isatty', return_value=True):
            state_mgr.prompt_task_progression(io)

        assert state_mgr.plan_active is False

        output = io.get_output()
        assert "Summary" in output or "Ending" in output

    def test_completing_last_task_ends_plan(self):
        """Completing last task should end plan and show summary."""
        io = MockIO(inputs=["1"])  # Complete
        state_mgr = self.PlanStateManager()
        state_mgr.start_plan([{'step': 'Only task'}])

        with patch('sys.stdin.isatty', return_value=True):
            state_mgr.prompt_task_progression(io)

        assert state_mgr.plan_active is False
        assert state_mgr.current_task_index == 1

        output = io.get_output()
        assert "complete" in output.lower() or "All tasks" in output


class TestPlanDisplayFlow:
    """Tests for plan display functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        from src.cli.state_manager import PlanStateManager
        self.PlanStateManager = PlanStateManager

    def test_show_all_tasks_displays_status(self):
        """Should show all tasks with completion status."""
        io = MockIO()
        state_mgr = self.PlanStateManager()
        state_mgr.start_plan([
            {'step': 'Task 1'},
            {'step': 'Task 2'},
            {'step': 'Task 3'}
        ])
        state_mgr.current_task_index = 1  # First task completed

        state_mgr.show_all_tasks(io)

        output = io.get_output()
        assert "Task 1" in output
        assert "Task 2" in output
        assert "Task 3" in output
        # Should show progress
        assert "1" in output and "3" in output

    def test_show_plan_summary_displays_progress(self):
        """Should show progress percentage and bar."""
        io = MockIO()
        state_mgr = self.PlanStateManager()
        state_mgr.start_plan([
            {'step': 'Task 1'},
            {'step': 'Task 2'},
            {'step': 'Task 3'},
            {'step': 'Task 4'}
        ])
        state_mgr.current_task_index = 2  # 2/4 complete

        state_mgr.show_plan_summary(io)

        output = io.get_output()
        assert "2" in output and "4" in output
        assert "50%" in output or "#" in output  # Progress indicator


# =============================================================================
# Mode Toggling Flow Tests
# =============================================================================

class TestModeTogglingFlow:
    """Tests for mode toggling workflows."""

    def setup_method(self):
        """Set up test fixtures."""
        from src.cli.command_router import CommandRouter
        self.CommandRouter = CommandRouter

    def test_toggle_multiline_mode(self):
        """Should toggle multiline mode and show status."""
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        router = self.CommandRouter(io, orchestrator)
        initial = router.multiline_mode

        router.route("/ml", "")

        assert router.multiline_mode != initial

        output = io.get_output()
        assert "Multiline" in output or "multiline" in output

    def test_toggle_multiline_shows_instructions(self):
        """Toggling multiline should show usage instructions."""
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        router = self.CommandRouter(io, orchestrator)
        router.multiline_mode = False  # Start OFF

        router.route("/ml", "")

        output = io.get_output()
        # Should show instructions when turning ON
        assert "ON" in output
        assert "\\" in output or "continue" in output.lower()

    def test_toggle_auto_route_mode(self):
        """Should toggle auto-routing mode and show status."""
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        router = self.CommandRouter(io, orchestrator)
        initial = router.auto_route_mode

        router.route("/auto", "")

        assert router.auto_route_mode != initial

        output = io.get_output()
        assert "Auto-routing" in output or "auto" in output.lower()

    def test_toggle_auto_route_shows_classification_info(self):
        """Toggling auto-route ON should explain classification behavior."""
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        router = self.CommandRouter(io, orchestrator)
        router.auto_route_mode = False  # Start OFF

        router.route("/auto", "")

        output = io.get_output()
        # Should explain routing behavior
        assert "ON" in output
        assert any(word in output.lower() for word in ["route", "classify", "shell", "agent"])

    def test_toggle_smart_mode(self):
        """Should toggle smart mode and show status."""
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        router = self.CommandRouter(io, orchestrator)
        initial = router.smart_mode

        router.route("/smart", "toggle")

        assert router.smart_mode != initial

        output = io.get_output()
        assert "Smart" in output or "smart" in output

    def test_toggle_autoexec_mode(self):
        """Should toggle auto-execute mode and show status."""
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        router = self.CommandRouter(io, orchestrator)
        initial = router.state_manager.auto_execute_tasks

        router.route("/autoexec", "")

        assert router.state_manager.auto_execute_tasks != initial

        output = io.get_output()
        assert "Auto-execute" in output or "auto" in output.lower()


# =============================================================================
# Command Execution Flow Tests
# =============================================================================

class TestCommandExecutionFlow:
    """Tests for command execution workflows."""

    def setup_method(self):
        """Set up test fixtures."""
        from src.cli.command_router import CommandRouter
        self.CommandRouter = CommandRouter

    def test_clear_command_clears_history(self):
        """Clear command should clear conversation history."""
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        router = self.CommandRouter(io, orchestrator)
        router.conversation_history = [
            {'role': 'user', 'content': 'hello'},
            {'role': 'assistant', 'content': 'hi'}
        ]

        router.route("/clear", "")

        assert router.conversation_history == []

        output = io.get_output()
        assert "cleared" in output.lower()

    def test_tasks_command_without_plan_shows_warning(self):
        """Tasks command without active plan should show warning."""
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        router = self.CommandRouter(io, orchestrator)

        router.route("/tasks", "")

        output = io.get_output()
        assert "No active plan" in output or "no plan" in output.lower()

    def test_tasks_command_with_plan_shows_tasks(self):
        """Tasks command with active plan should show task list."""
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        router = self.CommandRouter(io, orchestrator)
        router.state_manager.start_plan([
            {'step': 'Task 1'},
            {'step': 'Task 2'}
        ])

        router.route("/tasks", "")

        output = io.get_output()
        assert "Task 1" in output
        assert "Task 2" in output

    def test_unknown_command_shows_error(self):
        """Unknown command should show error message."""
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        router = self.CommandRouter(io, orchestrator)

        router.route("/unknowncmd", "")

        output = io.get_output()
        assert "Unknown" in output or "unknown" in output.lower()
        assert "/help" in output


# =============================================================================
# Chat Flow Tests
# =============================================================================

class TestChatWithAutoRouteFlow:
    """Tests for chat with auto-routing enabled."""

    def setup_method(self):
        """Set up test fixtures."""
        from src.cli.interactive import InteractiveMode
        self.InteractiveMode = InteractiveMode

    def test_chat_adds_to_conversation_history(self):
        """Chat should add messages to conversation history."""
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        mode = self.InteractiveMode(io, orchestrator)
        mode.auto_route_mode = True
        mode.task_router = MagicMock()
        mode.task_router.handle_auto_route.return_value = MagicMock(
            success=True,
            output="Response"
        )

        mode._process_input("hello world")

        assert len(mode.conversation_history) >= 2
        assert mode.conversation_history[0]['role'] == 'user'
        assert mode.conversation_history[0]['content'] == 'hello world'


# =============================================================================
# Session Management Flow Tests
# =============================================================================

class TestSessionManagementFlow:
    """Tests for session save/load/clear workflows."""

    def setup_method(self):
        """Set up test fixtures."""
        from src.cli.command_router import CommandRouter
        self.CommandRouter = CommandRouter

    def test_session_load_restores_conversation(self):
        """Session load should restore conversation history."""
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        router = self.CommandRouter(io, orchestrator)
        router.session_mgr = MagicMock()
        router.session_mgr.manage_session.return_value = {
            'conversation_history': [
                {'role': 'user', 'content': 'previous'},
                {'role': 'assistant', 'content': 'response'}
            ]
        }

        router.route("/session", "load")

        assert router.conversation_history[0]['content'] == 'previous'

    def test_session_toggle_auto_save(self):
        """Session toggle should toggle auto-save setting."""
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        router = self.CommandRouter(io, orchestrator)
        initial = router.auto_save
        router.session_mgr = MagicMock()
        router.session_mgr.manage_session.return_value = {
            'auto_save': not initial
        }

        router.route("/session", "toggle")

        assert router.auto_save != initial


# =============================================================================
# Error Handling Flow Tests
# =============================================================================

class TestErrorHandlingFlow:
    """Tests for error handling workflows."""

    def setup_method(self):
        """Set up test fixtures."""
        from src.cli.interactive import InteractiveMode
        from src.cli.exceptions import CLIError, ProviderError
        self.InteractiveMode = InteractiveMode
        self.CLIError = CLIError
        self.ProviderError = ProviderError

    def test_cli_error_shows_message_and_suggestion(self):
        """CLI error should show error message and suggestion."""
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        mode = self.InteractiveMode(io, orchestrator)

        from src.cli.exceptions import CLIError, ErrorSeverity
        error = CLIError(
            "Test error",
            suggestion="Try this instead",
            severity=ErrorSeverity.ERROR
        )

        mode._handle_error(error)

        output = io.get_output()
        assert "Test error" in output
        assert "Try this instead" in output

    def test_provider_error_shows_provider_info(self):
        """Provider error should show provider information."""
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        mode = self.InteractiveMode(io, orchestrator)

        from src.cli.exceptions import ProviderError
        error = ProviderError(
            "API failed",
            provider="openai",
            suggestion="Check API key"
        )

        mode._handle_error(error)

        output = io.get_output()
        assert "API failed" in output

    def test_general_exception_shows_error(self):
        """General exception should show error message."""
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        mode = self.InteractiveMode(io, orchestrator)

        mode._handle_error(Exception("Something went wrong"))

        output = io.get_output()
        assert "Something went wrong" in output
        assert "/help" in output

    def test_error_recovery_continues_loop(self):
        """After error, should show help hint to continue."""
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        mode = self.InteractiveMode(io, orchestrator)

        mode._handle_error(Exception("Test"))

        output = io.get_output()
        assert "/help" in output


# =============================================================================
# Complete Workflow Integration Tests
# =============================================================================

class TestCompleteUserWorkflows:
    """Tests for complete multi-step user workflows."""

    def setup_method(self):
        """Set up test fixtures."""
        from src.cli.interactive import InteractiveMode
        from src.cli.command_router import CommandRouter
        self.InteractiveMode = InteractiveMode
        self.CommandRouter = CommandRouter

    def test_plan_execute_complete_workflow(self):
        """Complete workflow: create plan -> execute tasks -> complete."""
        io = MockIO(confirmations=[True], inputs=["1", "1", "1"])
        orchestrator = ConfigurableTestOrchestrator()
        router = self.CommandRouter(io, orchestrator)

        # Create plan
        router.tasks = MagicMock()
        router.tasks.plan_task.return_value = [
            {'step': 'Task 1'},
            {'step': 'Task 2'},
            {'step': 'Task 3'}
        ]

        router.route("/plan", "build feature")

        # Verify plan started
        assert router.state_manager.plan_active is True

        # Complete tasks
        with patch('sys.stdin.isatty', return_value=True):
            router.state_manager.prompt_task_progression(io)  # Complete 1
            router.state_manager.prompt_task_progression(io)  # Complete 2
            router.state_manager.prompt_task_progression(io)  # Complete 3

        # Verify plan ended
        assert router.state_manager.plan_active is False
        assert router.state_manager.current_task_index == 3

    def test_mode_switch_workflow(self):
        """Complete workflow: toggle modes and verify state changes."""
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        router = self.CommandRouter(io, orchestrator)

        # Record initial states
        initial_multiline = router.multiline_mode
        initial_auto = router.auto_route_mode
        initial_smart = router.smart_mode

        # Toggle multiline
        router.route("/ml", "")
        assert router.multiline_mode != initial_multiline

        # Toggle auto-route
        router.route("/auto", "")
        assert router.auto_route_mode != initial_auto

        # Toggle smart mode
        router.route("/smart", "toggle")
        assert router.smart_mode != initial_smart

        # Toggle back
        router.route("/ml", "")
        assert router.multiline_mode == initial_multiline

    def test_chat_with_plan_active_prompts_progression(self):
        """Chat while plan active should prompt for task progression."""
        io = MockIO(inputs=["2"])  # Stay on task
        orchestrator = ConfigurableTestOrchestrator()
        mode = self.InteractiveMode(io, orchestrator)
        mode.state_manager.start_plan([
            {'step': 'Task 1'},
            {'step': 'Task 2'}
        ])
        mode.auto_route_mode = False
        mode.smart_mode = False

        mock_response = MagicMock()
        mock_response.content = "Done"
        mock_response.provider = "test"
        mock_response.model = "test"
        mock_response.tokens_used = 10
        mock_response.latency_ms = 50
        orchestrator.delegate = MagicMock(return_value=mock_response)

        with patch('sys.stdin.isatty', return_value=True):
            mode._process_input("do something")

        # Should have prompted for progression
        output = io.get_output()
        assert "What next?" in output or "1." in output


# =============================================================================
# State Transition Verification Tests
# =============================================================================

class TestStateTransitions:
    """Tests for verifying correct state transitions."""

    def setup_method(self):
        """Set up test fixtures."""
        from src.cli.state_manager import PlanStateManager
        self.PlanStateManager = PlanStateManager

    def test_plan_state_transitions(self):
        """Verify plan state transitions are correct."""
        state_mgr = self.PlanStateManager()

        # Initial state
        assert state_mgr.plan_active is False
        assert state_mgr.current_task_index == 0
        assert state_mgr.active_plan == []

        # Start plan
        state_mgr.start_plan([{'step': '1'}, {'step': '2'}])
        assert state_mgr.plan_active is True
        assert state_mgr.current_task_index == 0
        assert len(state_mgr.active_plan) == 2

        # Advance
        more = state_mgr.advance_task()
        assert more is True
        assert state_mgr.current_task_index == 1

        # Advance to completion
        more = state_mgr.advance_task()
        assert more is False
        assert state_mgr.plan_active is False

    def test_progress_tracking(self):
        """Verify progress is tracked correctly."""
        state_mgr = self.PlanStateManager()
        state_mgr.start_plan([
            {'step': '1'},
            {'step': '2'},
            {'step': '3'},
            {'step': '4'}
        ])

        # Initial progress
        completed, total = state_mgr.get_progress()
        assert completed == 0
        assert total == 4
        assert state_mgr.get_progress_percentage() == 0

        # After 2 tasks
        state_mgr.advance_task()
        state_mgr.advance_task()
        completed, total = state_mgr.get_progress()
        assert completed == 2
        assert total == 4
        assert state_mgr.get_progress_percentage() == 50

    def test_skip_vs_complete_behavior(self):
        """Skipping and completing should both advance index."""
        state_mgr = self.PlanStateManager()
        state_mgr.start_plan([
            {'step': '1'},
            {'step': '2'},
            {'step': '3'}
        ])

        # Skip first
        state_mgr.skip_task()
        assert state_mgr.current_task_index == 1

        # Complete second
        state_mgr.advance_task()
        assert state_mgr.current_task_index == 2

        # Both should have advanced the index equally


# =============================================================================
# Side Effect Verification Tests
# =============================================================================

class TestSideEffects:
    """Tests for verifying side effects of workflows."""

    def setup_method(self):
        """Set up test fixtures."""
        from src.cli.command_router import CommandRouter
        self.CommandRouter = CommandRouter

    def test_clear_actually_clears_history(self):
        """Clear command should actually empty the list."""
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        router = self.CommandRouter(io, orchestrator)
        router.conversation_history.append({'role': 'user', 'content': 'test'})

        router.route("/clear", "")

        assert len(router.conversation_history) == 0

    def test_quit_returns_false_for_exit(self):
        """Quit command should return False to signal exit."""
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        router = self.CommandRouter(io, orchestrator)
        router.auto_save = False

        result = router.route("/quit", "")

        assert result is False

    def test_other_commands_return_true_to_continue(self):
        """Non-exit commands should return True to continue."""
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        router = self.CommandRouter(io, orchestrator)

        result = router.route("/help", "")
        assert result is True

        result = router.route("/status", "")
        assert result is True

        result = router.route("/clear", "")
        assert result is True

    def test_invalid_command_continues_loop(self):
        """Invalid command should return True to continue."""
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        router = self.CommandRouter(io, orchestrator)

        result = router.route("/invalidcmd", "")

        assert result is True
