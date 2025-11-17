"""
Minimal orchestrator adapter interface for the CodeAgent.

This provides a clean abstraction layer between the agent and the
full orchestrator, making the agent more testable and flexible.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Protocol, runtime_checkable

# Import LLMResponse from providers to get full feature set including tool_calls
from .providers.base import LLMResponse, ToolCall


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

    def delegate_with_tools(
        self,
        provider: str,
        prompt: str,
        tools: List[dict],
        system_prompt: Optional[str] = None,
        max_tokens: int = 1500,
        temperature: float = 0.3,
        tool_choice: str = "auto",
        **kwargs
    ) -> LLMResponse:
        """
        Delegate to an LLM provider with native tool calling support.

        Args:
            provider: Name of the provider to use
            prompt: User prompt to send
            tools: List of OpenAI-compatible tool schemas
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            tool_choice: How the model should choose tools ("auto", "none", or specific tool)
            **kwargs: Additional provider-specific parameters

        Returns:
            LLMResponse with tool_calls field populated if model decided to call tools
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
        provider: Optional[str] = None,
        prompt: str = "",
        system_prompt: Optional[str] = None,
        max_tokens: int = 1500,
        temperature: float = 0.3,
        use_context: bool = False,
        task_type: str = 'general',
        provider_name: Optional[str] = None,  # Alias for provider
        **kwargs
    ) -> LLMResponse:
        """Delegate to the orchestrator's delegate method.

        Args:
            provider: Provider name (legacy positional, can be None for auto-selection)
            prompt: The prompt to send
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            use_context: Whether to use context augmentation
            task_type: Type of task for provider selection
            provider_name: Alias for provider (keyword-only)
            **kwargs: Additional arguments passed to orchestrator
        """
        # Support both 'provider' and 'provider_name' for compatibility
        actual_provider = provider_name if provider_name is not None else provider

        # Pass to orchestrator with new signature
        response = self._orch.delegate(
            provider_name=actual_provider,
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            use_context=use_context,
            task_type=task_type,
            **kwargs
        )

        # Wrap in our LLMResponse if needed
        if isinstance(response, LLMResponse):
            return response

        # Adapt from orchestrator's response format
        # Use response.provider if available, otherwise fall back to actual_provider
        response_provider = getattr(response, 'provider', actual_provider or 'unknown')
        return LLMResponse(
            content=getattr(response, 'content', str(response)),
            model=getattr(response, 'model', ''),
            provider=response_provider,
            tokens_used=getattr(response, 'tokens_used', 0),
            # Preserve tool_calls if present in the response
            tool_calls=getattr(response, 'tool_calls', None)
        )

    def delegate_with_tools(
        self,
        provider: Optional[str] = None,
        prompt: str = "",
        tools: List[dict] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1500,
        temperature: float = 0.3,
        tool_choice: str = "auto",
        provider_name: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Delegate to provider with native tool calling support.

        Args:
            provider: Provider name (legacy positional, can be None for auto-selection)
            prompt: The prompt to send
            tools: List of OpenAI-compatible tool schemas
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            tool_choice: How the model should choose tools
            provider_name: Alias for provider (keyword-only)
            **kwargs: Additional arguments

        Returns:
            LLMResponse with tool_calls field populated if model called tools
        """
        if tools is None:
            tools = []

        # Support both 'provider' and 'provider_name' for compatibility
        actual_provider = provider_name if provider_name is not None else provider

        # Get the provider instance from registry
        provider_obj = self._orch._registry.get(actual_provider)
        if provider_obj is None:
            raise ValueError(f"Provider {actual_provider} not found in registry")

        # Check if provider supports native tool calling
        if not provider_obj.supports_tool_calling:
            raise ValueError(
                f"Provider {actual_provider} does not support native tool calling. "
                "Use regular delegate() with JSON parsing instead."
            )

        # Build messages array with system prompt if provided
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Call provider's chat_with_tools method
        response = provider_obj.chat_with_tools(
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs
        )

        return response

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
