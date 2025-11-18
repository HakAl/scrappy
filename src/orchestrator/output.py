"""
Output abstraction for the orchestrator.

Provides a protocol and implementations for output operations,
enabling testability by allowing injection of different output handlers.
"""

from typing import Protocol, List, Tuple


class OutputInterface(Protocol):
    """Protocol for output operations."""

    def info(self, message: str) -> None:
        """Output an informational message."""
        ...

    def warn(self, message: str) -> None:
        """Output a warning message."""
        ...

    def error(self, message: str) -> None:
        """Output an error message."""
        ...

    def success(self, message: str) -> None:
        """Output a success message."""
        ...


class ConsoleOutput:
    """Standard console output implementation."""

    def info(self, message: str) -> None:
        """Print informational message to stdout."""
        print(message)

    def warn(self, message: str) -> None:
        """Print warning message with [WARN] prefix."""
        print(f"[WARN] {message}")

    def error(self, message: str) -> None:
        """Print error message with [ERROR] prefix."""
        print(f"[ERROR] {message}")

    def success(self, message: str) -> None:
        """Print success message with [OK] prefix."""
        print(f"[OK] {message}")


class NullOutput:
    """Silent output implementation - captures nothing, outputs nothing.

    Useful for running operations silently or in quiet mode.
    """

    def info(self, message: str) -> None:
        """Discard informational message."""
        pass

    def warn(self, message: str) -> None:
        """Discard warning message."""
        pass

    def error(self, message: str) -> None:
        """Discard error message."""
        pass

    def success(self, message: str) -> None:
        """Discard success message."""
        pass


class CapturingOutput:
    """Capturing output implementation for testing.

    Captures all messages for later inspection without writing to stdout.
    Provides helper methods for test assertions.

    Usage:
        output = CapturingOutput()

        # Run code that uses output
        my_function(output)

        # Assert on captured messages
        assert output.has_errors() is False
        assert 'success' in output.get_by_level('info')[0]
    """

    def __init__(self) -> None:
        """Initialize with empty message list."""
        self.messages: List[Tuple[str, str]] = []

    def info(self, message: str) -> None:
        """Capture informational message."""
        self.messages.append(('info', message))

    def warn(self, message: str) -> None:
        """Capture warning message."""
        self.messages.append(('warn', message))

    def error(self, message: str) -> None:
        """Capture error message."""
        self.messages.append(('error', message))

    def success(self, message: str) -> None:
        """Capture success message."""
        self.messages.append(('success', message))

    def get_by_level(self, level: str) -> List[str]:
        """Get all messages of a specific level.

        Args:
            level: One of 'info', 'warn', 'error', 'success'

        Returns:
            List of message strings for that level
        """
        return [msg for lvl, msg in self.messages if lvl == level]

    def clear(self) -> None:
        """Clear all captured messages."""
        self.messages = []

    def has_errors(self) -> bool:
        """Check if any error messages were captured."""
        return any(lvl == 'error' for lvl, _ in self.messages)

    def has_warnings(self) -> bool:
        """Check if any warning messages were captured."""
        return any(lvl == 'warn' for lvl, _ in self.messages)
