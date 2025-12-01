"""
Base classes and protocols for execution strategies.

All strategies implement the ExecutionStrategyProtocol from protocols.py.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from ..classifier import ClassifiedTask


@dataclass
class ExecutionResult:
    """Result from task execution."""
    success: bool
    output: str
    error: Optional[str] = None
    execution_time: float = 0.0
    metadata: Dict[str, object] = field(default_factory=dict)
    tokens_used: int = 0
    provider_used: Optional[str] = None


class ContextLike(Protocol):
    """Protocol for codebase context."""

    def is_explored(self) -> bool:
        """Check if codebase has been explored."""
        ...

    def get_summary(self) -> str:
        """Get summary of codebase."""
        ...

    @property
    def file_index(self) -> Dict[str, List[str]]:
        """Get file index mapping."""
        ...

    def explore(self, force: bool = False) -> None:
        """Explore the codebase."""
        ...


class ProviderRegistryLike(Protocol):
    """Protocol for provider registry."""

    def list_available(self) -> List[str]:
        """List available providers."""
        ...


class LLMResponseLike(Protocol):
    """Protocol for LLM response."""

    @property
    def content(self) -> str:
        """Get response content."""
        ...

    @property
    def tokens_used(self) -> int:
        """Get tokens used."""
        ...


class OrchestratorLike(Protocol):
    """Protocol for orchestrator dependency."""

    def delegate(
        self,
        provider: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1500,
        temperature: float = 0.3,
        use_context: bool = False
    ) -> LLMResponseLike:
        """Delegate prompt to a provider."""
        ...

    @property
    def context(self) -> ContextLike:
        """Get codebase context."""
        ...

    @property
    def brain(self) -> str:
        """Get the brain provider name."""
        ...

    @property
    def providers(self) -> ProviderRegistryLike:
        """Get provider registry."""
        ...


@runtime_checkable
class ToolLike(Protocol):
    """Protocol for task execution tools.

    Tools are callable objects that perform specific operations
    like reading files, searching code, or fetching web content.
    """

    @property
    def name(self) -> str:
        """Tool name for registration and lookup."""
        ...

    def __call__(self, context: Any, **kwargs) -> str:
        """
        Execute the tool with given context and parameters.

        Args:
            context: Tool context with project root, settings, etc.
            **kwargs: Tool-specific parameters

        Returns:
            String result of tool execution
        """
        ...

    def get_full_description(self) -> str:
        """
        Get full description of tool for LLM prompts.

        Returns:
            Human-readable description including parameters
        """
        ...


@runtime_checkable
class ToolRegistryLike(Protocol):
    """Protocol for tool registration and lookup.

    Manages a collection of tools that can be retrieved by name.
    """

    def get(self, tool_name: str) -> Optional[ToolLike]:
        """
        Get a tool by name.

        Args:
            tool_name: Name of the tool to retrieve

        Returns:
            Tool instance or None if not found
        """
        ...

    def register(self, tool: ToolLike) -> None:
        """
        Register a tool in the registry.

        Args:
            tool: Tool instance to register
        """
        ...

    def list_tools(self) -> List[str]:
        """
        List all registered tool names.

        Returns:
            List of tool names
        """
        ...


class ProviderAwareStrategy:
    """
    Base class for strategies that need provider resolution.

    Provides common provider handling logic to avoid duplication:
    - set_provider() method for setting resolved provider/model
    - _resolve_and_validate_provider() for resolving with fallback

    Subclasses should call _resolve_and_validate_provider() in their
    execute() method to get the provider to use.
    """

    def __init__(self, orchestrator: OrchestratorLike):
        """
        Initialize with orchestrator.

        Args:
            orchestrator: Orchestrator instance for provider access
        """
        self.orchestrator = orchestrator
        self._resolved_provider: Optional[str] = None
        self._resolved_model: Optional[str] = None

    def set_provider(self, provider_name: Optional[str], model_name: Optional[str] = None):
        """
        Set the provider to use for the next execution.

        Called by TaskRouter with resolved provider from classifier hints.

        Args:
            provider_name: Provider name or None
            model_name: Model name or None
        """
        self._resolved_provider = provider_name
        self._resolved_model = model_name

    def _resolve_and_validate_provider(self, preferred_provider: Optional[str] = None) -> str:
        """
        Resolve and validate provider, with fallback to orchestrator.brain.

        Priority order:
        1. _resolved_provider (set via set_provider)
        2. preferred_provider parameter
        3. orchestrator.brain (fallback)

        Also validates provider is available, falling back to brain if not.

        Args:
            preferred_provider: Optional preferred provider if _resolved_provider not set

        Returns:
            Provider name to use

        Side effect:
            Clears _resolved_provider and _resolved_model after use
        """
        # Determine provider to use (priority: resolved > preferred > brain)
        if self._resolved_provider:
            provider_to_use = self._resolved_provider
        elif preferred_provider:
            provider_to_use = preferred_provider
        else:
            provider_to_use = self.orchestrator.brain

        # Validate provider is available
        try:
            available = self.orchestrator.providers.list_available()
            if provider_to_use not in available:
                provider_to_use = self.orchestrator.brain
        except Exception:
            provider_to_use = self.orchestrator.brain

        # Clear resolved values after use
        self._resolved_provider = None
        self._resolved_model = None

        return provider_to_use
