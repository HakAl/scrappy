"""
Provider selection strategies for the Code Agent.

This module extracts provider selection logic from CodeAgent into
focused strategy classes following the Strategy pattern.

Single Responsibility: Select LLM providers for agent tasks.
"""

from typing import Optional, List, TYPE_CHECKING

from ..agent_config import AgentConfig
from ..orchestrator.model_selection import ModelSelectionType
from .protocols import ProviderSelectionStrategyProtocol

if TYPE_CHECKING:
    from ..orchestrator_adapter import OrchestratorAdapter


class DynamicProviderStrategy:
    """
    Rate-limit-aware provider selection via orchestrator.

    Uses the orchestrator's intelligent provider selection which considers:
    - Current rate limit status across providers
    - Provider availability and health
    - Task type requirements (planning vs execution)

    Single Responsibility: Delegate provider selection to orchestrator.
    """

    def __init__(self, orchestrator: "OrchestratorAdapter"):
        """
        Initialize with orchestrator reference.

        Args:
            orchestrator: Orchestrator or adapter with get_recommended_provider method
        """
        self._orchestrator = orchestrator
        # Cache for display purposes (actual selection happens per-call)
        self._cached_planner: Optional[str] = None
        self._cached_executor: Optional[str] = None

    def get_planner(self) -> Optional[str]:
        """
        Get recommended provider for planning/reasoning tasks.

        Uses QUALITY selection for best reasoning capability.
        Planning requires strong reasoning to analyze problems and create solutions.
        """
        if hasattr(self._orchestrator, 'get_recommended_provider'):
            provider = self._orchestrator.get_recommended_provider(ModelSelectionType.QUALITY)
            self._cached_planner = provider
            return provider
        return self._cached_planner

    def get_executor(self) -> Optional[str]:
        """
        Get recommended provider for execution tasks.

        Uses INSTRUCT selection for JSON/tool compliance.
        Executor needs instruction-tuned models for reliable tool calling.
        """
        if hasattr(self._orchestrator, 'get_recommended_provider'):
            provider = self._orchestrator.get_recommended_provider(ModelSelectionType.INSTRUCT)
            self._cached_executor = provider
            return provider
        return self._cached_executor

    def supports_dynamic_selection(self) -> bool:
        """Dynamic strategy always supports dynamic selection."""
        return True

    @property
    def cached_planner(self) -> Optional[str]:
        """Get last cached planner provider (for display)."""
        return self._cached_planner

    @property
    def cached_executor(self) -> Optional[str]:
        """Get last cached executor provider (for display)."""
        return self._cached_executor


class StaticProviderStrategy:
    """
    Fixed provider preferences from configuration.

    Uses static provider preferences without considering rate limits
    or availability. Falls back through preference list until finding
    an available provider.

    Single Responsibility: Select providers from static preference list.
    """

    def __init__(
        self,
        config: AgentConfig,
        available_providers: List[str],
        preferred_provider: Optional[str] = None,
    ):
        """
        Initialize with config and available providers.

        Args:
            config: AgentConfig with planner_preferences and executor_preferences
            available_providers: List of available provider names
            preferred_provider: Override provider (e.g., from task routing)
        """
        self._config = config
        self._available = available_providers
        self._preferred = preferred_provider
        # Pre-compute selections
        self._planner = self._select_provider(config.planner_preferences)
        self._executor = self._select_provider(config.executor_preferences)

    def _select_provider(self, preferences: List[str]) -> Optional[str]:
        """Select first available provider from preferences."""
        # Preferred provider takes precedence
        if self._preferred and self._preferred in self._available:
            return self._preferred
        # Fall through preference list
        for pref in preferences:
            if pref in self._available:
                return pref
        # Last resort: first available
        return self._available[0] if self._available else None

    def get_planner(self) -> Optional[str]:
        """Get configured planner provider."""
        return self._planner

    def get_executor(self) -> Optional[str]:
        """Get configured executor provider."""
        return self._executor

    def supports_dynamic_selection(self) -> bool:
        """Static strategy does not support dynamic selection."""
        return False


def create_provider_strategy(
    orchestrator: "OrchestratorAdapter",
    config: AgentConfig,
    available_providers: List[str],
    preferred_provider: Optional[str] = None,
) -> ProviderSelectionStrategyProtocol:
    """
    Factory function to create appropriate provider strategy.

    Automatically selects DynamicProviderStrategy if orchestrator supports it,
    otherwise falls back to StaticProviderStrategy.

    Args:
        orchestrator: Orchestrator or adapter instance
        config: AgentConfig for static fallback
        available_providers: List of available provider names
        preferred_provider: Override provider (e.g., from task routing)

    Returns:
        ProviderSelectionStrategyProtocol implementation
    """
    # Check if orchestrator supports smart provider selection
    if hasattr(orchestrator, 'get_recommended_provider'):
        return DynamicProviderStrategy(orchestrator)
    else:
        return StaticProviderStrategy(
            config=config,
            available_providers=available_providers,
            preferred_provider=preferred_provider,
        )
