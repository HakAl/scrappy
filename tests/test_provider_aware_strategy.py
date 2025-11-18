"""
Tests for ProviderAwareStrategy - common provider logic extraction.

These tests drive the refactoring to remove code duplication in provider handling
across executors. The goal is a single source of truth for:
- set_provider() method
- Provider resolution and validation
- Fallback to orchestrator.brain
"""

import pytest
from unittest.mock import Mock, MagicMock
from typing import Optional

from src.task_router.strategies.base import ExecutionStrategy, ExecutionResult
from src.task_router.classifier import ClassifiedTask, TaskType


class TestProviderAwareStrategyBase:
    """Tests for ProviderAwareStrategy base class existence and interface."""

    @pytest.mark.unit
    def test_provider_aware_strategy_class_exists(self):
        """Test that ProviderAwareStrategy base class exists."""
        from src.task_router.strategies.base import ProviderAwareStrategy

        assert ProviderAwareStrategy is not None

    @pytest.mark.unit
    def test_provider_aware_strategy_extends_execution_strategy(self):
        """Test that ProviderAwareStrategy extends ExecutionStrategy."""
        from src.task_router.strategies.base import ProviderAwareStrategy

        assert issubclass(ProviderAwareStrategy, ExecutionStrategy)

    @pytest.mark.unit
    def test_provider_aware_strategy_has_set_provider_method(self):
        """Test that ProviderAwareStrategy has set_provider method."""
        from src.task_router.strategies.base import ProviderAwareStrategy

        assert hasattr(ProviderAwareStrategy, 'set_provider')

    @pytest.mark.unit
    def test_provider_aware_strategy_has_resolve_method(self):
        """Test that ProviderAwareStrategy has _resolve_and_validate_provider method."""
        from src.task_router.strategies.base import ProviderAwareStrategy

        assert hasattr(ProviderAwareStrategy, '_resolve_and_validate_provider')


class TestProviderAwareStrategySetProvider:
    """Tests for set_provider() method in base class."""

    @pytest.fixture
    def mock_orchestrator(self):
        """Create mock orchestrator with providers."""
        orch = Mock()
        orch.providers = Mock()
        orch.providers.list_available.return_value = ['cerebras', 'groq', 'gemini']
        orch.brain = 'cerebras'
        return orch

    @pytest.mark.unit
    def test_set_provider_stores_provider_name(self, mock_orchestrator):
        """Test that set_provider stores provider name."""
        from src.task_router.strategies.base import ProviderAwareStrategy

        # Create a concrete implementation for testing
        class TestStrategy(ProviderAwareStrategy):
            def execute(self, task):
                return ExecutionResult(success=True, output="test")

            def can_handle(self, task):
                return True

            @property
            def name(self):
                return "TestStrategy"

        strategy = TestStrategy(orchestrator=mock_orchestrator)
        strategy.set_provider('groq')

        assert strategy._resolved_provider == 'groq'

    @pytest.mark.unit
    def test_set_provider_stores_model_name(self, mock_orchestrator):
        """Test that set_provider stores model name."""
        from src.task_router.strategies.base import ProviderAwareStrategy

        class TestStrategy(ProviderAwareStrategy):
            def execute(self, task):
                return ExecutionResult(success=True, output="test")

            def can_handle(self, task):
                return True

            @property
            def name(self):
                return "TestStrategy"

        strategy = TestStrategy(orchestrator=mock_orchestrator)
        strategy.set_provider('cerebras', 'llama-3.3-70b')

        assert strategy._resolved_provider == 'cerebras'
        assert strategy._resolved_model == 'llama-3.3-70b'

    @pytest.mark.unit
    def test_set_provider_clears_previous_values(self, mock_orchestrator):
        """Test that set_provider clears previous values when called again."""
        from src.task_router.strategies.base import ProviderAwareStrategy

        class TestStrategy(ProviderAwareStrategy):
            def execute(self, task):
                return ExecutionResult(success=True, output="test")

            def can_handle(self, task):
                return True

            @property
            def name(self):
                return "TestStrategy"

        strategy = TestStrategy(orchestrator=mock_orchestrator)

        # Set first values
        strategy.set_provider('groq', 'model-a')
        assert strategy._resolved_provider == 'groq'
        assert strategy._resolved_model == 'model-a'

        # Set new values - should overwrite
        strategy.set_provider('cerebras', 'model-b')
        assert strategy._resolved_provider == 'cerebras'
        assert strategy._resolved_model == 'model-b'

    @pytest.mark.unit
    def test_set_provider_with_none_values(self, mock_orchestrator):
        """Test that set_provider handles None values."""
        from src.task_router.strategies.base import ProviderAwareStrategy

        class TestStrategy(ProviderAwareStrategy):
            def execute(self, task):
                return ExecutionResult(success=True, output="test")

            def can_handle(self, task):
                return True

            @property
            def name(self):
                return "TestStrategy"

        strategy = TestStrategy(orchestrator=mock_orchestrator)
        strategy.set_provider(None, None)

        assert strategy._resolved_provider is None
        assert strategy._resolved_model is None


class TestProviderAwareStrategyResolveAndValidate:
    """Tests for _resolve_and_validate_provider() method."""

    @pytest.fixture
    def mock_orchestrator(self):
        """Create mock orchestrator with providers."""
        orch = Mock()
        orch.providers = Mock()
        orch.providers.list_available.return_value = ['cerebras', 'groq', 'gemini']
        orch.brain = 'cerebras'
        return orch

    @pytest.mark.unit
    def test_resolve_uses_resolved_provider_if_set(self, mock_orchestrator):
        """Test that _resolve_and_validate_provider uses _resolved_provider first."""
        from src.task_router.strategies.base import ProviderAwareStrategy

        class TestStrategy(ProviderAwareStrategy):
            def execute(self, task):
                return ExecutionResult(success=True, output="test")

            def can_handle(self, task):
                return True

            @property
            def name(self):
                return "TestStrategy"

        strategy = TestStrategy(orchestrator=mock_orchestrator)
        strategy.set_provider('groq')

        provider = strategy._resolve_and_validate_provider()

        assert provider == 'groq'

    @pytest.mark.unit
    def test_resolve_falls_back_to_preferred_provider(self, mock_orchestrator):
        """Test fallback to preferred_provider when _resolved_provider is None."""
        from src.task_router.strategies.base import ProviderAwareStrategy

        class TestStrategy(ProviderAwareStrategy):
            def __init__(self, orchestrator, preferred_provider='gemini'):
                super().__init__(orchestrator)
                self.preferred_provider = preferred_provider

            def execute(self, task):
                return ExecutionResult(success=True, output="test")

            def can_handle(self, task):
                return True

            @property
            def name(self):
                return "TestStrategy"

        strategy = TestStrategy(orchestrator=mock_orchestrator)
        # Don't call set_provider - _resolved_provider is None

        # Pass preferred_provider as parameter (this is how subclasses use it)
        provider = strategy._resolve_and_validate_provider(strategy.preferred_provider)

        assert provider == 'gemini'

    @pytest.mark.unit
    def test_resolve_falls_back_to_brain_when_unavailable(self, mock_orchestrator):
        """Test fallback to orchestrator.brain when provider not available."""
        mock_orchestrator.providers.list_available.return_value = ['cerebras']  # groq not available

        from src.task_router.strategies.base import ProviderAwareStrategy

        class TestStrategy(ProviderAwareStrategy):
            def execute(self, task):
                return ExecutionResult(success=True, output="test")

            def can_handle(self, task):
                return True

            @property
            def name(self):
                return "TestStrategy"

        strategy = TestStrategy(orchestrator=mock_orchestrator)
        strategy.set_provider('groq')  # groq not in available list

        provider = strategy._resolve_and_validate_provider()

        # Should fall back to brain
        assert provider == 'cerebras'

    @pytest.mark.unit
    def test_resolve_handles_providers_list_exception(self, mock_orchestrator):
        """Test handling of exception when listing providers."""
        mock_orchestrator.providers.list_available.side_effect = Exception("API error")

        from src.task_router.strategies.base import ProviderAwareStrategy

        class TestStrategy(ProviderAwareStrategy):
            def execute(self, task):
                return ExecutionResult(success=True, output="test")

            def can_handle(self, task):
                return True

            @property
            def name(self):
                return "TestStrategy"

        strategy = TestStrategy(orchestrator=mock_orchestrator)
        strategy.set_provider('groq')

        provider = strategy._resolve_and_validate_provider()

        # Should fall back to brain on exception
        assert provider == 'cerebras'

    @pytest.mark.unit
    def test_resolve_clears_resolved_values_after_use(self, mock_orchestrator):
        """Test that resolved values are cleared after _resolve_and_validate_provider."""
        from src.task_router.strategies.base import ProviderAwareStrategy

        class TestStrategy(ProviderAwareStrategy):
            def execute(self, task):
                return ExecutionResult(success=True, output="test")

            def can_handle(self, task):
                return True

            @property
            def name(self):
                return "TestStrategy"

        strategy = TestStrategy(orchestrator=mock_orchestrator)
        strategy.set_provider('groq', 'some-model')

        # Call resolve
        strategy._resolve_and_validate_provider()

        # Values should be cleared
        assert strategy._resolved_provider is None
        assert strategy._resolved_model is None


class TestExecutorsExtendProviderAwareStrategy:
    """Tests to verify executors extend ProviderAwareStrategy."""

    @pytest.mark.unit
    def test_research_executor_extends_provider_aware_strategy(self):
        """Test that ResearchExecutor extends ProviderAwareStrategy."""
        from src.task_router.strategies.base import ProviderAwareStrategy
        from src.task_router.strategies.research_executor import ResearchExecutor

        assert issubclass(ResearchExecutor, ProviderAwareStrategy)

    @pytest.mark.unit
    def test_agent_executor_extends_provider_aware_strategy(self):
        """Test that AgentExecutor extends ProviderAwareStrategy."""
        from src.task_router.strategies.base import ProviderAwareStrategy
        from src.task_router.strategies.agent_executor import AgentExecutor

        assert issubclass(AgentExecutor, ProviderAwareStrategy)

    @pytest.mark.unit
    def test_research_executor_no_duplicate_set_provider(self):
        """Test that ResearchExecutor doesn't define its own set_provider."""
        from src.task_router.strategies.base import ProviderAwareStrategy
        from src.task_router.strategies.research_executor import ResearchExecutor

        # set_provider should come from ProviderAwareStrategy, not be redefined
        assert ResearchExecutor.set_provider is ProviderAwareStrategy.set_provider

    @pytest.mark.unit
    def test_agent_executor_no_duplicate_set_provider(self):
        """Test that AgentExecutor doesn't define its own set_provider."""
        from src.task_router.strategies.base import ProviderAwareStrategy
        from src.task_router.strategies.agent_executor import AgentExecutor

        # set_provider should come from ProviderAwareStrategy, not be redefined
        assert AgentExecutor.set_provider is ProviderAwareStrategy.set_provider


class TestResearchExecutorUsesBaseClassMethods:
    """Tests that ResearchExecutor uses base class provider methods."""

    @pytest.fixture
    def mock_orchestrator(self):
        """Create mock orchestrator."""
        orch = Mock()
        orch.providers = Mock()
        orch.providers.list_available.return_value = ['cerebras', 'groq']
        orch.brain = 'cerebras'
        orch.context = Mock()
        orch.context.is_explored.return_value = False

        # Mock delegate response
        response = Mock()
        response.content = "Test response"
        response.tokens_used = 100
        orch.delegate.return_value = response

        return orch

    @pytest.mark.unit
    def test_research_executor_uses_resolve_method(self, mock_orchestrator):
        """Test that ResearchExecutor uses _resolve_and_validate_provider."""
        from src.task_router.strategies.research_executor import ResearchExecutor

        executor = ResearchExecutor(orchestrator=mock_orchestrator)
        executor.set_provider('groq')

        task = ClassifiedTask(
            original_input="explain python",
            task_type=TaskType.RESEARCH,
            confidence=0.9,
            reasoning="Research"
        )

        result = executor.execute(task)

        # Should have used groq
        call_args = mock_orchestrator.delegate.call_args
        assert call_args[0][0] == 'groq'

    @pytest.mark.unit
    def test_research_executor_clears_provider_after_execute(self, mock_orchestrator):
        """Test that ResearchExecutor clears provider after execution."""
        from src.task_router.strategies.research_executor import ResearchExecutor

        executor = ResearchExecutor(orchestrator=mock_orchestrator)
        executor.set_provider('groq', 'some-model')

        task = ClassifiedTask(
            original_input="explain python",
            task_type=TaskType.RESEARCH,
            confidence=0.9,
            reasoning="Research"
        )

        executor.execute(task)

        # Should be cleared after execution
        assert executor._resolved_provider is None
        assert executor._resolved_model is None


class TestAgentExecutorUsesBaseClassMethods:
    """Tests that AgentExecutor uses base class provider methods."""

    @pytest.fixture
    def mock_orchestrator(self):
        """Create mock orchestrator."""
        orch = Mock()
        orch.providers = Mock()
        orch.providers.list_available.return_value = ['cerebras', 'groq']
        orch.brain = 'cerebras'
        orch.context = Mock()
        orch.context.is_explored.return_value = False
        return orch

    @pytest.mark.unit
    def test_agent_executor_has_resolved_provider_attributes(self, mock_orchestrator):
        """Test that AgentExecutor has _resolved_provider and _resolved_model from base."""
        from src.task_router.strategies.agent_executor import AgentExecutor

        executor = AgentExecutor(orchestrator=mock_orchestrator)

        # Should have these attributes from ProviderAwareStrategy
        assert hasattr(executor, '_resolved_provider')
        assert hasattr(executor, '_resolved_model')


class TestSingleSourceOfTruthForProviderPriority:
    """Tests to ensure provider priority is defined in one place."""

    @pytest.mark.unit
    def test_provider_resolver_is_single_source_for_fast_priority(self):
        """Test that ProviderResolver defines the fast provider priority."""
        from src.task_router.provider_resolver import ProviderResolver

        # Create mock orchestrator
        orch = Mock()
        orch.providers = Mock()
        orch.providers.list_available.return_value = ['gemini', 'groq', 'cerebras']

        resolver = ProviderResolver(orchestrator=orch, use_provider_selector=False)

        # Fast hint should prefer cerebras even if listed last
        provider, _ = resolver.resolve('fast')
        assert provider == 'cerebras'

    @pytest.mark.unit
    def test_provider_resolver_is_single_source_for_quality_priority(self):
        """Test that ProviderResolver defines the quality provider priority."""
        from src.task_router.provider_resolver import ProviderResolver

        orch = Mock()
        orch.providers = Mock()
        orch.providers.list_available.return_value = ['gemini', 'groq', 'cerebras']

        resolver = ProviderResolver(orchestrator=orch, use_provider_selector=False)

        # Quality hint should prefer cerebras with 70B model
        provider, model = resolver.resolve('quality')
        assert provider == 'cerebras'
        assert model == 'llama-3.3-70b'


class TestProviderAwareStrategyInitialization:
    """Tests for ProviderAwareStrategy initialization."""

    @pytest.mark.unit
    def test_provider_aware_strategy_requires_orchestrator(self):
        """Test that ProviderAwareStrategy requires orchestrator in __init__."""
        from src.task_router.strategies.base import ProviderAwareStrategy

        class TestStrategy(ProviderAwareStrategy):
            def execute(self, task):
                return ExecutionResult(success=True, output="test")

            def can_handle(self, task):
                return True

            @property
            def name(self):
                return "TestStrategy"

        orch = Mock()
        strategy = TestStrategy(orchestrator=orch)

        assert strategy.orchestrator is orch

    @pytest.mark.unit
    def test_provider_aware_strategy_initializes_resolved_to_none(self):
        """Test that resolved provider/model start as None."""
        from src.task_router.strategies.base import ProviderAwareStrategy

        class TestStrategy(ProviderAwareStrategy):
            def execute(self, task):
                return ExecutionResult(success=True, output="test")

            def can_handle(self, task):
                return True

            @property
            def name(self):
                return "TestStrategy"

        orch = Mock()
        strategy = TestStrategy(orchestrator=orch)

        assert strategy._resolved_provider is None
        assert strategy._resolved_model is None


class TestProviderResolverIntegration:
    """Tests for integration between ProviderAwareStrategy and ProviderResolver."""

    @pytest.mark.unit
    def test_provider_aware_strategy_can_use_provider_resolver(self):
        """Test that ProviderAwareStrategy can delegate to ProviderResolver."""
        from src.task_router.strategies.base import ProviderAwareStrategy
        from src.task_router.provider_resolver import ProviderResolver

        orch = Mock()
        orch.providers = Mock()
        orch.providers.list_available.return_value = ['cerebras', 'groq']
        orch.brain = 'cerebras'

        class TestStrategy(ProviderAwareStrategy):
            def execute(self, task):
                return ExecutionResult(success=True, output="test")

            def can_handle(self, task):
                return True

            @property
            def name(self):
                return "TestStrategy"

        strategy = TestStrategy(orchestrator=orch)

        # Should be able to create and use ProviderResolver
        resolver = ProviderResolver(orchestrator=orch)
        provider, model = resolver.resolve('fast')

        assert provider == 'cerebras'


class TestNoCodeDuplicationInExecutors:
    """Tests to verify there's no duplicated provider logic in executors."""

    @pytest.mark.unit
    def test_research_executor_does_not_redefine_provider_validation(self):
        """Test ResearchExecutor doesn't have inline provider validation."""
        from src.task_router.strategies import research_executor
        import inspect

        source = inspect.getsource(research_executor.ResearchExecutor.execute)

        # The execute method should NOT contain inline provider validation logic
        # It should delegate to _resolve_and_validate_provider
        assert 'list_available' not in source or '_resolve_and_validate_provider' in source

    @pytest.mark.unit
    def test_agent_executor_does_not_redefine_provider_validation(self):
        """Test AgentExecutor doesn't have inline provider validation."""
        from src.task_router.strategies import agent_executor
        import inspect

        # Get the execute method source
        source = inspect.getsource(agent_executor.AgentExecutor.execute)

        # Should not have inline checks for provider availability
        # The provider setting should be handled by base class
        inline_provider_check = (
            "if self._resolved_provider" in source and
            "list_available" in source
        )

        # This test will pass once we refactor to use base class
        assert not inline_provider_check or "_resolve_and_validate_provider" in source
