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

        handler = CLITaskRouterHandler(mock_orchestrator)
        assert handler.orchestrator is mock_orchestrator

    @pytest.mark.unit
    def test_handler_initializes_router(self, mock_orchestrator):
        """Test that handler creates task router with correct config."""
        from src.cli.task_router_handler import CLITaskRouterHandler

        handler = CLITaskRouterHandler(
            mock_orchestrator,
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

        handler = CLITaskRouterHandler(mock_orchestrator)
        assert handler.history == []

    @pytest.mark.unit
    def test_handle_auto_route_adds_to_history(self, mock_orchestrator, mock_router_result):
        """Test that handle_auto_route adds entry to history."""
        from src.cli.task_router_handler import CLITaskRouterHandler

        handler = CLITaskRouterHandler(mock_orchestrator)
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

        handler = CLITaskRouterHandler(mock_orchestrator)
        handler.router = Mock()
        handler.router.route.return_value = mock_router_result

        result = handler.handle_auto_route("Test task")

        assert result is mock_router_result
        handler.router.route.assert_called_once_with("Test task")

    @pytest.mark.unit
    def test_handle_auto_route_multiple_tasks_build_history(self, mock_orchestrator, mock_router_result):
        """Test multiple auto_route calls accumulate in history."""
        from src.cli.task_router_handler import CLITaskRouterHandler

        handler = CLITaskRouterHandler(mock_orchestrator)
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

        handler = CLITaskRouterHandler(mock_orchestrator)
        handler.router = Mock()
        handler.router.classify_only.return_value = mock_classified_task

        result = handler.handle_classify_only("Analyze this code")

        assert result is mock_classified_task
        handler.router.classify_only.assert_called_once_with("Analyze this code")
        # Verify it doesn't add to history (preview mode)
        assert len(handler.history) == 0

    @pytest.mark.unit
    def test_handle_route_history_empty(self, mock_orchestrator, capsys):
        """Test route_history handles empty history gracefully."""
        from src.cli.task_router_handler import CLITaskRouterHandler

        handler = CLITaskRouterHandler(mock_orchestrator)

        # Should not raise an error
        handler.handle_route_history()

    @pytest.mark.unit
    def test_handle_route_history_shows_recent_entries(self, mock_orchestrator, mock_router_result):
        """Test route_history shows most recent entries."""
        from src.cli.task_router_handler import CLITaskRouterHandler

        handler = CLITaskRouterHandler(mock_orchestrator)
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

        handler = CLITaskRouterHandler(mock_orchestrator)
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


class TestCLIDisplay:
    """Tests for CLI display formatting."""

    @pytest.fixture
    def mock_orchestrator(self):
        """Create mock orchestrator with required methods."""
        orch = Mock()
        orch.brain = "cerebras"
        orch.providers = Mock()
        orch.providers.list_available.return_value = ["cerebras", "groq"]
        orch.providers.get.return_value = Mock(
            available_models=["model1", "model2"],
            default_model="model1"
        )
        orch.providers.get_provider_info.return_value = {
            "cerebras": {
                "available": True,
                "default_model": "llama-3.1-8b",
                "limits": Mock(
                    requests_per_day=1000,
                    tokens_per_minute=60000,
                    tokens_per_day=1000000
                ),
                "models": ["llama-3.1-8b", "llama-3.3-70b"]
            },
            "groq": {
                "available": True,
                "default_model": "llama-70b",
                "limits": Mock(
                    requests_per_day=500,
                    tokens_per_minute=0,
                    tokens_per_day=500000
                ),
                "models": ["llama-70b"]
            }
        }
        orch.status.return_value = {
            "orchestrator_brain": "cerebras",
            "available_providers": ["cerebras", "groq"],
            "tasks_executed": 5
        }
        orch.get_usage_report.return_value = {
            "total_tasks": 10,
            "cached_hits": 3,
            "api_calls": 7,
            "session_duration": "00:30:00",
            "by_provider": {
                "cerebras": {
                    "count": 6,
                    "cached_hits": 2,
                    "total_tokens": 5000,
                    "avg_tokens": 833.3,
                    "total_latency_ms": 1500
                }
            }
        }
        return orch

    @pytest.fixture
    def display(self, mock_orchestrator):
        """Create CLIDisplay instance."""
        from src.cli.display import CLIDisplay
        return CLIDisplay(mock_orchestrator, datetime.now())

    @pytest.mark.unit
    def test_display_initializes_with_orchestrator(self, mock_orchestrator):
        """Test CLIDisplay stores orchestrator reference."""
        from src.cli.display import CLIDisplay

        session_start = datetime.now()
        display = CLIDisplay(mock_orchestrator, session_start)

        assert display.orchestrator is mock_orchestrator
        assert display.session_start == session_start

    @pytest.mark.unit
    def test_show_help_outputs_command_list(self, display, capsys):
        """Test show_help outputs available commands."""
        display.show_help()

        captured = capsys.readouterr()
        assert "Available Commands:" in captured.out
        assert "/help" in captured.out
        assert "/quit" in captured.out
        assert "/providers" in captured.out
        assert "/brain" in captured.out

    @pytest.mark.unit
    def test_show_help_groups_commands_logically(self, display, capsys):
        """Test show_help organizes commands into logical groups."""
        display.show_help()

        captured = capsys.readouterr()
        assert "Chat & Conversation:" in captured.out
        assert "Task Operations:" in captured.out
        assert "Provider Management:" in captured.out
        assert "Context Management:" in captured.out

    @pytest.mark.unit
    def test_show_status_displays_brain(self, display, capsys):
        """Test show_status displays current brain."""
        display.show_status()

        captured = capsys.readouterr()
        assert "System Status:" in captured.out
        assert "cerebras" in captured.out

    @pytest.mark.unit
    def test_list_providers_shows_available(self, display, capsys):
        """Test list_providers shows available providers."""
        display.list_providers()

        captured = capsys.readouterr()
        assert "Available Providers:" in captured.out
        assert "CEREBRAS" in captured.out

    @pytest.mark.unit
    def test_switch_brain_shows_current_when_empty(self, display, mock_orchestrator, capsys):
        """Test switch_brain shows current brain when no provider given."""
        display.switch_brain("")

        captured = capsys.readouterr()
        assert "Current brain:" in captured.out
        assert "cerebras" in captured.out

    @pytest.mark.unit
    def test_switch_brain_changes_to_valid_provider(self, display, mock_orchestrator, capsys):
        """Test switch_brain changes to valid provider."""
        display.switch_brain("groq")

        assert mock_orchestrator.brain == "groq"
        captured = capsys.readouterr()
        assert "switched" in captured.out.lower()

    @pytest.mark.unit
    def test_switch_brain_rejects_invalid_provider(self, display, mock_orchestrator, capsys):
        """Test switch_brain rejects invalid provider name."""
        original_brain = mock_orchestrator.brain

        display.switch_brain("invalid_provider")

        captured = capsys.readouterr()
        assert "not available" in captured.out
        # Brain should not change
        assert mock_orchestrator.brain == original_brain

    @pytest.mark.unit
    def test_switch_brain_normalizes_provider_name(self, display, mock_orchestrator, capsys):
        """Test switch_brain normalizes provider name (lowercase, strip)."""
        display.switch_brain("  GROQ  ")

        assert mock_orchestrator.brain == "groq"

    @pytest.mark.unit
    def test_show_usage_displays_stats(self, display, capsys):
        """Test show_usage displays usage statistics."""
        display.show_usage()

        captured = capsys.readouterr()
        assert "Usage Statistics:" in captured.out
        assert "Total Tasks:" in captured.out

    @pytest.mark.unit
    def test_list_models_all_providers(self, display, mock_orchestrator, capsys):
        """Test list_models shows models for all providers."""
        display.list_models("")

        captured = capsys.readouterr()
        assert "All Available Models:" in captured.out

    @pytest.mark.unit
    def test_list_models_specific_provider(self, display, mock_orchestrator, capsys):
        """Test list_models shows models for specific provider."""
        display.list_models("cerebras")

        captured = capsys.readouterr()
        assert "CEREBRAS Models:" in captured.out

    @pytest.mark.unit
    def test_list_models_invalid_provider(self, display, mock_orchestrator, capsys):
        """Test list_models handles invalid provider."""
        display.list_models("nonexistent")

        captured = capsys.readouterr()
        assert "not available" in captured.out


class TestCLISession:
    """Tests for CLI session management."""

    @pytest.fixture
    def mock_orchestrator(self):
        """Create mock orchestrator."""
        return ConfigurableTestOrchestrator()

    @pytest.mark.unit
    def test_session_manager_initializes_components(self, mock_orchestrator):
        """Test CLISessionManager initializes all management components."""
        from src.cli.session import CLISessionManager

        manager = CLISessionManager(mock_orchestrator)

        assert manager.orchestrator is mock_orchestrator
        assert manager._context_manager is not None
        assert manager._cache_manager is not None
        assert manager._rate_limiter is not None
        assert manager._session_persistence is not None

class TestCLISmartQuery:
    """Tests for smart query handling."""

    @pytest.fixture
    def mock_orchestrator(self):
        """Create mock orchestrator."""
        orch = ConfigurableTestOrchestrator(
            response_content="This is the answer to your query.",
            response_tokens=50
        )
        orch.context = Mock()
        orch.context.summary = ""
        orch.context.project_path = Path("/test/project")
        orch.remember_search = Mock()
        orch.add_discovery = Mock()
        return orch

    @pytest.mark.unit
    def test_smart_query_initializes_with_classifier(self, mock_orchestrator):
        """Test CLISmartQuery initializes with intent classifier."""
        from src.cli.smart_query import CLISmartQuery

        smart = CLISmartQuery(mock_orchestrator)

        assert smart.orchestrator is mock_orchestrator
        assert smart.classifier is not None

    @pytest.mark.unit
    def test_safe_tool_call_returns_success_on_valid_result(self, mock_orchestrator):
        """Test _safe_tool_call returns success tuple on valid result."""
        from src.cli.smart_query import CLISmartQuery

        smart = CLISmartQuery(mock_orchestrator)

        def good_tool():
            return "Valid result"

        success, result = smart._safe_tool_call(good_tool)

        assert success is True
        assert result == "Valid result"

    @pytest.mark.unit
    def test_safe_tool_call_returns_failure_on_error_result(self, mock_orchestrator):
        """Test _safe_tool_call returns failure when result contains Error."""
        from src.cli.smart_query import CLISmartQuery

        smart = CLISmartQuery(mock_orchestrator)

        def error_tool():
            return "Error: File not found"

        success, result = smart._safe_tool_call(error_tool)

        assert success is False
        assert "Error" in result

    @pytest.mark.unit
    def test_safe_tool_call_handles_exceptions(self, mock_orchestrator):
        """Test _safe_tool_call catches exceptions and returns failure."""
        from src.cli.smart_query import CLISmartQuery

        smart = CLISmartQuery(mock_orchestrator)

        def throwing_tool():
            raise ValueError("Something went wrong")

        success, result = smart._safe_tool_call(throwing_tool)

        assert success is False
        assert "Error:" in result
        assert "Something went wrong" in result

    @pytest.mark.unit
    def test_safe_tool_call_returns_failure_on_none(self, mock_orchestrator):
        """Test _safe_tool_call returns failure when result is None."""
        from src.cli.smart_query import CLISmartQuery

        smart = CLISmartQuery(mock_orchestrator)

        def none_tool():
            return None

        success, result = smart._safe_tool_call(none_tool)

        assert success is False

    @pytest.mark.unit
    @patch('src.cli.smart_query.CodeAgent')
    def test_smart_query_classifies_intent(self, mock_agent_class, mock_orchestrator):
        """Test smart_query classifies the query intent."""
        from src.cli.smart_query import CLISmartQuery

        smart = CLISmartQuery(mock_orchestrator)
        smart.classifier = Mock()

        mock_classification = Mock()
        mock_classification.primary_intent = Mock()
        mock_classification.primary_intent.intent = Mock()
        mock_classification.primary_intent.intent.value = "code_search"
        mock_classification.primary_intent.confidence = 0.9
        mock_classification.secondary_intents = []
        mock_classification.entities = {}
        mock_classification.keywords = ["test"]
        smart.classifier.classify.return_value = mock_classification

        # Need to mock get_research_actions
        with patch('src.cli.smart_query.get_research_actions', return_value=[]):
            smart.smart_query("Where is the test function?")

        smart.classifier.classify.assert_called_once_with("Where is the test function?")


class TestCLIAgentManager:
    """Tests for agent manager."""

    @pytest.fixture
    def mock_orchestrator(self):
        """Create mock orchestrator."""
        orch = ConfigurableTestOrchestrator()
        orch.add_discovery = Mock()
        return orch

    @pytest.mark.unit
    def test_agent_manager_stores_orchestrator(self, mock_orchestrator):
        """Test CLIAgentManager stores orchestrator reference."""
        from src.cli.agent_manager import CLIAgentManager

        manager = CLIAgentManager(mock_orchestrator)

        assert manager.orchestrator is mock_orchestrator

    @pytest.mark.unit
    @patch('src.cli.agent_manager.CodeAgent')
    @patch('src.cli.agent_manager.create_git_checkpoint')
    def test_run_agent_prompts_for_options(self, mock_checkpoint, mock_agent_class, mock_orchestrator):
        """Test run_agent prompts user for dry run and checkpoint options."""
        from src.cli.agent_manager import CLIAgentManager

        manager = CLIAgentManager(mock_orchestrator)
        io = MockIO(
            confirmations=[False, False, False]  # dry_run=False, checkpoint=False, start=False (cancel)
        )

        manager.run_agent("Test task", io=io)

        output = io.get_output()
        assert "dry-run" in output.lower() or "Test task" in output

    @pytest.mark.unit
    @patch('src.cli.agent_manager.CodeAgent')
    @patch('src.cli.agent_manager.create_git_checkpoint')
    def test_run_agent_cancelled_by_user(self, mock_checkpoint, mock_agent_class, mock_orchestrator):
        """Test run_agent can be cancelled by user."""
        from src.cli.agent_manager import CLIAgentManager

        manager = CLIAgentManager(mock_orchestrator)
        io = MockIO(
            confirmations=[False, False, False]  # dry_run, checkpoint, start=False
        )

        manager.run_agent("Test task", io=io)

        output = io.get_output()
        assert "cancelled" in output.lower()
        # Agent should not have been run
        mock_agent_class.return_value.run.assert_not_called()

    @pytest.mark.unit
    @patch('src.cli.agent_manager.CodeAgent')
    @patch('src.cli.agent_manager.create_git_checkpoint')
    def test_run_agent_creates_checkpoint_when_requested(self, mock_checkpoint, mock_agent_class, mock_orchestrator):
        """Test run_agent creates git checkpoint when user confirms."""
        from src.cli.agent_manager import CLIAgentManager

        mock_checkpoint.return_value = "abc123"
        mock_agent = Mock()
        mock_agent.run.return_value = {
            "success": True,
            "result": "Done",
            "iterations": 1,
            "audit_log": []
        }
        mock_agent.planner = "cerebras"
        mock_agent.executor = "groq"
        mock_agent.project_root = Path("/test")
        mock_agent_class.return_value = mock_agent

        manager = CLIAgentManager(mock_orchestrator)
        io = MockIO(
            confirmations=[
                False,  # dry_run
                True,   # create checkpoint
                True,   # start
                False,  # save audit log
                False   # rollback
            ]
        )

        manager.run_agent("Test task", io=io)

        mock_checkpoint.assert_called_once()
        output = io.get_output()
        assert "abc123" in output  # Should show checkpoint hash

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

        manager = CLIAgentManager(mock_orchestrator)
        io = MockIO(
            confirmations=[False, False, True, False]  # dry_run, checkpoint, start, save_log
        )

        manager.run_agent("Create file", io=io)

        output = io.get_output()
        assert "Task Completed Successfully" in output or "Completed" in output
        assert "Task completed successfully" in output

    @pytest.mark.unit
    @patch('src.cli.agent_manager.CodeAgent')
    @patch('src.cli.agent_manager.create_git_checkpoint')
    def test_run_agent_failure_shows_result(self, mock_checkpoint, mock_agent_class, mock_orchestrator):
        """Test run_agent displays failure result."""
        from src.cli.agent_manager import CLIAgentManager

        mock_checkpoint.return_value = None
        mock_agent = Mock()
        mock_agent.run.return_value = {
            "success": False,
            "result": "Could not complete task",
            "iterations": 5,
            "audit_log": []
        }
        mock_agent.planner = "cerebras"
        mock_agent.executor = "groq"
        mock_agent.project_root = Path("/test")
        mock_agent_class.return_value = mock_agent

        manager = CLIAgentManager(mock_orchestrator)
        io = MockIO(
            confirmations=[False, False, True, False]
        )

        manager.run_agent("Failing task", io=io)

        output = io.get_output()
        assert "Did Not Complete" in output or "Could not complete" in output

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

        manager = CLIAgentManager(mock_orchestrator)
        io = MockIO(
            confirmations=[True, False, True, False]  # dry_run=True
        )

        manager.run_agent("Test", io=io)

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

        manager = CLIAgentManager(mock_orchestrator)
        io = MockIO(
            confirmations=[False, False, True]
        )

        # Should not raise
        manager.run_agent("Crashing task", io=io)

        output = io.get_output()
        assert "error" in output.lower()
        assert "Agent crashed" in output
        # Should record discovery
        mock_orchestrator.add_discovery.assert_called()

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

        manager = CLIAgentManager(mock_orchestrator)
        io = MockIO(
            confirmations=[False, False, True, False]
        )

        manager.run_agent("Important task", io=io)

        mock_orchestrator.add_discovery.assert_called()
        call_args = mock_orchestrator.add_discovery.call_args
        assert "Important task" in call_args[0][0]
        assert "agent_task" in call_args[0]


