"""
Progress reporter implementations.

Provides concrete implementations of ProgressReporterProtocol for different
progress display strategies (Rich, logging, callbacks, silent).
"""

import logging
import time
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class RichProgressReporter:
    """
    Progress reporter using Rich library with status spinner.

    Displays progress using Rich's Status component which is simpler and
    less intrusive than Progress bars. Automatically cleans up on completion.

    Implements ProgressReporterProtocol.
    """

    def __init__(self):
        """Initialize Rich progress reporter."""
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
            import sys

            # Use stderr to avoid interfering with user input
            self._console = Console(stderr=True)
            self._status = self._console.status(f"[cyan]{description}[/cyan]")
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
            self._status.update(f"[cyan]{description}[/cyan]")

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
                self._console.print(f"[green]{message}[/green]")

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
                self._console.print(f"[red]Error: {message}[/red]")


class LiveProgressReporter:
    """
    Progress reporter using Rich Live display.

    Live display creates a dedicated area that updates in-place without
    scrolling or interfering with user input prompts.

    Implements ProgressReporterProtocol.
    """

    def __init__(self):
        """Initialize Live progress reporter."""
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
            renderable = Spinner("dots", text=Text(description, style="cyan"))

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

            renderable = Spinner("dots", text=Text(description, style="cyan"))
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
            self._live.update(Text(f"[OK] {message}", style="green"))
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
            self._live.update(Text(f"[ERROR] {message}", style="red"))
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
