"""
Test helper classes and utilities.

Provides mock adapters and utilities for testing the orchestrator and agent.
"""

from typing import List, Optional, Dict, Any, Callable
from unittest.mock import Mock

from src.providers.base import LLMResponse
from src.orchestrator_adapter import NullContext, ContextProvider


def make_response(
    content: str = '{"thought": "test", "action": "complete", "is_complete": true}',
    provider: str = "mock",
    model: str = "",
    tokens_used: int = 0
) -> LLMResponse:
    """
    Factory function to create LLMResponse with sensible defaults.

    Isolates tests from LLMResponse constructor signature changes.

    Args:
        content: Response content (default: completion JSON)
        provider: Provider name
        model: Model name (default: empty)
        tokens_used: Token count

    Returns:
        LLMResponse instance
    """
    return LLMResponse(
        content=content,
        model=model,
        provider=provider,
        tokens_used=tokens_used
    )


class ConfigurableTestOrchestrator:
    """
    Flexible test orchestrator that can be configured for various test scenarios.

    Supports:
    - Provider recommendation with configurable logic
    - Call tracking for assertions
    - Rate limit simulation
    - Provider rotation
    - Auto-selection when provider is None

    Usage:
        # Simple tracking
        orch = ConfigurableTestOrchestrator()

        # With specific provider recommendation
        orch = ConfigurableTestOrchestrator(recommended_provider='cerebras')

        # With rate limiting
        orch = ConfigurableTestOrchestrator(rate_limited={'gemini'})

        # With rotation
        orch = ConfigurableTestOrchestrator(rotation=['cerebras', 'groq', 'gemini'])

        # With custom response
        orch = ConfigurableTestOrchestrator(
            response_content='{"thought": "test", "action": "read_file", ...}'
        )
    """

    def __init__(
        self,
        available_providers: Optional[List[str]] = None,
        recommended_provider: str = 'cerebras',
        rate_limited: Optional[set] = None,
        rotation: Optional[List[str]] = None,
        response_content: str = '{"thought": "test", "action": "complete", "is_complete": true, "result": "done"}',
        response_tokens: int = 100,
        context_explored: bool = False
    ):
        """
        Initialize test orchestrator with configurable behavior.

        Args:
            available_providers: List of available provider names
            recommended_provider: Default provider to recommend
            rate_limited: Set of provider names that are rate limited
            rotation: List of providers to rotate through (if set, overrides recommended_provider)
            response_content: JSON content to return from delegate()
            response_tokens: Token count for responses
            context_explored: Whether context.is_explored() returns True
        """
        self.available_providers = available_providers or ['cerebras', 'groq', 'gemini']
        self._recommended_provider = recommended_provider
        self.rate_limited_providers = rate_limited or set()
        self.rotation = rotation
        self.response_content = response_content
        self.response_tokens = response_tokens

        # Tracking
        self.delegate_calls: List[Dict[str, Any]] = []
        self.call_count = 0
        self.providers_used: List[str] = []

        # Required interfaces
        self.registry = self
        self.context = Mock()
        self.context.is_explored.return_value = context_explored
        self.context.get_summary.return_value = "" if not context_explored else "Test codebase summary"

    def list_available(self) -> List[str]:
        """Return available providers."""
        return self.available_providers

    def is_rate_limited(self, provider: str) -> bool:
        """Check if provider is rate limited."""
        return provider in self.rate_limited_providers

    def get_recommended_provider(self, task_type: str = 'general') -> str:
        """
        Get recommended provider based on configuration.

        If rotation is configured, returns next in rotation.
        Otherwise returns recommended_provider, skipping rate-limited ones.
        """
        if self.rotation:
            # Rotate through providers
            provider = self.rotation[self.call_count % len(self.rotation)]
            return provider

        # Skip rate-limited providers
        if self._recommended_provider in self.rate_limited_providers:
            for prov in self.available_providers:
                if prov not in self.rate_limited_providers:
                    return prov

        return self._recommended_provider

    def delegate(
        self,
        provider_name: Optional[str] = None,
        prompt: str = "",
        **kwargs
    ) -> LLMResponse:
        """
        Delegate to mock provider with tracking.

        If provider_name is None, auto-selects based on task_type.
        """
        # Auto-select if not specified
        if provider_name is None:
            task_type = kwargs.get('task_type', 'general')
            provider_name = self.get_recommended_provider(task_type)

        # Check rate limits
        if self.is_rate_limited(provider_name):
            raise Exception(f"{provider_name} is rate limited")

        # Track the call
        self.delegate_calls.append({
            'provider': provider_name,
            'prompt': prompt,
            'task_type': kwargs.get('task_type'),
            'kwargs': kwargs
        })
        self.providers_used.append(provider_name)
        self.call_count += 1

        # Return configured response
        return make_response(
            content=self.response_content,
            provider=provider_name,
            tokens_used=self.response_tokens
        )

    def reset_tracking(self) -> None:
        """Reset call tracking (useful between test phases)."""
        self.delegate_calls = []
        self.call_count = 0
        self.providers_used = []


class SimpleLLMAdapter:
    """
    Simple adapter for testing or single-provider scenarios.

    This adapter allows using the agent with just a single LLM function,
    without needing the full orchestrator infrastructure.
    """

    def __init__(
        self,
        llm_func,
        provider_name: str = "default",
        context_provider: Optional[ContextProvider] = None
    ):
        """
        Initialize with a simple LLM function.

        Args:
            llm_func: Function that takes (prompt, system_prompt, max_tokens, temperature)
                      and returns a string response
            provider_name: Name to identify this provider
            context_provider: Optional context provider
        """
        self._llm_func = llm_func
        self._provider_name = provider_name
        self._context = context_provider or NullContext()

    @property
    def context(self) -> ContextProvider:
        """Get the context provider."""
        return self._context

    def list_providers(self) -> List[str]:
        """Return single provider."""
        return [self._provider_name]

    def delegate(
        self,
        provider: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1500,
        temperature: float = 0.3,
        use_context: bool = False
    ) -> LLMResponse:
        """Call the LLM function."""
        # Ignore provider name, use our single function
        content = self._llm_func(
            prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature
        )

        return LLMResponse(
            content=content,
            model="",
            provider=self._provider_name
        )


class MockOrchestratorAdapter:
    """
    Mock adapter for testing purposes.

    Allows setting up predetermined responses for testing agent behavior.
    """

    def __init__(self, responses: Optional[List[str]] = None):
        """
        Initialize with optional list of responses.

        Args:
            responses: List of responses to return in order
        """
        self._responses = responses or []
        self._call_index = 0
        self._context = NullContext()
        self._calls = []  # Track all calls for assertions

    @property
    def context(self) -> ContextProvider:
        """Get the context provider."""
        return self._context

    def list_providers(self) -> List[str]:
        """Return mock provider."""
        return ["mock"]

    def add_response(self, response: str) -> None:
        """Add a response to the queue."""
        self._responses.append(response)

    def delegate(
        self,
        provider: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1500,
        temperature: float = 0.3,
        use_context: bool = False
    ) -> LLMResponse:
        """Return next mock response."""
        # Track the call
        self._calls.append({
            'provider': provider,
            'prompt': prompt,
            'system_prompt': system_prompt,
            'max_tokens': max_tokens,
            'temperature': temperature,
            'use_context': use_context
        })

        if self._call_index >= len(self._responses):
            # Default completion response if no more responses
            content = '{"thought": "No more responses", "action": "complete", "is_complete": true, "result": "Mock completed"}'
        else:
            content = self._responses[self._call_index]
            self._call_index += 1

        return LLMResponse(
            content=content,
            model="",
            provider="mock"
        )

    def get_calls(self) -> List[dict]:
        """Get all calls made to delegate()."""
        return self._calls

    def reset(self) -> None:
        """Reset the adapter state."""
        self._call_index = 0
        self._calls = []
