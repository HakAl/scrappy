"""
Textual-based progress reporter implementation.

Provides progress reporting for Textual TUI applications by updating
the status bar widget directly.
"""

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.cli.textual_app import ScrappyApp


class TextualProgressReporter:
    """Progress reporter for Textual apps.

    Implements ProgressReporterProtocol by updating the status bar widget
    directly instead of using Rich's Live() context manager.

    The status bar shows progress updates with appropriate styling:
    - In-progress: cyan color
    - Complete: green color
    - Error: red color
    """

    def __init__(self, app: "ScrappyApp"):
        """Initialize the progress reporter.

        Args:
            app: The ScrappyApp instance to update
        """
        self._app = app
        self._current_description: Optional[str] = None
        self._total: Optional[int] = None
        self._current: Optional[int] = None

    def start(self, description: str, total: Optional[int] = None) -> None:
        """Start progress reporting.

        Args:
            description: Description of the operation
            total: Total number of items (None for indeterminate progress)
        """
        self._current_description = description
        self._total = total
        self._current = 0

        if total is not None:
            status_text = f"[cyan]{description} (0/{total})[/cyan]"
        else:
            status_text = f"[cyan]{description}...[/cyan]"

        self._update_status(status_text)

    def update(self, current: Optional[int] = None, description: Optional[str] = None) -> None:
        """Update progress.

        Args:
            current: Current progress count (None to keep existing)
            description: Updated description (None to keep existing)
        """
        if current is not None:
            self._current = current

        if description is not None:
            self._current_description = description

        # Build status text
        if self._total is not None and self._current is not None:
            status_text = f"[cyan]{self._current_description} ({self._current}/{self._total})[/cyan]"
        elif self._current_description:
            status_text = f"[cyan]{self._current_description}...[/cyan]"
        else:
            status_text = "[cyan]Processing...[/cyan]"

        self._update_status(status_text)

    def complete(self, message: str = "Complete") -> None:
        """Mark progress as complete.

        Args:
            message: Completion message
        """
        status_text = f"[green]{message}[/green]"
        self._update_status(status_text)

        # Reset state
        self._current_description = None
        self._total = None
        self._current = None

    def error(self, message: str) -> None:
        """Report an error.

        Args:
            message: Error message
        """
        status_text = f"[red]Error: {message}[/red]"
        self._update_status(status_text)

        # Reset state
        self._current_description = None
        self._total = None
        self._current = None

    def _update_status(self, content: str) -> None:
        """Update the status bar widget.

        Args:
            content: The status message with Rich markup
        """
        from textual.widgets import Static

        try:
            status_widget = self._app.query_one("#status", Static)
            status_widget.update(content)
        except Exception:
            # If we can't update the status (e.g., app not fully initialized),
            # fail silently to avoid breaking the operation
            pass
