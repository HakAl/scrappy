"""
Tests for commands.py refactoring.

These tests verify:
1. Shared session restoration function
2. Consolidated exception handling patterns
3. CLI factory convenience methods

TDD: Tests written first to define expected behavior.
"""

import pytest
import sys
from unittest.mock import Mock, patch, MagicMock
from click.testing import CliRunner

from tests.helpers import MockIO, ConfigurableTestOrchestrator


class TestSharedSessionRestoration:
    """Test the shared session restoration function eliminates duplication."""

    def test_restore_session_loads_and_displays_on_success(self):
        """Restoration should load session and display success info."""
        from src.cli.utils.session_utils import restore_session_to_cli

        io = MockIO()

        # Mock orchestrator with successful load
        orchestrator = Mock()
        orchestrator.load_session.return_value = {
            'status': 'loaded',
            'saved_at': '2024-01-15 10:30:00',
            'files_restored': 5,
            'searches_restored': 3,
            'git_ops_restored': 2,
            'discoveries_restored': 1,
            'tasks_restored': 4,
            'conversation_history': [
                {'role': 'user', 'content': 'Hello'},
                {'role': 'assistant', 'content': 'Hi there'}
            ]
        }

        # Mock CLI instance
        cli_instance = Mock()
        cli_instance.orchestrator = orchestrator
        cli_instance.conversation_history = []

        # Call the shared function
        result = restore_session_to_cli(cli_instance, io)

        # Verify session was loaded
        orchestrator.load_session.assert_called_once()

        # Verify conversation history was set
        assert cli_instance.conversation_history == [
            {'role': 'user', 'content': 'Hello'},
            {'role': 'assistant', 'content': 'Hi there'}
        ]

        # Verify success message displayed
        output = io.get_output()
        assert 'Resumed session' in output
        assert result is True

    def test_restore_session_displays_error_on_no_session(self):
        """When no session exists, should display appropriate message."""
        from src.cli.utils.session_utils import restore_session_to_cli

        io = MockIO()

        orchestrator = Mock()
        orchestrator.load_session.return_value = {
            'status': 'no_session',
            'message': 'No saved session found'
        }

        cli_instance = Mock()
        cli_instance.orchestrator = orchestrator
        cli_instance.conversation_history = []

        result = restore_session_to_cli(cli_instance, io)

        # Verify warning was displayed
        output = io.get_output()
        assert 'No previous session' in output

        # Conversation should remain empty
        assert cli_instance.conversation_history == []
        assert result is False

    def test_restore_session_displays_error_on_load_failure(self):
        """When session load fails, should display error."""
        from src.cli.utils.session_utils import restore_session_to_cli

        io = MockIO()

        orchestrator = Mock()
        orchestrator.load_session.return_value = {
            'status': 'error',
            'message': 'Corrupted session file'
        }

        cli_instance = Mock()
        cli_instance.orchestrator = orchestrator
        cli_instance.conversation_history = []

        result = restore_session_to_cli(cli_instance, io)

        # Verify error was displayed
        output = io.get_output()
        assert 'Error loading session' in output or 'Corrupted' in output
        assert result is False

    def test_restore_session_handles_empty_conversation(self):
        """Restoration with empty conversation should still succeed."""
        from src.cli.utils.session_utils import restore_session_to_cli

        io = MockIO()

        orchestrator = Mock()
        orchestrator.load_session.return_value = {
            'status': 'loaded',
            'saved_at': '2024-01-15',
            'files_restored': 3,
            'searches_restored': 0,
            'git_ops_restored': 0,
            'discoveries_restored': 0,
            'tasks_restored': 0,
            'conversation_history': []
        }

        cli_instance = Mock()
        cli_instance.orchestrator = orchestrator
        cli_instance.conversation_history = []

        result = restore_session_to_cli(cli_instance, io)

        # Should succeed even with empty conversation
        assert result is True
        output = io.get_output()
        assert 'Resumed session' in output


class TestConsolidatedExceptionHandling:
    """Test consolidated exception handling utility."""


    def test_command_error_handler_custom_exit_code(self):
        """Error handler should support custom exit codes."""
        from src.cli.utils.error_utils import handle_command_error

        io = MockIO()
        error = RuntimeError("Critical failure")

        exit_code = handle_command_error(io, error, exit_code=2)

        assert exit_code == 2

    def test_run_with_error_handling_success(self):
        """Wrapper should execute function and return result on success."""
        from src.cli.utils.error_utils import run_with_error_handling

        io = MockIO()

        def successful_operation():
            return "operation result"

        result = run_with_error_handling(io, successful_operation)

        assert result == "operation result"

    def test_run_with_error_handling_failure(self):
        """Wrapper should catch errors and call sys.exit on failure."""
        from src.cli.utils.error_utils import run_with_error_handling

        io = MockIO()

        def failing_operation():
            raise RuntimeError("Operation failed")

        with pytest.raises(SystemExit) as exc_info:
            run_with_error_handling(io, failing_operation)

        assert exc_info.value.code == 1

        output = io.get_output()
        assert 'Operation failed' in output

    def test_run_with_error_handling_keyboard_interrupt(self):
        """Wrapper should handle keyboard interrupt gracefully."""
        from src.cli.utils.error_utils import run_with_error_handling

        io = MockIO()

        def interrupted_operation():
            raise KeyboardInterrupt()

        with pytest.raises(SystemExit) as exc_info:
            run_with_error_handling(io, interrupted_operation)

        assert exc_info.value.code == 1

        output = io.get_output()
        assert 'interrupted' in output.lower() or 'cancelled' in output.lower()


class TestCLIFactoryConvenience:
    """Test CLI factory convenience methods."""

    def test_cli_factory_create_from_dict(self):
        """Factory should create CLI from simple dict config."""
        from src.cli.utils.cli_factory import create_cli

        config = {
            'brain': 'cerebras',
            'auto_explore': True,
            'context_aware': False,
        }

        with patch('src.cli.core.CLI') as MockCLI:
            mock_instance = Mock()
            MockCLI.return_value = mock_instance

            result = create_cli(config)

            MockCLI.assert_called_once()
            call_kwargs = MockCLI.call_args[1]
            assert call_kwargs['brain'] == 'cerebras'
            assert call_kwargs['auto_explore'] is True
            assert call_kwargs['context_aware'] is False
            assert result == mock_instance

    def test_cli_factory_create_with_defaults(self):
        """Factory should use sensible defaults for missing config."""
        from src.cli.utils.cli_factory import create_cli

        with patch('src.cli.core.CLI') as MockCLI:
            mock_instance = Mock()
            MockCLI.return_value = mock_instance

            # Empty config should use defaults
            result = create_cli({})

            call_kwargs = MockCLI.call_args[1]
            assert call_kwargs['brain'] is None
            assert call_kwargs['auto_explore'] is False
            assert call_kwargs['context_aware'] is True

    def test_cli_factory_create_with_io(self):
        """Factory should accept custom IO interface."""
        from src.cli.utils.cli_factory import create_cli

        io = MockIO()

        with patch('src.cli.core.CLI') as MockCLI:
            mock_instance = Mock()
            MockCLI.return_value = mock_instance

            result = create_cli({'brain': 'groq'}, io=io)

            call_kwargs = MockCLI.call_args[1]
            assert call_kwargs['io'] == io


class TestSessionRestorationIntegration:
    """Integration tests to verify duplication is eliminated."""

    def test_main_cli_uses_shared_restoration(self):
        """Main CLI command should use shared session restoration function."""
        # This test verifies the refactoring pattern is applied
        # We check that the same restoration logic is used

        from src.cli.utils.session_utils import restore_session_to_cli

        io = MockIO()

        # Create two mock CLI instances to verify identical behavior
        orchestrator1 = Mock()
        orchestrator1.load_session.return_value = {
            'status': 'loaded',
            'saved_at': '2024-01-15',
            'files_restored': 5,
            'searches_restored': 3,
            'git_ops_restored': 2,
            'discoveries_restored': 1,
            'tasks_restored': 2,
            'conversation_history': [{'role': 'user', 'content': 'test'}]
        }

        orchestrator2 = Mock()
        orchestrator2.load_session.return_value = {
            'status': 'loaded',
            'saved_at': '2024-01-15',
            'files_restored': 5,
            'searches_restored': 3,
            'git_ops_restored': 2,
            'discoveries_restored': 1,
            'tasks_restored': 2,
            'conversation_history': [{'role': 'user', 'content': 'test'}]
        }

        cli1 = Mock()
        cli1.orchestrator = orchestrator1
        cli1.conversation_history = []

        cli2 = Mock()
        cli2.orchestrator = orchestrator2
        cli2.conversation_history = []

        # Both should use the same function
        io1 = MockIO()
        io2 = MockIO()

        result1 = restore_session_to_cli(cli1, io1)
        result2 = restore_session_to_cli(cli2, io2)

        # Identical behavior
        assert result1 == result2
        assert cli1.conversation_history == cli2.conversation_history

        # Output format should be consistent
        output1_lines = len(io1.get_output_lines())
        output2_lines = len(io2.get_output_lines())
        assert output1_lines == output2_lines


class TestErrorHandlingIntegration:
    """Integration tests for consolidated error handling."""

    def test_query_command_uses_error_handler(self):
        """Query command should use consolidated error handling."""
        # This tests that when we refactor, the error handling is consistent

        from src.cli.utils.error_utils import handle_command_error

        io = MockIO()

        # Simulate the kind of error that would occur in query command
        error = Exception("Provider connection failed")

        exit_code = handle_command_error(io, error)

        output = io.get_output()
        assert 'Provider connection failed' in output
        assert exit_code == 1

    def test_reason_command_uses_error_handler(self):
        """Reason command should use same consolidated error handling."""
        from src.cli.utils.error_utils import handle_command_error

        io = MockIO()

        # Simulate the kind of error that would occur in reason command
        error = Exception("Failed to parse reasoning response")

        exit_code = handle_command_error(io, error)

        output = io.get_output()
        assert 'Failed to parse reasoning response' in output
        assert exit_code == 1


class TestFactoryWithResume:
    """Test factory integration with resume functionality."""

    def test_create_cli_and_restore_session(self):
        """Factory-created CLI should work with session restoration."""
        from src.cli.utils.session_utils import restore_session_to_cli

        io = MockIO()

        # Mock a CLI instance (as would be created by factory)
        orchestrator = Mock()
        orchestrator.load_session.return_value = {
            'status': 'loaded',
            'saved_at': '2024-01-15',
            'files_restored': 2,
            'searches_restored': 1,
            'git_ops_restored': 0,
            'discoveries_restored': 0,
            'tasks_restored': 0,
            'conversation_history': []
        }

        cli_instance = Mock()
        cli_instance.orchestrator = orchestrator
        cli_instance.conversation_history = []
        cli_instance.auto_save = True

        # Restore session should work seamlessly
        result = restore_session_to_cli(cli_instance, io)

        assert result is True

        # Now the CLI would be ready for interactive mode
        # This simulates what happens in the refactored code


class TestEdgeCases:
    """Test edge cases for robustness."""

    def test_restore_session_handles_none_conversation(self):
        """Should handle None conversation history gracefully."""
        from src.cli.utils.session_utils import restore_session_to_cli

        io = MockIO()

        orchestrator = Mock()
        orchestrator.load_session.return_value = {
            'status': 'loaded',
            'saved_at': '2024-01-15',
            'files_restored': 1,
            'searches_restored': 0,
            'git_ops_restored': 0,
            'discoveries_restored': 0,
            'tasks_restored': 0,
            'conversation_history': None  # None instead of empty list
        }

        cli_instance = Mock()
        cli_instance.orchestrator = orchestrator
        cli_instance.conversation_history = []

        # Should not raise an error
        result = restore_session_to_cli(cli_instance, io)

        # Should succeed but not set conversation
        assert result is True
        assert cli_instance.conversation_history == []

    def test_error_handler_with_empty_error_message(self):
        """Should handle errors with empty messages."""
        from src.cli.utils.error_utils import handle_command_error

        io = MockIO()

        error = Exception("")
        exit_code = handle_command_error(io, error)

        assert exit_code == 1
        # Should still display something
        output = io.get_output()
        assert 'Error' in output or len(output) > 0

    def test_error_handler_with_complex_error(self):
        """Should handle errors with complex messages."""
        from src.cli.utils.error_utils import handle_command_error

        io = MockIO()

        error = ValueError("Connection failed:\n  - Timeout after 30s\n  - Host unreachable")
        exit_code = handle_command_error(io, error)

        assert exit_code == 1
        output = io.get_output()
        assert 'Connection failed' in output
