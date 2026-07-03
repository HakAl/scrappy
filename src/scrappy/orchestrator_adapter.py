"""
Minimal orchestrator adapter implementation for the CodeAgent.

This provides adapter implementations that wrap the full orchestrator.
The ContextProvider and OrchestratorAdapter protocols are defined in orchestrator/protocols.py.

After LiteLLM integration:
- Legacy provider names ("groq", "cerebras") map to model groups ("fast", "quality")
- Model groups are handled by LiteLLM Router with automatic fallback
- Tool calling is passed through to LiteLLM
"""

from typing import List, Optional

# Import protocols from centralized location
from .orchestrator.protocols import ContextProvider

# Import LLMResponse from orchestrator provider types
from .orchestrator.provider_types import LLMResponse

# Import canonical MODEL_GROUPS from model_selection
from .orchestrator.model_selection import MODEL_GROUPS, ModelSelectionType


# Map legacy provider names to model groups
PROVIDER_TO_GROUP = {
    "groq": "fast",       # Default to fast for Groq (has both fast and instruct models)
    "cerebras": "fast",   # Cerebras only has 8k context, always fast tier
    "gemini": "instruct", # Gemini is instruct tier (tool use, large context)
    "auto": "fast",       # Auto-select defaults to fast
}


class NullContext:
    """Null context provider that returns no context."""

    def is_explored(self) -> bool:
        return False

    def get_summary(self) -> str:
        return ""

    def augment_prompt(self, user_prompt: str, include_files: bool = False) -> str:
        return user_prompt


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
        tools: Optional[List[dict]] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1500,
        temperature: float = 0.3,
        tool_choice: str = "auto",
        selection_type: Optional["ModelSelectionType"] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Delegate to provider with native tool calling support.

        After LiteLLM integration:
        - No longer checks provider.supports_tool_calling
        - LiteLLM handles tool calling natively via kwargs
        - Defaults to INSTRUCT tier for tool calling (instruction-tuned models)

        Args:
            provider_name: Provider name or model group (defaults to "quality")
            prompt: The prompt to send
            tools: List of OpenAI-compatible tool schemas
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            tool_choice: How the model should choose tools
            selection_type: Model selection type (defaults to INSTRUCT for tool calling)
            **kwargs: Additional arguments

        Returns:
            LLMResponse with tool_calls field populated if model called tools
        """
        from .orchestrator.model_selection import ModelSelectionType

        if tools is None:
            tools = []

        # Default to INSTRUCT for tool calling (instruction-tuned models)
        if selection_type is None:
            selection_type = ModelSelectionType.INSTRUCT

        # Resolve provider name to model group (default to quality for tool calling)
        model_group = self._resolve_model_group(provider_name or "quality")

        # Delegate through normal path - tools passed as kwargs
        return self._orch.delegate(
            provider_name=model_group,
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=tools,
            tool_choice=tool_choice,
            selection_type=selection_type,
            **kwargs
        )

    async def stream_delegate(
        self,
        provider_name: Optional[str] = None,
        prompt: str = "",
        system_prompt: Optional[str] = None,
        max_tokens: int = 1500,
        temperature: float = 0.3,
        use_context: bool = False,
        **kwargs
    ):
        """
        Stream delegate to the orchestrator for real-time token output.

        Yields StreamChunk objects as tokens arrive from the LLM.

        Args:
            provider_name: Provider name (can be None for auto-selection)
            prompt: The prompt to send
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            use_context: Whether to use context augmentation
            **kwargs: Additional arguments passed to orchestrator

        Yields:
            StreamChunk objects with content tokens
        """
        if not hasattr(self._orch, 'stream_delegate'):
            raise NotImplementedError("Orchestrator does not support streaming")

        async for chunk in self._orch.stream_delegate(
            provider_name=provider_name,
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            use_context=use_context,
            **kwargs
        ):
            yield chunk

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

    def delegate_structured(
        self,
        provider_name: str,
        prompt: str,
        response_model: type,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        auto_fallback: bool = True,
        selection_type: Optional[ModelSelectionType | str] = None,
        min_context: Optional[int] = None,
        **kwargs
    ):
        """
        Delegate with structured output validation.

        Args:
            provider_name: Provider name or model group
            prompt: The prompt to send
            response_model: Pydantic model class for response validation
            system_prompt: Optional system prompt
            model: Specific concrete model to use
            auto_fallback: Automatically try other models on retryable failures
            selection_type: Selection type or value used for fallback candidates
            min_context: Minimum required context window
            **kwargs: Additional arguments passed to orchestrator

        Returns:
            Validated Pydantic model instance
        """
        return self._orch.delegate_structured(
            provider_name=provider_name,
            prompt=prompt,
            response_model=response_model,
            system_prompt=system_prompt,
            model=model,
            auto_fallback=auto_fallback,
            selection_type=selection_type,
            min_context=min_context,
            **kwargs
        )

    def _resolve_model_group(self, provider_or_group: Optional[str]) -> str:
        """
        Resolve provider name or group to a model group.

        After LiteLLM integration:
        - If already a model group ("fast", "quality"), return as-is
        - If legacy provider name ("groq", "cerebras"), map to appropriate group
        - If None or "auto", default to "fast"

        Args:
            provider_or_group: Provider name, model group, or None

        Returns:
            Model group name ("fast" or "quality")
        """
        if provider_or_group is None:
            return "fast"

        # Already a model group
        if provider_or_group in MODEL_GROUPS:
            return provider_or_group

        # Legacy provider name -> map to group
        return PROVIDER_TO_GROUP.get(provider_or_group, "fast")
