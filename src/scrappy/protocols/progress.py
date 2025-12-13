"""
Progress reporter protocols.

Defines the contracts for progress reporting and status bar updates.
These protocols enable infrastructure components to report progress
without depending on concrete CLI implementations.
"""

from typing import Protocol, Optional, runtime_checkable


@runtime_checkable
class ProgressReporterProtocol(Protocol):
    """Protocol for reporting progress of long-running operations.

    Implementations can use various mechanisms (Rich, logging, UI widgets, etc.)
    to display progress to users. This protocol defines the standard interface
    that all progress reporters must implement.

    Example:
        reporter = get_progress_reporter()
        reporter.start("Processing items", total=100)
        for i in range(100):
            reporter.update(current=i+1)
        reporter.complete("Processing finished")
    """

    def start(self, description: str, total: Optional[int] = None) -> None:
        """Start progress reporting.

        Args:
            description: Description of the operation
            total: Total number of items (None for indeterminate progress)
        """
        ...

    def update(self, current: Optional[int] = None, description: Optional[str] = None) -> None:
        """Update progress.

        Args:
            current: Current progress count (None to keep existing)
            description: Updated description (None to keep existing)
        """
        ...

    def complete(self, message: str = "Complete") -> None:
        """Mark progress as complete.

        Args:
            message: Completion message
        """
        ...

    def error(self, message: str) -> None:
        """Report an error.

        Args:
            message: Error message
        """
        ...


@runtime_checkable
class StatusBarUpdaterProtocol(Protocol):
    """Protocol for updating status bar displays.

    This protocol defines the minimal interface needed to update a status bar
    widget. It abstracts the concrete implementation (e.g., Textual widgets)
    to enable infrastructure components to update status without depending
    on the CLI layer.

    Example:
        class MyApp:
            def update_status(self, content: str) -> None:
                status_widget = self.query_one("#status")
                status_widget.update(content)

        # Infrastructure can now depend on protocol, not concrete app
        reporter = TextualProgressReporter(status_updater=my_app)
    """

    def update_status(self, content: str) -> None:
        """Update the status bar content.

        Args:
            content: The status message, typically with Rich markup
        """
        ...
