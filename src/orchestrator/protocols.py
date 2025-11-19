"""
Protocols for orchestrator module.

Defines abstract interfaces (Protocols) for orchestrator implementations,
enabling loose coupling and better testability throughout the codebase.
"""

from typing import Protocol, Optional, Dict, Any, runtime_checkable

from ..providers.base import LLMResponse


@runtime_checkable
class Orchestrator(Protocol):
    """
    Protocol for orchestrator implementations.

    Defines the minimal interface required for an orchestrator that can
    delegate tasks to LLM providers and report usage statistics.

    This protocol enables:
    - Type hints that accept any conforming implementation
    - Easy substitution of test mocks for unit testing
    - Loose coupling between components and the orchestrator

    Implementations:
    - AgentOrchestrator: Full-featured multi-provider orchestrator
    - ConfigurableTestOrchestrator: Test mock in tests/helpers.py
    """

    def delegate(
        self,
        provider_name: Optional[str] = None,
        prompt: str = "",
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs: Any
    ) -> LLMResponse:
        """
        Delegate a task to an LLM provider.

        Args:
            provider_name: Target provider (None for auto-selection)
            prompt: The prompt to send to the LLM
            model: Specific model to use (None for provider default)
            system_prompt: System prompt for context
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            **kwargs: Additional provider-specific parameters

        Returns:
            LLMResponse with the provider's response
        """
        ...

    async def delegate_async(
        self,
        provider_name: str,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs: Any
    ) -> LLMResponse:
        """
        Asynchronously delegate a task to an LLM provider.

        Args:
            provider_name: Target provider
            prompt: The prompt to send to the LLM
            model: Specific model to use (None for provider default)
            system_prompt: System prompt for context
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            **kwargs: Additional provider-specific parameters

        Returns:
            LLMResponse with the provider's response
        """
        ...

    def get_usage_report(self) -> Dict[str, Any]:
        """
        Get usage statistics report.

        Returns:
            Dictionary containing usage statistics including:
            - total_tasks: Total tasks delegated
            - by_provider: Per-provider breakdown
            - cache_stats: Cache hit/miss statistics
        """
        ...
