"""
Progress reporter implementations.

Provides concrete implementations of ProgressReporterProtocol for different
progress display strategies (Rich, logging, callbacks, silent).
"""

import logging
import time
from typing import Optional, Callable, TYPE_CHECKING

from src.infrastructure.output_mode import OutputModeContext
from src.infrastructure.theme import ThemeProtocol, DEFAULT_THEME

if TYPE_CHECKING:
    from ..cli.io_interface import CLIIOProtocol

logger = logging.getLogger(__name__)


class RichProgressReporter:
    """
    Progress reporter using Rich library with status spinner.

    Displays progress using Rich's Status component which is simpler and
    less intrusive than Progress bars. Automatically cleans up on completion.

    Implements ProgressReporterProtocol.

    WARNING: CLI MODE ONLY. This reporter outputs directly to the console
    and will bypass Textual's output routing in TUI mode. For TUI-compatible
    progress reporting, use UnifiedIOProgressReporter instead, or use the
    create_progress_reporter() factory function which automatically selects
    the correct reporter.
    """

    def __init__(self, theme: Optional[ThemeProtocol] = None):
        """Initialize Rich progress reporter.

        Args:
            theme: Optional theme for color styling. Uses DEFAULT_THEME if not provided.

        Raises:
            RuntimeError: If called in TUI mode (must use UnifiedIOProgressReporter)

        Note:
            For TUI mode, use UnifiedIOProgressReporter instead which routes
            through the IO abstraction.
        """
        if OutputModeContext.is_tui_mode():
            raise RuntimeError(
                "RichProgressReporter cannot be used in TUI mode. "
                "Use UnifiedIOProgressReporter or create_progress_reporter() factory instead."
            )
        self._theme = theme or DEFAULT_THEME
        self._status = None
        self._console = None

    def start(self, description: str, total: Optional[int] = None) -> None:
        """
        Start progress reporting with Rich status display.

        Args:
            description: Description of the operation
            total: Total number of items (None for indeterminate progress)
        """
        try:
            from rich.console import Console

            # Use stderr to avoid interfering with user input
            self._console = Console(stderr=True)
            self._status = self._console.status(f"[{self._theme.primary}]{description}[/{self._theme.primary}]")
            self._status.start()

        except ImportError:
            logger.warning("Rich library not available, progress display disabled")
            self._status = None

    def update(self, current: Optional[int] = None, description: Optional[str] = None) -> None:
        """
        Update progress.

        Args:
            current: Current progress count (ignored for status display)
            description: Updated description (None to keep existing)
        """
        if self._status and description is not None:
            self._status.update(f"[{self._theme.primary}]{description}[/{self._theme.primary}]")

    def complete(self, message: str = "Complete") -> None:
        """
        Mark progress as complete and clean up display.

        Args:
            message: Completion message
        """
        if self._status:
            self._status.stop()
            self._status = None
            # Print completion message that stays visible
            if self._console:
                self._console.print(f"[{self._theme.success}]{message}[/{self._theme.success}]")

    def error(self, message: str) -> None:
        """
        Report an error and clean up display.

        Args:
            message: Error message
        """
        if self._status:
            self._status.stop()
            self._status = None
            # Print error message that stays visible
            if self._console:
                self._console.print(f"[{self._theme.error}]Error: {message}[/{self._theme.error}]")


class LiveProgressReporter:
    """
    Progress reporter using Rich Live display.

    Live display creates a dedicated area that updates in-place without
    scrolling or interfering with user input prompts.

    Implements ProgressReporterProtocol.

    WARNING: CLI MODE ONLY. This reporter outputs directly to the console
    and will bypass Textual's output routing in TUI mode. For TUI-compatible
    progress reporting, use UnifiedIOProgressReporter instead, or use the
    create_progress_reporter() factory function which automatically selects
    the correct reporter.
    """

    def __init__(self, theme: Optional[ThemeProtocol] = None):
        """Initialize Live progress reporter.

        Args:
            theme: Optional theme for color styling. Uses DEFAULT_THEME if not provided.

        Raises:
            RuntimeError: If called in TUI mode (must use UnifiedIOProgressReporter)

        Note:
            For TUI mode, use UnifiedIOProgressReporter instead which routes
            through the IO abstraction.
        """
        if OutputModeContext.is_tui_mode():
            raise RuntimeError(
                "LiveProgressReporter cannot be used in TUI mode. "
                "Use UnifiedIOProgressReporter or create_progress_reporter() factory instead."
            )
        self._theme = theme or DEFAULT_THEME
        self._live = None
        self._console = None

    def start(self, description: str, total: Optional[int] = None) -> None:
        """
        Start Live progress display.

        Args:
            description: Operation description
            total: Total items (unused for spinner display)
        """
        try:
            from rich.console import Console
            from rich.live import Live
            from rich.spinner import Spinner
            from rich.text import Text

            self._console = Console(stderr=True)
            renderable = Spinner("dots", text=Text(description, style=self._theme.primary))

            # Live display updates in-place, doesn't scroll
            # transient=True makes it disappear when stopped
            self._live = Live(
                renderable,
                console=self._console,
                transient=True,
                refresh_per_second=10
            )
            self._live.start()

        except ImportError:
            logger.warning("Rich library not available, progress display disabled")
            self._live = None
        except Exception as e:
            logger.error(f"Error starting Live progress: {e}")
            self._live = None

    def update(self, current: Optional[int] = None, description: Optional[str] = None) -> None:
        """
        Update progress display.

        Args:
            current: Current count (unused)
            description: Updated description
        """
        if self._live and description:
            from rich.spinner import Spinner
            from rich.text import Text

            renderable = Spinner("dots", text=Text(description, style=self._theme.primary))
            self._live.update(renderable)

    def complete(self, message: str = "Complete") -> None:
        """
        Show completion and hide.

        Args:
            message: Completion message
        """
        if self._live:
            from rich.text import Text

            # Show completion briefly
            self._live.update(Text(f"[OK] {message}", style=self._theme.success))
            time.sleep(0.5)
            # Then disappear (transient=True)
            self._live.stop()
            self._live = None

    def error(self, message: str) -> None:
        """
        Show error and hide.

        Args:
            message: Error message
        """
        if self._live:
            from rich.text import Text

            # Show error longer
            self._live.update(Text(f"[ERROR] {message}", style=self._theme.error))
            time.sleep(1.0)
            # Then disappear
            self._live.stop()
            self._live = None


class LoggingProgressReporter:
    """
    Progress reporter using Python logging.

    Reports progress via logger.info() calls.
    Useful for background processes or when Rich is not available.

    Implements ProgressReporterProtocol.
    """

    def __init__(self, logger_name: Optional[str] = None):
        """
        Initialize logging progress reporter.

        Args:
            logger_name: Logger name (defaults to module logger)
        """
        self._logger = logging.getLogger(logger_name or __name__)
        self._total = None

    def start(self, description: str, total: Optional[int] = None) -> None:
        """
        Start progress reporting via logging.

        Args:
            description: Description of the operation
            total: Total number of items (None for indeterminate progress)
        """
        self._total = total
        if total is not None:
            self._logger.info(f"{description} (0/{total})")
        else:
            self._logger.info(f"{description}")

    def update(self, current: Optional[int] = None, description: Optional[str] = None) -> None:
        """
        Update progress via logging.

        Args:
            current: Current progress count (None to keep existing)
            description: Updated description (None to keep existing)
        """
        if description:
            if current is not None and self._total is not None:
                self._logger.info(f"{description} ({current}/{self._total})")
            else:
                self._logger.info(description)

    def complete(self, message: str = "Complete") -> None:
        """
        Mark progress as complete.

        Args:
            message: Completion message
        """
        self._logger.info(message)

    def error(self, message: str) -> None:
        """
        Report an error.

        Args:
            message: Error message
        """
        self._logger.error(message)


class CallbackProgressReporter:
    """
    Progress reporter using callback functions.

    Calls a user-provided callback function with progress updates.
    Useful for integrating with custom UI frameworks.

    Implements ProgressReporterProtocol.
    """

    def __init__(self, callback: Callable[[str], None]):
        """
        Initialize callback progress reporter.

        Args:
            callback: Function to call with progress messages
        """
        self._callback = callback
        self._total = None

    def start(self, description: str, total: Optional[int] = None) -> None:
        """
        Start progress reporting via callback.

        Args:
            description: Description of the operation
            total: Total number of items (None for indeterminate progress)
        """
        self._total = total
        if total is not None:
            self._callback(f"{description} (0/{total})")
        else:
            self._callback(description)

    def update(self, current: Optional[int] = None, description: Optional[str] = None) -> None:
        """
        Update progress via callback.

        Args:
            current: Current progress count (None to keep existing)
            description: Updated description (None to keep existing)
        """
        if description:
            if current is not None and self._total is not None:
                self._callback(f"{description} ({current}/{self._total})")
            else:
                self._callback(description)

    def complete(self, message: str = "Complete") -> None:
        """
        Mark progress as complete.

        Args:
            message: Completion message
        """
        self._callback(message)

    def error(self, message: str) -> None:
        """
        Report an error.

        Args:
            message: Error message
        """
        self._callback(f"Error: {message}")


class NullProgressReporter:
    """
    No-op progress reporter.

    Does nothing. Useful for silent operation or testing.

    Implements ProgressReporterProtocol.
    """

    def start(self, description: str, total: Optional[int] = None) -> None:
        """No-op start."""
        pass

    def update(self, current: Optional[int] = None, description: Optional[str] = None) -> None:
        """No-op update."""
        pass

    def complete(self, message: str = "Complete") -> None:
        """No-op complete."""
        pass

    def error(self, message: str) -> None:
        """No-op error."""
        pass


class UnifiedIOProgressReporter:
    """
    Progress reporter that routes through CLIIOProtocol.

    This ensures progress output goes through the IO abstraction and
    displays correctly in Textual/TUI mode. Uses simple text messages
    rather than animated spinners.

    Implements ProgressReporterProtocol.
    """

    def __init__(self, io: "CLIIOProtocol", theme: Optional[ThemeProtocol] = None):
        """
        Initialize progress reporter with IO interface.

        Args:
            io: CLIIOProtocol instance for output
            theme: Optional theme for color styling. Uses DEFAULT_THEME if not provided.
        """
        self._io = io
        self._theme = theme or DEFAULT_THEME
        self._description: Optional[str] = None

    def start(self, description: str, total: Optional[int] = None) -> None:
        """
        Start progress reporting via IO.

        Args:
            description: Description of the operation
            total: Total number of items (None for indeterminate progress)
        """
        self._description = description
        if total is not None:
            self._io.secho(f"{description} (0/{total})", fg=self._theme.primary)
        else:
            self._io.secho(f"{description}...", fg=self._theme.primary)

    def update(self, current: Optional[int] = None, description: Optional[str] = None) -> None:
        """
        Update progress via IO.

        Args:
            current: Current progress count (ignored - updates are minimal to avoid spam)
            description: Updated description
        """
        if description:
            self._description = description
            self._io.secho(f"  {description}", fg=self._theme.primary)

    def complete(self, message: str = "Complete") -> None:
        """
        Mark progress as complete via IO.

        Args:
            message: Completion message
        """
        self._io.secho(f"{message}", fg=self._theme.success)

    def error(self, message: str) -> None:
        """
        Report an error via IO.

        Args:
            message: Error message
        """
        self._io.secho(f"Error: {message}", fg=self._theme.error)


def create_progress_reporter(
    io: Optional["CLIIOProtocol"] = None,
    use_live: bool = False,
    use_spinner: bool = True,
    theme: Optional[ThemeProtocol] = None,
):
    """
    Factory function to create the appropriate progress reporter based on mode.

    This function selects the correct progress reporter implementation:
    - If io is None: Returns NullProgressReporter (silent)
    - If io is in TUI mode: Returns UnifiedIOProgressReporter (routes through IO)
    - If io is in CLI mode with use_live=True: Returns LiveProgressReporter
    - If io is in CLI mode with use_spinner=True: Returns RichProgressReporter
    - Otherwise: Returns UnifiedIOProgressReporter

    Args:
        io: Optional CLIIOProtocol instance
        use_live: Use Rich Live display (CLI mode only)
        use_spinner: Use Rich Status spinner (CLI mode only)
        theme: Optional theme for color styling. Uses DEFAULT_THEME if not provided.

    Returns:
        Progress reporter appropriate for the current mode

    Example:
        # In TUI mode, always uses IO-based reporter
        reporter = create_progress_reporter(io)

        # In CLI mode with animated spinner
        reporter = create_progress_reporter(io, use_spinner=True)

        # In CLI mode with live display
        reporter = create_progress_reporter(io, use_live=True)
    """
    if io is None:
        return NullProgressReporter()

    # Import here to avoid circular imports
    from ..cli.mode_utils import is_tui_mode

    if is_tui_mode(io):
        # TUI mode: always use IO-based reporter
        return UnifiedIOProgressReporter(io, theme=theme)

    # CLI mode: select based on options
    if use_live:
        return LiveProgressReporter(theme=theme)
    if use_spinner:
        return RichProgressReporter(theme=theme)

    # Default: use IO-based reporter (works in both modes)
    return UnifiedIOProgressReporter(io, theme=theme)
