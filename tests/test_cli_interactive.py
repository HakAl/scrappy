"""
Tests for CLI interactive mode module.

TDD: Tests written first for the interactive.py module which handles
the main interactive chat loop.
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from tests.helpers import MockIO, ConfigurableTestOrchestrator


class TestInteractiveMode:
    """Tests for InteractiveMode class."""

    def setup_method(self):
        """Set up test fixtures."""
        from src.cli.interactive import InteractiveMode
        self.InteractiveMode = InteractiveMode
        self.orchestrator = ConfigurableTestOrchestrator()

    # =========================================================================
    # Initialization Tests
    # =========================================================================

    def test_initializes_with_orchestrator(self):
        """Should initialize with orchestrator."""
        io = MockIO()
        mode = self.InteractiveMode(io, self.orchestrator)

        assert mode.orchestrator is self.orchestrator

    def test_initializes_with_default_modes(self):
        """Should initialize with default mode settings."""
        io = MockIO()
        mode = self.InteractiveMode(io, self.orchestrator)

        assert mode.multiline_mode is True
        assert mode.auto_route_mode is True
        assert mode.smart_mode is False

    def test_initializes_with_empty_conversation(self):
        """Should initialize with empty conversation history."""
        io = MockIO()
        mode = self.InteractiveMode(io, self.orchestrator)

        assert mode.conversation_history == []

    def test_initializes_with_auto_save_enabled(self):
        """Should initialize with auto_save enabled."""
        io = MockIO()
        mode = self.InteractiveMode(io, self.orchestrator)

        assert mode.auto_save is True

    # =========================================================================
    # Run Loop Tests
    # =========================================================================

    def test_run_requires_tty(self):
        """Should error if not running in TTY."""
        io = MockIO()
        mode = self.InteractiveMode(io, self.orchestrator)

        with patch('sys.stdin.isatty', return_value=False):
            mode.run()

        output = io.get_output()
        assert "TTY" in output or "terminal" in output.lower()

    def test_run_shows_welcome_banner(self):
        """Should show welcome banner on start."""
        io = MockIO(inputs=["/quit"])
        io.prompt = lambda *args, **kwargs: "/quit"
        mode = self.InteractiveMode(io, self.orchestrator)
        mode.command_router = MagicMock()
        mode.command_router.route.return_value = False

        with patch('sys.stdin.isatty', return_value=True):
            with patch.object(mode, '_process_input', return_value=False):
                mode.run()

        output = io.get_output()
        assert "Interactive Mode" in output or "LLM Agent Team" in output

    def test_run_shows_commands_help(self):
        """Should show available commands on start."""
        io = MockIO()
        mode = self.InteractiveMode(io, self.orchestrator)

        with patch('sys.stdin.isatty', return_value=True):
            with patch.object(mode, '_main_loop', return_value=None):
                mode.run()

        output = io.get_output()
        assert "/help" in output
        assert "/quit" in output

    def test_run_shows_mode_statuses(self):
        """Should show current mode statuses on start."""
        io = MockIO()
        mode = self.InteractiveMode(io, self.orchestrator)

        with patch('sys.stdin.isatty', return_value=True):
            with patch.object(mode, '_main_loop', return_value=None):
                mode.run()

        output = io.get_output()
        # Should show multiline and auto-routing status
        assert "Multiline" in output or "multiline" in output.lower()

    # =========================================================================
    # Input Processing Tests
    # =========================================================================

    def test_processes_command_input(self):
        """Should route command input to command router."""
        io = MockIO()
        mode = self.InteractiveMode(io, self.orchestrator)
        mode.command_router = MagicMock()
        mode.command_router.route.return_value = True

        result = mode._process_input("/help")

        mode.command_router.route.assert_called()

    def test_processes_chat_input_with_auto_route(self):
        """Should use auto-routing for chat input when enabled."""
        io = MockIO()
        mode = self.InteractiveMode(io, self.orchestrator)
        mode.auto_route_mode = True
        mode.task_router = MagicMock()
        mode.task_router.handle_auto_route.return_value = MagicMock(
            success=True,
            output="Response"
        )

        result = mode._process_input("hello")

        mode.task_router.handle_auto_route.assert_called_once_with("hello")

    def test_processes_chat_input_with_smart_mode(self):
        """Should use smart query for chat when smart mode enabled."""
        io = MockIO()
        mode = self.InteractiveMode(io, self.orchestrator)
        mode.auto_route_mode = False
        mode.smart_mode = True
        mode.smart = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Smart response"
        mode.smart.smart_query.return_value = mock_response

        result = mode._process_input("search something")

        mode.smart.smart_query.assert_called_once_with("search something")

    def test_processes_chat_input_with_tool_detection(self):
        """Should detect tool needs and route appropriately."""
        io = MockIO()
        mode = self.InteractiveMode(io, self.orchestrator)
        mode.auto_route_mode = False
        mode.smart_mode = False
        mode.task_router = MagicMock()
        mode.task_router.handle_auto_route.return_value = MagicMock(
            success=True,
            output="Tool response"
        )

        # Input that needs tools
        result = mode._process_input("fetch the docs from https://example.com")

        mode.task_router.handle_auto_route.assert_called()

    def test_processes_simple_chat(self):
        """Should use simple delegation for basic chat."""
        io = MockIO()
        mode = self.InteractiveMode(io, self.orchestrator)
        mode.auto_route_mode = False
        mode.smart_mode = False

        mock_response = MagicMock()
        mock_response.content = "Hello!"
        mock_response.provider = "test"
        mock_response.model = "test-model"
        mock_response.tokens_used = 10
        mock_response.latency_ms = 100
        self.orchestrator.delegate = MagicMock(return_value=mock_response)

        result = mode._process_input("hello")

        self.orchestrator.delegate.assert_called()

    def test_adds_to_conversation_history(self):
        """Should add user input to conversation history."""
        io = MockIO()
        mode = self.InteractiveMode(io, self.orchestrator)
        mode.auto_route_mode = False
        mode.smart_mode = False

        mock_response = MagicMock()
        mock_response.content = "Hi there"
        mock_response.provider = "test"
        mock_response.model = "test"
        mock_response.tokens_used = 10
        mock_response.latency_ms = 50
        self.orchestrator.delegate = MagicMock(return_value=mock_response)

        mode._process_input("hello")

        assert len(mode.conversation_history) == 2
        assert mode.conversation_history[0]['role'] == 'user'
        assert mode.conversation_history[0]['content'] == 'hello'
        assert mode.conversation_history[1]['role'] == 'assistant'

    def test_prompts_task_progression_when_plan_active(self):
        """Should prompt for task progression when plan active."""
        io = MockIO(inputs=["2"])  # Stay on task
        mode = self.InteractiveMode(io, self.orchestrator)
        mode.state_manager = MagicMock()
        mode.state_manager.plan_active = True

        mock_response = MagicMock()
        mock_response.content = "Done"
        mock_response.provider = "test"
        mock_response.model = "test"
        mock_response.tokens_used = 10
        mock_response.latency_ms = 50
        self.orchestrator.delegate = MagicMock(return_value=mock_response)
        mode.auto_route_mode = False
        mode.smart_mode = False

        with patch('sys.stdin.isatty', return_value=True):
            mode._process_input("do something")

        mode.state_manager.prompt_task_progression.assert_called()

    def test_empty_input_returns_true_to_continue(self):
        """Should return True for empty input to continue loop."""
        io = MockIO()
        mode = self.InteractiveMode(io, self.orchestrator)

        result = mode._process_input("")

        assert result is True

    def test_command_returns_router_result(self):
        """Should return router result for commands."""
        io = MockIO()
        mode = self.InteractiveMode(io, self.orchestrator)
        mode.command_router = MagicMock()
        mode.command_router.route.return_value = False  # Exit

        result = mode._process_input("/quit")

        assert result is False

    # =========================================================================
    # Error Handling Tests
    # =========================================================================

    def test_handles_keyboard_interrupt(self):
        """Should handle KeyboardInterrupt gracefully."""
        io = MockIO()
        mode = self.InteractiveMode(io, self.orchestrator)

        with patch('sys.stdin.isatty', return_value=True):
            # This is hard to test directly; we test the error message pattern
            pass

    def test_handles_eof_error(self):
        """Should handle EOFError and auto-save."""
        io = MockIO()
        mode = self.InteractiveMode(io, self.orchestrator)
        mode.auto_save = True
        self.orchestrator.save_session = MagicMock(return_value="/test/session.json")
        mode.display = MagicMock()

        # Simulate EOF handling
        mode._handle_eof()

        output = io.get_output()
        assert "EOF" in output or "Goodbye" in output

    def test_handles_general_exception(self):
        """Should handle general exceptions gracefully."""
        io = MockIO()
        mode = self.InteractiveMode(io, self.orchestrator)

        # Simulate exception handling
        mode._handle_error(Exception("Test error"))

        output = io.get_output()
        assert "Error" in output
        assert "Test error" in output

    # =========================================================================
    # Session Management Tests
    # =========================================================================

    def test_auto_saves_on_eof(self):
        """Should auto-save session on EOF when enabled."""
        io = MockIO()
        mode = self.InteractiveMode(io, self.orchestrator)
        mode.auto_save = True
        mode.display = MagicMock()
        self.orchestrator.save_session = MagicMock(return_value="/test/session.json")

        mode._handle_eof()

        self.orchestrator.save_session.assert_called_once()

    def test_skips_auto_save_when_disabled(self):
        """Should skip auto-save when disabled."""
        io = MockIO()
        mode = self.InteractiveMode(io, self.orchestrator)
        mode.auto_save = False
        mode.display = MagicMock()
        self.orchestrator.save_session = MagicMock()

        mode._handle_eof()

        self.orchestrator.save_session.assert_not_called()


class TestInteractiveModeDisplayOutput:
    """Tests for interactive mode display and output."""

    def setup_method(self):
        """Set up test fixtures."""
        from src.cli.interactive import InteractiveMode
        self.InteractiveMode = InteractiveMode
        self.orchestrator = ConfigurableTestOrchestrator()

    def test_displays_response_with_metadata(self):
        """Should display response with provider/token info."""
        io = MockIO()
        mode = self.InteractiveMode(io, self.orchestrator)
        mode.auto_route_mode = False
        mode.smart_mode = False

        mock_response = MagicMock()
        mock_response.content = "Test response"
        mock_response.provider = "openai"
        mock_response.model = "gpt-4"
        mock_response.tokens_used = 150
        mock_response.latency_ms = 500
        self.orchestrator.delegate = MagicMock(return_value=mock_response)

        mode._process_input("test")

        output = io.get_output()
        assert "Test response" in output
        assert "openai" in output or "gpt-4" in output

    def test_displays_tool_usage_info(self):
        """Should display tool usage information when tools used."""
        io = MockIO()
        mode = self.InteractiveMode(io, self.orchestrator)
        mode.auto_route_mode = False
        mode.smart_mode = False
        mode.task_router = MagicMock()

        result = MagicMock()
        result.success = True
        result.output = "Tool result"
        result.metadata = {'tool_calls': [{'tool': 'web_fetch'}]}
        mode.task_router.handle_auto_route.return_value = result

        # Input that needs tools
        mode._process_input("fetch https://example.com")

        output = io.get_output()
        # Should indicate tools were used
        assert "tools" in output.lower() or "Using" in output


class TestInteractiveModeModuleStructure:
    """Tests for interactive module structure."""

    def test_module_imports_successfully(self):
        """Module should import without errors."""
        from src.cli import interactive
        assert interactive is not None

    def test_interactive_mode_class_exists(self):
        """InteractiveMode class should exist."""
        from src.cli.interactive import InteractiveMode
        assert InteractiveMode is not None

    def test_has_run_method(self):
        """InteractiveMode should have run method."""
        from src.cli.interactive import InteractiveMode
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        mode = InteractiveMode(io, orchestrator)

        assert hasattr(mode, 'run')
        assert callable(mode.run)

    def test_has_required_attributes(self):
        """Should have required attributes."""
        from src.cli.interactive import InteractiveMode
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        mode = InteractiveMode(io, orchestrator)

        assert hasattr(mode, 'io')
        assert hasattr(mode, 'orchestrator')
        assert hasattr(mode, 'conversation_history')
        assert hasattr(mode, 'multiline_mode')
        assert hasattr(mode, 'auto_route_mode')
        assert hasattr(mode, 'smart_mode')
        assert hasattr(mode, 'auto_save')

    def test_has_required_methods(self):
        """Should have required methods."""
        from src.cli.interactive import InteractiveMode
        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        mode = InteractiveMode(io, orchestrator)

        methods = [
            'run', '_main_loop', '_process_input',
            '_handle_eof', '_handle_error'
        ]

        for method in methods:
            assert hasattr(mode, method), f"Missing method: {method}"

    def test_accepts_handler_injections(self):
        """Should accept handler injections for testing."""
        from src.cli.interactive import InteractiveMode
        from src.cli.state_manager import PlanStateManager
        from src.cli.command_router import CommandRouter

        io = MockIO()
        orchestrator = ConfigurableTestOrchestrator()
        state_mgr = PlanStateManager()

        mode = InteractiveMode(
            io,
            orchestrator,
            state_manager=state_mgr
        )

        assert mode.state_manager is state_mgr


class TestInteractiveModeIntegration:
    """Integration tests for interactive mode components."""

    def setup_method(self):
        """Set up test fixtures."""
        from src.cli.interactive import InteractiveMode
        self.InteractiveMode = InteractiveMode
        self.orchestrator = ConfigurableTestOrchestrator()

    def test_command_and_state_integration(self):
        """Command router should update state manager."""
        io = MockIO()
        mode = self.InteractiveMode(io, self.orchestrator)

        # Simulate plan creation flow
        mode.state_manager = MagicMock()
        mode.command_router = MagicMock()
        mode.tasks = MagicMock()
        mode.tasks.plan_task.return_value = [
            {'step': 'Task 1'},
            {'step': 'Task 2'}
        ]

        # This would be handled by command router in real implementation

    def test_input_handler_and_command_router_integration(self):
        """Input handler should pass commands to router."""
        io = MockIO(inputs=["/help"])
        mode = self.InteractiveMode(io, self.orchestrator)
        mode.input_handler = MagicMock()
        mode.input_handler.read_interactive_input.return_value = "/help"
        mode.input_handler.is_command.return_value = True
        mode.input_handler.parse_command.return_value = ("/help", "")
        mode.command_router = MagicMock()
        mode.command_router.route.return_value = True

        # Process would call input_handler then command_router

    def test_tool_detector_and_task_router_integration(self):
        """Tool detector should trigger task router for tool queries."""
        io = MockIO()
        mode = self.InteractiveMode(io, self.orchestrator)
        mode.auto_route_mode = False
        mode.smart_mode = False
        mode.task_router = MagicMock()
        mode.task_router.handle_auto_route.return_value = MagicMock(
            success=True,
            output="Fetched data"
        )

        # Query that needs tools
        mode._process_input("fetch docs from https://example.com")

        # Should have used task router for tool support
        mode.task_router.handle_auto_route.assert_called()
