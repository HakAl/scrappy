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
