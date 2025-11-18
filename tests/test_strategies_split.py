"""
Tests for strategies module split - demonstrates TDD for refactoring.

CRITICAL: These tests are written FIRST to prove the refactoring works.

We're testing that:
1. Each strategy can be imported from its own module
2. Each strategy maintains its original behavior
3. The base classes and protocols are properly shared
4. No circular dependencies exist
5. All strategies implement the required interface
"""
import pytest
from unittest.mock import Mock
from pathlib import Path

from src.task_router.classifier import ClassifiedTask, TaskType


class TestStrategyImports:
    """Test that all strategies can be imported from separate files."""

    @pytest.mark.unit
    def test_import_execution_result_from_base(self):
        """Test ExecutionResult can be imported from base module."""
        from src.task_router.strategies.base import ExecutionResult

        result = ExecutionResult(
            success=True,
            output="test output",
            execution_time=1.5
        )

        assert result.success is True
        assert result.output == "test output"
        assert result.execution_time == 1.5

    @pytest.mark.unit
    def test_import_execution_strategy_from_base(self):
        """Test ExecutionStrategy abstract base can be imported."""
        from src.task_router.strategies.base import ExecutionStrategy

        assert hasattr(ExecutionStrategy, 'execute')
        assert hasattr(ExecutionStrategy, 'can_handle')
        assert hasattr(ExecutionStrategy, 'name')

    @pytest.mark.unit
    def test_import_protocols_from_base(self):
        """Test all protocol classes can be imported from base."""
        from src.task_router.strategies.base import (
            ContextLike,
            ProviderRegistryLike,
            LLMResponseLike,
            OrchestratorLike
        )

        # Verify protocols exist and have expected methods
        assert hasattr(ContextLike, 'is_explored')
        assert hasattr(ProviderRegistryLike, 'list_available')
        assert hasattr(LLMResponseLike, 'content')
        assert hasattr(OrchestratorLike, 'delegate')

    @pytest.mark.unit
    def test_import_direct_executor(self):
        """Test DirectExecutor can be imported from its own module."""
        from src.task_router.strategies.direct_executor import DirectExecutor

        executor = DirectExecutor()
        assert executor.name == "DirectExecutor"

    @pytest.mark.unit
    def test_import_conversation_executor(self):
        """Test ConversationExecutor can be imported from its own module."""
        from src.task_router.strategies.conversation_executor import ConversationExecutor

        executor = ConversationExecutor()
        assert executor.name == "ConversationExecutor"

    @pytest.mark.unit
    def test_import_research_executor(self):
        """Test ResearchExecutor can be imported from its own module."""
        from src.task_router.strategies.research_executor import ResearchExecutor

        # Need mock orchestrator
        mock_orch = Mock()
        mock_orch.context = Mock()
        mock_orch.context.is_explored.return_value = False
        mock_orch.brain = "cerebras"
        mock_orch.providers = Mock()
        mock_orch.providers.list_available.return_value = ["cerebras"]

        executor = ResearchExecutor(orchestrator=mock_orch)
        assert executor.name == "ResearchExecutor"

    @pytest.mark.unit
    def test_import_agent_executor(self):
        """Test AgentExecutor can be imported from its own module."""
        from src.task_router.strategies.agent_executor import AgentExecutor

        # Need mock orchestrator
        mock_orch = Mock()
        executor = AgentExecutor(orchestrator=mock_orch)
        assert executor.name == "AgentExecutor"


class TestDirectExecutorBehavior:
    """Test DirectExecutor behavior after split."""

    @pytest.mark.unit
    def test_direct_executor_can_handle_direct_commands(self):
        """Test DirectExecutor correctly identifies tasks it can handle."""
        from src.task_router.strategies.direct_executor import DirectExecutor

        executor = DirectExecutor()

        # Can handle direct command
        task = ClassifiedTask(
            original_input="echo test",
            task_type=TaskType.DIRECT_COMMAND,
            confidence=0.9,
            reasoning="Direct command",
            extracted_command="echo test"
        )

        assert executor.can_handle(task) is True

    @pytest.mark.unit
    def test_direct_executor_rejects_non_direct_tasks(self):
        """Test DirectExecutor rejects tasks without extracted command."""
        from src.task_router.strategies.direct_executor import DirectExecutor

        executor = DirectExecutor()

        # Cannot handle research task
        task = ClassifiedTask(
            original_input="explain python",
            task_type=TaskType.RESEARCH,
            confidence=0.9,
            reasoning="Research task"
        )

        assert executor.can_handle(task) is False

    @pytest.mark.unit
    def test_direct_executor_blocks_unsafe_commands(self):
        """Test DirectExecutor blocks dangerous commands."""
        from src.task_router.strategies.direct_executor import DirectExecutor

        executor = DirectExecutor()

        task = ClassifiedTask(
            original_input="rm -rf /",
            task_type=TaskType.DIRECT_COMMAND,
            confidence=0.9,
            reasoning="Dangerous command",
            extracted_command="rm -rf /"
        )

        result = executor.execute(task)

        assert result.success is False
        assert "blocked" in result.error.lower() or "safety" in result.error.lower()

    @pytest.mark.unit
    def test_direct_executor_executes_safe_commands(self):
        """Test DirectExecutor executes safe commands."""
        from src.task_router.strategies.direct_executor import DirectExecutor

        executor = DirectExecutor()

        # Echo is safe
        task = ClassifiedTask(
            original_input='echo "hello world"',
            task_type=TaskType.DIRECT_COMMAND,
            confidence=0.9,
            reasoning="Safe echo command",
            extracted_command='echo "hello world"'
        )

        result = executor.execute(task)

        assert result.success is True
        assert "hello world" in result.output.lower()


class TestConversationExecutorBehavior:
    """Test ConversationExecutor behavior after split."""

    @pytest.mark.unit
    def test_conversation_executor_handles_greetings(self):
        """Test ConversationExecutor handles greeting patterns."""
        from src.task_router.strategies.conversation_executor import ConversationExecutor

        executor = ConversationExecutor()

        task = ClassifiedTask(
            original_input="hello",
            task_type=TaskType.CONVERSATION,
            confidence=0.95,
            reasoning="Greeting detected",
            matched_patterns=["greeting"]
        )

        result = executor.execute(task)

        assert result.success is True
        assert len(result.output) > 0
        assert "hello" in result.output.lower() or "help" in result.output.lower()

    @pytest.mark.unit
    def test_conversation_executor_handles_thanks(self):
        """Test ConversationExecutor handles thank you patterns."""
        from src.task_router.strategies.conversation_executor import ConversationExecutor

        executor = ConversationExecutor()

        task = ClassifiedTask(
            original_input="thanks",
            task_type=TaskType.CONVERSATION,
            confidence=0.95,
            reasoning="Thanks detected",
            matched_patterns=["thanks"]
        )

        result = executor.execute(task)

        assert result.success is True
        assert "welcome" in result.output.lower()

    @pytest.mark.unit
    def test_conversation_executor_only_handles_conversation(self):
        """Test ConversationExecutor only accepts CONVERSATION tasks."""
        from src.task_router.strategies.conversation_executor import ConversationExecutor

        executor = ConversationExecutor()

        # Should handle CONVERSATION
        conv_task = ClassifiedTask(
            original_input="hello",
            task_type=TaskType.CONVERSATION,
            confidence=0.9,
            reasoning="Conversation"
        )
        assert executor.can_handle(conv_task) is True

        # Should NOT handle CODE_GENERATION
        code_task = ClassifiedTask(
            original_input="write code",
            task_type=TaskType.CODE_GENERATION,
            confidence=0.9,
            reasoning="Code task"
        )
        assert executor.can_handle(code_task) is False


class TestResearchExecutorBehavior:
    """Test ResearchExecutor behavior after split."""

    @pytest.fixture
    def mock_orchestrator(self):
        """Create a mock orchestrator for ResearchExecutor."""
        mock = Mock()
        mock.context = Mock()
        mock.context.is_explored.return_value = False
        mock.context.get_summary.return_value = ""
        mock.brain = "cerebras"
        mock.providers = Mock()
        mock.providers.list_available.return_value = ["cerebras", "groq"]

        # Mock delegate to return a response
        mock_response = Mock()
        mock_response.content = "This is a research answer about Python."
        mock_response.tokens_used = 100
        mock.delegate.return_value = mock_response

        return mock

    @pytest.mark.unit
    def test_research_executor_can_handle_research_tasks(self, mock_orchestrator):
        """Test ResearchExecutor identifies RESEARCH tasks."""
        from src.task_router.strategies.research_executor import ResearchExecutor

        executor = ResearchExecutor(orchestrator=mock_orchestrator)

        task = ClassifiedTask(
            original_input="explain python",
            task_type=TaskType.RESEARCH,
            confidence=0.9,
            reasoning="Research question"
        )

        assert executor.can_handle(task) is True

    @pytest.mark.unit
    def test_research_executor_rejects_non_research_tasks(self, mock_orchestrator):
        """Test ResearchExecutor rejects non-RESEARCH tasks."""
        from src.task_router.strategies.research_executor import ResearchExecutor

        executor = ResearchExecutor(orchestrator=mock_orchestrator)

        task = ClassifiedTask(
            original_input="create file",
            task_type=TaskType.CODE_GENERATION,
            confidence=0.9,
            reasoning="Code generation"
        )

        assert executor.can_handle(task) is False

    @pytest.mark.unit
    def test_research_executor_executes_research_task(self, mock_orchestrator):
        """Test ResearchExecutor executes research tasks."""
        from src.task_router.strategies.research_executor import ResearchExecutor

        executor = ResearchExecutor(orchestrator=mock_orchestrator)

        task = ClassifiedTask(
            original_input="what is python?",
            task_type=TaskType.RESEARCH,
            confidence=0.95,
            reasoning="Question about Python"
        )

        result = executor.execute(task)

        assert result.success is True
        assert len(result.output) > 0
        assert result.tokens_used > 0
        # Verify orchestrator was called
        mock_orchestrator.delegate.assert_called()

    @pytest.mark.unit
    def test_research_executor_uses_preferred_provider(self, mock_orchestrator):
        """Test ResearchExecutor uses specified provider."""
        from src.task_router.strategies.research_executor import ResearchExecutor

        executor = ResearchExecutor(
            orchestrator=mock_orchestrator,
            preferred_provider="groq"
        )

        task = ClassifiedTask(
            original_input="explain recursion",
            task_type=TaskType.RESEARCH,
            confidence=0.9,
            reasoning="Research"
        )

        executor.execute(task)

        # Check that delegate was called with groq
        call_args = mock_orchestrator.delegate.call_args
        assert call_args[0][0] == "groq"

    @pytest.mark.unit
    def test_research_executor_handles_errors_gracefully(self, mock_orchestrator):
        """Test ResearchExecutor handles errors without crashing."""
        from src.task_router.strategies.research_executor import ResearchExecutor

        # Make delegate raise an exception
        mock_orchestrator.delegate.side_effect = Exception("API failure")

        executor = ResearchExecutor(orchestrator=mock_orchestrator)

        task = ClassifiedTask(
            original_input="what is AI?",
            task_type=TaskType.RESEARCH,
            confidence=0.9,
            reasoning="Research"
        )

        result = executor.execute(task)

        # Should fail gracefully
        assert result.success is False
        assert result.error is not None
        assert "failed" in result.error.lower()


class TestAgentExecutorBehavior:
    """Test AgentExecutor behavior after split."""

    @pytest.fixture
    def mock_orchestrator(self):
        """Create a mock orchestrator for AgentExecutor."""
        mock = Mock()
        mock.context = Mock()
        mock.brain = "groq"
        mock.providers = Mock()
        return mock

    @pytest.mark.unit
    def test_agent_executor_can_handle_code_generation(self, mock_orchestrator):
        """Test AgentExecutor identifies CODE_GENERATION tasks."""
        from src.task_router.strategies.agent_executor import AgentExecutor

        executor = AgentExecutor(orchestrator=mock_orchestrator)

        task = ClassifiedTask(
            original_input="create a file",
            task_type=TaskType.CODE_GENERATION,
            confidence=0.9,
            reasoning="Code generation needed"
        )

        assert executor.can_handle(task) is True

    @pytest.mark.unit
    def test_agent_executor_rejects_non_code_tasks(self, mock_orchestrator):
        """Test AgentExecutor rejects non-CODE_GENERATION tasks."""
        from src.task_router.strategies.agent_executor import AgentExecutor

        executor = AgentExecutor(orchestrator=mock_orchestrator)

        task = ClassifiedTask(
            original_input="what is python?",
            task_type=TaskType.RESEARCH,
            confidence=0.9,
            reasoning="Research question"
        )

        assert executor.can_handle(task) is False

    @pytest.mark.unit
    def test_agent_executor_has_max_iterations(self, mock_orchestrator):
        """Test AgentExecutor can be configured with max iterations."""
        from src.task_router.strategies.agent_executor import AgentExecutor

        executor = AgentExecutor(
            orchestrator=mock_orchestrator,
            max_iterations=15
        )

        assert executor.max_iterations == 15

    @pytest.mark.unit
    def test_agent_executor_has_project_root(self, mock_orchestrator):
        """Test AgentExecutor accepts project root path."""
        from src.task_router.strategies.agent_executor import AgentExecutor

        test_path = Path("/test/project")
        executor = AgentExecutor(
            orchestrator=mock_orchestrator,
            project_root=test_path
        )

        assert executor.project_root == test_path

    @pytest.mark.unit
    def test_agent_executor_provider_resolution(self, mock_orchestrator):
        """Test AgentExecutor can have provider set dynamically."""
        from src.task_router.strategies.agent_executor import AgentExecutor

        executor = AgentExecutor(orchestrator=mock_orchestrator)

        # Should be able to set provider
        executor.set_provider("openai", "gpt-4")

        # Verify provider was stored
        assert executor._resolved_provider == "openai"
        assert executor._resolved_model == "gpt-4"


class TestStrategyInterfaceCompliance:
    """Test all strategies implement the required interface."""

    @pytest.mark.unit
    def test_all_strategies_have_execute_method(self):
        """Test all strategies implement execute()."""
        from src.task_router.strategies.direct_executor import DirectExecutor
        from src.task_router.strategies.conversation_executor import ConversationExecutor

        strategies = [
            DirectExecutor(),
            ConversationExecutor(),
        ]

        for strategy in strategies:
            assert hasattr(strategy, 'execute')
            assert callable(strategy.execute)

    @pytest.mark.unit
    def test_all_strategies_have_can_handle_method(self):
        """Test all strategies implement can_handle()."""
        from src.task_router.strategies.direct_executor import DirectExecutor
        from src.task_router.strategies.conversation_executor import ConversationExecutor

        strategies = [
            DirectExecutor(),
            ConversationExecutor(),
        ]

        for strategy in strategies:
            assert hasattr(strategy, 'can_handle')
            assert callable(strategy.can_handle)

    @pytest.mark.unit
    def test_all_strategies_have_name_property(self):
        """Test all strategies have a name property."""
        from src.task_router.strategies.direct_executor import DirectExecutor
        from src.task_router.strategies.conversation_executor import ConversationExecutor

        strategies = [
            DirectExecutor(),
            ConversationExecutor(),
        ]

        for strategy in strategies:
            assert hasattr(strategy, 'name')
            assert isinstance(strategy.name, str)
            assert len(strategy.name) > 0

    @pytest.mark.unit
    def test_all_strategies_return_execution_result(self):
        """Test all strategies return ExecutionResult from execute()."""
        from src.task_router.strategies.base import ExecutionResult
        from src.task_router.strategies.conversation_executor import ConversationExecutor

        executor = ConversationExecutor()

        task = ClassifiedTask(
            original_input="hello",
            task_type=TaskType.CONVERSATION,
            confidence=0.9,
            reasoning="Test"
        )

        result = executor.execute(task)

        assert isinstance(result, ExecutionResult)


class TestBackwardCompatibility:
    """Test backward compatibility - strategies can still be imported from main module."""

    @pytest.mark.unit
    def test_import_from_main_strategies_module(self):
        """Test that strategies can still be imported from strategies.py for backward compat."""
        # This should work even after split (via __init__.py re-exports)
        from src.task_router import strategies

        assert hasattr(strategies, 'ExecutionResult')
        assert hasattr(strategies, 'ExecutionStrategy')
        assert hasattr(strategies, 'DirectExecutor')
        assert hasattr(strategies, 'ConversationExecutor')
        assert hasattr(strategies, 'ResearchExecutor')
        assert hasattr(strategies, 'AgentExecutor')

    @pytest.mark.unit
    def test_direct_import_execution_result(self):
        """Test ExecutionResult can be imported from strategies."""
        from src.task_router.strategies import ExecutionResult

        result = ExecutionResult(success=True, output="test")
        assert result.success is True

    @pytest.mark.unit
    def test_direct_import_all_executors(self):
        """Test all executors can be imported from strategies."""
        from src.task_router.strategies import (
            DirectExecutor,
            ConversationExecutor,
            ResearchExecutor,
            AgentExecutor
        )

        # All should be importable
        assert DirectExecutor is not None
        assert ConversationExecutor is not None
        assert ResearchExecutor is not None
        assert AgentExecutor is not None
