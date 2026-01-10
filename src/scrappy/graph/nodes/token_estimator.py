"""
Token estimation for context window management.

Single responsibility: Estimate token counts for text and messages.
Used by ContextManager to determine when to trim context.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class TokenEstimatorProtocol(Protocol):
    """Protocol for token estimation implementations."""

    def estimate_text(self, text: str) -> int:
        """Estimate token count for plain text."""
        ...

    def estimate_message(self, message: dict) -> int:
        """Estimate token count for a message dict."""
        ...


class TokenEstimator:
    """
    Character-based token estimator.

    Uses a simple character-to-token ratio. Not perfectly accurate but
    sufficient for context trimming decisions where we need ballpark
    estimates, not exact counts.

    The 0.25 ratio is conservative for English text. Claude/GPT tokenizers
    typically produce 0.2-0.3 tokens per character depending on content.
    """

    # Average tokens per character (conservative for English)
    TOKENS_PER_CHAR: float = 0.25

    # Overhead tokens per message (role marker, separators)
    MESSAGE_OVERHEAD: int = 4

    # Overhead per tool call (structure, separators)
    TOOL_CALL_OVERHEAD: int = 10

    def estimate_text(self, text: str) -> int:
        """
        Estimate token count for text.

        Args:
            text: Text to estimate tokens for

        Returns:
            Estimated token count
        """
        return int(len(text) * self.TOKENS_PER_CHAR)

    def estimate_message(self, message: dict) -> int:
        """
        Estimate token count for a message.

        Includes role overhead, content, and tool calls if present.

        Args:
            message: Message dict with role, content, etc.

        Returns:
            Estimated token count
        """
        tokens = self.MESSAGE_OVERHEAD

        # Content tokens (handle None values)
        content = message.get("content") or ""
        if content:
            tokens += self.estimate_text(content)

        # Tool calls overhead
        tool_calls = message.get("tool_calls", [])
        if tool_calls:
            for tc in tool_calls:
                name = tc.get("name", "")
                args = tc.get("arguments", "{}")
                tokens += self.estimate_text(name) + self.estimate_text(args)
                tokens += self.TOOL_CALL_OVERHEAD

        return tokens


# Default instance for simple usage
default_estimator = TokenEstimator()
