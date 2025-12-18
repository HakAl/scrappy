"""Task management protocols for agent progress tracking."""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol


class TaskStatus(Enum):
    """Status of a task in the task list."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class TaskPriority(Enum):
    """Priority level for tasks."""

    HIGH = "HIGH"
    MEDIUM = "MED"
    LOW = "LOW"


@dataclass
class Task:
    """A single task in the agent's task list."""

    description: str
    status: TaskStatus
    priority: TaskPriority | None = None

    def __post_init__(self) -> None:
        """Validate task on creation."""
        if not self.description or not self.description.strip():
            raise ValueError("Task description cannot be empty")


class TaskStorageProtocol(Protocol):
    """Contract for task persistence.

    Implementations handle reading/writing tasks to storage.
    Default implementation uses markdown files, but this protocol
    enables testing with in-memory storage.
    """

    def read_tasks(self) -> list[Task]:
        """Load all tasks from storage.

        Returns:
            List of Task objects, empty list if no tasks exist.
        """
        ...

    def write_tasks(self, tasks: list[Task]) -> None:
        """Persist all tasks to storage.

        Args:
            tasks: List of tasks to save.
        """
        ...

    def exists(self) -> bool:
        """Check if task storage exists.

        Returns:
            True if storage has been created (file exists, etc.)
        """
        ...

    def clear(self) -> None:
        """Remove all tasks and delete storage."""
        ...


class InMemoryTaskStorage:
    """In-memory task storage for testing.

    Implements TaskStorageProtocol without file I/O.
    """

    def __init__(self, initial: list[Task] | None = None) -> None:
        """Initialize with optional initial tasks.

        Args:
            initial: Optional list of tasks to start with.
        """
        self._tasks: list[Task] = list(initial) if initial else []
        self._exists = len(self._tasks) > 0

    def read_tasks(self) -> list[Task]:
        """Return copy of tasks."""
        return list(self._tasks)

    def write_tasks(self, tasks: list[Task]) -> None:
        """Store copy of tasks."""
        self._tasks = list(tasks)
        self._exists = True

    def exists(self) -> bool:
        """Check if storage has been written to."""
        return self._exists

    def clear(self) -> None:
        """Clear all tasks."""
        self._tasks = []
        self._exists = False
