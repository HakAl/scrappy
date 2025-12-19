"""
Tests for CLI Display, Tasks, and SmartQuery I/O dependency injection.

These tests verify that these CLI handlers accept an io: CLIIOProtocol parameter
and route all output through the io object instead of calling click directly.

TDD: These tests are written first and will fail until handlers are updated.
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime
from pathlib import Path

# Import test helpers
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.helpers import MockIO, ConfigurableTestOrchestrator


# =============================================================================
# CLIDisplay I/O Injection Tests
# =============================================================================

class TestDisplayIOInjection:
    """Tests for CLIDisplay I/O dependency injection."""

    def setup_method(self):
        """Set up test fixtures."""
        self.orchestrator = ConfigurableTestOrchestrator()
        self.session_start = datetime.now()
        self.io = MockIO()
        from scrappy.cli.display import CLIDisplay
        self.display = CLIDisplay(self.orchestrator, self.session_start, self.io)

    def test_show_help_accepts_io_parameter(self):
        """show_help() should use injected io from constructor."""
        # Should not raise TypeError
        self.display.show_help()

        # Verify output went to self.io object
        output = self.io.get_output()
        assert "Available Commands" in output


    def test_show_help_outputs_all_sections(self):
        """show_help() should output key command sections through io."""
        self.display.show_help()

        output = self.io.get_output()

        # Check key sections are present (fallback mode has condensed sections)
        assert "Chat" in output
        assert "Task" in output
        assert "Provider" in output
        assert "System" in output
        # Verify commands are shown
        assert "/help" in output
        assert "/quit" in output

    def test_show_help_command_styling(self):
        """show_help() should style command names through io."""
        self.display.show_help()

        output = self.io.get_output()

        # Commands should be present
        assert "/help" in output
        assert "/quit" in output
        assert "/plan" in output

    def test_show_status_accepts_io_parameter(self):
        """show_status() should use injected io from constructor."""
        self.display.show_status()

        output = self.io.get_output()
        assert "System Status" in output


    def test_show_status_outputs_brain_info(self):
        """show_status() should output brain info through io."""
        self.orchestrator.brain = 'anthropic'

        self.display.show_status()

        output = self.io.get_output()
        assert "Current Brain" in output
        assert "anthropic" in output

    def test_show_status_outputs_providers(self):
        """show_status() should output provider info through io."""
        self.display.show_status()

        output = self.io.get_output()
        assert "Total Providers" in output
        assert "Available" in output

    def test_show_status_outputs_session_duration(self):
        """show_status() should output session duration through io."""
        self.display.show_status()

        output = self.io.get_output()
        assert "Session Duration" in output

    def test_show_usage_accepts_io_parameter(self):
        """show_usage() should use injected io from constructor."""
        io = MockIO()
        # Create a new display instance with the test io
        from scrappy.cli.display import CLIDisplay
        display = CLIDisplay(self.orchestrator, self.session_start, io)

        display.show_usage()

        output = io.get_output()
        assert "Usage Statistics" in output


    def test_show_usage_outputs_totals(self):
        """show_usage() should output totals through io."""
        io = MockIO()
        # Create a new display instance with the test io
        from scrappy.cli.display import CLIDisplay
        display = CLIDisplay(self.orchestrator, self.session_start, io)

        # Make some delegate calls to generate usage
        self.orchestrator.delegate('cerebras', 'test')

        display.show_usage()

        output = io.get_output()
        assert "Total Tasks" in output
        assert "Session Duration" in output

    def test_show_usage_outputs_by_provider(self):
        """show_usage() should output per-provider stats through io."""
        io = MockIO()
        # Create a new display instance with the test io
        from scrappy.cli.display import CLIDisplay
        display = CLIDisplay(self.orchestrator, self.session_start, io)

        # Make delegate calls
        self.orchestrator.delegate('cerebras', 'test')
        self.orchestrator.delegate('groq', 'test')

        display.show_usage()

        output = io.get_output()
        assert "By Provider" in output



    def test_list_models_specific_provider(self):
        """list_models() with provider name should list that provider through io."""
        io = MockIO()
        from scrappy.cli.display import CLIDisplay
        display = CLIDisplay(self.orchestrator, self.session_start, io)

        from dataclasses import dataclass
        @dataclass
        class MockModel:
            model_id: str
            provider: str
            group: str
            context_length: int = 8192
            rpd: int = 1000

        mock_models = [
            MockModel("cerebras/llama-3.3-70b", "cerebras", "fast"),
        ]

        with patch('scrappy.orchestrator.litellm_config.get_configured_models', return_value=mock_models):
            display.list_models("cerebras")

        output = io.get_output()
        assert "CEREBRAS" in output or "cerebras" in output.lower()



# =============================================================================
# CLITaskExecution I/O Injection Tests
# =============================================================================

class TestTaskExecutionIOInjection:
    """Tests for CLITaskExecution I/O dependency injection."""

    def setup_method(self):
        """Set up test fixtures."""
        self.orchestrator = ConfigurableTestOrchestrator()
        self.io = MockIO()
        from scrappy.cli.tasks import CLITaskExecution
        self.tasks = CLITaskExecution(self.orchestrator, self.io)

    def test_plan_task_accepts_io_parameter(self):
        """plan_task() should use injected io from constructor."""
        io = MockIO()
        # Create a new tasks instance with the test io
        from scrappy.cli.tasks import CLITaskExecution
        tasks = CLITaskExecution(self.orchestrator, io)

        # Mock the plan method
        self.orchestrator.plan = MagicMock(return_value=[
            {'step': 'Step 1', 'description': 'First step'}
        ])

        # Should not raise TypeError
        tasks.plan_task("test task")

        # Verify output went to io object
        output = io.get_output()
        assert "Planning" in output

    def test_plan_task_outputs_header(self):
        """plan_task() should output task header through io."""
        io = MockIO()
        # Create a new tasks instance with the test io
        from scrappy.cli.tasks import CLITaskExecution
        tasks = CLITaskExecution(self.orchestrator, io)

        self.orchestrator.plan = MagicMock(return_value=[])

        tasks.plan_task("analyze code")

        output = io.get_output()
        assert "Planning: analyze code" in output

        # Check bold header
        styled = io.get_styled_outputs()
        header_outputs = [s for s in styled if "Planning" in s['text']]
        assert len(header_outputs) > 0
        assert header_outputs[0]['bold'] is True

    def test_plan_task_outputs_steps(self):
        """plan_task() should output plan steps through io."""
        io = MockIO()
        # Create a new tasks instance with the test io
        from scrappy.cli.tasks import CLITaskExecution
        tasks = CLITaskExecution(self.orchestrator, io)

        self.orchestrator.plan = MagicMock(return_value=[
            {'step': 'Step 1', 'description': 'First step'},
            {'step': 'Step 2', 'description': 'Second step'}
        ])

        tasks.plan_task("test task")

        output = io.get_output()
        assert "Step 1" in output
        assert "First step" in output
        assert "Step 2" in output
        assert "Second step" in output



    def test_plan_task_string_steps(self):
        """plan_task() should handle string steps through io."""
        io = MockIO()
        # Create a new tasks instance with the test io
        from scrappy.cli.tasks import CLITaskExecution
        tasks = CLITaskExecution(self.orchestrator, io)

        self.orchestrator.plan = MagicMock(return_value=[
            "Step 1: Do something",
            "Step 2: Do another thing"
        ])

        tasks.plan_task("test task")

        output = io.get_output()
        assert "Step 1" in output
        assert "Step 2" in output

    def test_plan_task_non_list_response(self):
        """plan_task() should handle non-list responses through io."""
        io = MockIO()
        # Create a new tasks instance with the test io
        from scrappy.cli.tasks import CLITaskExecution
        tasks = CLITaskExecution(self.orchestrator, io)

        self.orchestrator.plan = MagicMock(return_value="Single step plan")

        tasks.plan_task("test task")

        output = io.get_output()
        assert "Single step plan" in output

    def test_plan_task_returns_steps(self):
        """plan_task() should return the steps for tracking."""
        io = MockIO()
        # Create a new tasks instance with the test io
        from scrappy.cli.tasks import CLITaskExecution
        tasks = CLITaskExecution(self.orchestrator, io)

        steps = [
            {'step': 'Step 1', 'description': 'First step'},
            {'step': 'Step 2', 'description': 'Second step'}
        ]
        self.orchestrator.plan = MagicMock(return_value=steps)

        result = tasks.plan_task("test task")

        assert result == steps

    def test_plan_task_saves_to_working_memory(self):
        """plan_task() should save plan to working memory."""
        io = MockIO()
        # Create a new tasks instance with the test io
        from scrappy.cli.tasks import CLITaskExecution
        tasks = CLITaskExecution(self.orchestrator, io)

        self.orchestrator.plan = MagicMock(return_value=[
            {'step': 'Step 1', 'description': 'First step'}
        ])

        tasks.plan_task("test task")

        # Verify working memory was updated
        summary = self.orchestrator.working_memory.get_summary()
        assert summary['discoveries'] > 0

    def test_reason_accepts_io_parameter(self):
        """reason() should use injected io from constructor."""
        io = MockIO()
        # Create a new tasks instance with the test io
        from scrappy.cli.tasks import CLITaskExecution
        tasks = CLITaskExecution(self.orchestrator, io)

        # Mock the reason method
        self.orchestrator.reason = MagicMock(return_value={
            'question': 'test',
            'analysis': 'analysis',
            'conclusion': 'conclusion',
            'confidence': 'high'
        })

        # Should not raise TypeError
        tasks.reason("test question")

        # Verify output went to io object
        output = io.get_output()
        assert "Reasoning" in output

    def test_reason_outputs_header(self):
        """reason() should output question header through io."""
        io = MockIO()
        # Create a new tasks instance with the test io
        from scrappy.cli.tasks import CLITaskExecution
        tasks = CLITaskExecution(self.orchestrator, io)

        self.orchestrator.reason = MagicMock(return_value={})

        tasks.reason("What is Python?")

        output = io.get_output()
        assert "Reasoning about: What is Python?" in output

        # Check bold header
        styled = io.get_styled_outputs()
        header_outputs = [s for s in styled if "Reasoning" in s['text']]
        assert len(header_outputs) > 0
        assert header_outputs[0]['bold'] is True

    def test_reason_outputs_analysis(self):
        """reason() should output analysis through io."""
        io = MockIO()
        # Create a new tasks instance with the test io
        from scrappy.cli.tasks import CLITaskExecution
        tasks = CLITaskExecution(self.orchestrator, io)

        self.orchestrator.reason = MagicMock(return_value={
            'question': 'test',
            'analysis': 'This is the analysis',
            'conclusion': 'This is the conclusion',
            'confidence': 'high'
        })

        tasks.reason("test")

        output = io.get_output()
        assert "Analysis" in output
        assert "This is the analysis" in output

    def test_reason_outputs_conclusion(self):
        """reason() should output conclusion through io."""
        io = MockIO()
        # Create a new tasks instance with the test io
        from scrappy.cli.tasks import CLITaskExecution
        tasks = CLITaskExecution(self.orchestrator, io)

        self.orchestrator.reason = MagicMock(return_value={
            'question': 'test',
            'analysis': 'analysis',
            'conclusion': 'Final conclusion',
            'confidence': 'high'
        })

        tasks.reason("test")

        output = io.get_output()
        assert "Conclusion" in output
        assert "Final conclusion" in output

        # Check bold styling for conclusion label
        styled = io.get_styled_outputs()
        conclusion_outputs = [s for s in styled if "Conclusion" in s['text']]
        if conclusion_outputs:
            assert conclusion_outputs[0]['bold'] is True

    def test_reason_outputs_confidence(self):
        """reason() should output confidence through io."""
        io = MockIO()
        # Create a new tasks instance with the test io
        from scrappy.cli.tasks import CLITaskExecution
        tasks = CLITaskExecution(self.orchestrator, io)

        self.orchestrator.reason = MagicMock(return_value={
            'question': 'test',
            'analysis': 'analysis',
            'conclusion': 'conclusion',
            'confidence': 'high'
        })

        tasks.reason("test")

        output = io.get_output()
        assert "Confidence" in output
        assert "high" in output


    def test_reason_string_response(self):
        """reason() should handle string responses through io."""
        io = MockIO()
        # Create a new tasks instance with the test io
        from scrappy.cli.tasks import CLITaskExecution
        tasks = CLITaskExecution(self.orchestrator, io)

        self.orchestrator.reason = MagicMock(return_value="Simple string response")

        tasks.reason("test")

        output = io.get_output()
        assert "Simple string response" in output

    def test_reason_saves_to_working_memory(self):
        """reason() should save result to working memory."""
        io = MockIO()
        # Create a new tasks instance with the test io
        from scrappy.cli.tasks import CLITaskExecution
        tasks = CLITaskExecution(self.orchestrator, io)

        self.orchestrator.reason = MagicMock(return_value={
            'question': 'test',
            'analysis': 'analysis',
            'conclusion': 'conclusion',
            'confidence': 'high'
        })

        tasks.reason("test question")

        # Verify working memory was updated
        summary = self.orchestrator.working_memory.get_summary()
        assert summary['discoveries'] > 0


# =============================================================================
# Constructor Injection Tests
# =============================================================================

class TestDisplayTasksSmartDefaultIO:
    """Tests to verify handlers use constructor-injected IO."""

    def test_display_show_help_uses_constructor_io(self):
        """CLIDisplay.show_help should use constructor-injected IO (no io parameter)."""
        orchestrator = ConfigurableTestOrchestrator()
        io = MockIO()
        from scrappy.cli.display import CLIDisplay
        display = CLIDisplay(orchestrator, datetime.now(), io)

        import inspect
        sig = inspect.signature(display.show_help)
        params = sig.parameters

        assert 'io' not in params, "show_help should NOT have an 'io' parameter (uses self.io)"

    def test_display_show_status_uses_constructor_io(self):
        """CLIDisplay.show_status should use constructor-injected IO (no io parameter)."""
        orchestrator = ConfigurableTestOrchestrator()
        io = MockIO()
        from scrappy.cli.display import CLIDisplay
        display = CLIDisplay(orchestrator, datetime.now(), io)

        import inspect
        sig = inspect.signature(display.show_status)
        params = sig.parameters

        assert 'io' not in params, "show_status should NOT have an 'io' parameter (uses self.io)"

    def test_display_show_usage_uses_constructor_io(self):
        """CLIDisplay.show_usage should use constructor-injected IO (no io parameter)."""
        orchestrator = ConfigurableTestOrchestrator()
        io = MockIO()
        from scrappy.cli.display import CLIDisplay
        display = CLIDisplay(orchestrator, datetime.now(), io)

        import inspect
        sig = inspect.signature(display.show_usage)
        params = sig.parameters

        assert 'io' not in params, "show_usage should NOT have an 'io' parameter (uses self.io)"

    def test_display_list_models_uses_constructor_io(self):
        """CLIDisplay.list_models should use constructor-injected IO (no io parameter)."""
        orchestrator = ConfigurableTestOrchestrator()
        io = MockIO()
        from scrappy.cli.display import CLIDisplay
        display = CLIDisplay(orchestrator, datetime.now(), io)

        import inspect
        sig = inspect.signature(display.list_models)
        params = sig.parameters

        assert 'io' not in params, "list_models should NOT have an 'io' parameter (uses self.io)"

    def test_tasks_plan_task_uses_constructor_io(self):
        """CLITaskExecution.plan_task should use constructor-injected IO (no io parameter)."""
        orchestrator = ConfigurableTestOrchestrator()
        io = MockIO()
        from scrappy.cli.tasks import CLITaskExecution
        tasks = CLITaskExecution(orchestrator, io)

        import inspect
        sig = inspect.signature(tasks.plan_task)
        params = sig.parameters

        assert 'io' not in params, "plan_task should NOT have an 'io' parameter (uses self.display.get_io())"

    def test_tasks_reason_uses_constructor_io(self):
        """CLITaskExecution.reason should use constructor-injected IO (no io parameter)."""
        orchestrator = ConfigurableTestOrchestrator()
        io = MockIO()
        from scrappy.cli.tasks import CLITaskExecution
        tasks = CLITaskExecution(orchestrator, io)

        import inspect
        sig = inspect.signature(tasks.reason)
        params = sig.parameters

        assert 'io' not in params, "reason should NOT have an 'io' parameter (uses self.display.get_io())"

    def test_smart_query_uses_constructor_io(self):
        """CLISmartQuery.smart_query should use constructor-injected IO (no io parameter)."""
        orchestrator = ConfigurableTestOrchestrator()
        io = MockIO()
        from scrappy.cli.smart_query import CLISmartQuery
        smart = CLISmartQuery(orchestrator, io)

        import inspect
        sig = inspect.signature(smart.smart_query)
        params = sig.parameters

        assert 'io' not in params, "smart_query should NOT have an 'io' parameter (uses self.display.get_io())"
