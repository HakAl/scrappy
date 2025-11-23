"""
File collection for semantic search indexing.

Implements intelligent file filtering following the hierarchy:
1. Trust Git first (respect .gitignore)
2. Fall back to regex/directory filters (only if not a git repo)
3. Check file size before reading
4. Detect and skip binary files
"""

import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class IndexFilterConfig:
    """
    Configuration for file filtering during indexing.

    Uses mixed strategy:
    1. Exact directory/file name matches (safer than regex for names like "build")
    2. Regex for extensions/patterns
    """

    # Exact directory/file names to ignore
    ignore_names: Set[str] = field(default_factory=lambda: {
        '__pycache__', 'node_modules', '.git', '.svn', '.hg',
        '.idea', '.vscode', '.DS_Store', 'Thumbs.db',
        'dist', 'build', 'target', 'venv', '.venv', '.env',
        '.pytest_cache', '.mypy_cache', '.ruff_cache', '.tox',
        'htmlcov', 'coverage', '.coverage', '.cache',
        'vendor', 'third_party', 'packages',
        '.scrappy', '.lancedb',  # Our own data directories
    })

    # Regex patterns for file extensions/names to ignore
    ignore_extensions: list = field(default_factory=lambda: [
        r'\.py[cod]$',  # Python bytecode
        r'\.so$', r'\.dylib$', r'\.dll$', r'\.exe$',  # Binaries
        r'\.bin$', r'\.o$', r'\.obj$',  # Object files
        r'\.jpe?g$', r'\.png$', r'\.gif$', r'\.svg$', r'\.ico$',  # Images
        r'\.woff2?$', r'\.ttf$', r'\.eot$',  # Fonts
        r'\.mp[34]$', r'\.wav$', r'\.flac$',  # Audio
        r'\.mp4$', r'\.avi$', r'\.mov$',  # Video
        r'\.zip$', r'\.tar$', r'\.gz$', r'\.bz2$', r'\.7z$',  # Archives
        r'\.pdf$', r'\.doc[x]?$', r'\.xls[x]?$', r'\.ppt[x]?$',  # Documents
        r'\.db$', r'\.sqlite$', r'\.sqlite3$',  # Databases
        r'-lock\.json$', r'\.lock$',  # Lock files
        r'package-lock\.json$', r'yarn\.lock$', r'poetry\.lock$',
        r'\.min\.js$', r'\.min\.css$',  # Minified files
        r'\.map$',  # Source maps
    ])

    # Git configuration
    respect_gitignore: bool = True
    include_untracked: bool = False  # Whether to include untracked files in git repos

    # Size limits
    max_file_size_bytes: int = 5 * 1024 * 1024  # 5MB default

    def __post_init__(self):
        """Compile regex patterns after initialization."""
        self._compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.ignore_extensions]

    def should_skip_by_path(self, path: Path, root: Path) -> bool:
        """
        Check if path should be skipped based on path parts.

        This prevents "dist" matching "distributed_systems.py" by checking
        path components, not substrings.

        Args:
            path: Absolute path to check
            root: Project root path

        Returns:
            True if path should be skipped
        """
        try:
            rel_path = path.relative_to(root)
        except ValueError:
            # Path is outside root - skip it
            return True

        # Check if any path part is in ignore_names
        # This catches directories at any level
        if any(part in self.ignore_names for part in rel_path.parts):
            return True

        # Check filename against regex patterns
        filename = path.name
        if any(pattern.search(filename) for pattern in self._compiled_patterns):
            return True

        return False

    def should_skip_by_size(self, path: Path) -> bool:
        """
        Check if file should be skipped due to size.

        Args:
            path: Path to file

        Returns:
            True if file exceeds size limit
        """
        try:
            size = path.stat().st_size
            if size > self.max_file_size_bytes:
                logger.debug(
                    f"Skipping large file: {path.name} "
                    f"({size / 1024 / 1024:.1f}MB > "
                    f"{self.max_file_size_bytes / 1024 / 1024:.1f}MB)"
                )
                return True
            return False
        except OSError as e:
            logger.debug(f"Cannot stat file {path}: {e}")
            return True

    def is_binary(self, path: Path) -> bool:
        """
        Check if file is binary by reading first 8KB.

        Uses heuristic: if file contains null bytes, it's binary.

        Args:
            path: Path to file

        Returns:
            True if file appears to be binary
        """
        try:
            with open(path, 'rb') as f:
                chunk = f.read(8192)
                if b'\x00' in chunk:
                    logger.debug(f"Skipping binary file: {path.name}")
                    return True
            return False
        except Exception as e:
            logger.debug(f"Cannot read file {path}: {e}")
            return True


class SemanticFileCollector:
    """
    Collects files for semantic search indexing with intelligent filtering.

    Follows the hierarchy:
    1. Trust Git first - use git ls-files to respect .gitignore
    2. Fall back to directory scanning only if NOT a git repo
    3. Check file size before reading
    4. Detect and skip binary files

    Architecture:
    - Follows SOLID principles (dependency injection, single responsibility)
    - No I/O in constructor (lazy evaluation)
    - Protocol-based design
    """

    def __init__(
        self,
        project_path: Path,
        filter_config: Optional[IndexFilterConfig] = None
    ):
        """
        Initialize file collector (NO I/O in constructor).

        Args:
            project_path: Project root path
            filter_config: Optional filter configuration (uses defaults if None)
        """
        self._project_path = project_path.resolve()
        self._filter_config = filter_config or IndexFilterConfig()

    def collect_files(self) -> Dict[str, str]:
        """
        Collect files for semantic search indexing.

        Implements FileCollectorProtocol.

        Returns:
            Dict mapping relative file paths to content
        """
        logger.info("Collecting files for semantic search indexing...")

        # Determine if this is a git repository
        is_git_repo = (self._project_path / '.git').exists()

        # Get candidate files
        if self._filter_config.respect_gitignore and is_git_repo:
            logger.debug("Using git ls-files (respects .gitignore)")
            try:
                candidates = self._list_files_git()
            except RuntimeError as e:
                logger.error(
                    f"Git command failed in git repository: {e}. "
                    "Returning empty set for security (won't bypass .gitignore)."
                )
                # Security: Don't fallback to plain scan in git repos when git fails
                # This ensures we never bypass .gitignore
                return {}
        else:
            if is_git_repo:
                logger.info("Git repo detected but respect_gitignore=False, using plain scan")
            logger.debug("Using plain directory scan")
            candidates = self._list_files_plain()

        logger.debug(f"Found {len(candidates)} candidate files")

        # Read and filter files
        files = {}
        stats = {
            'skipped_size': 0,
            'skipped_binary': 0,
            'skipped_read_error': 0,
            'collected': 0,
        }

        for file_path in candidates:
            full_path = self._project_path / file_path

            # Skip if file doesn't exist (rare, but possible in git edge cases)
            if not full_path.exists():
                continue

            # Skip by size
            if self._filter_config.should_skip_by_size(full_path):
                stats['skipped_size'] += 1
                continue

            # Skip binary files
            if self._filter_config.is_binary(full_path):
                stats['skipped_binary'] += 1
                continue

            # Read file content
            try:
                content = full_path.read_text(encoding='utf-8', errors='ignore')
                files[file_path] = content
                stats['collected'] += 1
            except Exception as e:
                logger.debug(f"Failed to read {file_path}: {e}")
                stats['skipped_read_error'] += 1

        logger.info(
            f"Collected {stats['collected']} files for indexing "
            f"(skipped: {stats['skipped_size']} too large, "
            f"{stats['skipped_binary']} binary, "
            f"{stats['skipped_read_error']} read errors)"
        )

        return files

    def collect_files_batched(self, batch_size: int = 50):
        """
        Collect files in batches (generator) to prevent memory spikes.

        Implements FileCollectorProtocol.

        Yields batches of files instead of loading entire codebase into memory.
        Each batch contains up to batch_size files.

        Args:
            batch_size: Maximum number of files per batch (default: 50)

        Yields:
            Dict[str, str]: Batch of file paths to content
        """
        logger.info(f"Collecting files in batches of {batch_size}...")

        # Determine if this is a git repository
        is_git_repo = (self._project_path / '.git').exists()

        # Get candidate files
        if self._filter_config.respect_gitignore and is_git_repo:
            logger.debug("Using git ls-files (respects .gitignore)")
            try:
                candidates = self._list_files_git()
            except RuntimeError as e:
                logger.error(
                    f"Git command failed in git repository: {e}. "
                    "Returning empty for security (won't bypass .gitignore)."
                )
                # Security: Don't fallback to plain scan in git repos when git fails
                # This ensures we never bypass .gitignore
                return  # Empty generator
        else:
            if is_git_repo:
                logger.info("Git repo detected but respect_gitignore=False, using plain scan")
            logger.debug("Using plain directory scan")
            candidates = self._list_files_plain()

        logger.debug(f"Found {len(candidates)} candidate files")

        # Process files in batches
        batch = {}
        stats = {
            'skipped_size': 0,
            'skipped_binary': 0,
            'skipped_read_error': 0,
            'collected': 0,
            'batches': 0,
        }

        for file_path in candidates:
            full_path = self._project_path / file_path

            # Skip if file doesn't exist
            if not full_path.exists():
                continue

            # Skip by size
            if self._filter_config.should_skip_by_size(full_path):
                stats['skipped_size'] += 1
                continue

            # Skip binary files
            if self._filter_config.is_binary(full_path):
                stats['skipped_binary'] += 1
                continue

            # Read file content
            try:
                content = full_path.read_text(encoding='utf-8', errors='ignore')
                batch[file_path] = content
                stats['collected'] += 1

                # Yield batch when full
                if len(batch) >= batch_size:
                    stats['batches'] += 1
                    logger.debug(f"Yielding batch {stats['batches']} ({len(batch)} files)")
                    yield batch
                    batch = {}  # Clear batch to release memory

            except Exception as e:
                logger.debug(f"Failed to read {file_path}: {e}")
                stats['skipped_read_error'] += 1

        # Yield final partial batch if any
        if batch:
            stats['batches'] += 1
            logger.debug(f"Yielding final batch {stats['batches']} ({len(batch)} files)")
            yield batch

        logger.info(
            f"Collected {stats['collected']} files in {stats['batches']} batches "
            f"(skipped: {stats['skipped_size']} too large, "
            f"{stats['skipped_binary']} binary, "
            f"{stats['skipped_read_error']} read errors)"
        )

    def _list_files_git(self) -> Set[str]:
        """
        Get file list from git ls-files.

        This respects .gitignore and only returns tracked (and optionally untracked) files.

        Returns:
            Set of relative file paths

        Raises:
            RuntimeError: If git command fails (to distinguish from "no files found")
        """
        try:
            files = set()

            # Get tracked files
            result_tracked = subprocess.run(
                ['git', 'ls-files'],
                cwd=self._project_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result_tracked.returncode != 0:
                logger.warning(f"git ls-files failed: {result_tracked.stderr}")
                raise RuntimeError(f"git ls-files failed: {result_tracked.stderr}")

            # Parse tracked files
            for line in result_tracked.stdout.strip().split('\n'):
                if line:
                    path = Path(line)
                    if not self._filter_config.should_skip_by_path(
                        self._project_path / path,
                        self._project_path
                    ):
                        files.add(line)

            # Add untracked files if configured
            if self._filter_config.include_untracked:
                result_untracked = subprocess.run(
                    ['git', 'ls-files', '--others', '--exclude-standard'],
                    cwd=self._project_path,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result_untracked.returncode != 0:
                    logger.warning(f"git ls-files --others failed: {result_untracked.stderr}")
                    raise RuntimeError(f"git ls-files --others failed: {result_untracked.stderr}")

                # Parse untracked files
                for line in result_untracked.stdout.strip().split('\n'):
                    if line:
                        path = Path(line)
                        if not self._filter_config.should_skip_by_path(
                            self._project_path / path,
                            self._project_path
                        ):
                            files.add(line)

            return files

        except subprocess.TimeoutExpired:
            logger.error("git ls-files timed out after 30 seconds")
            raise RuntimeError("git ls-files timed out")
        except FileNotFoundError:
            logger.warning("git command not found")
            raise RuntimeError("git command not found")
        except RuntimeError:
            # Re-raise RuntimeError (git failures)
            raise
        except Exception as e:
            logger.error(f"Unexpected error running git ls-files: {e}")
            raise RuntimeError(f"Unexpected error running git ls-files: {e}")

    def _list_files_plain(self) -> Set[str]:
        """
        Get file list by scanning filesystem with regex/directory filters.

        ONLY used when NOT a git repository or respect_gitignore=False.

        Returns:
            Set of relative file paths
        """
        files = set()

        try:
            for path in self._project_path.rglob('*'):
                # Skip directories
                if not path.is_file():
                    continue

                # Apply filtering
                if self._filter_config.should_skip_by_path(path, self._project_path):
                    continue

                # Get relative path
                try:
                    rel_path = path.relative_to(self._project_path)
                    files.add(str(rel_path))
                except ValueError:
                    # Path outside project root - skip
                    continue

        except Exception as e:
            logger.error(f"Error during filesystem scan: {e}")

        return files
