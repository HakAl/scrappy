"""
Type definitions for orchestrator streaming functionality.

Defines dataclasses for streaming responses, tool call fragments,
streaming configuration, and streaming-specific errors.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List


@dataclass
class StreamingConfig:
    """
    Configuration for streaming output behavior.

    Controls buffering, pacing, and display of streaming responses
    for optimal user experience across different terminals and modes.

    Attributes:
        buffer_threshold: Characters to buffer before flush (0 = no buffering).
            Higher values reduce I/O overhead but feel less "live".
            Default 80 (typical terminal width).
        token_delay_ms: Milliseconds to wait between tokens for readability.
            0 = no delay (maximum speed), higher values slow the stream.
            Default 8ms provides slight pacing without feeling slow.
            Use 15-30ms for comfortable reading, 0 for maximum speed.
        line_buffer: If True, always flush on newlines regardless of threshold.
            Default True for proper line-by-line display.
        show_metadata: If True, display stream start/end metadata.
            Default False for cleaner output.
    """
    buffer_threshold: int = 80
    token_delay_ms: int = 8  # Slight pacing for readability
    line_buffer: bool = True
    show_metadata: bool = False

    @classmethod
    def fast(cls) -> "StreamingConfig":
        """Create config for maximum speed (no buffering, no delay)."""
        return cls(buffer_threshold=0, token_delay_ms=0, line_buffer=False)

    @classmethod
    def readable(cls) -> "StreamingConfig":
        """Create config for comfortable reading pace."""
        return cls(buffer_threshold=80, token_delay_ms=20, line_buffer=True)

    @classmethod
    def slow(cls) -> "StreamingConfig":
        """Create config for slow, dramatic output (demos, presentations)."""
        return cls(buffer_threshold=0, token_delay_ms=40, line_buffer=True)


# Default streaming configuration
DEFAULT_STREAMING_CONFIG = StreamingConfig()


@dataclass
class ToolCallFragment:
    """
    Represents a partial tool call being accumulated during streaming.

    Streaming responses may deliver tool calls in fragments across
    multiple chunks. This dataclass represents the current state of
    a tool call as it's being accumulated.

    Attributes:
        id: Tool call identifier (may be partial or complete)
        type: Tool type (typically "function")
        name: Function name (accumulated across chunks)
        arguments: JSON string of arguments (accumulated across chunks)
        index: Position in the tool call array
        complete: Whether this fragment represents a complete tool call
    """
    id: str
    type: str
    name: str
    arguments: str
    index: int
    complete: bool = False


@dataclass
class StreamChunk:
    """
    Represents a single chunk in a streaming LLM response.

    During streaming, the LLM provider sends multiple chunks of data.
    Each chunk may contain partial content, tool call fragments, or
    metadata about the ongoing response.

    Attributes:
        content: Text content in this chunk (empty string if none)
        tool_call_fragments: List of tool call fragments in this chunk
        finish_reason: Reason streaming ended (None if still streaming)
        model: Model identifier (may be empty until final chunk)
        provider: Provider name (may be empty until final chunk)
        metadata: Additional chunk-specific metadata
    """
    content: str = ""
    tool_call_fragments: List[ToolCallFragment] = field(default_factory=list)
    finish_reason: Optional[str] = None
    model: str = ""
    provider: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StreamStuckError(Exception):
    """
    Raised when streaming appears to have stalled.

    This error is raised when:
    - No chunks received within timeout period
    - Stream stops without finish_reason
    - Provider connection appears hung

    Attributes:
        message: Error description
        provider: Provider where stream stalled
        model: Model that was being streamed
        chunks_received: Number of chunks received before stall
        last_content: Last content received (for debugging)
    """
    message: str
    provider: str = ""
    model: str = ""
    chunks_received: int = 0
    last_content: str = ""

    def __str__(self) -> str:
        parts = [self.message]
        if self.provider:
            parts.append(f"provider={self.provider}")
        if self.model:
            parts.append(f"model={self.model}")
        if self.chunks_received > 0:
            parts.append(f"chunks_received={self.chunks_received}")
        return ", ".join(parts)
