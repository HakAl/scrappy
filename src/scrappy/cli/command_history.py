"""Command history management for TUI mode.

Provides persistent command history with up/down arrow navigation.
"""

from pathlib import Path
from typing import Optional, Protocol, List


class CommandHistoryProtocol(Protocol):
    """Protocol for command history implementations."""

    def add_to_history(self, command: str) -> None:
        """Add a command to history."""
        ...

    def get_previous(self) -> Optional[str]:
        """Get previous history entry (up arrow)."""
        ...

    def get_next(self) -> Optional[str]:
        """Get next history entry (down arrow)."""
        ...

    def reset_position(self) -> None:
        """Reset navigation position to end of history."""
        ...


class CommandHistory:
    """Persistent command history with file-based storage.

    Provides up/down arrow navigation through previous commands
    and persists history to disk.
    """

    def __init__(
        self,
        history_file: Optional[Path] = None,
        max_size: int = 1000
    ):
        """Initialize command history.

        Args:
            history_file: Path to history file. If None, uses in-memory only.
            max_size: Maximum number of commands to store.
        """
        self._max_size = max_size
        self._history_file = history_file
        self._entries: List[str] = []
        self._position: int = 0

        if history_file:
            history_file.parent.mkdir(parents=True, exist_ok=True)
            self._load_entries()

    def _load_entries(self) -> None:
        """Load history entries from file."""
        if self._history_file and self._history_file.exists():
            try:
                content = self._history_file.read_text(encoding="utf-8")
                self._entries = [line for line in content.split("\n") if line.strip()]
                # Trim to max size
                if len(self._entries) > self._max_size:
                    self._entries = self._entries[-self._max_size:]
                self._position = len(self._entries)
            except Exception:
                self._entries = []
                self._position = 0

    def _save_entries(self) -> None:
        """Save history entries to file."""
        if self._history_file:
            try:
                content = "\n".join(self._entries[-self._max_size:])
                self._history_file.write_text(content, encoding="utf-8")
            except Exception:
                pass  # Silently fail on save errors

    def add_to_history(self, command: str) -> None:
        """Add a command to history.

        Args:
            command: Command string to add
        """
        if not command or not command.strip():
            return

        command = command.strip()

        # Avoid consecutive duplicates
        if self._entries and self._entries[-1] == command:
            self._position = len(self._entries)
            return

        self._entries.append(command)

        # Trim if over max
        if len(self._entries) > self._max_size:
            self._entries = self._entries[-self._max_size:]

        self._position = len(self._entries)
        self._save_entries()

    def get_previous(self) -> Optional[str]:
        """Get previous history entry (up arrow navigation).

        Returns:
            Previous entry or None if at start
        """
        if not self._entries or self._position <= 0:
            return None
        self._position -= 1
        return self._entries[self._position]

    def get_next(self) -> Optional[str]:
        """Get next history entry (down arrow navigation).

        Returns:
            Next entry or None if at end
        """
        if self._position >= len(self._entries) - 1:
            self._position = len(self._entries)
            return None
        self._position += 1
        return self._entries[self._position]

    def reset_position(self) -> None:
        """Reset navigation position to end of history."""
        self._position = len(self._entries)


class InMemoryCommandHistory:
    """Non-persistent command history for testing."""

    def __init__(self):
        """Initialize in-memory history."""
        self._entries: List[str] = []
        self._position: int = 0

    def add_to_history(self, command: str) -> None:
        """Add a command to history."""
        if command and command.strip():
            command = command.strip()
            if not self._entries or self._entries[-1] != command:
                self._entries.append(command)
            self._position = len(self._entries)

    def get_previous(self) -> Optional[str]:
        """Get previous history entry."""
        if not self._entries or self._position <= 0:
            return None
        self._position -= 1
        return self._entries[self._position]

    def get_next(self) -> Optional[str]:
        """Get next history entry."""
        if self._position >= len(self._entries) - 1:
            self._position = len(self._entries)
            return None
        self._position += 1
        return self._entries[self._position]

    def reset_position(self) -> None:
        """Reset navigation position to end of history."""
        self._position = len(self._entries)


def get_default_history_path() -> Path:
    """Get the default path for command history file.

    Returns:
        Path to ~/.scrappy/command_history
    """
    return Path.home() / ".scrappy" / "command_history"
