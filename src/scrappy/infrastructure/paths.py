"""
Path provider implementations.

Provides concrete implementations of PathProviderProtocol for production
and testing environments.
"""

import logging
from pathlib import Path
from typing import Optional
from .protocols import PathProviderProtocol

logger = logging.getLogger(__name__)


class ScrappyPathProvider:
    """
    Production path provider using .scrappy/ directory.

    Stores all Scrappy data files in a centralized .scrappy/ directory
    within the project root to avoid clutter.
    """

    def __init__(self, project_root: Path):
        """
        Initialize path provider.

        Args:
            project_root: Root directory of the project
        """
        self._project_root = project_root
        self._data_dir = project_root / ".scrappy"

    def data_dir(self) -> Path:
        """Get the .scrappy/ directory."""
        return self._data_dir

    def session_file(self) -> Path:
        """Get path to session.json."""
        return self._data_dir / "session.json"

    def rate_limits_file(self) -> Path:
        """Get path to rate_limits.json."""
        return self._data_dir / "rate_limits.json"

    def audit_file(self) -> Path:
        """Get path to audit.json."""
        return self._data_dir / "audit.json"

    def response_cache_file(self) -> Path:
        """Get path to response_cache.json."""
        return self._data_dir / "response_cache.json"

    def context_file(self) -> Path:
        """Get path to context.json."""
        return self._data_dir / "context.json"

    def todo_file(self) -> Path:
        """Get path to .todo.md (agent task list)."""
        return self._data_dir / ".todo.md"

    def debug_log_file(self) -> Path:
        """Get path to debug.log file."""
        return self._data_dir / "debug.log"

    def ensure_data_dir(self) -> None:
        """Create .scrappy/ directory if it doesn't exist."""
        self._data_dir.mkdir(parents=True, exist_ok=True)


class TempPathProvider:
    """
    Test path provider using temporary directory.

    Uses a temporary directory for all files, ensuring test isolation.
    """

    def __init__(self, temp_dir: Path):
        """
        Initialize test path provider.

        Args:
            temp_dir: Temporary directory (e.g., from pytest tmp_path fixture)
        """
        self._temp_dir = temp_dir
        self._data_dir = temp_dir / ".scrappy"

    def data_dir(self) -> Path:
        """Get the temporary data directory."""
        return self._data_dir

    def session_file(self) -> Path:
        """Get path to test session file."""
        return self._data_dir / "session.json"

    def rate_limits_file(self) -> Path:
        """Get path to test rate limits file."""
        return self._data_dir / "rate_limits.json"

    def audit_file(self) -> Path:
        """Get path to test audit file."""
        return self._data_dir / "audit.json"

    def response_cache_file(self) -> Path:
        """Get path to test response cache file."""
        return self._data_dir / "response_cache.json"

    def context_file(self) -> Path:
        """Get path to test context file."""
        return self._data_dir / "context.json"

    def todo_file(self) -> Path:
        """Get path to test todo file."""
        return self._data_dir / ".todo.md"

    def debug_log_file(self) -> Path:
        """Get path to test debug.log file."""
        return self._data_dir / "debug.log"

    def ensure_data_dir(self) -> None:
        """Create temporary data directory if it doesn't exist."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
