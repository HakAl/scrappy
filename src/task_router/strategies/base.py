"""
Base classes and protocols for execution strategies.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol

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


class ExecutionStrategy(ABC):
    """Abstract base for execution strategies."""

    @abstractmethod
    def execute(self, task: ClassifiedTask) -> ExecutionResult:
        """Execute the classified task."""
        pass

    @abstractmethod
    def can_handle(self, task: ClassifiedTask) -> bool:
        """Check if this strategy can handle the task."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy name for logging."""
        pass
