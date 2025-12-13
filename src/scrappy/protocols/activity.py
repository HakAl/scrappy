"""Activity indicator protocols for UI feedback."""

from enum import Enum
from typing import Protocol, runtime_checkable


class ActivityState(Enum):
    """Activity states for UI indicators."""
    IDLE = "idle"
    THINKING = "thinking"
    SYNCING = "syncing"
    TOOL_EXECUTION = "tool_execution"


@runtime_checkable
class ActivityIndicatorProtocol(Protocol):
    """Protocol for activity indicator widgets.

    Defines the contract for UI components that display current activity state
    with elapsed time tracking. Used to show user feedback during long-running
    operations like Q/A processing and codebase re-indexing.

    Implementations should:
    - Show/hide indicator based on activity state
    - Track and display elapsed time during operations
    - Prevent flicker with delayed show threshold
    - Update display without blocking main thread

    Example:
        def show_activity(indicator: ActivityIndicatorProtocol, state: ActivityState):
            indicator.show(state, "Processing query...")
            # ... long operation ...
            indicator.update_elapsed(1500)  # 1.5 seconds
            indicator.hide()
    """

    def show(self, state: ActivityState, message: str = "") -> None:
        """Show the activity indicator with state and message.

        Args:
            state: Current activity state
            message: Optional descriptive message
        """
        ...

    def update_elapsed(self, elapsed_ms: int) -> None:
        """Update elapsed time display.

        Args:
            elapsed_ms: Elapsed time in milliseconds
        """
        ...

    def hide(self) -> None:
        """Hide the activity indicator."""
        ...

    @property
    def is_visible(self) -> bool:
        """Whether indicator is currently visible.

        Returns:
            True if indicator is displayed
        """
        ...
