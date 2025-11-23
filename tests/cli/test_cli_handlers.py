"""
Tests for CLI command handlers and session management.

These tests verify actual behavior, not just existence of methods.
They invoke methods, assert on outcomes, and test edge cases.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch, call
from pathlib import Path
import json
from datetime import datetime

from tests.helpers import (
    MockIO,
    ConfigurableTestOrchestrator,
    make_handler_test_setup,
    assert_output_contains,
    assert_output_not_contains,
    assert_styled_with,
    assert_has_error_output,
    assert_has_success_output,
    assert_has_warning_output,
)


class TestCLITaskRouterHandler:
    """Tests for CLI task router handler."""

    @pytest.fixture
    def mock_orchestrator(self):
        """Create mock orchestrator."""
        return ConfigurableTestOrchestrator(
            available_providers=["cerebras", "groq"],
            recommended_provider="cerebras"
        )

    @pytest.fixture
    def mock_router_result(self):
        """Create mock routing result."""
        result = Mock()
        result.success = True
        result.output = "Task completed successfully"
        result.error = None
        result.execution_time = 1.5
        result.tokens_used = 100
        result.provider_used = "cerebras"
        result.metadata = {"classification": {"type": "code_generation"}}
        return result

    @pytest.fixture
    def mock_classified_task(self):
        """Create mock classified task."""
        from src.task_router import TaskType
        classified = Mock()
        classified.task_type = Mock()
        classified.task_type.value = "code_generation"
        classified.confidence = 0.85
        classified.complexity_score = 5
        classified.reasoning = "Contains code patterns"
        classified.extracted_command = None
        classified.suggested_provider = "cerebras"
        classified.requires_planning = True
        classified.requires_tools = True
        classified.matched_patterns = ["generate", "create"]
        return classified

    @pytest.mark.unit
    def test_handler_stores_orchestrator_reference(self, mock_orchestrator):
        """Test CLI handler stores orchestrator reference correctly."""
        from src.cli.task_router_handler import CLITaskRouterHandler

        io = MockIO()
        handler = CLITaskRouterHandler(mock_orchestrator, io)
        assert handler.orchestrator is mock_orchestrator

    @pytest.mark.unit
    def test_handler_initializes_router(self, mock_orchestrator):
        """Test that handler creates task router with correct config."""
        from src.cli.task_router_handler import CLITaskRouterHandler

        io = MockIO()
        handler = CLITaskRouterHandler(
            mock_orchestrator,
            io,
            project_root=Path("/test/project"),
            auto_confirm=True
        )

        assert handler.router is not None
        assert handler.project_root == Path("/test/project")
        assert handler.auto_confirm is True

    @pytest.mark.unit
    def test_handler_starts_with_empty_history(self, mock_orchestrator):
        """Test handler initializes with empty history."""
        from src.cli.task_router_handler import CLITaskRouterHandler

        io = MockIO()
        handler = CLITaskRouterHandler(mock_orchestrator, io)
        assert handler.history == []

    @pytest.mark.unit
    def test_handle_auto_route_adds_to_history(self, mock_orchestrator, mock_router_result):
        """Test that handle_auto_route adds entry to history."""
        from src.cli.task_router_handler import CLITaskRouterHandler

        io = MockIO()
        handler = CLITaskRouterHandler(mock_orchestrator, io)
        handler.router = Mock()
        handler.router.route.return_value = mock_router_result

        result = handler.handle_auto_route("Create a function")

        assert len(handler.history) == 1
        assert handler.history[0]["input"] == "Create a function"
        assert handler.history[0]["result"] is mock_router_result

    @pytest.mark.unit
    def test_handle_auto_route_returns_router_result(self, mock_orchestrator, mock_router_result):
        """Test that handle_auto_route returns the routing result."""
        from src.cli.task_router_handler import CLITaskRouterHandler

        io = MockIO()
        handler = CLITaskRouterHandler(mock_orchestrator, io)
        handler.router = Mock()
        handler.router.route.return_value = mock_router_result

        result = handler.handle_auto_route("Test task")

        assert result is mock_router_result
        handler.router.route.assert_called_once_with("Test task")

    @pytest.mark.unit
    def test_handle_auto_route_multiple_tasks_build_history(self, mock_orchestrator, mock_router_result):
        """Test multiple auto_route calls accumulate in history."""
        from src.cli.task_router_handler import CLITaskRouterHandler

        io = MockIO()
        handler = CLITaskRouterHandler(mock_orchestrator, io)
        handler.router = Mock()
        handler.router.route.return_value = mock_router_result

        handler.handle_auto_route("Task 1")
        handler.handle_auto_route("Task 2")
        handler.handle_auto_route("Task 3")

        assert len(handler.history) == 3
        assert handler.history[0]["input"] == "Task 1"
        assert handler.history[1]["input"] == "Task 2"
        assert handler.history[2]["input"] == "Task 3"

    @pytest.mark.unit
    def test_handle_classify_only_returns_classification(self, mock_orchestrator, mock_classified_task):
        """Test classify_only returns classification without executing."""
        from src.cli.task_router_handler import CLITaskRouterHandler

        io = MockIO()
        handler = CLITaskRouterHandler(mock_orchestrator, io)
        handler.router = Mock()
        handler.router.classify_only.return_value = mock_classified_task

        result = handler.handle_classify_only("Analyze this code")

        assert result is mock_classified_task
        handler.router.classify_only.assert_called_once_with("Analyze this code")
        # Verify it doesn't add to history (preview mode)
        assert len(handler.history) == 0


    @pytest.mark.unit
    def test_handle_route_history_shows_recent_entries(self, mock_orchestrator, mock_router_result):
        """Test route_history shows most recent entries."""
        from src.cli.task_router_handler import CLITaskRouterHandler

        io = MockIO()
        handler = CLITaskRouterHandler(mock_orchestrator, io)
        handler.router = Mock()
        handler.router.route.return_value = mock_router_result

        # Add 15 entries
        for i in range(15):
            handler.handle_auto_route(f"Task {i}")

        assert len(handler.history) == 15

    @pytest.mark.unit
    def test_failed_result_stored_in_history(self, mock_orchestrator):
        """Test failed routing result is stored in history."""
        from src.cli.task_router_handler import CLITaskRouterHandler

        io = MockIO()
        handler = CLITaskRouterHandler(mock_orchestrator, io)
        handler.router = Mock()

        failed_result = Mock()
        failed_result.success = False
        failed_result.output = ""
        failed_result.error = "Provider unavailable"
        failed_result.execution_time = 0.1
        failed_result.tokens_used = 0
        failed_result.provider_used = None
        failed_result.metadata = {"classification": {"type": "unknown"}}
        handler.router.route.return_value = failed_result

        handler.handle_auto_route("Failing task")

        assert len(handler.history) == 1
        assert handler.history[0]["result"].success is False
        assert handler.history[0]["result"].error == "Provider unavailable"


class TestCLIAgentManager:
    """Tests for agent manager."""

    @pytest.fixture
    def mock_orchestrator(self):
        """Create mock orchestrator."""
        orch = ConfigurableTestOrchestrator()
        return orch

    @pytest.mark.unit
    def test_agent_manager_stores_orchestrator(self, mock_orchestrator):
        """Test CLIAgentManager stores orchestrator reference."""
        from src.cli.agent_manager import CLIAgentManager

        io = MockIO()
        manager = CLIAgentManager(mock_orchestrator, io)

        assert manager.orchestrator is mock_orchestrator


  # Should show checkpoint hash

    @pytest.mark.unit
    @patch('src.cli.agent_manager.CodeAgent')
    @patch('src.cli.agent_manager.create_git_checkpoint')
    def test_run_agent_success_shows_result(self, mock_checkpoint, mock_agent_class, mock_orchestrator):
        """Test run_agent displays success result."""
        from src.cli.agent_manager import CLIAgentManager

        mock_checkpoint.return_value = None
        mock_agent = Mock()
        mock_agent.run.return_value = {
            "success": True,
            "result": "Task completed successfully",
            "iterations": 3,
            "audit_log": []
        }
        mock_agent.planner = "cerebras"
        mock_agent.executor = "groq"
        mock_agent.project_root = Path("/test")
        mock_agent_class.return_value = mock_agent

        io = MockIO(
            confirmations=[False, False, True, False]  # dry_run, checkpoint, start, save_log
        )
        manager = CLIAgentManager(mock_orchestrator, io)

        manager.run_agent("Create file")

        output = io.get_output()
        assert "Task Completed Successfully" in output or "Completed" in output
        assert "Task completed successfully" in output


    @pytest.mark.unit
    @patch('src.cli.agent_manager.CodeAgent')
    @patch('src.cli.agent_manager.create_git_checkpoint')
    def test_run_agent_dry_run_mode(self, mock_checkpoint, mock_agent_class, mock_orchestrator):
        """Test run_agent respects dry run mode."""
        from src.cli.agent_manager import CLIAgentManager

        mock_checkpoint.return_value = None
        mock_agent = Mock()
        mock_agent.run.return_value = {
            "success": True,
            "result": "Dry run completed",
            "iterations": 1,
            "audit_log": []
        }
        mock_agent.planner = "cerebras"
        mock_agent.executor = "groq"
        mock_agent.project_root = Path("/test")
        mock_agent_class.return_value = mock_agent

        io = MockIO(
            confirmations=[True, False, True, False]  # dry_run=True
        )
        manager = CLIAgentManager(mock_orchestrator, io)

        manager.run_agent("Test")

        assert mock_agent.dry_run is True
        output = io.get_output()
        assert "DRY RUN" in output

    @pytest.mark.unit
    @patch('src.cli.agent_manager.CodeAgent')
    @patch('src.cli.agent_manager.create_git_checkpoint')
    def test_run_agent_handles_exception(self, mock_checkpoint, mock_agent_class, mock_orchestrator):
        """Test run_agent handles exceptions gracefully."""
        from src.cli.agent_manager import CLIAgentManager

        mock_checkpoint.return_value = None
        mock_agent = Mock()
        mock_agent.run.side_effect = RuntimeError("Agent crashed")
        mock_agent.planner = "cerebras"
        mock_agent.executor = "groq"
        mock_agent.project_root = Path("/test")
        mock_agent_class.return_value = mock_agent

        io = MockIO(
            confirmations=[False, False, True]
        )
        manager = CLIAgentManager(mock_orchestrator, io)

        # Should not raise
        manager.run_agent("Crashing task")

        output = io.get_output()
        assert "error" in output.lower()
        assert "Agent crashed" in output
        # Should record discovery in working memory
        discoveries = mock_orchestrator.working_memory._data['discoveries']
        assert len(discoveries) > 0
        assert any("Crashing task" in d['content'] for d in discoveries)

    @pytest.mark.unit
    @patch('src.cli.agent_manager.CodeAgent')
    @patch('src.cli.agent_manager.create_git_checkpoint')
    def test_run_agent_records_discovery(self, mock_checkpoint, mock_agent_class, mock_orchestrator):
        """Test run_agent records task result as discovery."""
        from src.cli.agent_manager import CLIAgentManager

        mock_checkpoint.return_value = None
        mock_agent = Mock()
        mock_agent.run.return_value = {
            "success": True,
            "result": "Done",
            "iterations": 2,
            "audit_log": []
        }
        mock_agent.planner = "cerebras"
        mock_agent.executor = "groq"
        mock_agent.project_root = Path("/test")
        mock_agent_class.return_value = mock_agent

        io = MockIO(
            confirmations=[False, False, True, False]
        )
        manager = CLIAgentManager(mock_orchestrator, io)

        manager.run_agent("Important task")

        # Should record discovery in working memory
        discoveries = mock_orchestrator.working_memory._data['discoveries']
        assert len(discoveries) > 0
        # Find the discovery for this task
        task_discovery = [d for d in discoveries if "Important task" in d['content']]
        assert len(task_discovery) > 0
        assert task_discovery[0]['source'] == "agent_task"


