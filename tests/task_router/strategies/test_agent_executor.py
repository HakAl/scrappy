"""
Tests for AgentExecutor strategy.

Tests the full agent loop execution strategy for code generation tasks.
"""
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from scrappy.task_router.strategies.agent_executor import AgentExecutor
from scrappy.task_router.strategies.base import ExecutionResult
from scrappy.task_router.classifier import ClassifiedTask
from scrappy.task_router.classification_strategy import TaskType


def create_mock_orchestrator():
    """Create a mock orchestrator for testing."""
    orchestrator = Mock()
    orchestrator.brain = "test_provider"
    orchestrator.providers = Mock()
    orchestrator.providers.list_available.return_value = ["test_provider", "other"]
    return orchestrator


def create_classified_task(
    task_type: TaskType = TaskType.CODE_GENERATION,
    original_input: str = "Create a hello world function",
    requires_planning: bool = False,
    confidence: float = 0.9,
) -> ClassifiedTask:
    """Create a ClassifiedTask for testing."""
    return ClassifiedTask(
        original_input=original_input,
        task_type=task_type,
        confidence=confidence,
        reasoning="Test task",
        requires_planning=requires_planning,
    )


class TestAgentExecutorInit:
    """Tests for AgentExecutor initialization."""

    @pytest.mark.unit
    def test_init_with_defaults(self):
        """Should initialize with default values."""
        orchestrator = create_mock_orchestrator()
        executor = AgentExecutor(orchestrator)

        assert executor.orchestrator is orchestrator
        assert executor.project_root == Path.cwd()
        assert executor.max_iterations == 50  # Updated default for extended agent mode
        assert executor.require_approval is True
        assert executor.io is None

    @pytest.mark.unit
    def test_init_with_custom_values(self):
        """Should accept custom configuration."""
        orchestrator = create_mock_orchestrator()
        project_root = Path("/custom/path")
        io = Mock()

        executor = AgentExecutor(
            orchestrator=orchestrator,
            project_root=project_root,
            max_iterations=5,
            require_approval=False,
            io=io,
        )

        assert executor.project_root == project_root
        assert executor.max_iterations == 5
        assert executor.require_approval is False
        assert executor.io is io

    @pytest.mark.unit
    def test_name_property(self):
        """name property should return 'AgentExecutor'."""
        orchestrator = create_mock_orchestrator()
        executor = AgentExecutor(orchestrator)

        assert executor.name == "AgentExecutor"


class TestAgentExecutorCanHandle:
    """Tests for can_handle method."""

    @pytest.mark.unit
    def test_can_handle_code_generation(self):
        """Should handle CODE_GENERATION tasks."""
        orchestrator = create_mock_orchestrator()
        executor = AgentExecutor(orchestrator)
        task = create_classified_task(task_type=TaskType.CODE_GENERATION)

        assert executor.can_handle(task) is True

    @pytest.mark.unit
    def test_cannot_handle_research(self):
        """Should not handle RESEARCH tasks."""
        orchestrator = create_mock_orchestrator()
        executor = AgentExecutor(orchestrator)
        task = create_classified_task(task_type=TaskType.RESEARCH)

        assert executor.can_handle(task) is False

    @pytest.mark.unit
    def test_cannot_handle_direct_command(self):
        """Should not handle DIRECT_COMMAND tasks."""
        orchestrator = create_mock_orchestrator()
        executor = AgentExecutor(orchestrator)
        task = create_classified_task(task_type=TaskType.DIRECT_COMMAND)

        assert executor.can_handle(task) is False

    @pytest.mark.unit
    def test_cannot_handle_conversation(self):
        """Should not handle CONVERSATION tasks."""
        orchestrator = create_mock_orchestrator()
        executor = AgentExecutor(orchestrator)
        task = create_classified_task(task_type=TaskType.CONVERSATION)

        assert executor.can_handle(task) is False


class TestAgentExecutorExecute:
    """Tests for execute method.

    Note: Tests that require mocking internal imports (CodeAgent, AgentOrchestratorAdapter)
    are tested via the fallback path since the local imports make direct mocking difficult.
    """

    @pytest.mark.unit
    def test_execute_triggers_fallback_on_import_error(self):
        """Execute should fall back to LLM when imports fail."""
        orchestrator = create_mock_orchestrator()
        mock_response = Mock()
        mock_response.content = "Generated code here"
        mock_response.tokens_used = 100
        orchestrator.delegate.return_value = mock_response

        executor = AgentExecutor(orchestrator)
        task = create_classified_task()

        # The execute method uses local imports that may fail
        # In that case, it should fall back to _fallback_execution
        result = executor.execute(task)

        # Result should either be from agent loop or fallback
        assert result is not None
        assert hasattr(result, 'success')
        assert hasattr(result, 'output')
        assert hasattr(result, 'execution_time')

    @pytest.mark.unit
    def test_execute_handles_exception_gracefully(self):
        """Execute should handle exceptions without crashing."""
        orchestrator = create_mock_orchestrator()
        # Make delegate raise to test error handling in fallback too
        orchestrator.delegate.side_effect = Exception("Total failure")

        executor = AgentExecutor(orchestrator)
        task = create_classified_task()

        result = executor.execute(task)

        # Should return an error result, not crash
        assert result.success is False
        assert result.error is not None

    @pytest.mark.unit
    def test_execute_measures_execution_time(self):
        """Execute should measure and return execution time."""
        orchestrator = create_mock_orchestrator()
        mock_response = Mock()
        mock_response.content = "code"
        mock_response.tokens_used = 10
        orchestrator.delegate.return_value = mock_response

        executor = AgentExecutor(orchestrator)
        task = create_classified_task()

        result = executor.execute(task)

        # Execution time should be positive (even if small)
        assert result.execution_time >= 0


class TestAgentExecutorRunPlanning:
    """Tests for _run_planning method."""

    @pytest.mark.unit
    def test_run_planning_with_list_result(self):
        """Plan list should be formatted as bullet points."""
        orchestrator = create_mock_orchestrator()
        orchestrator.plan.return_value = ["Step 1", "Step 2", "Step 3"]

        executor = AgentExecutor(orchestrator)
        task = create_classified_task()

        result = executor._run_planning(task)

        assert "- Step 1" in result
        assert "- Step 2" in result
        assert "- Step 3" in result

    @pytest.mark.unit
    def test_run_planning_with_string_result(self):
        """Plan string should be returned as-is."""
        orchestrator = create_mock_orchestrator()
        orchestrator.plan.return_value = "Complete plan as string"

        executor = AgentExecutor(orchestrator)
        task = create_classified_task()

        result = executor._run_planning(task)

        assert result == "Complete plan as string"

    @pytest.mark.unit
    def test_run_planning_no_plan_method(self):
        """Should return None if orchestrator has no plan method."""
        orchestrator = create_mock_orchestrator()
        del orchestrator.plan  # Remove the plan attribute

        executor = AgentExecutor(orchestrator)
        task = create_classified_task()

        result = executor._run_planning(task)

        assert result is None

    @pytest.mark.unit
    def test_run_planning_exception_returns_none(self):
        """Exception during planning should return None."""
        orchestrator = create_mock_orchestrator()
        orchestrator.plan.side_effect = Exception("Planning failed")

        executor = AgentExecutor(orchestrator)
        task = create_classified_task()

        result = executor._run_planning(task)

        assert result is None


class TestAgentExecutorTaskGuidance:
    """Tests for _get_task_specific_guidance method."""

    @pytest.mark.unit
    def test_guidance_for_requirements_creation(self):
        """Requirements.txt creation should get specific guidance."""
        orchestrator = create_mock_orchestrator()
        executor = AgentExecutor(orchestrator)
        task = create_classified_task(
            original_input="Create requirements.txt for this project"
        )

        guidance = executor._get_task_specific_guidance(task)

        assert "CRITICAL GUIDANCE for requirements.txt" in guidance
        assert "THIRD-PARTY" in guidance
        assert "STANDARD LIBRARY" in guidance

    @pytest.mark.unit
    def test_guidance_for_config_file(self):
        """Config file creation should get specific guidance."""
        orchestrator = create_mock_orchestrator()
        executor = AgentExecutor(orchestrator)
        task = create_classified_task(
            original_input="Create a .env configuration file"
        )

        guidance = executor._get_task_specific_guidance(task)

        assert "IMPORTANT GUIDANCE for config files" in guidance
        assert "sensitive values" in guidance

    @pytest.mark.unit
    def test_guidance_for_refactoring(self):
        """Refactoring should get specific guidance."""
        orchestrator = create_mock_orchestrator()
        executor = AgentExecutor(orchestrator)
        task = create_classified_task(
            original_input="Refactor this class to use dependency injection"
        )

        guidance = executor._get_task_specific_guidance(task)

        assert "IMPORTANT GUIDANCE for code modification" in guidance
        assert "read the existing file first" in guidance

    @pytest.mark.unit
    def test_guidance_for_file_creation(self):
        """File creation should get specific guidance."""
        orchestrator = create_mock_orchestrator()
        executor = AgentExecutor(orchestrator)
        task = create_classified_task(
            original_input="Create a new utility module"
        )

        guidance = executor._get_task_specific_guidance(task)

        assert "IMPORTANT GUIDANCE for file creation" in guidance
        assert "NEVER write an empty file" in guidance

    @pytest.mark.unit
    def test_guidance_for_dockerfile(self):
        """Dockerfile creation should get specific guidance."""
        orchestrator = create_mock_orchestrator()
        executor = AgentExecutor(orchestrator)
        task = create_classified_task(
            original_input="Create a Dockerfile for this application"
        )

        guidance = executor._get_task_specific_guidance(task)

        assert "IMPORTANT GUIDANCE for Dockerfile" in guidance
        assert "base image" in guidance

    @pytest.mark.unit
    def test_guidance_empty_for_generic_task(self):
        """Generic task should get empty guidance."""
        orchestrator = create_mock_orchestrator()
        executor = AgentExecutor(orchestrator)
        task = create_classified_task(
            original_input="Fix the bug in login function"
        )

        guidance = executor._get_task_specific_guidance(task)

        assert guidance == ""

    @pytest.mark.unit
    def test_guidance_multiple_matches(self):
        """Task matching multiple patterns should get combined guidance."""
        orchestrator = create_mock_orchestrator()
        executor = AgentExecutor(orchestrator)
        task = create_classified_task(
            original_input="Create and update the config settings file"
        )

        guidance = executor._get_task_specific_guidance(task)

        # Should have both config and file creation guidance
        assert "IMPORTANT GUIDANCE for config files" in guidance
        assert "IMPORTANT GUIDANCE for file creation" in guidance


class TestAgentExecutorFallback:
    """Tests for _fallback_execution method."""

    @pytest.mark.unit
    def test_fallback_success(self):
        """Successful fallback should return generated code."""
        orchestrator = create_mock_orchestrator()
        mock_response = Mock()
        mock_response.content = "def hello(): pass"
        mock_response.tokens_used = 50
        orchestrator.delegate.return_value = mock_response

        executor = AgentExecutor(orchestrator)
        task = create_classified_task()

        result = executor._fallback_execution(task, time.time(), "Import error")

        assert result.success is True
        assert result.output == "def hello(): pass"
        assert result.tokens_used == 50
        assert result.provider_used == "fallback_llm"
        assert result.metadata["fallback_reason"] == "Import error"
        assert result.metadata["mode"] == "simple_generation"

    @pytest.mark.unit
    def test_fallback_with_response_without_content_attr(self):
        """Fallback should handle response without content attribute."""
        orchestrator = create_mock_orchestrator()
        orchestrator.delegate.return_value = "Plain string response"

        executor = AgentExecutor(orchestrator)
        task = create_classified_task()

        result = executor._fallback_execution(task, time.time(), "Import error")

        assert result.success is True
        assert result.output == "Plain string response"
        assert result.tokens_used == 0

    @pytest.mark.unit
    def test_fallback_exception(self):
        """Exception in fallback should return error result."""
        orchestrator = create_mock_orchestrator()
        orchestrator.delegate.side_effect = Exception("Delegate failed")

        executor = AgentExecutor(orchestrator)
        task = create_classified_task()

        result = executor._fallback_execution(task, time.time(), "Import error")

        assert result.success is False
        assert "Fallback execution failed" in result.error
        assert "Delegate failed" in result.error

    @pytest.mark.unit
    def test_fallback_uses_brain_provider(self):
        """Fallback should use orchestrator's brain provider."""
        orchestrator = create_mock_orchestrator()
        orchestrator.brain = "gpt-4"
        mock_response = Mock()
        mock_response.content = "code"
        mock_response.tokens_used = 10
        orchestrator.delegate.return_value = mock_response

        executor = AgentExecutor(orchestrator)
        task = create_classified_task()

        executor._fallback_execution(task, time.time(), "error")

        # Check delegate was called with brain provider
        call_args = orchestrator.delegate.call_args
        assert call_args[0][0] == "gpt-4"


class TestAgentExecutorIntegration:
    """Integration-style tests for AgentExecutor."""

    @pytest.mark.unit
    def test_planning_and_guidance_combined(self):
        """Test that planning result and guidance work together."""
        orchestrator = create_mock_orchestrator()
        orchestrator.plan.return_value = ["Step 1", "Step 2"]

        executor = AgentExecutor(orchestrator)
        task = create_classified_task(
            original_input="Create requirements.txt for this project",
            requires_planning=True,
        )

        # Test planning returns proper format
        plan = executor._run_planning(task)
        assert plan is not None
        assert "Step 1" in plan

        # Test guidance is generated
        guidance = executor._get_task_specific_guidance(task)
        assert "requirements.txt" in guidance

    @pytest.mark.unit
    def test_set_provider_stored_correctly(self):
        """Test provider can be set and retrieved."""
        orchestrator = create_mock_orchestrator()
        executor = AgentExecutor(orchestrator)

        # Initially no provider set
        assert executor._resolved_provider is None
        assert executor._resolved_model is None

        # Set provider
        executor.set_provider("custom_provider", "custom_model")
        assert executor._resolved_provider == "custom_provider"
        assert executor._resolved_model == "custom_model"

        # Can be set to None
        executor.set_provider(None, None)
        assert executor._resolved_provider is None
        assert executor._resolved_model is None

    @pytest.mark.unit
    def test_fallback_flow_complete(self):
        """Test complete fallback execution flow."""
        orchestrator = create_mock_orchestrator()
        mock_response = Mock()
        mock_response.content = "def hello():\n    print('Hello')"
        mock_response.tokens_used = 25
        orchestrator.delegate.return_value = mock_response

        executor = AgentExecutor(orchestrator)
        task = create_classified_task(
            original_input="Write a hello world function"
        )

        result = executor.execute(task)

        # Verify fallback produced valid result
        assert result is not None
        assert result.execution_time >= 0
        # Output should contain something (either from agent or fallback)
        assert result.output is not None
