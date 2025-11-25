"""
Unified output bridge for routing between different output modes.

This module consolidates output adapters and provides mode-based routing
for the CLI/TUI output system.

The OutputBridge enables:
- Routing BaseOutputProtocol messages to OutputSink (TUI mode)
- Mode detection (CLI vs TUI)
- Consistent output behavior across modes

Following SOLID principles:
- Single Responsibility: Bridges one protocol to another
- Open/Closed: New adapters can be added without modification
- Dependency Inversion: Depends on protocols, not implementations
"""

from typing import Optional, TYPE_CHECKING

from ..protocols.output import BaseOutputProtocol, RichRenderableProtocol

if TYPE_CHECKING:
    from .protocols import OutputSink
    from rich.console import RenderableType


class OutputBridge:
    """Bridges BaseOutputProtocol to RichRenderableProtocol (OutputSink).

    This adapter enables orchestrator output (info, warn, error, success)
    to be routed through the Textual TUI's OutputSink, maintaining
    thread-safe output routing in TUI mode.

    Implements BaseOutputProtocol so it can be used wherever operational
    output is expected.

    Usage:
        # Create bridge to route orchestrator output to Textual
        bridge = OutputBridge(textual_adapter)
        orchestrator.output = bridge

        # Now orchestrator.output.info("message") routes through Textual
    """

    def __init__(self, output_sink: "OutputSink"):
        """Initialize with OutputSink for routing.

        Args:
            output_sink: OutputSink protocol implementation (e.g., TextualOutputAdapter)
        """
        self.output_sink = output_sink

    def info(self, message: str) -> None:
        """Output informational message via OutputSink."""
        self.output_sink.post_output(message + "\n")

    def warn(self, message: str) -> None:
        """Output warning message with yellow styling."""
        from rich.text import Text
        warning_text = Text(message, style="yellow")
        self.output_sink.post_renderable(warning_text)

    def error(self, message: str) -> None:
        """Output error message with red bold styling."""
        from rich.text import Text
        error_text = Text(message, style="red bold")
        self.output_sink.post_renderable(error_text)

    def success(self, message: str) -> None:
        """Output success message with green styling."""
        from rich.text import Text
        success_text = Text(message, style="green")
        self.output_sink.post_renderable(success_text)


class ConsoleOutputBridge:
    """Direct console output implementation of BaseOutputProtocol.

    Used in CLI mode when output should go directly to console
    rather than through an OutputSink.

    This is a thin wrapper that provides BaseOutputProtocol interface
    over direct console print operations.
    """

    def __init__(self, use_colors: bool = True):
        """Initialize console output bridge.

        Args:
            use_colors: Whether to use ANSI colors (default True)
        """
        self.use_colors = use_colors

    def info(self, message: str) -> None:
        """Output informational message to console."""
        print(message)

    def warn(self, message: str) -> None:
        """Output warning message with yellow styling."""
        if self.use_colors:
            print(f"\033[33m{message}\033[0m")  # Yellow
        else:
            print(f"[WARN] {message}")

    def error(self, message: str) -> None:
        """Output error message with red bold styling."""
        if self.use_colors:
            print(f"\033[1;31m{message}\033[0m")  # Bold red
        else:
            print(f"[ERROR] {message}")

    def success(self, message: str) -> None:
        """Output success message with green styling."""
        if self.use_colors:
            print(f"\033[32m{message}\033[0m")  # Green
        else:
            print(f"[OK] {message}")


def create_output_bridge(
    output_sink: Optional["OutputSink"] = None,
    use_colors: bool = True
) -> BaseOutputProtocol:
    """Factory function to create appropriate output bridge.

    Creates either:
    - OutputBridge (TUI mode): Routes through OutputSink for Textual
    - ConsoleOutputBridge (CLI mode): Direct console output

    Args:
        output_sink: Optional OutputSink for TUI mode. If None, CLI mode.
        use_colors: Whether to use colors in CLI mode.

    Returns:
        BaseOutputProtocol implementation appropriate for the mode.
    """
    if output_sink is not None:
        return OutputBridge(output_sink)
    else:
        return ConsoleOutputBridge(use_colors=use_colors)


# Re-export for backward compatibility
# OrchestratorOutputAdapter is now an alias to OutputBridge
OrchestratorOutputAdapter = OutputBridge
