"""
RateLimitNotifier - Delivers rate limit notifications to users.

Implements UserNotifierProtocol following SOLID:
- Single Responsibility: Only handles user notifications
- Open/Closed: Notification format configurable without code changes
- Dependency Inversion: Depends on OutputInterfaceProtocol
"""
from __future__ import annotations
from datetime import datetime
from typing import Dict, List, Protocol


class OutputProtocol(Protocol):
    """Minimal output interface for notifications."""

    def print(self, message: str) -> None:
        """Print informational message."""
        ...

    def print_warning(self, message: str) -> None:
        """Print warning message."""
        ...

    def print_error(self, message: str) -> None:
        """Print error message."""
        ...


class RateLimitNotifier:
    """
    Delivers rate limit notifications to users.

    Features:
    - Cooldown to prevent notification spam
    - Quiet mode for non-interactive use
    - Configurable message format
    """

    def __init__(
        self,
        output: OutputProtocol,
        *,
        quiet_mode: bool = False,
        notification_cooldown: int = 60,
    ):
        """
        Initialize notifier.

        Args:
            output: Output interface for displaying messages
            quiet_mode: If True, suppress non-critical notifications
            notification_cooldown: Seconds between repeat warnings for same provider
        """
        self._output = output
        self._quiet_mode = quiet_mode
        self._cooldown = notification_cooldown
        self._last_notification: Dict[str, datetime] = {}

    def notify_approaching_limit(
        self,
        provider: str,
        remaining_percent: float,
        remaining_requests: int,
    ) -> None:
        """
        Warn user that limits are approaching.

        Args:
            provider: Provider name
            remaining_percent: Percentage of quota remaining (0.0-1.0)
            remaining_requests: Absolute requests remaining
        """
        if self._quiet_mode:
            return

        if not self._should_notify(f"approaching_{provider}"):
            return

        percent_display = int(remaining_percent * 100)
        message = (
            f"Rate limit warning: {provider} has {percent_display}% quota remaining "
            f"({remaining_requests} requests)"
        )
        self._output.print_warning(message)

    def notify_fallback(
        self,
        from_provider: str,
        to_provider: str,
        reason: str,
    ) -> None:
        """
        Inform user of automatic provider switch.

        Args:
            from_provider: Original provider
            to_provider: Fallback provider
            reason: Why fallback occurred
        """
        if self._quiet_mode:
            return

        message = f"Switching from {from_provider} to {to_provider}: {reason}"
        self._output.print(message)

    def notify_all_exhausted(
        self,
        attempted_providers: List[str],
    ) -> None:
        """
        Alert user that all providers are exhausted.

        Args:
            attempted_providers: List of providers that were tried
        """
        # Always show this - it's critical
        providers_str = ", ".join(attempted_providers) if attempted_providers else "none"
        message = f"All providers exhausted (tried: {providers_str})"
        self._output.print_error(message)

    def _should_notify(self, key: str) -> bool:
        """
        Check if notification should be shown (respects cooldown).

        Args:
            key: Unique key for this notification type

        Returns:
            True if notification should be shown
        """
        now = datetime.now()
        last = self._last_notification.get(key)

        if last is None or (now - last).total_seconds() >= self._cooldown:
            self._last_notification[key] = now
            return True

        return False

    def reset_cooldowns(self) -> None:
        """Reset all notification cooldowns."""
        self._last_notification.clear()


class NullNotifier:
    """No-op notifier for testing or when notifications are disabled."""

    def notify_approaching_limit(
        self,
        provider: str,
        remaining_percent: float,
        remaining_requests: int,
    ) -> None:
        """No-op."""
        pass

    def notify_fallback(
        self,
        from_provider: str,
        to_provider: str,
        reason: str,
    ) -> None:
        """No-op."""
        pass

    def notify_all_exhausted(
        self,
        attempted_providers: List[str],
    ) -> None:
        """No-op."""
        pass
