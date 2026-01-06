"""
Protocols for the graph package.

Centralizes protocol definitions to avoid duplication across modules.
"""

from pathlib import Path
from typing import Any, AsyncIterator, Callable, Protocol, runtime_checkable

from scrappy.orchestrator.types import StreamChunk


@runtime_checkable
class ToolContextProtocol(Protocol):
    """
    Protocol for tool execution context.

    Defines the minimal interface needed by execute_node.
    Implementations can provide additional features.
    """

    @property
    def project_root(self) -> Path:
        """Project root directory for file operations."""
        ...

    @property
    def dry_run(self) -> bool:
        """Whether to simulate operations without side effects."""
        ...


# Factory type for creating tool contexts
# Takes working_dir (str) and returns a ToolContextProtocol
ToolContextFactory = Callable[[str], ToolContextProtocol]


@runtime_checkable
class LLMServiceProtocol(Protocol):
    """
    Protocol for LLM service integration.

    Abstracts the LLM completion interface to enable testing
    without real API calls.
    """

    def completion_sync(
        self,
        model: str,
        messages: list[dict],
        **kwargs: Any,
    ) -> tuple[Any, dict]:
        """
        Sync completion call.

        Args:
            model: Model tier ("fast" or "quality")
            messages: Chat messages
            **kwargs: Additional params (tools, tool_choice, max_tokens, etc.)

        Returns:
            Tuple of (LLMResponse, task_record)
        """
        ...

    def completion_direct(
        self,
        model: str,
        messages: list[dict],
        **kwargs: Any,
    ) -> tuple[Any, dict]:
        """
        Direct completion call to a specific model (bypasses Router).

        Use for fallback calls when Router's model group is exhausted.

        Args:
            model: Specific model name (e.g., "gemini/gemini-2.5-flash")
            messages: Chat messages
            **kwargs: Additional params (tools, tool_choice, max_tokens, etc.)

        Returns:
            Tuple of (LLMResponse, task_record)
        """
        ...


@runtime_checkable
class StreamingLLMServiceProtocol(Protocol):
    """
    Protocol for streaming LLM service integration.

    Extends LLMServiceProtocol with streaming capabilities.
    """

    def stream_completion(
        self,
        model: str,
        messages: list[dict],
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """
        Streaming completion call.

        Args:
            model: Model tier ("fast" or "quality")
            messages: Chat messages
            **kwargs: Additional params (tools, tool_choice, max_tokens, etc.)

        Returns:
            AsyncIterator of StreamChunk objects
        """
        ...
