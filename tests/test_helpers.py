"""
Tests for test helper classes and utilities.

TDD: Tests written first to define the expected behavior of test helpers.
"""

import pytest
from unittest.mock import Mock, MagicMock
from pathlib import Path


class TestMockIOExisting:
    """Tests for existing MockIO functionality."""

    def test_mock_io_captures_output(self):
        """MockIO should capture echo output."""
        from tests.helpers import MockIO

        io = MockIO()
        io.echo("Hello world")

        assert "Hello world" in io.get_output()

    def test_mock_io_captures_styled_output(self):
        """MockIO should capture styled output with metadata."""
        from tests.helpers import MockIO

        io = MockIO()
        io.secho("Error message", fg="red", bold=True)

        styled = io.get_styled_outputs()
        assert len(styled) == 1
        assert styled[0]['text'] == "Error message"
        assert styled[0]['fg'] == "red"
        assert styled[0]['bold'] is True

    def test_mock_io_returns_preset_inputs(self):
        """MockIO should return preset inputs in order."""
        from tests.helpers import MockIO

        io = MockIO(inputs=["first", "second"])

        assert io.prompt("Question:") == "first"
        assert io.input_line() == "second"

    def test_mock_io_returns_preset_confirmations(self):
        """MockIO should return preset confirmations in order."""
        from tests.helpers import MockIO

        io = MockIO(confirmations=[True, False])

        assert io.confirm("Continue?") is True
        assert io.confirm("Really?") is False


class TestFactoryFunctions:
    """Tests for factory functions that create common test setups."""


    def test_make_handler_test_setup_accepts_inputs(self):
        """make_handler_test_setup should accept inputs and confirmations."""
        from tests.helpers import make_handler_test_setup

        io, orch = make_handler_test_setup(
            inputs=["test input"],
            confirmations=[True, False]
        )

        assert io.prompt("Q:") == "test input"
        assert io.confirm("C1:") is True
        assert io.confirm("C2:") is False

    def test_make_handler_test_setup_configures_orchestrator(self):
        """make_handler_test_setup should accept orchestrator configuration."""
        from tests.helpers import make_handler_test_setup

        io, orch = make_handler_test_setup(
            providers=['openai', 'anthropic'],
            brain='anthropic'
        )

        assert 'openai' in orch.available_providers
        assert 'anthropic' in orch.available_providers
        assert orch.brain == 'anthropic'

    def test_make_cli_test_context_returns_full_setup(self):
        """make_cli_test_context should return io, orchestrator, and handler components."""
        from tests.helpers import make_cli_test_context

        ctx = make_cli_test_context()

        assert 'io' in ctx
        assert 'orchestrator' in ctx
        # Should also have mock components commonly used
        assert 'context' in ctx

    def test_make_cli_test_context_with_explored_context(self):
        """make_cli_test_context should configure explored context."""
        from tests.helpers import make_cli_test_context

        ctx = make_cli_test_context(context_explored=True)

        assert ctx['orchestrator'].context.is_explored() is True

    def test_make_mock_agent_result_success(self):
        """make_mock_agent_result should create success result dict."""
        from tests.helpers import make_mock_agent_result

        result = make_mock_agent_result(
            success=True,
            result="Task completed",
            iterations=3
        )

        assert result['success'] is True
        assert result['result'] == "Task completed"
        assert result['iterations'] == 3
        assert 'audit_log' in result

    def test_make_mock_agent_result_failure(self):
        """make_mock_agent_result should create failure result dict."""
        from tests.helpers import make_mock_agent_result

        result = make_mock_agent_result(
            success=False,
            result="Task incomplete"
        )

        assert result['success'] is False
        assert result['result'] == "Task incomplete"

    def test_make_mock_agent_result_with_audit_log(self):
        """make_mock_agent_result should accept custom audit log."""
        from tests.helpers import make_mock_agent_result

        audit_log = [
            {'timestamp': '2024-01-01', 'action': 'write_file', 'approved': True}
        ]
        result = make_mock_agent_result(audit_log=audit_log)

        assert result['audit_log'] == audit_log


class TestVerificationHelpers:
    """Tests for behavior verification helper functions."""

    def test_assert_output_contains_passes_when_found(self):
        """assert_output_contains should pass when text is in output."""
        from tests.helpers import MockIO, assert_output_contains

        io = MockIO()
        io.echo("Hello world")

        # Should not raise
        assert_output_contains(io, "Hello")
        assert_output_contains(io, "world")

    def test_assert_output_contains_fails_when_not_found(self):
        """assert_output_contains should fail when text is not in output."""
        from tests.helpers import MockIO, assert_output_contains

        io = MockIO()
        io.echo("Hello world")

        with pytest.raises(AssertionError) as exc_info:
            assert_output_contains(io, "goodbye")

        assert "goodbye" in str(exc_info.value)
        assert "not found" in str(exc_info.value).lower()

    def test_assert_output_not_contains_passes_when_absent(self):
        """assert_output_not_contains should pass when text is absent."""
        from tests.helpers import MockIO, assert_output_not_contains

        io = MockIO()
        io.echo("Hello world")

        # Should not raise
        assert_output_not_contains(io, "goodbye")

    def test_assert_output_not_contains_fails_when_present(self):
        """assert_output_not_contains should fail when text is present."""
        from tests.helpers import MockIO, assert_output_not_contains

        io = MockIO()
        io.echo("Hello world")

        with pytest.raises(AssertionError) as exc_info:
            assert_output_not_contains(io, "world")

        assert "world" in str(exc_info.value)

    def test_assert_styled_with_passes_for_matching_style(self):
        """assert_styled_with should pass when text has matching style."""
        from tests.helpers import MockIO, assert_styled_with

        io = MockIO()
        io.secho("Error message", fg="red", bold=True)

        # Should not raise
        assert_styled_with(io, "Error message", fg="red", bold=True)

    def test_assert_styled_with_passes_for_partial_match(self):
        """assert_styled_with should pass when only some styles are checked."""
        from tests.helpers import MockIO, assert_styled_with

        io = MockIO()
        io.secho("Warning", fg="yellow", bold=False)

        # Should not raise - only checking fg
        assert_styled_with(io, "Warning", fg="yellow")

    def test_assert_styled_with_fails_for_wrong_color(self):
        """assert_styled_with should fail when color doesn't match."""
        from tests.helpers import MockIO, assert_styled_with

        io = MockIO()
        io.secho("Error", fg="green")

        with pytest.raises(AssertionError) as exc_info:
            assert_styled_with(io, "Error", fg="red")

        assert "red" in str(exc_info.value)

    def test_assert_styled_with_fails_for_wrong_bold(self):
        """assert_styled_with should fail when bold doesn't match."""
        from tests.helpers import MockIO, assert_styled_with

        io = MockIO()
        io.secho("Title", bold=False)

        with pytest.raises(AssertionError) as exc_info:
            assert_styled_with(io, "Title", bold=True)

    def test_assert_styled_with_substring_match(self):
        """assert_styled_with should match substrings in text."""
        from tests.helpers import MockIO, assert_styled_with

        io = MockIO()
        io.secho("Success: Task completed", fg="green")

        # Should match substring
        assert_styled_with(io, "Success", fg="green")

    def test_assert_has_error_output_passes_for_red_text(self):
        """assert_has_error_output should pass when red-colored output exists."""
        from tests.helpers import MockIO, assert_has_error_output

        io = MockIO()
        io.secho("Error occurred", fg="red")

        # Should not raise
        assert_has_error_output(io)

    def test_assert_has_error_output_fails_when_no_red(self):
        """assert_has_error_output should fail when no red output exists."""
        from tests.helpers import MockIO, assert_has_error_output

        io = MockIO()
        io.secho("All good", fg="green")

        with pytest.raises(AssertionError) as exc_info:
            assert_has_error_output(io)

        assert "error" in str(exc_info.value).lower()

    def test_assert_has_success_output_passes_for_green_text(self):
        """assert_has_success_output should pass when green-colored output exists."""
        from tests.helpers import MockIO, assert_has_success_output

        io = MockIO()
        io.secho("Success!", fg="green")

        # Should not raise
        assert_has_success_output(io)

    def test_assert_has_success_output_fails_when_no_green(self):
        """assert_has_success_output should fail when no green output exists."""
        from tests.helpers import MockIO, assert_has_success_output

        io = MockIO()
        io.secho("Error!", fg="red")

        with pytest.raises(AssertionError) as exc_info:
            assert_has_success_output(io)

    def test_assert_has_warning_output_passes_for_yellow_text(self):
        """assert_has_warning_output should pass when yellow-colored output exists."""
        from tests.helpers import MockIO, assert_has_warning_output

        io = MockIO()
        io.secho("Warning!", fg="yellow")

        # Should not raise
        assert_has_warning_output(io)

    def test_assert_has_warning_output_fails_when_no_yellow(self):
        """assert_has_warning_output should fail when no yellow output exists."""
        from tests.helpers import MockIO, assert_has_warning_output

        io = MockIO()
        io.echo("Normal text")

        with pytest.raises(AssertionError) as exc_info:
            assert_has_warning_output(io)

    def test_assert_provider_used_passes_when_used(self):
        """assert_provider_used should pass when provider was used."""
        from tests.helpers import ConfigurableTestOrchestrator, assert_provider_used

        orch = ConfigurableTestOrchestrator()
        orch.delegate(provider_name='cerebras', prompt='test')

        # Should not raise
        assert_provider_used(orch, 'cerebras')

    def test_assert_provider_used_fails_when_not_used(self):
        """assert_provider_used should fail when provider was not used."""
        from tests.helpers import ConfigurableTestOrchestrator, assert_provider_used

        orch = ConfigurableTestOrchestrator()
        orch.delegate(provider_name='groq', prompt='test')

        with pytest.raises(AssertionError) as exc_info:
            assert_provider_used(orch, 'cerebras')

        assert "cerebras" in str(exc_info.value)

    def test_assert_provider_used_with_count(self):
        """assert_provider_used should verify exact call count when specified."""
        from tests.helpers import ConfigurableTestOrchestrator, assert_provider_used

        orch = ConfigurableTestOrchestrator()
        orch.delegate(provider_name='cerebras', prompt='test1')
        orch.delegate(provider_name='cerebras', prompt='test2')

        # Should pass
        assert_provider_used(orch, 'cerebras', count=2)

        # Should fail
        with pytest.raises(AssertionError):
            assert_provider_used(orch, 'cerebras', count=3)

    def test_assert_delegate_called_with_passes_for_matching_prompt(self):
        """assert_delegate_called_with should pass when prompt matches."""
        from tests.helpers import ConfigurableTestOrchestrator, assert_delegate_called_with

        orch = ConfigurableTestOrchestrator()
        orch.delegate(prompt='Find the bug in auth.py')

        # Should not raise
        assert_delegate_called_with(orch, prompt_contains='bug')
        assert_delegate_called_with(orch, prompt_contains='auth.py')

    def test_assert_delegate_called_with_fails_for_no_match(self):
        """assert_delegate_called_with should fail when no call matches."""
        from tests.helpers import ConfigurableTestOrchestrator, assert_delegate_called_with

        orch = ConfigurableTestOrchestrator()
        orch.delegate(prompt='Hello world')

        with pytest.raises(AssertionError):
            assert_delegate_called_with(orch, prompt_contains='goodbye')

    def test_get_styled_by_color_filters_correctly(self):
        """get_styled_by_color should return only outputs with specified color."""
        from tests.helpers import MockIO, get_styled_by_color

        io = MockIO()
        io.secho("Error 1", fg="red")
        io.secho("Success", fg="green")
        io.secho("Error 2", fg="red")

        red_outputs = get_styled_by_color(io, "red")

        assert len(red_outputs) == 2
        assert red_outputs[0]['text'] == "Error 1"
        assert red_outputs[1]['text'] == "Error 2"


class TestOrchestratorHelpers:
    """Tests for orchestrator-related helper functions."""

    def test_make_delegate_response_creates_response(self):
        """make_delegate_response should create properly structured response."""
        from tests.helpers import make_delegate_response

        response = make_delegate_response(
            content="Test response",
            provider="openai",
            tokens_used=100
        )

        assert response.content == "Test response"
        assert response.provider == "openai"
        assert response.tokens_used == 100

    def test_make_completion_response_creates_complete_json(self):
        """make_completion_response should create agent completion response."""
        from tests.helpers import make_completion_response

        response = make_completion_response(result="Task done")

        import json
        data = json.loads(response.content)

        assert data['action'] == 'complete'
        assert data['is_complete'] is True
        assert data['result'] == "Task done"


class TestHandlerTestSetupIntegration:
    """Integration tests for using factory functions in handler tests."""

    def test_setup_can_be_used_for_agent_manager(self):
        """Factory setup should work for testing CLIAgentManager."""
        from tests.helpers import make_handler_test_setup

        io, orch = make_handler_test_setup(
            confirmations=[False, False, False]  # dry_run, checkpoint, start
        )

        from src.cli.agent_manager import CLIAgentManager
        manager = CLIAgentManager(orch)

        manager.run_agent("test task", io=io)

        output = io.get_output()
        assert "Code Agent" in output or "test task" in output

    def test_setup_can_be_used_for_session_manager(self):
        """Factory setup should work for testing CLISessionManager."""
        from tests.helpers import make_handler_test_setup

        io, orch = make_handler_test_setup()

        from src.cli.session import CLISessionManager
        session = CLISessionManager(orch)

        session.manage_context("", io=io)

        output = io.get_output()
        assert len(output) > 0


class TestMockIOAdvanced:
    """Advanced tests for MockIO functionality."""

    def test_reset_clears_all_state(self):
        """reset() should clear all captured output and indices."""
        from tests.helpers import MockIO

        io = MockIO(inputs=["a", "b"], confirmations=[True])
        io.echo("test")
        io.secho("styled", fg="red")
        io.prompt("Q:")
        io.confirm("C:")

        io.reset()

        assert io.get_output() == ""
        assert io.get_styled_outputs() == []
        assert io._input_index == 0
        assert io._confirm_index == 0

    def test_add_input_appends_to_queue(self):
        """add_input() should append to existing inputs."""
        from tests.helpers import MockIO

        io = MockIO(inputs=["first"])
        io.add_input("second")

        assert io.prompt("Q1:") == "first"
        assert io.prompt("Q2:") == "second"

    def test_get_output_lines_splits_correctly(self):
        """get_output_lines() should split output into lines."""
        from tests.helpers import MockIO

        io = MockIO()
        io.echo("Line 1")
        io.echo("Line 2")
        io.echo("Line 3")

        lines = io.get_output_lines()

        # Each echo adds newline, so we get lines + empty string at end
        assert "Line 1" in lines
        assert "Line 2" in lines
        assert "Line 3" in lines
