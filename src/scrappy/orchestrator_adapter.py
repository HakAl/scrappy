"""
Minimal orchestrator adapter implementation for the CodeAgent.

This provides adapter implementations that wrap the full orchestrator.
The ContextProvider and OrchestratorAdapter protocols are defined in orchestrator/protocols.py.
"""

from typing import List, Optional

# Import protocols from centralized location
from .orchestrator.protocols import ContextProvider, OrchestratorAdapter

# Import LLMResponse from providers to get full feature set including tool_calls
from .providers.base import LLMResponse, ToolCall


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
        provider_name: Optional[str] = None,
        prompt: str = "",
        system_prompt: Optional[str] = None,
        max_tokens: int = 1500,
        temperature: float = 0.3,
        use_context: bool = False,
        selection_type: Optional["ModelSelectionType"] = None,
        **kwargs
    ) -> LLMResponse:
        """Delegate to the orchestrator's delegate method.

        Args:
            provider_name: Provider name (can be None for auto-selection)
            prompt: The prompt to send
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            use_context: Whether to use context augmentation
            selection_type: What kind of model to use for auto-selection
            **kwargs: Additional arguments passed to orchestrator
        """

        # Build kwargs for orchestrator - only pass selection_type if not None
        # This allows orchestrator to use its default value
        orch_kwargs = {
            'provider_name': provider_name,
            'prompt': prompt,
            'system_prompt': system_prompt,
            'max_tokens': max_tokens,
            'temperature': temperature,
            'use_context': use_context,
            **kwargs
        }
        if selection_type is not None:
            orch_kwargs['selection_type'] = selection_type

        # Pass to orchestrator with new signature
        response = self._orch.delegate(**orch_kwargs)

        # Wrap in our LLMResponse if needed
        if isinstance(response, LLMResponse):
            return response

        # Adapt from orchestrator's response format
        # Use response.provider if available, otherwise fall back to provider_name
        response_provider = getattr(response, 'provider', provider_name or 'unknown')
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
        provider_name: Optional[str] = None,
        prompt: str = "",
        tools: List[dict] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1500,
        temperature: float = 0.3,
        tool_choice: str = "auto",
        **kwargs
    ) -> LLMResponse:
        """
        Delegate to provider with native tool calling support.

        Args:
            provider_name: Provider name (can be None for auto-selection)
            prompt: The prompt to send
            tools: List of OpenAI-compatible tool schemas
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            tool_choice: How the model should choose tools
            **kwargs: Additional arguments

        Returns:
            LLMResponse with tool_calls field populated if model called tools
        """
        if tools is None:
            tools = []

        # Get the provider instance from registry
        provider_obj = self._orch._registry.get(provider_name)
        if provider_obj is None:
            raise ValueError(f"Provider {provider_name} not found in registry")

        # Check if provider supports native tool calling
        if not provider_obj.supports_tool_calling:
            raise ValueError(
                f"Provider {provider_name} does not support native tool calling. "
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
        """Proxy to orchestrator's working memory."""
        if hasattr(self._orch, 'working_memory'):
            self._orch.working_memory.remember_file_read(path, content, lines)

    def remember_search(self, query: str, results: list):
        """Proxy to orchestrator's working memory."""
        if hasattr(self._orch, 'working_memory'):
            self._orch.working_memory.remember_search(query, results)

    def remember_git_operation(self, operation: str, result: str):
        """Proxy to orchestrator's working memory."""
        if hasattr(self._orch, 'working_memory'):
            self._orch.working_memory.remember_git_operation(operation, result)