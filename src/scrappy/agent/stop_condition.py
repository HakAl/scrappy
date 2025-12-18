"""
Unified stop condition handling for agent loop.

Provides a single source of truth for all conditions that should
terminate the agent loop, replacing scattered cancellation checks.
"""

from enum import Enum
from typing import Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .cancellation import CancellationTokenProtocol
    from ..agent_config import AgentConfig


class StopReason(Enum):
    """Reasons why the agent loop should stop."""
    NONE = "none"
    USER_CANCELLED = "user_cancelled"
    RATE_LIMITED = "rate_limited"
    MAX_ITERATIONS = "max_iterations"
    PARSE_FAILURES = "parse_failures"
    REPEATED_DENIALS = "repeated_denials"
    NETWORK_ERROR = "network_error"
    COMPLETED = "completed"


class AgentStopCondition:
    """
    Single source of truth for agent stop conditions.

    Centralizes all the scattered cancellation/termination checks
    into one place. The agent loop calls should_stop() at the start
    of each iteration.

    Tracks:
    - User cancellation (Escape, Ctrl+C, app exit)
    - Rate limit exhaustion (all models rate limited)
    - Max iterations
    - Consecutive parse failures
    - Repeated user denials
    - Network errors
    """

    # Default thresholds
    DEFAULT_MAX_PARSE_FAILURES = 3
    DEFAULT_MAX_DENIALS = 5
    DEFAULT_MAX_NETWORK_ERRORS = 3

    def __init__(
        self,
        cancellation_token: Optional["CancellationTokenProtocol"] = None,
        max_iterations: int = 50,
        max_parse_failures: int = DEFAULT_MAX_PARSE_FAILURES,
        max_denials: int = DEFAULT_MAX_DENIALS,
        max_network_errors: int = DEFAULT_MAX_NETWORK_ERRORS,
    ):
        """
        Initialize stop condition tracker.

        Args:
            cancellation_token: Token for user-initiated cancellation
            max_iterations: Maximum loop iterations allowed
            max_parse_failures: Stop after N consecutive parse failures
            max_denials: Stop after N consecutive user denials
            max_network_errors: Stop after N consecutive network errors
        """
        self._token = cancellation_token
        self._max_iterations = max_iterations
        self._max_parse_failures = max_parse_failures
        self._max_denials = max_denials
        self._max_network_errors = max_network_errors

        # Counters
        self._current_iteration = 0
        self._consecutive_parse_failures = 0
        self._consecutive_denials = 0
        self._consecutive_network_errors = 0

        # Flags
        self._rate_limited = False
        self._completed = False
        self._stop_reason: Optional[StopReason] = None

    def should_stop(self) -> Tuple[bool, StopReason]:
        """
        Check all stop conditions.

        Returns:
            Tuple of (should_stop, reason)
        """
        # Force cancellation has highest priority - immediate exit
        if self._token and hasattr(self._token, 'is_force_cancelled') and self._token.is_force_cancelled():
            return True, StopReason.USER_CANCELLED

        # Graceful cancellation
        if self._token and self._token.is_cancelled():
            return True, StopReason.USER_CANCELLED

        # Explicit completion
        if self._completed:
            return True, StopReason.COMPLETED

        # Rate limited with no fallbacks
        if self._rate_limited:
            return True, StopReason.RATE_LIMITED

        # Max iterations
        if self._current_iteration >= self._max_iterations:
            return True, StopReason.MAX_ITERATIONS

        # Consecutive failures
        if self._consecutive_parse_failures >= self._max_parse_failures:
            return True, StopReason.PARSE_FAILURES

        if self._consecutive_denials >= self._max_denials:
            return True, StopReason.REPEATED_DENIALS

        if self._consecutive_network_errors >= self._max_network_errors:
            return True, StopReason.NETWORK_ERROR

        return False, StopReason.NONE

    def increment_iteration(self) -> None:
        """Increment iteration counter."""
        self._current_iteration += 1

    def record_parse_failure(self) -> None:
        """Record a parse failure. Consecutive failures trigger stop."""
        self._consecutive_parse_failures += 1

    def clear_parse_failures(self) -> None:
        """Clear parse failure counter after successful parse."""
        self._consecutive_parse_failures = 0

    def record_denial(self) -> None:
        """Record a user denial. Consecutive denials trigger stop."""
        self._consecutive_denials += 1

    def clear_denials(self) -> None:
        """Clear denial counter after approved action."""
        self._consecutive_denials = 0

    def record_network_error(self) -> None:
        """Record a network error. Consecutive errors trigger stop."""
        self._consecutive_network_errors += 1

    def clear_network_errors(self) -> None:
        """Clear network error counter after successful request."""
        self._consecutive_network_errors = 0

    def mark_rate_limited(self) -> None:
        """Mark that all models are rate limited."""
        self._rate_limited = True

    def mark_completed(self) -> None:
        """Mark task as completed."""
        self._completed = True

    def reset(self) -> None:
        """Reset all counters for a new task."""
        self._current_iteration = 0
        self._consecutive_parse_failures = 0
        self._consecutive_denials = 0
        self._consecutive_network_errors = 0
        self._rate_limited = False
        self._completed = False
        self._stop_reason = None

    @property
    def current_iteration(self) -> int:
        """Current iteration number."""
        return self._current_iteration

    @property
    def consecutive_denials(self) -> int:
        """Current consecutive denial count."""
        return self._consecutive_denials

    def get_stop_message(self, reason: StopReason) -> str:
        """Get human-readable stop message for a reason."""
        messages = {
            StopReason.NONE: "",
            StopReason.USER_CANCELLED: "Cancelled by user",
            StopReason.RATE_LIMITED: "All models are rate limited. Try again later.",
            StopReason.MAX_ITERATIONS: f"Max iterations ({self._max_iterations}) reached",
            StopReason.PARSE_FAILURES: f"Too many consecutive parse failures ({self._max_parse_failures})",
            StopReason.REPEATED_DENIALS: f"Too many consecutive denials ({self._max_denials})",
            StopReason.NETWORK_ERROR: f"Too many network errors ({self._max_network_errors})",
            StopReason.COMPLETED: "Task completed",
        }
        return messages.get(reason, f"Stopped: {reason.value}")
