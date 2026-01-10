"""
Context window management for LLM conversations.

Single responsibility: Manage message history to fit within context limits.
Handles observation masking and context trimming.
"""

from typing import Protocol, runtime_checkable

from scrappy.graph.nodes.token_estimator import TokenEstimator, TokenEstimatorProtocol
from scrappy.infrastructure.logging import get_logger

logger = get_logger(__name__)


@runtime_checkable
class ContextManagerProtocol(Protocol):
    """Protocol for context management implementations."""

    def mask_old_tool_results(
        self,
        messages: list[dict],
        keep_full: int,
    ) -> list[dict]:
        """Replace old tool results with placeholders."""
        ...

    def sanitize(
        self,
        messages: list[dict],
        max_tokens: int,
    ) -> list[dict]:
        """Trim message history to fit within token limit."""
        ...


class ContextManager:
    """
    Manages conversation context to fit within LLM token limits.

    Two-phase approach:
    1. Observation masking - Replace old tool results with placeholders
    2. Context trimming - Drop old messages if still over limit

    This is critical for long agent runs where tool results accumulate
    and consume the context window.
    """

    # Keep last N tool results in full, mask older ones
    DEFAULT_KEEP_FULL: int = 2

    # Safety margin - trim at 80% of limit to leave room for response
    TOKEN_LIMIT_MARGIN: float = 0.8

    # Default context window (128k tokens)
    DEFAULT_MAX_TOKENS: int = 128000

    # Minimum messages to keep (system + last user message)
    MIN_MESSAGES_TO_KEEP: int = 2

    def __init__(
        self,
        token_estimator: TokenEstimatorProtocol | None = None,
    ) -> None:
        """
        Initialize context manager.

        Args:
            token_estimator: Token estimator implementation (uses default if None)
        """
        self._estimator = token_estimator or TokenEstimator()

    def mask_old_tool_results(
        self,
        messages: list[dict],
        keep_full: int | None = None,
    ) -> list[dict]:
        """
        Replace old tool result content with placeholder to save context.

        Pattern from task_router/strategies/research_loop.py:
        - Recent tool results (last `keep_full`) are preserved in full
        - Older tool results are replaced with "[X chars returned]" placeholder
        - Non-tool messages (user, assistant, system) are never masked

        Args:
            messages: List of messages to process
            keep_full: Number of recent tool results to keep in full

        Returns:
            New list with old tool results masked (original unchanged)
        """
        if not messages:
            return messages

        if keep_full is None:
            keep_full = self.DEFAULT_KEEP_FULL

        # Find indices of all tool result messages
        tool_indices: list[int] = []
        for i, msg in enumerate(messages):
            if msg.get("role") == "tool":
                tool_indices.append(i)

        # If we have fewer tool results than keep_full, no masking needed
        if len(tool_indices) <= keep_full:
            return messages

        # Indices to mask (all except last keep_full)
        indices_to_mask = set(tool_indices[:-keep_full])

        # Create new list with masked content
        result: list[dict] = []
        for i, msg in enumerate(messages):
            if i in indices_to_mask:
                content = msg.get("content") or ""
                content_len = len(content)
                masked_msg = dict(msg)  # Shallow copy
                masked_msg["content"] = f"[{content_len} chars returned]"
                result.append(masked_msg)
            else:
                result.append(msg)

        return result

    def sanitize(
        self,
        messages: list[dict],
        max_tokens: int | None = None,
    ) -> list[dict]:
        """
        Trim message history if approaching token limit.

        Strategy:
        1. Apply observation masking - replace old tool results with placeholders
        2. Always keep first message (system prompt) if present
        3. Always keep last few messages (current conversation)
        4. Drop middle messages one by one until within limit

        Args:
            messages: Full message history
            max_tokens: Maximum allowed tokens

        Returns:
            Trimmed message list within token budget
        """
        if not messages:
            return messages

        if max_tokens is None:
            max_tokens = self.DEFAULT_MAX_TOKENS

        # Phase 1: Apply observation masking
        messages = self.mask_old_tool_results(messages)

        # Calculate current token usage (after masking)
        total_tokens = sum(self._estimator.estimate_message(m) for m in messages)

        # Calculate effective limit with margin
        effective_limit = int(max_tokens * self.TOKEN_LIMIT_MARGIN)

        # If within limit, return as-is
        if total_tokens <= effective_limit:
            return messages

        logger.warning(
            "Context approaching limit: %d tokens (limit: %d). Trimming.",
            total_tokens,
            effective_limit,
        )

        # Phase 2: Drop old messages to fit
        if len(messages) <= self.MIN_MESSAGES_TO_KEEP:
            return messages

        # Separate system message if present
        first_message = messages[0] if messages else None
        has_system = first_message is not None and first_message.get("role") == "system"

        if has_system:
            system_msg: dict = messages[0]
            remaining: list[dict] = messages[1:]
            system_tokens = self._estimator.estimate_message(system_msg)
        else:
            remaining = messages[:]
            system_tokens = 0

        # Pre-compute token counts (O(n) once)
        token_counts = [self._estimator.estimate_message(m) for m in remaining]

        # Build suffix sums for O(1) lookup of "tokens for last k messages"
        n = len(remaining)
        suffix_sums = [0] * (n + 1)
        for i in range(n - 1, -1, -1):
            suffix_sums[i] = suffix_sums[i + 1] + token_counts[i]

        # Find how many recent messages we can keep
        for keep_count in range(n, 0, -1):
            candidate_tokens = system_tokens + suffix_sums[n - keep_count]
            if candidate_tokens <= effective_limit:
                recent_msgs: list[dict] = remaining[-keep_count:]

                if keep_count < len(remaining):
                    dropped = len(remaining) - keep_count
                    logger.info("Dropped %d messages to fit context window.", dropped)

                    # Add summary message indicating trimming
                    summary_msg: dict = {
                        "role": "system",
                        "content": f"[Earlier conversation of {dropped} messages omitted for context limit]",
                    }
                    if has_system:
                        return [system_msg, summary_msg] + recent_msgs
                    return [summary_msg] + recent_msgs

                if has_system:
                    return [system_msg] + recent_msgs
                return recent_msgs

        # Worst case: just keep the minimum
        logger.warning("Had to drop all but minimum messages for context limit.")
        if has_system:
            return [system_msg, remaining[-1]] if remaining else [system_msg]
        return [remaining[-1]] if remaining else []


# Default instance for simple usage
default_context_manager = ContextManager()
