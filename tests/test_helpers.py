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


    def test_make_cli_test_context_with_explored_context(self):
        """make_cli_test_context should configure explored context."""
        from tests.helpers import make_cli_test_context

        ctx = make_cli_test_context(context_explored=True)

        assert ctx['orchestrator'].context.is_explored() is True





class TestVerificationHelpers:
    """Tests for behavior verification helper functions."""


    def test_assert_output_contains_fails_when_not_found(self):
        """assert_output_contains should fail when text is not in output."""
        from tests.helpers import MockIO, assert_output_contains

        io = MockIO()
        io.echo("Hello world")

        with pytest.raises(AssertionError) as exc_info:
            assert_output_contains(io, "goodbye")

        assert "goodbye" in str(exc_info.value)
        assert "not found" in str(exc_info.value).lower()


    def test_assert_output_not_contains_fails_when_present(self):
        """assert_output_not_contains should fail when text is present."""
        from tests.helpers import MockIO, assert_output_not_contains

        io = MockIO()
        io.echo("Hello world")

        with pytest.raises(AssertionError) as exc_info:
            assert_output_not_contains(io, "world")

        assert "world" in str(exc_info.value)



    def test_assert_styled_with_fails_for_wrong_color(self):
        """assert_styled_with should fail when color doesn't match."""
        from tests.helpers import MockIO, assert_styled_with

        io = MockIO()
        io.secho("Error", fg="green")

        with pytest.raises(AssertionError) as exc_info:
            assert_styled_with(io, "Error", fg="red")

        assert "red" in str(exc_info.value)




    def test_assert_has_error_output_fails_when_no_red(self):
        """assert_has_error_output should fail when no red output exists."""
        from tests.helpers import MockIO, assert_has_error_output

        io = MockIO()
        io.secho("All good", fg="green")

        with pytest.raises(AssertionError) as exc_info:
            assert_has_error_output(io)

        assert "error" in str(exc_info.value).lower()






    def test_assert_provider_used_fails_when_not_used(self):
        """assert_provider_used should fail when provider was not used."""
        from tests.helpers import ConfigurableTestOrchestrator, assert_provider_used

        orch = ConfigurableTestOrchestrator()
        orch.delegate(provider_name='groq', prompt='test')

        with pytest.raises(AssertionError) as exc_info:
            assert_provider_used(orch, 'cerebras')

        assert "cerebras" in str(exc_info.value)




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
