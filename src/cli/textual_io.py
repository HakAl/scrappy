"""
Textual-based I/O implementation for CLI operations.

Implements CLIIOProtocol by writing to Textual widgets instead of
direct console output, enabling rich terminal UI interactions.
"""

from typing import Optional, TYPE_CHECKING
import sys
import logging
import threading
from rich.console import Console
from textual.widgets import RichLog

if TYPE_CHECKING:
    from src.cli.textual_app import ScrappyApp

logger = logging.getLogger(__name__)


class TextualIO:
    """Textual-based IO implementation.

    Implements CLIIOProtocol by writing to Textual widgets
    instead of console. All output goes to the RichLog widget,
    with full Rich markup and renderable support.

    Acts as a file-like object for Rich Console - write() method
    immediately posts messages to the Textual app (no buffering).
    """

    def __init__(self, app: "ScrappyApp"):
        """Initialize TextualIO with reference to the Textual app.

        Args:
            app: The ScrappyApp instance to write output to
        """
        self._app = app
        # Console writes directly to self (via write() method)
        self._console = Console(file=self, force_terminal=True, width=120)

    @property
    def console(self) -> Console:
        """Return the Rich Console for rendering Rich objects.

        Returns:
            Console instance that writes to this TextualIO
        """
        return self._console

    def write(self, text: str) -> int:
        """File-like write method for Rich Console.

        Called by Rich Console when rendering output. Immediately
        posts message to Textual app (no buffering).

        Args:
            text: The text to write (may include ANSI codes, Rich markup)

        Returns:
            Number of characters written
        """
        from src.cli.textual_app import WriteOutput

        if text:
            logger.debug(
                f"[TextualIO.write] Posting {len(text)} chars from thread: "
                f"{threading.current_thread().name}"
            )
            try:
                self._app.post_message(WriteOutput(text))
            except Exception as e:
                logger.error(f"CRITICAL: Failed to post message: {e}")
                sys.stderr.write(f"{text}\n")

        return len(text)

    def flush(self) -> None:
        """File-like flush method.

        No-op since we don't buffer - all writes are immediate.
        """
        pass

    def echo(self, message: str = "", nl: bool = True) -> None:
        """Output a message to the RichLog widget via message.

        Args:
            message: The text to output
            nl: Whether to append a newline (default True)
        """
        # Import here to avoid circular dependency
        from src.cli.textual_app import WriteOutput

        content = message + ("\n" if nl else "")
        logger.debug(
            f"[TextualIO.echo] Posting from thread: {threading.current_thread().name}"
        )
        try:
            self._app.post_message(WriteOutput(content))
        except Exception as e:
            logger.error(f"CRITICAL: Failed to post message: {e}")
            sys.stderr.write(f"{content}\n")

    def secho(
        self,
        message: str,
        fg: Optional[str] = None,
        bold: bool = False,
        nl: bool = True
    ) -> None:
        """Output a styled message with Rich markup via message.

        Args:
            message: The text to output
            fg: Foreground color (e.g., 'red', 'green', 'cyan')
            bold: Whether to make text bold
            nl: Whether to append a newline (default True)
        """
        # Import here to avoid circular dependency
        from src.cli.textual_app import WriteOutput

        styled = self._apply_style(message, fg, bold)
        content = styled + ("\n" if nl else "")
        logger.debug(
            f"[TextualIO.secho] Posting from thread: {threading.current_thread().name}"
        )
        try:
            self._app.post_message(WriteOutput(content))
        except Exception as e:
            logger.error(f"CRITICAL: Failed to post message: {e}")
            sys.stderr.write(f"{content}\n")

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
        return self._apply_style(text, fg, bold)

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

    def _apply_style(
        self,
        text: str,
        fg: Optional[str] = None,
        bold: bool = False
    ) -> str:
        """Apply Rich markup styling to text.

        Args:
            text: The text to style
            fg: Foreground color
            bold: Whether to make text bold

        Returns:
            Text with Rich markup tags
        """
        # Build Rich markup
        if fg and bold:
            return f"[bold {fg}]{text}[/bold {fg}]"
        elif fg:
            return f"[{fg}]{text}[/{fg}]"
        elif bold:
            return f"[bold]{text}[/bold]"
        else:
            return text
