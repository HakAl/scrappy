"""
Protocols for the graph package.

Centralizes protocol definitions to avoid duplication across modules.
"""

from pathlib import Path
from typing import Any, AsyncIterator, Callable, Iterator, Protocol, runtime_checkable

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

    def stream_completion_sync(
        self,
        model: str,
        messages: list[dict],
        **kwargs: Any,
    ) -> Iterator[StreamChunk]:
        """
        Sync streaming completion call.

        Yields chunks as they arrive from the LLM provider. Used by
        think_node when stream_callback is provided for real-time output.

        Args:
            model: Model tier ("fast", "chat", or "instruct")
            messages: Chat messages
            **kwargs: Additional params (tools, tool_choice, max_tokens, etc.)

        Yields:
            StreamChunk objects as they arrive
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


@runtime_checkable
class WorkingMemoryProtocol(Protocol):
    """
    Protocol for session-scoped working memory.

    Tracks recent file reads, searches, git operations, and discoveries
    to provide context for LLM augmentation.
    """

    def remember_file_read(self, path: str, content: str, lines: int = 0) -> None:
        """
        Store a file read in working memory.

        Args:
            path: File path
            content: File content
            lines: Number of lines in file
        """
        ...

    def remember_search(self, query: str, results: list) -> None:
        """
        Store a search result in working memory.

        Args:
            query: Search query
            results: Search results
        """
        ...

    def remember_git_operation(self, operation: str, output: str) -> None:
        """
        Store a git operation result in working memory.

        Args:
            operation: Git command executed
            output: Command output
        """
        ...

    def add_discovery(self, finding: str, location: str = "") -> None:
        """
        Add a discovery/learning to working memory.

        Args:
            finding: What was discovered
            location: Where it was found (optional)
        """
        ...

    def get_context(self) -> str:
        """
        Get working memory context string for LLM augmentation.

        Returns:
            Context string summarizing recent interactions
        """
        ...


@runtime_checkable
class ContextFactoryProtocol(Protocol):
    """
    Protocol for building agent execution context.

    Single Responsibility: Create context (RAG, search strategy) based on task.

    Implementations:
    - GraphContextFactory: Full RAG + search strategy for graph agent
    - MockContextFactory: Fixed context for testing
    - NullContextFactory: No-op for when RAG unavailable

    Example:
        def enhance_prompt(factory: ContextFactoryProtocol, task: str, prompt: str) -> str:
            rag_context = factory.build_rag_context(task)
            if rag_context:
                return prompt + rag_context
            return prompt
    """

    def build_rag_context(self, task: str) -> str | None:
        """
        Build passive RAG context using semantic search.

        Computes token budget heuristically, searches codebase,
        filters results by quality, formats into context block.

        Args:
            task: User task description

        Returns:
            Formatted RAG context string, or None if unavailable
        """
        ...

    def build_search_strategy_section(self, tool_names: list[str]) -> str:
        """
        Build search strategy guidance based on available tools.

        Args:
            tool_names: List of available tool names

        Returns:
            Search strategy prompt section, empty if no search tools
        """
        ...

    def is_ready(self) -> bool:
        """
        Check if context factory is ready (semantic search indexed).

        Returns:
            True if ready to provide RAG context, False otherwise
        """
        ...
