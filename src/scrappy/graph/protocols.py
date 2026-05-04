"""
Protocols for the graph package.

Centralizes protocol definitions to avoid duplication across modules.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncIterator, Callable, Iterator, Optional, Protocol, runtime_checkable

from scrappy.orchestrator.types import StreamChunk
from scrappy.graph.state import ToolCall

if TYPE_CHECKING:
    from scrappy.graph.run_context import AgentRunContextProtocol


# =============================================================================
# Think Node Types
# =============================================================================


@dataclass(frozen=True)
class ThinkResult:
    """
    Result of a think delegation - either success or error.

    Immutable value object that encapsulates everything the think node
    needs to update agent state after an LLM call.

    Success case: content and/or tool_calls populated, error is None
    Error case: error populated, recovery_action guides next step

    Examples:
        # Successful text response (agent is done)
        ThinkResult(
            content="The answer is 42.",
            model_display="cerebras: llama-3.3-70b",
            input_tokens=100,
            output_tokens=10,
        )

        # Successful tool call response (agent continues)
        ThinkResult(
            content="I'll search for that.",
            tool_calls=[ToolCall(...)],
            model_display="groq: llama-3.1-70b",
        )

        ThinkResult(
            content="Done.",
            model_display="groq: llama-3.3-70b",
            trace_chain="cerebras(429)->groq: llama-3.3-70b",
        )

        # Retriable error
        ThinkResult(
            error="Rate limit exceeded",
            suggestion="Try another provider or wait before retrying.",
            recovery_action="fallback",
            error_category="rate_limit",
        )

        # Fatal error
        ThinkResult(
            error="API key invalid",
            recovery_action="abort",
            error_category="auth",
            is_fatal=True,
        )
    """

    # Success fields
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = field(default_factory=tuple)
    model_display: Optional[str] = None  # e.g., "cerebras: llama-3.3-70b"
    trace_chain: Optional[str] = None  # e.g., "cerebras(429)->groq: llama-3.3-70b"

    # Token usage from API (None if not available, e.g., provider doesn't report)
    input_tokens: Optional[int] = None  # Actual prompt tokens from API
    output_tokens: Optional[int] = None  # Actual completion tokens from API

    # Error fields (mutually exclusive with success)
    error: Optional[str] = None
    suggestion: Optional[str] = None
    recovery_action: Optional[str] = None  # "retry", "fallback", "abort"
    error_category: Optional[str] = None  # "rate_limit", "auth", "network", etc.
    is_fatal: bool = False  # Should graph stop immediately?

    @property
    def is_success(self) -> bool:
        """True if this is a successful result (no error)."""
        return self.error is None

    @property
    def is_done(self) -> bool:
        """True if this is a final response (success with no tool calls)."""
        return self.is_success and len(self.tool_calls) == 0 and self.content.strip() != ""

    @property
    def has_tool_calls(self) -> bool:
        """True if response includes tool calls."""
        return len(self.tool_calls) > 0


@runtime_checkable
class ThinkDelegatorProtocol(Protocol):
    """
    Handles LLM completion for think node with model selection and error recovery.

    This protocol abstracts the LLM call logic out of think.py, encapsulating:
    - Model selection (tier-based or affinity-based via run_context)
    - Streaming with cancellation support
    - Error handling with automatic fallback
    - Provider affinity tracking

    Implementations:
    - LiteLLMThinkDelegator: Production implementation using LiteLLM
    - MockThinkDelegator: Test double with scripted responses

    Example:
        def think_node(state, delegator: ThinkDelegatorProtocol, ...):
            result = delegator.complete(messages, tools, run_context, state.current_tier)
            if result.is_success:
                # Update state with content/tool_calls
            else:
                # Handle error based on recovery_action
    """

    def complete(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        run_context: Optional["AgentRunContextProtocol"] = None,
        current_tier: str = "instruct",
    ) -> ThinkResult:
        """
        Synchronous completion with automatic model selection and fallback.

        Selects model based on:
        1. run_context.preferred_model (affinity from previous success)
        2. run_context.model_selection.select() (priority-based)
        3. current_tier fallback (Router-based)

        On error, may retry with fallback models based on error type.

        Args:
            messages: Chat messages in OpenAI format
            tools: Optional tool schemas for function calling
            run_context: Optional context for affinity, cancellation, model selection
            current_tier: Model tier ("fast", "chat", "instruct")

        Returns:
            ThinkResult with content/tool_calls on success, error info on failure
        """
        ...

    async def complete_streaming(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        run_context: Optional["AgentRunContextProtocol"] = None,
        current_tier: str = "instruct",
        on_chunk: Optional[Callable[[str], None]] = None,
    ) -> ThinkResult:
        """
        Async streaming completion with chunk callback.

        Same model selection and fallback logic as complete(), but:
        - Yields content chunks via on_chunk callback as they arrive
        - Supports cancellation check between chunks
        - Returns final ThinkResult when stream completes

        Args:
            messages: Chat messages in OpenAI format
            tools: Optional tool schemas for function calling
            run_context: Optional context for affinity, cancellation, model selection
            current_tier: Model tier ("fast", "chat", "instruct")
            on_chunk: Optional callback invoked with each content chunk

        Returns:
            ThinkResult with accumulated content/tool_calls on success
        """
        ...


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

    @property
    def run_context(self) -> Optional["AgentRunContextProtocol"]:
        """Ephemeral run context for file caching and status updates."""
        ...


# Factory type for creating tool contexts
# Takes working_dir (str) and returns a ToolContextProtocol
ToolContextFactory = Callable[[str], ToolContextProtocol]


@runtime_checkable
class StreamingOrchestratorProtocol(Protocol):
    """
    Protocol for orchestrator's streaming completion with fallback.

    This protocol captures the minimal interface needed by think_delegator
    to stream completions with automatic model selection and rate limit handling.

    The orchestrator owns:
    - Model selection via model_selector
    - Rate limit detection and marking
    - Automatic fallback to alternative models
    - Session-sticky model preferences

    Implementations:
    - AgentOrchestrator: Full production orchestrator
    - MockStreamingOrchestrator: Test double for unit tests

    Example:
        def stream_with_fallback(orch: StreamingOrchestratorProtocol, messages: list[dict]):
            for chunk in orch.stream_completion_with_fallback(messages):
                if chunk.content:
                    print(chunk.content, end="")
    """

    def stream_completion_with_fallback(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        selection_type: Optional[Any] = None,  # ModelSelectionType
        **kwargs: Any,
    ) -> Iterator[StreamChunk]:
        """
        Stream completion with automatic model selection and fallback on rate limit.

        Args:
            messages: Chat messages in OpenAI format
            model: Specific model ID (optional - will select if not provided)
            selection_type: Model selection type (default: INSTRUCT)
            **kwargs: Additional params (max_tokens, temperature, tools, etc.)

        Yields:
            StreamChunk objects as they arrive from the provider

        Raises:
            AllModelsRateLimitedError: If all models are rate limited
            ValueError: If no models configured for selection type
        """
        ...


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
