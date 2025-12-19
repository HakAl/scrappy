"""
Denial handler implementations.

Provides different strategies for handling user denials of actions:
- InteractiveDenialHandler: Asks user if they want to stop entirely
- AutoStopDenialHandler: Stops after N denials
- ContinueDenialHandler: Always continues (default behavior)
"""

from .protocols import AgentUIProtocol
from .types import DenialHandlerResult


class InteractiveDenialHandler:
    """
    Interactive denial handler that asks user if they want to stop.

    Implements DenialHandlerProtocol.

    When a user denies an action, this handler prompts them to decide
    whether to stop the entire task or continue with a different approach.
    """

    def __init__(self, ui: AgentUIProtocol):
        """
        Initialize with UI for user interaction.

        Args:
            ui: AgentUIProtocol for prompting user
        """
        self._ui = ui

    def handle_denial(
        self,
        action: str,
        denial_count: int,
    ) -> DenialHandlerResult:
        """
        Handle denial by asking user if they want to stop.

        Args:
            action: The action that was denied
            denial_count: Number of denials so far

        Returns:
            DenialHandlerResult with should_stop flag and message
        """
        stop_entirely = self._ui.prompt_confirm(
            f"You denied the '{action}' action. Stop the task entirely?",
            default=False
        )

        if stop_entirely:
            return DenialHandlerResult(
                should_stop=True,
                message="Task stopped by user after denying action.",
            )
        else:
            return DenialHandlerResult(
                should_stop=False,
                message=(
                    f"User denied the {action} action but wants to continue. "
                    "Please try a different approach."
                ),
            )


class AutoStopDenialHandler:
    """
    Denial handler that auto-stops after N denials.

    Useful for automated/testing scenarios where you want to
    prevent infinite loops of denied actions.
    """

    def __init__(self, max_denials: int = 3):
        """
        Initialize with maximum denial count.

        Args:
            max_denials: Maximum denials before auto-stopping
        """
        self._max_denials = max_denials

    def handle_denial(
        self,
        action: str,
        denial_count: int,
    ) -> DenialHandlerResult:
        """
        Handle denial by auto-stopping after max denials.

        Args:
            action: The action that was denied
            denial_count: Number of denials so far

        Returns:
            DenialHandlerResult with should_stop flag and message
        """
        if denial_count >= self._max_denials:
            return DenialHandlerResult(
                should_stop=True,
                message=f"Task stopped after {denial_count} denied actions.",
            )
        return DenialHandlerResult(
            should_stop=False,
            message=(
                f"User denied the {action} action. "
                f"({denial_count}/{self._max_denials} denials) "
                "Please try a different approach."
            ),
        )


class ContinueDenialHandler:
    """
    Denial handler that always continues (default behavior).

    This handler never stops - it always returns should_stop=False.
    Use this to maintain backwards compatibility with existing behavior.
    """

    def handle_denial(
        self,
        action: str,
        denial_count: int,
    ) -> DenialHandlerResult:
        """
        Handle denial by always continuing.

        Args:
            action: The action that was denied
            denial_count: Number of denials so far (ignored)

        Returns:
            DenialHandlerResult with should_stop=False
        """
        return DenialHandlerResult(
            should_stop=False,
            message=(
                f"User denied the {action} action. "
                "Please try a different approach or explain why this action is necessary."
            ),
        )
