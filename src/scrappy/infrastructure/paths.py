"""
Path provider implementations.

Provides concrete implementations of PathProviderProtocol for production
and testing environments.

Uses platformdirs for cross-platform XDG-compliant paths:
- Linux: ~/.local/share/scrappy, ~/.config/scrappy, ~/.cache/scrappy
- macOS: ~/Library/Application Support/scrappy
- Windows: C:/Users/<user>/AppData/Local/scrappy
"""

import logging
import shutil
from pathlib import Path

from platformdirs import user_data_dir, user_config_dir, user_cache_dir

logger = logging.getLogger(__name__)

# App name for platformdirs
APP_NAME = "scrappy"

# Legacy path for migration
LEGACY_USER_DIR = Path.home() / ".scrappy"


class ScrappyPathProvider:
    """
    Production path provider using .scrappy/ directory.

    Stores project-specific files in .scrappy/ within the project root.
    Stores user-level files in platform-appropriate locations via platformdirs.
    """

    def __init__(self, project_root: Path):
        """
        Initialize path provider.

        Args:
            project_root: Root directory of the project
        """
        self._project_root = project_root
        self._data_dir = project_root / ".scrappy"
        # Use platformdirs for cross-platform user directories
        self._user_dir = Path(user_data_dir(APP_NAME))
        self._user_config_dir = Path(user_config_dir(APP_NAME))
        self._user_cache_dir = Path(user_cache_dir(APP_NAME))

    def data_dir(self) -> Path:
        """Get the .scrappy/ directory (project-level)."""
        return self._data_dir

    def user_data_dir(self) -> Path:
        """Get user data directory (platform-appropriate)."""
        return self._user_dir

    def user_config_dir(self) -> Path:
        """Get user config directory (platform-appropriate)."""
        return self._user_config_dir

    def user_cache_dir(self) -> Path:
        """Get user cache directory (platform-appropriate)."""
        return self._user_cache_dir

    def session_file(self) -> Path:
        """Get path to session.json."""
        return self._data_dir / "session.json"

    def rate_limits_file(self) -> Path:
        """Get path to rate_limits.json (user-level, shared across projects)."""
        return self._user_dir / "rate_limits.json"

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

    def ensure_user_dir(self) -> None:
        """Create user directories and migrate from legacy paths if needed."""
        self._user_dir.mkdir(parents=True, exist_ok=True)
        self._user_config_dir.mkdir(parents=True, exist_ok=True)
        self._user_cache_dir.mkdir(parents=True, exist_ok=True)
        self._migrate_from_legacy()
        self._migrate_rate_limits()

    def _migrate_from_legacy(self) -> None:
        """Migrate data from legacy ~/.scrappy to platform-appropriate location."""
        if not LEGACY_USER_DIR.exists():
            return

        # Already migrated if new location has data
        if (self._user_dir / "rate_limits.json").exists():
            return

        # Migrate all files from legacy location
        for item in LEGACY_USER_DIR.iterdir():
            if item.is_file():
                dest = self._user_dir / item.name
                if not dest.exists():
                    shutil.copy(item, dest)
                    logger.info("Migrated %s to %s", item, dest)

        logger.info(
            "Migration complete. Legacy directory %s can be removed.",
            LEGACY_USER_DIR
        )

    def _migrate_rate_limits(self) -> None:
        """Migrate rate_limits.json from project-level to user-level."""
        project_file = self._data_dir / "rate_limits.json"
        user_file = self._user_dir / "rate_limits.json"

        if project_file.exists() and not user_file.exists():
            shutil.copy(project_file, user_file)
            project_file.unlink()
            logger.info(
                "Migrated rate_limits.json from %s to %s",
                project_file,
                user_file
            )


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
        self._user_dir = temp_dir / ".scrappy_user"  # Separate for test isolation
        self._user_config_dir = temp_dir / ".scrappy_config"
        self._user_cache_dir = temp_dir / ".scrappy_cache"

    def data_dir(self) -> Path:
        """Get the temporary data directory."""
        return self._data_dir

    def user_data_dir(self) -> Path:
        """Get the temporary user data directory."""
        return self._user_dir

    def user_config_dir(self) -> Path:
        """Get the temporary user config directory."""
        return self._user_config_dir

    def user_cache_dir(self) -> Path:
        """Get the temporary user cache directory."""
        return self._user_cache_dir

    def session_file(self) -> Path:
        """Get path to test session file."""
        return self._data_dir / "session.json"

    def rate_limits_file(self) -> Path:
        """Get path to test rate limits file (user-level)."""
        return self._user_dir / "rate_limits.json"

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

    def ensure_user_dir(self) -> None:
        """Create temporary user directories if they don't exist."""
        self._user_dir.mkdir(parents=True, exist_ok=True)
        self._user_config_dir.mkdir(parents=True, exist_ok=True)
        self._user_cache_dir.mkdir(parents=True, exist_ok=True)
