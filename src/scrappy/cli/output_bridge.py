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

from .protocols import BaseOutputProtocol
from scrappy.infrastructure.theme import ThemeProtocol, DEFAULT_THEME

if TYPE_CHECKING:
    from .protocols import OutputSink


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

    def __init__(
        self,
        output_sink: "OutputSink",
        theme: Optional[ThemeProtocol] = None
    ):
        """Initialize with OutputSink for routing.

        Args:
            output_sink: OutputSink protocol implementation (e.g., TextualOutputAdapter)
            theme: Optional theme for styling. Defaults to DEFAULT_THEME.
        """
        self.output_sink = output_sink
        self._theme = theme or DEFAULT_THEME

    def info(self, message: str) -> None:
        """Output informational message via OutputSink."""
        self.output_sink.post_output(message + "\n")

    def warn(self, message: str) -> None:
        """Output warning message with theme warning color."""
        from rich.text import Text
        warning_text = Text(message, style=self._theme.warning)
        self.output_sink.post_renderable(warning_text)

    def error(self, message: str) -> None:
        """Output error message with theme error color (bold)."""
        from rich.text import Text
        error_text = Text(message, style=f"{self._theme.error} bold")
        self.output_sink.post_renderable(error_text)

    def success(self, message: str) -> None:
        """Output success message with theme success color."""
        from rich.text import Text
        success_text = Text(message, style=self._theme.success)
        self.output_sink.post_renderable(success_text)


class ConsoleOutputBridge:
    """Direct console output implementation of BaseOutputProtocol.

    Used in CLI mode when output should go directly to console
    rather than through an OutputSink.

    This is a thin wrapper that provides BaseOutputProtocol interface
    over direct console print operations.
    """

    # ANSI color code mapping for theme colors
    ANSI_COLORS = {
        "cyan": "\033[36m",
        "yellow": "\033[33m",
        "red": "\033[31m",
        "green": "\033[32m",
        "blue": "\033[34m",
        "magenta": "\033[35m",
        "white": "\033[37m",
        "black": "\033[30m",
        "bright_black": "\033[90m",
    }

    def __init__(
        self,
        use_colors: bool = True,
        theme: Optional[ThemeProtocol] = None
    ):
        """Initialize console output bridge.

        Args:
            use_colors: Whether to use ANSI colors (default True)
            theme: Optional theme for styling. Defaults to DEFAULT_THEME.
        """
        self.use_colors = use_colors
        self._theme = theme or DEFAULT_THEME

    def _get_ansi_code(self, color: str) -> str:
        """Get ANSI escape code for a color name."""
        return self.ANSI_COLORS.get(color, "")

    def info(self, message: str) -> None:
        """Output informational message to console."""
        print(message)

    def warn(self, message: str) -> None:
        """Output warning message with theme warning color."""
        if self.use_colors:
            ansi = self._get_ansi_code(self._theme.warning)
            print(f"{ansi}{message}\033[0m")
        else:
            print(f"[WARN] {message}")

    def error(self, message: str) -> None:
        """Output error message with theme error color (bold)."""
        if self.use_colors:
            ansi = self._get_ansi_code(self._theme.error)
            print(f"\033[1m{ansi}{message}\033[0m")  # Bold + color
        else:
            print(f"[ERROR] {message}")

    def success(self, message: str) -> None:
        """Output success message with theme success color."""
        if self.use_colors:
            ansi = self._get_ansi_code(self._theme.success)
            print(f"{ansi}{message}\033[0m")
        else:
            print(f"[OK] {message}")


def create_output_bridge(
    output_sink: Optional["OutputSink"] = None,
    use_colors: bool = True,
    theme: Optional[ThemeProtocol] = None
) -> BaseOutputProtocol:
    """Factory function to create appropriate output bridge.

    Creates either:
    - OutputBridge (TUI mode): Routes through OutputSink for Textual
    - ConsoleOutputBridge (CLI mode): Direct console output

    Args:
        output_sink: Optional OutputSink for TUI mode. If None, CLI mode.
        use_colors: Whether to use colors in CLI mode.
        theme: Optional theme for styling. Defaults to DEFAULT_THEME.

    Returns:
        BaseOutputProtocol implementation appropriate for the mode.
    """
    if output_sink is not None:
        return OutputBridge(output_sink, theme=theme)
    else:
        return ConsoleOutputBridge(use_colors=use_colors, theme=theme)


# Re-export for backward compatibility
# OrchestratorOutputAdapter is now an alias to OutputBridge
OrchestratorOutputAdapter = OutputBridge
