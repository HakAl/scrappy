"""
Tests for CLI interactive mode module.

TDD: Tests written first for the interactive.py module which handles
the main interactive chat loop.
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from tests.helpers import MockIO, ConfigurableTestOrchestrator


from datetime import datetime
from scrappy.cli.utils.cli_factory import initialize_cli_handlers
from scrappy.cli.state_manager import PlanStateManager
from scrappy.cli.session_context import SessionContext
from scrappy.cli.input_handler import InputHandler
from scrappy.cli.logging import get_logger


def create_test_interactive_mode(io, orchestrator):
    """Helper to create InteractiveMode with all dependencies."""
    session_start = datetime.now()
    handlers = initialize_cli_handlers(orchestrator, session_start, io)

    # Import here to avoid circular imports
    from scrappy.cli.interactive import InteractiveMode
    from scrappy.cli.command_router import CommandRouter

    state_manager = PlanStateManager()
    session_context = SessionContext()
    input_handler = InputHandler(io)
    logger = get_logger('cli.interactive', io=io)

    # Create command router with all handlers
    command_router = CommandRouter(
        io=io,
        orchestrator=orchestrator,
        session_context=session_context,
        display=handlers['display'],
        session_mgr=handlers['session_mgr'],
        codebase=handlers['codebase'],
        tasks=handlers['tasks'],
        multiprovider=handlers['multiprovider'],
        smart=handlers['smart'],
        agent_mgr=handlers['agent_mgr'],
        task_router=handlers['task_router'],
        state_manager=state_manager
    )

    return InteractiveMode(
        io=io,
        orchestrator=orchestrator,
        session_context=session_context,
        state_manager=state_manager,
        input_handler=input_handler,
        command_router=command_router,
        display=handlers['display'],
        smart=handlers['smart'],
        task_router=handlers['task_router'],
        tasks=handlers['tasks'],
        logger=logger
    )


class TestInteractiveMode:
    """Tests for InteractiveMode class."""

    def setup_method(self):
        """Set up test fixtures."""
        from scrappy.cli.interactive import InteractiveMode
        self.InteractiveMode = InteractiveMode
        self.orchestrator = ConfigurableTestOrchestrator()

    # =========================================================================
    # Initialization Tests
    # =========================================================================

    def test_initializes_with_orchestrator(self):
        """Should initialize with orchestrator."""
        io = MockIO()
        mode = create_test_interactive_mode(io, self.orchestrator)

        assert mode.orchestrator is self.orchestrator

    def test_initializes_with_default_modes(self):
        """Should initialize with default mode settings."""
        io = MockIO()
        mode = create_test_interactive_mode(io, self.orchestrator)

        assert mode.session_context.smart_mode is False

    def test_initializes_with_empty_conversation(self):
        """Should initialize with empty conversation history."""
        io = MockIO()
        mode = create_test_interactive_mode(io, self.orchestrator)

        assert mode.session_context.conversation_history == []

    def test_initializes_with_auto_save_enabled(self):
        """Should initialize with auto_save enabled."""
        io = MockIO()
        mode = create_test_interactive_mode(io, self.orchestrator)

        assert mode.session_context.auto_save is True

    # =========================================================================
    # Input Processing Tests
    # =========================================================================

    def test_adds_to_conversation_history(self):
        """Should add user input to conversation history."""
        io = MockIO()
        mode = create_test_interactive_mode(io, self.orchestrator)

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.output = "Hi there"
        mock_result.metadata = {"streaming": False}
        mode.task_router.handle_auto_route_streaming_sync = MagicMock(return_value=mock_result)

        mode._process_input("hello")

        assert len(mode.session_context.conversation_history) == 2
        assert mode.session_context.conversation_history[0]['role'] == 'user'
        assert mode.session_context.conversation_history[0]['content'] == 'hello'
        assert mode.session_context.conversation_history[1]['role'] == 'assistant'

    def test_empty_input_returns_true_to_continue(self):
        """Should return True for empty input to continue loop."""
        io = MockIO()
        mode = create_test_interactive_mode(io, self.orchestrator)

        result = mode._process_input("")

        assert result is True

    def test_command_returns_router_result(self):
        """Should return router result for commands."""
        io = MockIO()
        mode = create_test_interactive_mode(io, self.orchestrator)
        mode.command_router = MagicMock()
        mode.command_router.route.return_value = False  # Exit

        result = mode._process_input("/quit")

        assert result is False

    # =========================================================================
    # Error Handling Tests
    # =========================================================================

    def test_handles_eof_error(self):
        """Should handle EOFError and auto-save."""
        io = MockIO()
        mode = create_test_interactive_mode(io, self.orchestrator)
        mode.session_context.auto_save = True
        self.orchestrator.save_session = MagicMock(return_value="/test/session.json")
        mode.display = MagicMock()

        # Simulate EOF handling
        mode._handle_eof()

        output = io.get_output()
        assert "EOF" in output or "Goodbye" in output

    def test_handles_general_exception(self):
        """Should handle general exceptions gracefully."""
        io = MockIO()
        mode = create_test_interactive_mode(io, self.orchestrator)

        # Simulate exception handling
        mode._handle_error(Exception("Test error"))

        output = io.get_output()
        assert "Error" in output
        assert "Test error" in output

    # =========================================================================
    # Session Management Tests
    # =========================================================================



class TestInteractiveModeDisplayOutput:
    """Tests for interactive mode display and output."""

    def setup_method(self):
        """Set up test fixtures."""
        from scrappy.cli.interactive import InteractiveMode
        self.InteractiveMode = InteractiveMode
        self.orchestrator = ConfigurableTestOrchestrator()

    def test_displays_response_with_metadata(self):
        """Should display response with provider/token info in verbose mode."""
        io = MockIO()
        mode = create_test_interactive_mode(io, self.orchestrator)
        mode.session_context.verbose_mode = True  # Enable verbose to show metadata

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.output = "Test response"
        mock_result.provider_used = "openai"
        mock_result.tokens_used = 150
        mock_result.execution_time = 0.5
        mock_result.metadata = {"streaming": False}
        mode.task_router.handle_auto_route_streaming_sync = MagicMock(return_value=mock_result)

        mode._process_input("test")

        output = io.get_output()
        assert "Test response" in output
        assert "openai" in output or "150" in output

    def test_displays_metadata_in_verbose_mode(self):
        """Should display metadata when verbose mode is enabled."""
        io = MockIO()
        mode = create_test_interactive_mode(io, self.orchestrator)
        mode.session_context.verbose_mode = True

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.output = "Tool result"
        mock_result.provider_used = "cerebras"
        mock_result.tokens_used = 100
        mock_result.execution_time = 0.25
        mock_result.metadata = {"streaming": False}
        mode.task_router.handle_auto_route_streaming_sync = MagicMock(return_value=mock_result)

        mode._process_input("fetch https://example.com")

        output = io.get_output()
        # Should show metadata in verbose mode
        assert "cerebras" in output or "100" in output
