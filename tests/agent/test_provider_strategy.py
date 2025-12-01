"""
Tests for provider selection strategies.

Tests the ProviderSelectionStrategy implementations extracted from CodeAgent.
"""

import pytest
from unittest.mock import Mock, MagicMock

from scrappy.agent.provider_strategy import (
    DynamicProviderStrategy,
    StaticProviderStrategy,
    create_provider_strategy,
)
from scrappy.agent_config import AgentConfig
from scrappy.orchestrator.model_selection import ModelSelectionType


class TestDynamicProviderStrategy:
    """Tests for DynamicProviderStrategy."""

    def test_get_planner_delegates_to_orchestrator(self):
        """get_planner should delegate to orchestrator.get_recommended_provider."""
        mock_orchestrator = Mock()
        mock_orchestrator.get_recommended_provider.return_value = "openai"

        strategy = DynamicProviderStrategy(mock_orchestrator)
        result = strategy.get_planner()

        assert result == "openai"
        mock_orchestrator.get_recommended_provider.assert_called_once_with(ModelSelectionType.INSTRUCT)

    def test_get_executor_delegates_to_orchestrator(self):
        """get_executor should delegate to orchestrator.get_recommended_provider."""
        mock_orchestrator = Mock()
        mock_orchestrator.get_recommended_provider.return_value = "anthropic"

        strategy = DynamicProviderStrategy(mock_orchestrator)
        result = strategy.get_executor()

        assert result == "anthropic"
        mock_orchestrator.get_recommended_provider.assert_called_once_with(ModelSelectionType.INSTRUCT)

    def test_get_planner_passes_enum_not_string(self):
        """REGRESSION: get_planner must pass ModelSelectionType enum, not string."""
        mock_orchestrator = Mock()
        mock_orchestrator.get_recommended_provider.return_value = "openai"

        strategy = DynamicProviderStrategy(mock_orchestrator)
        strategy.get_planner()

        # Verify enum was passed, not string
        call_args = mock_orchestrator.get_recommended_provider.call_args
        arg = call_args[0][0]  # First positional argument
        assert isinstance(arg, ModelSelectionType), f"Expected ModelSelectionType enum, got {type(arg).__name__}: {arg!r}"

    def test_get_executor_passes_enum_not_string(self):
        """REGRESSION: get_executor must pass ModelSelectionType enum, not string."""
        mock_orchestrator = Mock()
        mock_orchestrator.get_recommended_provider.return_value = "anthropic"

        strategy = DynamicProviderStrategy(mock_orchestrator)
        strategy.get_executor()

        # Verify enum was passed, not string
        call_args = mock_orchestrator.get_recommended_provider.call_args
        arg = call_args[0][0]  # First positional argument
        assert isinstance(arg, ModelSelectionType), f"Expected ModelSelectionType enum, got {type(arg).__name__}: {arg!r}"

    def test_supports_dynamic_selection_returns_true(self):
        """DynamicProviderStrategy always supports dynamic selection."""
        mock_orchestrator = Mock()
        strategy = DynamicProviderStrategy(mock_orchestrator)

        assert strategy.supports_dynamic_selection() is True

    def test_caches_last_provider_for_display(self):
        """Strategy should cache last provider for display purposes."""
        mock_orchestrator = Mock()
        mock_orchestrator.get_recommended_provider.return_value = "openai"

        strategy = DynamicProviderStrategy(mock_orchestrator)
        strategy.get_planner()

        assert strategy.cached_planner == "openai"

    def test_handles_orchestrator_without_method(self):
        """Strategy should return cached value if orchestrator lacks method."""
        # Create mock without get_recommended_provider
        mock_orchestrator = Mock(spec=[])

        strategy = DynamicProviderStrategy(mock_orchestrator)
        result = strategy.get_planner()

        assert result is None  # No cached value yet


class TestStaticProviderStrategy:
    """Tests for StaticProviderStrategy."""

    def test_selects_first_available_from_preferences(self):
        """Should select first available provider from preferences."""
        config = AgentConfig()
        config.planner_preferences = ["anthropic", "openai", "gemini"]
        config.executor_preferences = ["openai", "anthropic"]

        strategy = StaticProviderStrategy(
            config=config,
            available_providers=["openai", "gemini"],
        )

        assert strategy.get_planner() == "openai"  # anthropic not available
        assert strategy.get_executor() == "openai"

    def test_uses_preferred_provider_over_config(self):
        """Preferred provider should take precedence over config preferences."""
        config = AgentConfig()
        config.planner_preferences = ["anthropic", "openai"]
        config.executor_preferences = ["anthropic", "openai"]

        strategy = StaticProviderStrategy(
            config=config,
            available_providers=["openai", "gemini"],
            preferred_provider="gemini",
        )

        assert strategy.get_planner() == "gemini"
        assert strategy.get_executor() == "gemini"

    def test_falls_back_to_first_available(self):
        """Should fall back to first available if no preferences match."""
        config = AgentConfig()
        config.planner_preferences = ["anthropic", "cohere"]  # None available
        config.executor_preferences = ["anthropic"]

        strategy = StaticProviderStrategy(
            config=config,
            available_providers=["openai", "gemini"],
        )

        assert strategy.get_planner() == "openai"  # First available
        assert strategy.get_executor() == "openai"

    def test_returns_none_if_no_providers(self):
        """Should return None if no providers available."""
        config = AgentConfig()

        strategy = StaticProviderStrategy(
            config=config,
            available_providers=[],
        )

        assert strategy.get_planner() is None
        assert strategy.get_executor() is None

    def test_supports_dynamic_selection_returns_false(self):
        """StaticProviderStrategy does not support dynamic selection."""
        config = AgentConfig()

        strategy = StaticProviderStrategy(
            config=config,
            available_providers=["openai"],
        )

        assert strategy.supports_dynamic_selection() is False


class TestCreateProviderStrategy:
    """Tests for create_provider_strategy factory function."""

    def test_creates_dynamic_strategy_when_orchestrator_supports_it(self):
        """Should create DynamicProviderStrategy when orchestrator has method."""
        mock_orchestrator = Mock()
        mock_orchestrator.get_recommended_provider.return_value = "openai"

        strategy = create_provider_strategy(
            orchestrator=mock_orchestrator,
            config=AgentConfig(),
            available_providers=["openai"],
        )

        assert isinstance(strategy, DynamicProviderStrategy)

    def test_creates_static_strategy_when_orchestrator_lacks_method(self):
        """Should create StaticProviderStrategy when orchestrator lacks method."""
        # Create mock without get_recommended_provider
        mock_orchestrator = Mock(spec=['delegate', 'list_providers'])

        strategy = create_provider_strategy(
            orchestrator=mock_orchestrator,
            config=AgentConfig(),
            available_providers=["openai"],
        )

        assert isinstance(strategy, StaticProviderStrategy)

    def test_passes_preferred_provider_to_static_strategy(self):
        """Should pass preferred_provider to StaticProviderStrategy."""
        mock_orchestrator = Mock(spec=['delegate'])
        config = AgentConfig()

        strategy = create_provider_strategy(
            orchestrator=mock_orchestrator,
            config=config,
            available_providers=["openai", "gemini"],
            preferred_provider="gemini",
        )

        assert isinstance(strategy, StaticProviderStrategy)
        assert strategy.get_planner() == "gemini"
