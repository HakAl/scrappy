"""
Textual-based I/O implementation for CLI operations.

Implements CLIIOProtocol by writing to Textual widgets instead of
direct console output, enabling rich terminal UI interactions.
"""

from typing import Optional, Any
import sys
import logging
from rich.console import Console
from rich.text import Text
from rich.protocol import is_renderable
from src.cli.protocols import OutputSink

logger = logging.getLogger(__name__)


class TextualConsole(Console):
    """Console that intercepts Rich objects and posts to Textual.

    This hybrid console extends Rich Console to intercept print() calls
    and route them appropriately:
    - Strings: Convert to Rich Text with markup, post as renderable
    - Renderables (Panel, Table, etc.): Post directly
    - Other types: Convert to string, then to Text

    This ensures all output goes through the message queue for thread safety.
    """

    def __init__(self, output_sink: OutputSink):
        """Initialize console with output sink.

        Args:
            output_sink: OutputSink protocol implementation to post output to
        """
        super().__init__(force_terminal=False)
        self.output_sink = output_sink

    def print(self, *objects, **kwargs) -> None:
        """Intercept print calls and route to appropriate output method.

        Routes based on object type:
        - Strings: Convert to Rich Text with markup
        - Renderables: Send directly
        - Other: Convert to string then Text

        Args:
            *objects: Objects to print
            **kwargs: Keyword arguments (ignored, kept for compatibility)
        """
        for obj in objects:
            if isinstance(obj, str):
                # Handle Rich markup like "[bold red]Error[/]"
                renderable = Text.from_markup(obj)
                self.output_sink.post_renderable(renderable)
            elif is_renderable(obj):
                # Panel, Table, Markdown, etc.
                self.output_sink.post_renderable(obj)
            else:
                # Fallback for primitives (int, dict, etc.)
                renderable = Text(str(obj))
                self.output_sink.post_renderable(renderable)


class TextualIO:
    """Textual-based IO implementation.

    Implements CLIIOProtocol using OutputSink protocol for dependency inversion.
    All output is routed through the OutputSink interface, enabling testing
    with mocks and clean separation from Textual internals.
    """

    def __init__(self, output_sink: OutputSink):
        """Initialize TextualIO with output sink.

        Args:
            output_sink: OutputSink protocol implementation to post output to
        """
        self.output_sink = output_sink
        self._console = TextualConsole(output_sink)

    @property
    def console(self) -> TextualConsole:
        """Return console that posts to Textual.

        Returns:
            TextualConsole instance that routes through OutputSink
        """
        return self._console

    def echo(self, message: str = "", nl: bool = True) -> None:
        """Output a plain text message.

        Args:
            message: The text to output
            nl: Whether to append a newline (default True)
        """
        content = message + ("\n" if nl else "")
        self.output_sink.post_output(content)

    def secho(
        self,
        message: str,
        fg: Optional[str] = None,
        bold: bool = False,
        nl: bool = True
    ) -> None:
        """Output a styled message using Rich markup.

        Converts Click-style color names to Rich markup and posts
        as a renderable Text object.

        Args:
            message: The text to output
            fg: Foreground color (e.g., 'red', 'green', 'cyan')
            bold: Whether to make text bold
            nl: Whether to append a newline (default True)
        """
        # Convert Click colors to Rich markup
        color_map = {
            "cyan": "cyan",
            "yellow": "yellow",
            "red": "red",
            "green": "green",
            "blue": "blue",
            "magenta": "magenta",
            "white": "white",
            "black": "black",
        }

        # Build Rich markup
        styled_text = message
        if fg or bold:
            rich_color = color_map.get(fg, fg) if fg else None
            if rich_color and bold:
                styled_text = f"[bold {rich_color}]{message}[/bold {rich_color}]"
            elif rich_color:
                styled_text = f"[{rich_color}]{message}[/{rich_color}]"
            elif bold:
                styled_text = f"[bold]{message}[/bold]"

        # Add newline if requested
        if nl:
            styled_text += "\n"

        # Convert to Text renderable and post
        renderable = Text.from_markup(styled_text)
        self.output_sink.post_renderable(renderable)

    def styled_echo(
        self,
        message: str,
        fg: Optional[str] = None,
        bold: bool = False,
        nl: bool = True
    ) -> None:
        """Alias for secho() for backwards compatibility.

        Args:
            message: The text to output
            fg: Foreground color
            bold: Whether to make text bold
            nl: Whether to append a newline
        """
        self.secho(message, fg=fg, bold=bold, nl=nl)

    def style(
        self,
        text: str,
        fg: Optional[str] = None,
        bold: bool = False
    ) -> str:
        """Return styled text using Rich markup.

        Args:
            text: The text to style
            fg: Foreground color
            bold: Whether to make text bold

        Returns:
            The text with Rich markup tags
        """
        # Convert Click colors to Rich markup
        color_map = {
            "cyan": "cyan",
            "yellow": "yellow",
            "red": "red",
            "green": "green",
            "blue": "blue",
            "magenta": "magenta",
            "white": "white",
            "black": "black",
        }

        # Build Rich markup
        if fg and bold:
            rich_color = color_map.get(fg, fg)
            return f"[bold {rich_color}]{text}[/bold {rich_color}]"
        elif fg:
            rich_color = color_map.get(fg, fg)
            return f"[{rich_color}]{text}[/{rich_color}]"
        elif bold:
            return f"[bold]{text}[/bold]"
        else:
            return text

    def prompt(
        self,
        text: str,
        default: str = "",
        show_default: bool = True
    ) -> str:
        """Get user input with a prompt.

        Note: Not used in Textual mode. Input comes via Input widget events.

        Args:
            text: The prompt text to display
            default: Default value if user enters nothing
            show_default: Whether to show the default in the prompt

        Raises:
            NotImplementedError: Always raised in Textual mode
        """
        raise NotImplementedError(
            "prompt() not supported in Textual mode. "
            "Use Input widget events instead."
        )

    def confirm(
        self,
        text: str,
        default: bool = False
    ) -> bool:
        """Get yes/no confirmation from user.

        Note: Not used in Textual mode. Use modal dialogs instead.

        Args:
            text: The confirmation prompt
            default: Default value if user just presses enter

        Raises:
            NotImplementedError: Always raised in Textual mode
        """
        raise NotImplementedError(
            "confirm() not supported in Textual mode. "
            "Use modal dialogs instead."
        )

    def input_line(self) -> str:
        """Read a raw line of input.

        Note: Not used in Textual mode. Input comes via Input widget events.

        Raises:
            NotImplementedError: Always raised in Textual mode
        """
        raise NotImplementedError(
            "input_line() not supported in Textual mode. "
            "Use Input widget events instead."
        )
