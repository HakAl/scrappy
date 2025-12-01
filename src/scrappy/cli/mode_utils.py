"""Mode detection utilities for CLI/TUI output routing.

This module provides utilities for checking whether the application is running
in CLI mode (direct console output) or TUI mode (Textual/OutputSink routing).

The canonical source of truth for mode is UnifiedIO.is_tui_mode property.
This module provides helper functions to check mode without requiring direct
access to UnifiedIO internals.

Usage:
    from scrappy.cli.mode_utils import is_tui_mode

    def my_function(io: CLIIOProtocol) -> None:
        if is_tui_mode(io):
            # Route through IO methods
            io.echo("TUI mode output")
        else:
            # Can use direct console if needed (prefer IO methods)
            io.echo("CLI mode output")
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .io_interface import CLIIOProtocol


def is_tui_mode(io: "CLIIOProtocol") -> bool:
    """Check if the IO interface is in TUI mode.

    This function safely checks whether the provided IO interface is
    operating in TUI (Textual) mode, where output should be routed
    through the OutputSink rather than direct console output.

    Args:
        io: CLIIOProtocol instance (typically UnifiedIO)

    Returns:
        True if in TUI mode (Textual), False for CLI mode.
        Returns False if the io object doesn't have is_tui_mode attribute.

    Example:
        >>> io = UnifiedIO(output_sink=textual_adapter)
        >>> is_tui_mode(io)
        True

        >>> io = UnifiedIO()  # CLI mode
        >>> is_tui_mode(io)
        False
    """
    return getattr(io, "is_tui_mode", False)


def get_output_sink(io: "CLIIOProtocol"):
    """Get the OutputSink from an IO interface if in TUI mode.

    Args:
        io: CLIIOProtocol instance (typically UnifiedIO)

    Returns:
        OutputSink instance if in TUI mode, None otherwise.
    """
    return getattr(io, "output_sink", None)
