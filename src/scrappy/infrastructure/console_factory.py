"""
Console factory for mode-aware Rich Console creation.

Provides a factory that returns appropriate Console instances based
on the current output mode (TUI vs CLI). In TUI mode, returns a
Console that captures output to StringIO for routing through the
Textual output queue.
"""

from typing import TYPE_CHECKING, Optional, Protocol, Tuple
from io import StringIO

from rich.console import Console

from scrappy.infrastructure.output_mode import OutputModeContext

if TYPE_CHECKING:
    pass


class ConsoleFactoryProtocol(Protocol):
    """Factory protocol for Console creation.

    Defines the interface for creating Rich Console instances
    in a mode-aware manner.

    Implementations:
    - ConsoleFactory: Returns mode-aware Console instances
    - TestConsoleFactory: Returns preset Console for testing
    """

    def get_console(self) -> Console:
        """Get appropriate Console for current mode.

        Returns:
            Console configured for the current output mode
        """
        ...

    def create_string_console(self) -> Tuple[Console, StringIO]:
        """Create Console with StringIO for string rendering.

        Returns:
            Tuple of (Console, StringIO buffer)
        """
        ...


class ConsoleFactory:
    """Mode-aware Console factory.

    Creates Rich Console instances that respect the current output mode.
    In TUI mode, returns Console instances that write to StringIO
    so output can be captured and routed through the Textual output queue.

    Example:
        factory = ConsoleFactory()

        # In CLI mode - writes to stdout
        console = factory.get_console()
        console.print("Hello")  # Goes to terminal

        # In TUI mode - captures to StringIO
        OutputModeContext.set_tui_mode(True, sink)
        console = factory.get_console()
        console.print("Hello")  # Captured, not written to terminal

        # For string rendering (mode-independent)
        console, buffer = factory.create_string_console()
        console.print("Hello")
        output = buffer.getvalue()
    """

    def __init__(self, fallback_console: Optional[Console] = None):
        """Initialize the factory.

        Args:
            fallback_console: Console to use in CLI mode.
                            If None, creates a new default Console.
        """
        self._fallback = fallback_console or Console()

    def get_console(self) -> Console:
        """Get appropriate Console for current mode.

        In TUI mode, returns a Console that writes to StringIO
        so output can be routed through the OutputSink.
        In CLI mode, returns the fallback Console (direct output).

        Returns:
            Console instance appropriate for current mode
        """
        if OutputModeContext.is_tui_mode():
            # Return console that captures output for TUI routing
            buffer = StringIO()
            return Console(file=buffer, force_terminal=True)
        return self._fallback

    def get_console_with_buffer(self) -> Tuple[Console, Optional[StringIO]]:
        """Get Console with its buffer if in TUI mode.

        This method is useful when you need to capture the output
        and route it through the OutputSink.

        Returns:
            Tuple of (Console, StringIO) in TUI mode
            Tuple of (Console, None) in CLI mode
        """
        if OutputModeContext.is_tui_mode():
            buffer = StringIO()
            console = Console(file=buffer, force_terminal=True)
            return console, buffer
        return self._fallback, None

    def create_string_console(self) -> Tuple[Console, StringIO]:
        """Create Console with StringIO for string rendering.

        This is mode-independent - always returns a Console that
        writes to StringIO. Useful for rendering to string regardless
        of current mode.

        Returns:
            Tuple of (Console, StringIO buffer)
        """
        buffer = StringIO()
        console = Console(file=buffer, force_terminal=True)
        return console, buffer

    def route_console_output(
        self,
        console: Console,
        buffer: Optional[StringIO],
    ) -> None:
        """Route buffered console output through OutputSink if in TUI mode.

        Call this after printing to a Console obtained from get_console_with_buffer()
        to route the output through the Textual output queue.

        Args:
            console: Console instance (unused but kept for API clarity)
            buffer: StringIO buffer from get_console_with_buffer(), or None

        Example:
            console, buffer = factory.get_console_with_buffer()
            console.print("Hello")
            factory.route_console_output(console, buffer)
        """
        if buffer is not None and OutputModeContext.is_tui_mode():
            sink = OutputModeContext.get_output_sink()
            if sink is not None:
                output = buffer.getvalue()
                if output:
                    sink.post_output(output)
