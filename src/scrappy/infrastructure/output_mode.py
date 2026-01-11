"""
Output mode context for TUI/CLI mode detection.

Provides thread-safe, async-safe context tracking for determining
whether output should be routed through Textual TUI or direct console.

Uses contextvars.ContextVar for proper isolation across threads and
async contexts.
"""

from typing import TYPE_CHECKING, Optional, Protocol
from contextvars import ContextVar

if TYPE_CHECKING:
    from scrappy.cli.protocols import RichRenderableProtocol as OutputSink


class OutputModeProtocol(Protocol):
    """Protocol for output mode detection.

    Defines the interface for determining the current output mode
    (TUI vs CLI) and retrieving the appropriate output sink.

    Implementations:
    - OutputModeContext: Uses contextvars for thread-safe mode tracking
    - TestOutputMode: Returns preset values for testing
    """

    def is_tui_mode(self) -> bool:
        """Check if running in TUI mode.

        Returns:
            True if TUI mode is active, False for CLI mode
        """
        ...

    def get_output_sink(self) -> Optional["OutputSink"]:
        """Get the current output sink for TUI mode.

        Returns:
            OutputSink if in TUI mode and sink is set, None otherwise
        """
        ...


class OutputModeContext:
    """Context-aware output mode tracking using contextvars.

    Provides class-level methods for getting/setting the output mode.
    Uses ContextVar for thread-safety and async isolation.

    Why ContextVar?
    1. Thread-safe mode detection
    2. Async-safe (works with asyncio)
    3. No global mutable state issues
    4. Proper isolation in tests

    Example:
        # In Textual app on_mount
        OutputModeContext.set_tui_mode(True, self._output_adapter)

        # In any component
        if OutputModeContext.is_tui_mode():
            sink = OutputModeContext.get_output_sink()
            sink.post_output("Hello TUI")
        else:
            print("Hello CLI")

        # On unmount
        OutputModeContext.set_tui_mode(False)
    """

    _tui_mode: ContextVar[bool] = ContextVar("tui_mode", default=False)
    _output_sink: ContextVar[Optional["OutputSink"]] = ContextVar(
        "output_sink", default=None
    )

    @classmethod
    def set_tui_mode(cls, enabled: bool, sink: Optional["OutputSink"] = None) -> None:
        """Set the TUI mode state.

        Args:
            enabled: True to enable TUI mode, False for CLI mode
            sink: OutputSink to use in TUI mode (required if enabled=True)
        """
        cls._tui_mode.set(enabled)
        cls._output_sink.set(sink if enabled else None)

    @classmethod
    def is_tui_mode(cls) -> bool:
        """Check if TUI mode is currently active.

        Returns:
            True if TUI mode is active, False otherwise
        """
        return cls._tui_mode.get()

    @classmethod
    def get_output_sink(cls) -> Optional["OutputSink"]:
        """Get the current output sink.

        Returns:
            OutputSink if in TUI mode and sink is set, None otherwise
        """
        return cls._output_sink.get()

    @classmethod
    def reset(cls) -> None:
        """Reset to default state (CLI mode, no sink).

        Primarily used for testing to ensure clean state.
        """
        cls._tui_mode.set(False)
        cls._output_sink.set(None)
