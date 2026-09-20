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
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_dir, user_config_dir, user_cache_dir

logger = logging.getLogger(__name__)

# App name for platformdirs
APP_NAME = "scrappy"

# User config location (platform-appropriate via platformdirs)
USER_CONFIG_DIR = Path(user_config_dir(APP_NAME))
USER_CONFIG_FILE = USER_CONFIG_DIR / "config.json"

# Legacy path for migration
LEGACY_USER_DIR = Path.home() / ".scrappy"


@dataclass(frozen=True)
class UserPaths:
    """User-level storage locations and the legacy migration source.

    These four values are one configuration: three destinations and the
    source the migration reads from. No field carries a default, so none
    can be forgotten, and a caller cannot mix disposable destinations with
    the real legacy source by accident.
    """

    user_data_dir: Path
    user_config_dir: Path
    user_cache_dir: Path
    legacy_user_dir: Path


class ScrappyPathProvider:
    """
    Production path provider using .scrappy/ directory.

    Stores project-specific files in .scrappy/ within the project root.
    Stores user-level files in platform-appropriate locations via platformdirs.
    """

    def __init__(self, project_root: Path, *, user_paths: UserPaths):
        """
        Initialize path provider.

        Args:
            project_root: Root directory of the project
            user_paths: User-level locations and the legacy migration source.
                Required and keyword-only: omitting it is a TypeError rather
                than a silent selection of the real user profile. Production
                callers should use create_default_path_provider().
        """
        self._project_root = project_root
        self._data_dir = project_root / ".scrappy"
        self._user_paths = user_paths
        self._user_dir = user_paths.user_data_dir
        self._user_config_dir = user_paths.user_config_dir
        self._user_cache_dir = user_paths.user_cache_dir

    def project_root(self) -> Path:
        """Get the project root directory."""
        return self._project_root

    def workspace_display(self) -> str:
        """
        Get workspace path formatted for display.

        Returns path with ~ substituted for home directory.
        Uses forward slashes for consistent display across platforms.
        """
        try:
            home = Path.home()
            if self._project_root.is_relative_to(home):
                relative = self._project_root.relative_to(home)
                return "~/" + str(relative).replace("\\", "/")
        except (ValueError, RuntimeError):
            pass
        return str(self._project_root).replace("\\", "/")

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

    def command_history_file(self) -> Path:
        """Get path to command_history (user-level, under ~/.scrappy).

        Resolved from Path.home() AT CALL TIME so that relocating HOME after
        construction is followed, preserving today's production location
        (~/.scrappy/command_history). Deliberately not derived from the
        import-bound _data_dir (which is the project-level .scrappy/).
        """
        return Path.home() / ".scrappy" / "command_history"

    def model_cooldowns_file(self) -> Path:
        """Get path to model_cooldowns.json (user-level, under ~/.scrappy).

        Resolved from Path.home() AT CALL TIME, preserving today's production
        location (~/.scrappy/model_cooldowns.json).
        """
        return Path.home() / ".scrappy" / "model_cooldowns.json"

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
        """Migrate data from the legacy directory to the user data location."""
        legacy_user_dir = self._user_paths.legacy_user_dir
        if not legacy_user_dir.exists():
            return

        # Already migrated if new location has data
        if (self._user_dir / "rate_limits.json").exists():
            return

        # Migrate all files from legacy location
        for item in legacy_user_dir.iterdir():
            if item.is_file():
                dest = self._user_dir / item.name
                if not dest.exists():
                    shutil.copy(item, dest)
                    logger.info("Migrated %s to %s", item, dest)

        logger.info(
            "Migration complete. Legacy directory %s can be removed.",
            legacy_user_dir
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


def create_default_path_provider(project_root: Path) -> ScrappyPathProvider:
    """Create a provider pointed at today's production user locations.

    This is the one production composition point. The three platform
    directories are discovered HERE, when the provider is created, matching
    the timing they had inside the constructor. The legacy migration source
    CAPTURES the existing module-level LEGACY_USER_DIR, which is bound at
    import time; it is deliberately not recomputed from Path.home(), because
    that would convert an import-bound default into a call-time one.

    Args:
        project_root: Root directory of the project

    Returns:
        A provider whose user-level locations match production exactly.
    """
    return ScrappyPathProvider(
        project_root,
        user_paths=UserPaths(
            user_data_dir=Path(user_data_dir(APP_NAME)),
            user_config_dir=Path(user_config_dir(APP_NAME)),
            user_cache_dir=Path(user_cache_dir(APP_NAME)),
            legacy_user_dir=LEGACY_USER_DIR,
        ),
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

    def project_root(self) -> Path:
        """Get the project root directory (temp dir for tests)."""
        return self._temp_dir

    def workspace_display(self) -> str:
        """
        Get workspace path formatted for display.

        For tests, returns the temp directory path with forward slashes.
        """
        return str(self._temp_dir).replace("\\", "/")

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

    def command_history_file(self) -> Path:
        """Get path to test command_history (under the injected temp dir).

        Derived from the injected temp_dir like every other member; sending it
        back to HOME would defeat the provider's isolation contract.
        """
        return self._data_dir / "command_history"

    def model_cooldowns_file(self) -> Path:
        """Get path to test model_cooldowns.json (under the injected temp dir)."""
        return self._data_dir / "model_cooldowns.json"

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
