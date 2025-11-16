"""
Minimal orchestrator adapter interface for the CodeAgent.

This provides a clean abstraction layer between the agent and the
full orchestrator, making the agent more testable and flexible.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Protocol, runtime_checkable


@dataclass
class LLMResponse:
    """Response from an LLM call."""
    content: str
    provider: str
    model: str = ""
    tokens_used: int = 0
    cached: bool = False


@runtime_checkable
class ContextProvider(Protocol):
    """Protocol for providing codebase context."""

    def is_explored(self) -> bool:
        """Check if the codebase has been explored."""
        ...

    def get_summary(self) -> str:
        """Get a summary of the codebase context."""
        ...


@runtime_checkable
class OrchestratorAdapter(Protocol):
    """
    Minimal interface for orchestrator functionality needed by CodeAgent.

    This protocol defines only what the agent actually needs:
    - List available providers
    - Delegate LLM calls
    - Access codebase context
    """

    @property
    def context(self) -> ContextProvider:
        """Get the context provider."""
        ...

    def list_providers(self) -> List[str]:
        """List available LLM providers."""
        ...

    def delegate(
        self,
        provider: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1500,
        temperature: float = 0.3,
        use_context: bool = False
    ) -> LLMResponse:
        """
        Delegate a prompt to an LLM provider.

        Args:
            provider: Name of the provider to use
            prompt: User prompt to send
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            use_context: Whether to augment with codebase context

        Returns:
            LLMResponse with the model's response
        """
        ...


class NullContext:
    """Null context provider that returns no context."""

    def is_explored(self) -> bool:
        return False

    def get_summary(self) -> str:
        return ""


class AgentOrchestratorAdapter:
    """
    Adapter that wraps the full AgentOrchestrator to provide minimal interface.

    This is the default adapter for production use.
    """

    def __init__(self, orchestrator):
        """
        Initialize with a full AgentOrchestrator instance.

        Args:
            orchestrator: AgentOrchestrator instance
        """
        self._orch = orchestrator
        self._preferred_provider: Optional[str] = None
        self._preferred_model: Optional[str] = None

    def set_preferred_provider(
        self,
        provider_name: Optional[str],
        model_name: Optional[str] = None
    ):
        """
        Set preferred provider for this adapter.

        This allows dynamic provider selection based on task requirements.
        The CodeAgent can query this to adjust its planner/executor choices.

        Args:
            provider_name: Name of preferred provider (e.g., "cerebras", "gemini")
            model_name: Optional specific model (e.g., "llama-3.3-70b")
        """
        self._preferred_provider = provider_name
        self._preferred_model = model_name

    def get_preferred_provider(self) -> tuple[Optional[str], Optional[str]]:
        """
        Get the preferred provider and model.

        Returns:
            Tuple of (provider_name, model_name) or (None, None) if not set
        """
        return (self._preferred_provider, self._preferred_model)

    @property
    def context(self) -> ContextProvider:
        """Get the context provider from orchestrator."""
        return self._orch.context

    def list_providers(self) -> List[str]:
        """List available providers from registry."""
        return self._orch.registry.list_available()

    def delegate(
        self,
        provider: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1500,
        temperature: float = 0.3,
        use_context: bool = False
    ) -> LLMResponse:
        """Delegate to the orchestrator's delegate method."""
        response = self._orch.delegate(
            provider,
            prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            use_context=use_context
        )

        # Wrap in our LLMResponse if needed
        if isinstance(response, LLMResponse):
            return response

        # Adapt from orchestrator's response format
        return LLMResponse(
            content=getattr(response, 'content', str(response)),
            provider=provider,
            model=getattr(response, 'model', ''),
            tokens_used=getattr(response, 'tokens_used', 0),
            cached=getattr(response, 'cached', False)
        )

    # Proxy methods for working memory
    def remember_file_read(self, path: str, content: str, lines: int = 0):
        """Proxy to orchestrator's remember_file_read."""
        if hasattr(self._orch, 'remember_file_read'):
            self._orch.remember_file_read(path, content, lines)

    def remember_search(self, query: str, results: list):
        """Proxy to orchestrator's remember_search."""
        if hasattr(self._orch, 'remember_search'):
            self._orch.remember_search(query, results)

    def remember_git_operation(self, operation: str, result: str):
        """Proxy to orchestrator's remember_git_operation."""
        if hasattr(self._orch, 'remember_git_operation'):
            self._orch.remember_git_operation(operation, result)


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
            provider="mock"
        )

    def get_calls(self) -> List[dict]:
        """Get all calls made to delegate()."""
        return self._calls

    def reset(self) -> None:
        """Reset the adapter state."""
        self._call_index = 0
        self._calls = []
