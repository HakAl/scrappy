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

    def ensure_data_dir(self) -> None:
        """Create temporary data directory if it doesn't exist."""
        self._data_dir.mkdir(parents=True, exist_ok=True)


def migrate_legacy_files(
    project_root: Path,
    path_provider: PathProviderProtocol,
    verbose: bool = False
) -> dict[str, bool]:
    """
    Migrate old .llm_* files to new .scrappy/ directory.

    Args:
        project_root: Root directory of the project
        path_provider: Path provider to use for new locations
        verbose: If True, print migration progress

    Returns:
        Dict mapping old filename to migration success status
    """
    # Mapping of old filenames to new path methods
    legacy_mappings = {
        '.llm_team_session.json': path_provider.session_file,
        '.llm_rate_limits.json': path_provider.rate_limits_file,
        '.llm_agent_audit.json': path_provider.audit_file,
        '.llm_response_cache.json': path_provider.response_cache_file,
        '.llm_team_context.json': path_provider.context_file,
    }

    results = {}

    # Ensure target directory exists
    path_provider.ensure_data_dir()

    for old_name, new_path_func in legacy_mappings.items():
        old_path = project_root / old_name
        new_path = new_path_func()

        if old_path.exists():
            try:
                # Move file to new location
                if new_path.exists():
                    # If new file exists, back up old file
                    backup_path = project_root / f"{old_name}.backup"
                    old_path.rename(backup_path)
                    if verbose:
                        logger.info(f"Backed up {old_name} to {backup_path.name}")
                    results[old_name] = True
                else:
                    # Move to new location
                    old_path.rename(new_path)
                    if verbose:
                        logger.info(f"Migrated {old_name} to {new_path.relative_to(project_root)}")
                    results[old_name] = True
            except Exception as e:
                if verbose:
                    logger.error(f"Failed to migrate {old_name}: {e}")
                results[old_name] = False
        else:
            results[old_name] = True  # File doesn't exist, no migration needed

    return results
