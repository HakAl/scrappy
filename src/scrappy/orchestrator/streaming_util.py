"""
Streaming utilities for LLM response processing.

Provides utilities for:
- Accumulating streamed tool call fragments into complete tool calls
- Formatting stream errors for user-friendly display
"""

import json
from typing import Dict, List, Optional
from dataclasses import dataclass

from .types import ToolCallFragment


# =============================================================================
# Stream Error Formatting
# =============================================================================

@dataclass
class StreamErrorInfo:
    """
    Information about a stream error for display.

    Attributes:
        message: The error message
        category: Categorized error type (Rate Limit, Timeout, etc.)
        provider: Provider where error occurred
        chunks_received: Number of chunks received before error
        suggestion: Actionable suggestion for the user
    """
    message: str
    category: Optional[str] = None
    provider: Optional[str] = None
    chunks_received: int = 0
    suggestion: Optional[str] = None


class StreamErrorFormatter:
    """
    Formats stream errors for user-friendly display.

    Provides consistent error display across streaming paths with:
    - Visual separation from streamed content
    - Error categorization for common issues
    - Context about partial results
    - Actionable suggestions

    Example:
        formatter = StreamErrorFormatter()
        error_text = formatter.format(
            error="Rate limit exceeded",
            chunks_received=42,
            provider="groq"
        )
        await output.stream_token(error_text)
    """

    # Error patterns for categorization
    PATTERNS = {
        "Rate Limit": ["rate limit", "throttl", "too many requests", "429"],
        "Timeout": ["timeout", "timed out", "deadline", "stall"],
        "Context Overflow": ["context", "token limit", "too long", "maximum length", "context_length"],
        "Auth Error": ["auth", "api key", "unauthorized", "403", "401", "invalid key"],
        "Network Error": ["connect", "network", "unreachable", "dns", "socket", "connection reset"],
        "Model Error": ["model not found", "model_not_found", "invalid model"],
    }

    # Suggestions per category
    SUGGESTIONS = {
        "Rate Limit": "Wait a moment and retry, or use /provider to switch.",
        "Timeout": "The response may be incomplete. Try a simpler query.",
        "Context Overflow": "Input too long. Try shorter input or split the task.",
        "Auth Error": "Check API key configuration with /status.",
        "Network Error": "Check your connection and retry.",
        "Model Error": "Check model name or try a different provider.",
    }

    def categorize(self, error: str, metadata: Optional[dict] = None) -> Optional[str]:
        """
        Categorize an error message.

        Args:
            error: The error message string
            metadata: Optional metadata that may contain explicit category

        Returns:
            Category string or None if uncategorizable
        """
        metadata = metadata or {}

        # Check metadata first
        if "category" in metadata:
            return metadata["category"]

        # Pattern matching on error message
        error_lower = error.lower()
        for category, patterns in self.PATTERNS.items():
            if any(pattern in error_lower for pattern in patterns):
                return category

        return None

    def get_suggestion(self, category: Optional[str]) -> Optional[str]:
        """Get suggestion for an error category."""
        if category:
            return self.SUGGESTIONS.get(category)
        return None

    def format(
        self,
        error: str,
        chunks_received: int = 0,
        provider: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> str:
        """
        Format an error for display during streaming.

        Args:
            error: The error message
            chunks_received: Number of chunks received before error
            provider: Provider where error occurred
            metadata: Additional error metadata

        Returns:
            Formatted error string for display
        """
        metadata = metadata or {}
        category = self.categorize(error, metadata)
        provider = provider or metadata.get("provider")

        lines = ["", "--- Stream Error ---"]

        # Category + message
        if category:
            lines.append(f"[{category}] {error}")
        else:
            lines.append(error)

        # Provider context
        if provider:
            lines.append(f"Provider: {provider}")

        # Partial results context
        if chunks_received > 0:
            lines.append(f"({chunks_received} chunks received before error)")
            lines.append("Partial response above may still be useful.")

        # Suggestion
        suggestion = self.get_suggestion(category)
        if suggestion:
            lines.append(f"Tip: {suggestion}")

        lines.append("--------------------")
        lines.append("")

        return "\n".join(lines)

    def format_info(self, info: StreamErrorInfo) -> str:
        """
        Format error from StreamErrorInfo dataclass.

        Args:
            info: StreamErrorInfo with error details

        Returns:
            Formatted error string
        """
        return self.format(
            error=info.message,
            chunks_received=info.chunks_received,
            provider=info.provider,
            metadata={"category": info.category} if info.category else None
        )


# Singleton instance for convenience
_error_formatter = StreamErrorFormatter()


def format_stream_error(
    error: str,
    chunks_received: int = 0,
    provider: Optional[str] = None,
    metadata: Optional[dict] = None
) -> str:
    """
    Format a stream error for display (convenience function).

    Args:
        error: The error message
        chunks_received: Number of chunks received before error
        provider: Provider where error occurred
        metadata: Additional error metadata

    Returns:
        Formatted error string for display
    """
    return _error_formatter.format(error, chunks_received, provider, metadata)


@dataclass
class ToolCall:
    """
    Represents a complete tool call.

    Attributes:
        id: Tool call unique identifier
        type: Tool type (typically "function")
        name: Function name
        arguments: Parsed arguments as dictionary
        index: Position in the tool call array
    """
    id: str
    type: str
    name: str
    arguments: Dict
    index: int


class ToolCallAccumulator:
    """
    Accumulates streaming tool call fragments into complete tool calls.

    During streaming, LLM providers send tool calls incrementally across
    multiple chunks. This class maintains state for each tool call being
    accumulated, parsing JSON arguments as they arrive, and detecting
    when tool calls are complete.

    This handles provider-specific quirks:
    - Incomplete JSON strings across chunks
    - Tool calls arriving out of order
    - Multiple tool calls in parallel
    - Varying fragment formats

    Example:
        accumulator = ToolCallAccumulator()

        # Process chunks as they arrive
        for chunk in stream:
            for fragment in chunk.tool_call_fragments:
                accumulator.add_fragment(fragment)

        # Get completed tool calls
        completed = accumulator.get_completed()
        for tool_call in completed:
            print(f"Tool: {tool_call.name}, Args: {tool_call.arguments}")
    """

    def __init__(self) -> None:
        """Initialize an empty accumulator."""
        self._fragments: Dict[int, ToolCallFragment] = {}
        self._completed: List[ToolCall] = []

    def add_fragment(self, fragment: ToolCallFragment) -> Optional[ToolCall]:
        """
        Add a tool call fragment and potentially complete a tool call.

        Args:
            fragment: ToolCallFragment to process

        Returns:
            Completed ToolCall if fragment completes a tool call, None otherwise

        Raises:
            ValueError: If fragment has invalid JSON arguments
        """
        index = fragment.index

        if index in self._fragments:
            # Merge with existing fragment
            existing = self._fragments[index]
            existing.id = fragment.id or existing.id
            existing.name = fragment.name or existing.name
            existing.arguments += fragment.arguments
            existing.complete = fragment.complete or existing.complete
        else:
            # Store new fragment
            self._fragments[index] = ToolCallFragment(
                id=fragment.id,
                type=fragment.type,
                name=fragment.name,
                arguments=fragment.arguments,
                index=fragment.index,
                complete=fragment.complete
            )

        # Check if fragment is now complete
        current = self._fragments[index]
        if current.complete and current.id and current.name:
            return self._finalize_tool_call(index)

        return None

    def _finalize_tool_call(self, index: int) -> ToolCall:
        """
        Finalize a tool call by parsing arguments and marking complete.

        Args:
            index: Index of the tool call to finalize

        Returns:
            Completed ToolCall

        Raises:
            ValueError: If arguments are not valid JSON
        """
        fragment = self._fragments[index]

        # Parse JSON arguments
        try:
            arguments = json.loads(fragment.arguments) if fragment.arguments else {}
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Invalid JSON in tool call arguments at index {index}: {fragment.arguments}"
            ) from e

        # Create completed tool call
        tool_call = ToolCall(
            id=fragment.id,
            type=fragment.type,
            name=fragment.name,
            arguments=arguments,
            index=fragment.index
        )

        # Store and remove from fragments
        self._completed.append(tool_call)
        del self._fragments[index]

        return tool_call

    def get_completed(self) -> List[ToolCall]:
        """
        Get all completed tool calls.

        Returns:
            List of completed ToolCall objects, ordered by index
        """
        return sorted(self._completed, key=lambda tc: tc.index)

    def get_pending(self) -> List[ToolCallFragment]:
        """
        Get all pending (incomplete) tool call fragments.

        Returns:
            List of incomplete ToolCallFragment objects, ordered by index
        """
        return sorted(self._fragments.values(), key=lambda f: f.index)

    def has_pending(self) -> bool:
        """
        Check if there are pending fragments.

        Returns:
            True if there are incomplete fragments, False otherwise
        """
        return len(self._fragments) > 0

    def reset(self) -> None:
        """
        Reset accumulator state, clearing all fragments and completed calls.
        """
        self._fragments.clear()
        self._completed.clear()

    def force_complete_pending(self) -> List[ToolCall]:
        """
        Force complete all pending fragments, even if marked incomplete.

        This is useful when streaming ends unexpectedly but fragments contain
        valid data. Attempts to parse all pending fragments as complete tool calls.

        Returns:
            List of force-completed ToolCall objects

        Raises:
            ValueError: If any pending fragment has invalid JSON arguments
        """
        completed = []
        pending_indexes = list(self._fragments.keys())

        for index in pending_indexes:
            fragment = self._fragments[index]
            if fragment.id and fragment.name and fragment.arguments:
                # Mark as complete and finalize
                fragment.complete = True
                tool_call = self._finalize_tool_call(index)
                completed.append(tool_call)

        return completed
