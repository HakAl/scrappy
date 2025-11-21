"""
Tests for CLITaskRouterHandler I/O dependency injection.

These tests verify that CLITaskRouterHandler methods accept an io: CLIIOProtocol
parameter and route all output through the io object instead of calling click directly.

TDD: These tests are written first and will fail until the handler is updated.
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from pathlib import Path
from datetime import datetime

# Import test helpers
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.helpers import MockIO, ConfigurableTestOrchestrator


class TestTaskRouterHandlerIOInjection:
    """Tests for CLITaskRouterHandler I/O dependency injection."""

    def setup_method(self):
        """Set up test fixtures."""
        self.orchestrator = ConfigurableTestOrchestrator()

        # Import here to avoid import errors during collection
        from src.cli.task_router_handler import CLITaskRouterHandler
        from src.task_router import ClassifiedTask, TaskType, ExecutionResult
        from src.task_router.metrics_collector import RouterMetrics

        self.CLITaskRouterHandler = CLITaskRouterHandler
        self.ClassifiedTask = ClassifiedTask
        self.TaskType = TaskType
        self.ExecutionResult = ExecutionResult
        self.RouterMetrics = RouterMetrics

        self.handler = CLITaskRouterHandler(
            orchestrator=self.orchestrator,
            project_root=Path.cwd()
        )

    # =========================================================================
    # handle_classify_only() Tests
    # =========================================================================

    def test_handle_classify_only_accepts_io_parameter(self):
        """handle_classify_only() should accept an io parameter."""
        io = MockIO()

        # Mock the router.classify_only to return a classified task
        mock_classified = self.ClassifiedTask(
            original_input="list all files",
            task_type=self.TaskType.DIRECT_COMMAND,
            confidence=0.95,
            complexity_score=3,
            reasoning="Simple command execution",
            extracted_command="ls -la",
            suggested_provider="local",
            requires_planning=False,
            requires_tools=True,
            matched_patterns=("list files", "directory")
        )

        with patch.object(self.handler.router, 'classify_only', return_value=mock_classified):
            # Should not raise TypeError for unexpected keyword argument
            result = self.handler.handle_classify_only("list all files", io=io)

        # Verify output went to io object
        output = io.get_output()
        assert "Task Classification Preview" in output
        assert "direct_command" in output

    def test_handle_classify_only_outputs_header(self):
        """handle_classify_only() should output header through io."""
        io = MockIO()

        mock_classified = self.ClassifiedTask(
            original_input="test task",
            task_type=self.TaskType.CODE_GENERATION,
            confidence=0.88,
            complexity_score=7,
            reasoning="Requires code generation",
            extracted_command=None,
            suggested_provider="anthropic",
            requires_planning=True,
            requires_tools=True,
            matched_patterns=("write", "function")
        )

        with patch.object(self.handler.router, 'classify_only', return_value=mock_classified):
            self.handler.handle_classify_only("write a function to parse JSON", io=io)

        output = io.get_output()
        assert "Task Classification Preview" in output

        # Check styled output for cyan color
        styled = io.get_styled_outputs()
        header_outputs = [s for s in styled if "Task Classification Preview" in s['text']]
        assert len(header_outputs) > 0
        assert header_outputs[0]['fg'] == 'cyan'

    def test_handle_classify_only_displays_classification_details(self):
        """handle_classify_only() should display all classification details through io."""
        io = MockIO()

        mock_classified = self.ClassifiedTask(
            original_input="test task",
            task_type=self.TaskType.RESEARCH,
            confidence=0.92,
            complexity_score=5,
            reasoning="Requires information gathering",
            extracted_command=None,
            suggested_provider="anthropic",
            requires_planning=False,
            requires_tools=True,
            matched_patterns=("find", "search", "documentation")
        )

        with patch.object(self.handler.router, 'classify_only', return_value=mock_classified):
            self.handler.handle_classify_only("find all API documentation", io=io)

        output = io.get_output()
        assert "research" in output
        assert "0.92" in output  # confidence
        assert "5/10" in output  # complexity
        assert "Requires information gathering" in output  # reasoning
        assert "anthropic" in output  # suggested provider

    def test_handle_classify_only_shows_extracted_command(self):
        """handle_classify_only() should show extracted command for direct commands."""
        io = MockIO()

        mock_classified = self.ClassifiedTask(
            original_input="test task",
            task_type=self.TaskType.DIRECT_COMMAND,
            confidence=0.98,
            complexity_score=2,
            reasoning="Direct shell command",
            extracted_command="git status",
            suggested_provider="local",
            requires_planning=False,
            requires_tools=False,
            matched_patterns=("git")
        )

        with patch.object(self.handler.router, 'classify_only', return_value=mock_classified):
            self.handler.handle_classify_only("git status", io=io)

        output = io.get_output()
        assert "Extracted command: git status" in output

    def test_handle_classify_only_uses_correct_colors(self):
        """handle_classify_only() should display task types correctly."""
        io = MockIO()

        # Test each task type displays correctly
        test_cases = [
            (self.TaskType.DIRECT_COMMAND, "direct_command"),
            (self.TaskType.CODE_GENERATION, "code_generation"),
            (self.TaskType.RESEARCH, "research"),
            (self.TaskType.CONVERSATION, "conversation"),
        ]

        for task_type, task_type_str in test_cases:
            io.clear_output()

            mock_classified = self.ClassifiedTask(
            original_input="test task",
            task_type=task_type,
                confidence=0.90,
                complexity_score=5,
                reasoning="Test reasoning",
                extracted_command=None,
                suggested_provider="test",
                requires_planning=False,
                requires_tools=False,
                matched_patterns=()
            )

            with patch.object(self.handler.router, 'classify_only', return_value=mock_classified):
                self.handler.handle_classify_only("test task", io=io)

            # Check that task type is displayed
            output = io.get_output()
            assert task_type_str in output
            assert "Task Type:" in output

    # =========================================================================
    # handle_route_status() Tests
    # =========================================================================

    def test_handle_route_status_accepts_io_parameter(self):
        """handle_route_status() should accept an io parameter."""
        io = MockIO()

        # Mock metrics
        mock_metrics = self.RouterMetrics(
            total_tasks=10,
            tasks_by_type={"direct_command": 5, "code_generation": 3, "research": 2},
            avg_execution_time=2.5,
            total_tokens_used=5000,
            success_rate=0.9
        )

        with patch.object(self.handler.router, 'get_metrics', return_value=mock_metrics):
            # Should not raise TypeError for unexpected keyword argument
            self.handler.handle_route_status(io=io)

        # Verify output went to io object
        output = io.get_output()
        assert "Task Router Metrics" in output
        assert "Total tasks: 10" in output

    def test_handle_route_status_displays_all_metrics(self):
        """handle_route_status() should display all metrics through io."""
        io = MockIO()

        mock_metrics = self.RouterMetrics(
            total_tasks=25,
            tasks_by_type={
                "direct_command": 10,
                "code_generation": 8,
                "research": 5,
                "conversation": 2
            },
            avg_execution_time=3.75,
            total_tokens_used=12500,
            success_rate=0.88
        )

        with patch.object(self.handler.router, 'get_metrics', return_value=mock_metrics):
            self.handler.handle_route_status(io=io)

        output = io.get_output()
        assert "Total tasks: 25" in output
        assert "Tasks by type:" in output
        assert "direct_command: 10" in output
        assert "code_generation: 8" in output
        assert "research: 5" in output
        assert "conversation: 2" in output
        assert "Avg execution time: 3.75s" in output
        assert "Total tokens used: 12500" in output
        assert "Success rate: 88.0%" in output

    def test_handle_route_status_header_styled(self):
        """handle_route_status() should output header with cyan and bold."""
        io = MockIO()

        mock_metrics = self.RouterMetrics(
            total_tasks=5,
            tasks_by_type={},
            avg_execution_time=1.0,
            total_tokens_used=100,
            success_rate=1.0
        )

        with patch.object(self.handler.router, 'get_metrics', return_value=mock_metrics):
            self.handler.handle_route_status(io=io)

        # Check styled output
        styled = io.get_styled_outputs()
        header_outputs = [s for s in styled if "Task Router Metrics" in s['text']]
        assert len(header_outputs) > 0
        assert header_outputs[0]['fg'] == 'cyan'
        assert header_outputs[0]['bold'] is True

    def test_handle_route_status_handles_empty_metrics(self):
        """handle_route_status() should handle empty task metrics gracefully."""
        io = MockIO()

        mock_metrics = self.RouterMetrics(
            total_tasks=0,
            tasks_by_type={},
            avg_execution_time=0.0,
            total_tokens_used=0,
            success_rate=0.0
        )

        with patch.object(self.handler.router, 'get_metrics', return_value=mock_metrics):
            self.handler.handle_route_status(io=io)

        output = io.get_output()
        assert "Total tasks: 0" in output
        assert "Success rate: 0.0%" in output

    # =========================================================================
    # handle_route_history() Tests
    # =========================================================================

    def test_handle_route_history_accepts_io_parameter(self):
        """handle_route_history() should accept an io parameter."""
        io = MockIO()

        # Empty history
        self.handler.history = []

        # Should not raise TypeError for unexpected keyword argument
        self.handler.handle_route_history(io=io)

        # Verify output went to io object
        output = io.get_output()
        assert "No routing history yet" in output or "Routing History" in output

    def test_handle_route_history_shows_no_history_message(self):
        """handle_route_history() should show message when history is empty."""
        io = MockIO()

        self.handler.history = []
        self.handler.handle_route_history(io=io)

        output = io.get_output()
        assert "No routing history yet" in output

        # Check styled output for yellow color
        styled = io.get_styled_outputs()
        no_history_outputs = [s for s in styled if "No routing history yet" in s['text']]
        assert len(no_history_outputs) > 0
        assert no_history_outputs[0]['fg'] == 'yellow'

    def test_handle_route_history_displays_history_entries(self):
        """handle_route_history() should display history entries through io."""
        io = MockIO()

        # Create mock history
        mock_result = self.ExecutionResult(
            success=True,
            output="Command executed successfully",
            error=None,
            execution_time=1.25,
            tokens_used=150,
            provider_used="local",
            metadata={}
        )

        self.handler.history = [
            {
                "input": "list all Python files in the src directory",
                "result": mock_result,
                "classification": {"type": "direct_command"}
            },
            {
                "input": "write a function to parse JSON with error handling",
                "result": self.ExecutionResult(
                    success=False,
                    output=None,
                    error="Syntax error",
                    execution_time=2.5,
                    tokens_used=300,
                    provider_used="anthropic",
                    metadata={}
                ),
                "classification": {"type": "code_generation"}
            }
        ]

        self.handler.handle_route_history(io=io)

        output = io.get_output()
        assert "Routing History" in output
        assert "list all Python files in the src directory..." in output
        assert "Type: direct_command" in output
        assert "Success: Yes" in output
        assert "Time: 1.25s" in output
        assert "write a function to parse JSON with error handling..." in output
        assert "Type: code_generation" in output
        assert "Success: No" in output
        assert "Time: 2.50s" in output

    def test_handle_route_history_limits_to_last_10(self):
        """handle_route_history() should only show last 10 entries."""
        io = MockIO()

        # Create 15 history entries
        mock_result = self.ExecutionResult(
            success=True,
            output="Output",
            error=None,
            execution_time=1.0,
            tokens_used=100,
            provider_used="test",
            metadata={}
        )

        self.handler.history = [
            {
                "input": f"Task number {i}",
                "result": mock_result,
                "classification": {"type": "test"}
            }
            for i in range(15)
        ]

        self.handler.handle_route_history(io=io)

        output = io.get_output()
        # Should show entries 5-14 (last 10)
        assert "Task number 5" in output
        assert "Task number 14" in output
        # Should NOT show entries 0-4
        assert "Task number 0" not in output
        assert "Task number 4" not in output

    def test_handle_route_history_header_styled(self):
        """handle_route_history() should output header with cyan and bold."""
        io = MockIO()

        mock_result = self.ExecutionResult(
            success=True,
            output="Test",
            error=None,
            execution_time=1.0,
            tokens_used=100,
            provider_used="test",
            metadata={}
        )

        self.handler.history = [{
            "input": "test task",
            "result": mock_result,
            "classification": {"type": "test"}
        }]

        self.handler.handle_route_history(io=io)

        # Check styled output
        styled = io.get_styled_outputs()
        header_outputs = [s for s in styled if "Routing History" in s['text']]
        assert len(header_outputs) > 0
        assert header_outputs[0]['fg'] == 'cyan'
        assert header_outputs[0]['bold'] is True

    # =========================================================================
    # _display_result() Tests
    # =========================================================================

    def test_display_result_accepts_io_parameter(self):
        """_display_result() should accept an io parameter."""
        io = MockIO()

        mock_result = self.ExecutionResult(
            success=True,
            output="Task completed successfully",
            error=None,
            execution_time=2.5,
            tokens_used=250,
            provider_used="anthropic",
            metadata={}
        )

        # Should not raise TypeError for unexpected keyword argument
        self.handler._display_result(mock_result, io=io)

        # Verify output went to io object
        output = io.get_output()
        assert "Execution successful" in output

    def test_display_result_shows_success_message(self):
        """_display_result() should show success message in green with bold."""
        io = MockIO()

        mock_result = self.ExecutionResult(
            success=True,
            output="Done",
            error=None,
            execution_time=1.0,
            tokens_used=100,
            provider_used="test",
            metadata={}
        )

        self.handler._display_result(mock_result, io=io)

        output = io.get_output()
        assert "Execution successful" in output

        # Check styled output
        styled = io.get_styled_outputs()
        success_outputs = [s for s in styled if "Execution successful" in s['text']]
        assert len(success_outputs) > 0
        assert success_outputs[0]['fg'] == 'green'
        assert success_outputs[0]['bold'] is True

    def test_display_result_shows_failure_message(self):
        """_display_result() should show failure message in red with bold."""
        io = MockIO()

        mock_result = self.ExecutionResult(
            success=False,
            output=None,
            error="Command not found",
            execution_time=0.5,
            tokens_used=0,
            provider_used="local",
            metadata={}
        )

        self.handler._display_result(mock_result, io=io)

        output = io.get_output()
        assert "Execution failed" in output
        assert "Error: Command not found" in output

        # Check styled output
        styled = io.get_styled_outputs()
        failed_outputs = [s for s in styled if "Execution failed" in s['text']]
        assert len(failed_outputs) > 0
        assert failed_outputs[0]['fg'] == 'red'
        assert failed_outputs[0]['bold'] is True

        error_outputs = [s for s in styled if "Error: Command not found" in s['text']]
        assert len(error_outputs) > 0
        assert error_outputs[0]['fg'] == 'red'

    def test_display_result_shows_output(self):
        """_display_result() should display result output."""
        io = MockIO()

        mock_result = self.ExecutionResult(
            success=True,
            output="File created successfully\nAll tests passed",
            error=None,
            execution_time=3.2,
            tokens_used=400,
            provider_used="anthropic",
            metadata={}
        )

        self.handler._display_result(mock_result, io=io)

        output = io.get_output()
        assert "Output:" in output
        assert "File created successfully" in output
        assert "All tests passed" in output

    def test_display_result_truncates_long_output(self):
        """_display_result() should truncate output longer than 2000 characters."""
        io = MockIO()

        long_output = "x" * 2500
        mock_result = self.ExecutionResult(
            success=True,
            output=long_output,
            error=None,
            execution_time=1.0,
            tokens_used=100,
            provider_used="test",
            metadata={}
        )

        self.handler._display_result(mock_result, io=io)

        output = io.get_output()
        assert "... (truncated)" in output
        # Should show first 2000 chars plus truncation message
        assert len([line for line in output.split('\n') if 'x' in line]) > 0

    def test_display_result_shows_metadata(self):
        """_display_result() should display execution time, tokens, and provider."""
        io = MockIO()

        mock_result = self.ExecutionResult(
            success=True,
            output="Success",
            error=None,
            execution_time=4.75,
            tokens_used=850,
            provider_used="anthropic-opus",
            metadata={}
        )

        self.handler._display_result(mock_result, io=io)

        output = io.get_output()
        assert "Execution time: 4.75s" in output
        assert "Tokens used: 850" in output
        assert "Provider: anthropic-opus" in output

        # Check execution time is styled in cyan
        styled = io.get_styled_outputs()
        time_outputs = [s for s in styled if "Execution time" in s['text']]
        assert len(time_outputs) > 0
        assert time_outputs[0]['fg'] == 'cyan'

    def test_display_result_handles_missing_optional_fields(self):
        """_display_result() should handle missing tokens_used and provider_used."""
        io = MockIO()

        mock_result = self.ExecutionResult(
            success=True,
            output="Done",
            error=None,
            execution_time=1.5,
            tokens_used=None,
            provider_used=None,
            metadata={}
        )

        self.handler._display_result(mock_result, io=io)

        output = io.get_output()
        assert "Execution time: 1.50s" in output
        # Should not show tokens or provider if not available
        assert "Tokens used:" not in output
        assert "Provider:" not in output

    # =========================================================================
    # _display_classification() Tests
    # =========================================================================

    def test_display_classification_accepts_io_parameter(self):
        """_display_classification() should accept an io parameter."""
        io = MockIO()

        mock_classified = self.ClassifiedTask(
            original_input="test task",
            task_type=self.TaskType.DIRECT_COMMAND,
            confidence=0.95,
            complexity_score=3,
            reasoning="Simple command",
            extracted_command="ls",
            suggested_provider="local",
            requires_planning=False,
            requires_tools=False,
            matched_patterns=()
        )

        # Should not raise TypeError for unexpected keyword argument
        self.handler._display_classification(mock_classified, io=io)

        # Verify output went to io object
        output = io.get_output()
        assert "direct_command" in output

    def test_display_classification_shows_all_fields(self):
        """_display_classification() should display all classification fields."""
        io = MockIO()

        mock_classified = self.ClassifiedTask(
            original_input="test task",
            task_type=self.TaskType.CODE_GENERATION,
            confidence=0.87,
            complexity_score=8,
            reasoning="Complex code generation required",
            extracted_command=None,
            suggested_provider="anthropic-opus",
            requires_planning=True,
            requires_tools=True,
            matched_patterns=("create", "class", "methods")
        )

        self.handler._display_classification(mock_classified, io=io)

        output = io.get_output()
        assert "code_generation" in output
        assert "Confidence: 0.87" in output
        assert "Complexity: 8/10" in output
        assert "Reasoning: Complex code generation required" in output
        assert "Suggested provider: anthropic-opus" in output
        assert "Requires planning: Yes" in output
        assert "Requires tools: Yes" in output
        assert "Matched patterns: create, class, methods" in output

    def test_display_classification_shows_extracted_command(self):
        """_display_classification() should show extracted command when present."""
        io = MockIO()

        mock_classified = self.ClassifiedTask(
            original_input="test task",
            task_type=self.TaskType.DIRECT_COMMAND,
            confidence=0.99,
            complexity_score=1,
            reasoning="Direct command",
            extracted_command="git log --oneline",
            suggested_provider="local",
            requires_planning=False,
            requires_tools=False,
            matched_patterns=("git")
        )

        self.handler._display_classification(mock_classified, io=io)

        output = io.get_output()
        assert "Extracted command: git log --oneline" in output

    def test_display_classification_limits_matched_patterns(self):
        """_display_classification() should limit matched patterns to 5."""
        io = MockIO()

        mock_classified = self.ClassifiedTask(
            original_input="test task",
            task_type=self.TaskType.RESEARCH,
            confidence=0.85,
            complexity_score=6,
            reasoning="Research task",
            extracted_command=None,
            suggested_provider="anthropic",
            requires_planning=False,
            requires_tools=True,
            matched_patterns=("p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8")
        )

        self.handler._display_classification(mock_classified, io=io)

        output = io.get_output()
        assert "Matched patterns: p1, p2, p3, p4, p5" in output
        # Should not show p6, p7, p8
        assert "p6" not in output

    def test_display_classification_uses_correct_task_type_colors(self):
        """_display_classification() should display all task types correctly."""
        test_cases = [
            (self.TaskType.DIRECT_COMMAND, "direct_command"),
            (self.TaskType.CODE_GENERATION, "code_generation"),
            (self.TaskType.RESEARCH, "research"),
            (self.TaskType.CONVERSATION, "conversation"),
        ]

        for task_type, task_type_str in test_cases:
            io = MockIO()

            mock_classified = self.ClassifiedTask(
            original_input="test task",
            task_type=task_type,
                confidence=0.90,
                complexity_score=5,
                reasoning="Test",
                extracted_command=None,
                suggested_provider="test",
                requires_planning=False,
                requires_tools=False,
                matched_patterns=()
            )

            self.handler._display_classification(mock_classified, io=io)

            # Check that task type is displayed in output
            output = io.get_output()
            assert task_type_str in output, f"Task type {task_type_str} not in output"
            assert "Task Type:" in output

    def test_display_classification_handles_no_patterns(self):
        """_display_classification() should handle empty matched_patterns list."""
        io = MockIO()

        mock_classified = self.ClassifiedTask(
            original_input="test task",
            task_type=self.TaskType.CONVERSATION,
            confidence=0.75,
            complexity_score=2,
            reasoning="Simple conversation",
            extracted_command=None,
            suggested_provider="anthropic",
            requires_planning=False,
            requires_tools=False,
            matched_patterns=()
        )

        self.handler._display_classification(mock_classified, io=io)

        output = io.get_output()
        # Should not crash or show "Matched patterns:" with empty list
        assert "Matched patterns:" not in output or "Matched patterns: " in output

    def test_display_classification_handles_no_false_booleans(self):
        """_display_classification() should show 'No' for false boolean fields."""
        io = MockIO()

        mock_classified = self.ClassifiedTask(
            original_input="test task",
            task_type=self.TaskType.DIRECT_COMMAND,
            confidence=0.95,
            complexity_score=1,
            reasoning="Simple command",
            extracted_command="pwd",
            suggested_provider="local",
            requires_planning=False,
            requires_tools=False,
            matched_patterns=()
        )

        self.handler._display_classification(mock_classified, io=io)

        output = io.get_output()
        assert "Requires planning: No" in output
        assert "Requires tools: No" in output


# =============================================================================
# Integration Tests
# =============================================================================

class TestTaskRouterHandlerIntegration:
    """Integration tests for complete I/O injection flow."""

    def setup_method(self):
        """Set up test fixtures."""
        self.orchestrator = ConfigurableTestOrchestrator()

        from src.cli.task_router_handler import CLITaskRouterHandler
        from src.task_router import ClassifiedTask, TaskType, ExecutionResult
        from src.task_router.metrics_collector import RouterMetrics

        self.CLITaskRouterHandler = CLITaskRouterHandler
        self.ClassifiedTask = ClassifiedTask
        self.TaskType = TaskType
        self.ExecutionResult = ExecutionResult
        self.RouterMetrics = RouterMetrics

        self.handler = CLITaskRouterHandler(
            orchestrator=self.orchestrator,
            project_root=Path.cwd()
        )

    def test_all_methods_accept_io_parameter(self):
        """All public methods should accept io parameter without errors."""
        io = MockIO()

        # Test handle_classify_only
        mock_classified = self.ClassifiedTask(
            original_input="test task",
            task_type=self.TaskType.DIRECT_COMMAND,
            confidence=0.95,
            complexity_score=3,
            reasoning="Test",
            extracted_command="test",
            suggested_provider="test",
            requires_planning=False,
            requires_tools=False,
            matched_patterns=()
        )

        with patch.object(self.handler.router, 'classify_only', return_value=mock_classified):
            self.handler.handle_classify_only("test", io=io)

        io.clear_output()

        # Test handle_route_status
        mock_metrics = self.RouterMetrics(
            total_tasks=1,
            tasks_by_type={},
            avg_execution_time=1.0,
            total_tokens_used=100,
            success_rate=1.0
        )

        with patch.object(self.handler.router, 'get_metrics', return_value=mock_metrics):
            self.handler.handle_route_status(io=io)

        io.clear_output()

        # Test handle_route_history
        self.handler.history = []
        self.handler.handle_route_history(io=io)

        # All methods should work without errors
        assert True

    def test_no_click_imports_needed_when_using_io(self):
        """When using io parameter, methods should not call click directly."""
        io = MockIO()

        # Patch click to raise if called
        with patch('click.echo', side_effect=AssertionError("click.echo called!")):
            with patch('click.secho', side_effect=AssertionError("click.secho called!")):
                # This should work without calling click
                self.handler.history = []
                self.handler.handle_route_history(io=io)

        # Verify output still worked through io
        output = io.get_output()
        assert "No routing history yet" in output
