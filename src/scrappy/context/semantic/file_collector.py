"""
File collection for semantic search indexing.

Implements intelligent file filtering:
1. Apply regex/directory filters
2. Check file size before reading
3. Detect and skip binary files
"""

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

from scrappy.context.protocols import FilePrioritizerProtocol
from scrappy.context.semantic.file_prioritizer import DefaultFilePrioritizer

logger = logging.getLogger(__name__)


class FileCollectionError(Exception):
    """Exception raised when file collection fails."""
    pass


@dataclass
class IndexFilterConfig:
    """
    Configuration for file filtering during indexing.

    Uses mixed strategy:
    1. Exact directory/file name matches (safer than regex for names like "build")
    2. Regex for extensions/patterns
    3. Test noise exclusion patterns
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

    # Test noise exclusion - directories containing test data (not test code)
    test_noise_patterns: Set[str] = field(default_factory=lambda: {
        '__snapshots__',
        'snapshots',
        'fixtures',
        'test/data',
        'tests/data',
        'test/fixtures',
        'tests/fixtures',
        'testdata',
        '__mocks__',
    })

    # Test noise file extensions (snapshot files, etc.)
    test_noise_extensions: Set[str] = field(default_factory=lambda: {
        '.snap',
        '.snapshot',
    })

    # Skip large JSON files in test directories (likely test data fixtures)
    skip_large_json_in_tests: bool = True
    large_json_threshold_bytes: int = 50_000  # 50KB

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

        # Check test noise patterns (directories containing test data)
        path_str = str(rel_path).lower().replace('\\', '/')
        if any(pattern in path_str for pattern in self.test_noise_patterns):
            return True

        # Check test noise file extensions (.snap, .snapshot)
        if path.suffix.lower() in self.test_noise_extensions:
            return True

        return False

    def should_skip_large_json_in_tests(self, path: Path, root: Path) -> bool:
        """
        Check if file is a large JSON file in a test directory.

        Args:
            path: Absolute path to file
            root: Project root path

        Returns:
            True if file is a large JSON in a test directory and should be skipped
        """
        if not self.skip_large_json_in_tests:
            return False

        if path.suffix.lower() != '.json':
            return False

        try:
            rel_path = path.relative_to(root)
            path_str = str(rel_path).lower().replace('\\', '/')

            # Check if file is in a test directory
            test_dir_patterns = ('test/', 'tests/', 'spec/', '__tests__/')
            if not any(pattern in path_str for pattern in test_dir_patterns):
                return False

            # Check file size
            try:
                file_size = path.stat().st_size
                if file_size > self.large_json_threshold_bytes:
                    logger.debug(
                        f"Skipping large test JSON: {path.name} "
                        f"({file_size / 1024:.1f}KB > "
                        f"{self.large_json_threshold_bytes / 1024:.1f}KB)"
                    )
                    return True
            except OSError:
                pass

        except ValueError:
            pass

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

        Raises:
            PermissionError: If file cannot be accessed due to permissions
        """
        try:
            with open(path, 'rb') as f:
                chunk = f.read(8192)
                if b'\x00' in chunk:
                    logger.debug(f"Skipping binary file: {path.name}")
                    return True
            return False
        except PermissionError:
            raise
        except Exception as e:
            logger.debug(f"Cannot read file {path}: {e}")
            return True


class SemanticFileCollector:
    """
    Collects files for semantic search indexing with intelligent filtering.

    Follows the hierarchy:
    1. Scan filesystem with configurable filters
    2. Check file size before reading
    3. Detect and skip binary files

    Architecture:
    - Follows SOLID principles (dependency injection, single responsibility)
    - No I/O in constructor (lazy evaluation)
    - Protocol-based design
    """

    def __init__(
        self,
        project_path: Path,
        filter_config: Optional[IndexFilterConfig] = None,
        prioritizer: Optional[FilePrioritizerProtocol] = None,
    ):
        """
        Initialize file collector (NO I/O in constructor).

        Args:
            project_path: Project root path
            filter_config: Optional filter configuration (uses defaults if None)
            prioritizer: Optional file prioritizer (uses DefaultFilePrioritizer if None)
        """
        self._project_path = project_path.resolve()
        self._filter_config = filter_config or IndexFilterConfig()
        self._prioritizer = prioritizer or DefaultFilePrioritizer()

    def collect_file_paths(self) -> List[Path]:
        """
        Return list of file paths without reading content (fast scan for metrics).

        This method quickly scans the filesystem to determine which files would be
        indexed, without the overhead of reading their content. Used for metrics
        calculation and change detection.

        Returns:
            List of relative file paths (as Path objects)
        """
        candidates = self._list_files()
        return [Path(p) for p in candidates]

    def collect_files(self) -> Dict[str, str]:
        """
        Collect files for semantic search indexing.

        Implements FileCollectorProtocol.

        Returns:
            Dict mapping relative file paths to content
        """
        logger.info("Collecting files for semantic search indexing...")

        # Get candidate files
        candidates = self._list_files()
        logger.debug(f"Found {len(candidates)} candidate files")

        # Prioritize files for indexing order
        candidate_paths = [Path(p) for p in candidates]
        prioritized = self._prioritizer.sort_by_priority(candidate_paths)
        logger.debug("Files prioritized for indexing")

        # Read and filter files
        files = {}
        stats = {
            'skipped_size': 0,
            'skipped_binary': 0,
            'skipped_read_error': 0,
            'skipped_test_json': 0,
            'collected': 0,
        }

        for path_obj in prioritized:
            file_path = str(path_obj)
            full_path = self._project_path / file_path

            # Skip if file doesn't exist (defensive check)
            if not full_path.exists():
                continue

            # Skip by size
            if self._filter_config.should_skip_by_size(full_path):
                stats['skipped_size'] += 1
                continue

            # Skip large JSON files in test directories
            if self._filter_config.should_skip_large_json_in_tests(full_path, self._project_path):
                stats['skipped_test_json'] += 1
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
            f"{stats['skipped_test_json']} test JSON, "
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

        # Get candidate files
        candidates = self._list_files()
        logger.debug(f"Found {len(candidates)} candidate files")

        # Prioritize files for indexing order
        candidate_paths = [Path(p) for p in candidates]
        prioritized = self._prioritizer.sort_by_priority(candidate_paths)
        logger.debug("Files prioritized for indexing")

        # Process files in batches
        batch = {}
        stats = {
            'skipped_size': 0,
            'skipped_binary': 0,
            'skipped_read_error': 0,
            'skipped_test_json': 0,
            'collected': 0,
            'batches': 0,
        }

        for path_obj in prioritized:
            file_path = str(path_obj)
            full_path = self._project_path / file_path

            # Skip if file doesn't exist
            if not full_path.exists():
                continue

            # Skip by size
            if self._filter_config.should_skip_by_size(full_path):
                stats['skipped_size'] += 1
                continue

            # Skip large JSON files in test directories
            if self._filter_config.should_skip_large_json_in_tests(full_path, self._project_path):
                stats['skipped_test_json'] += 1
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
            f"{stats['skipped_test_json']} test JSON, "
            f"{stats['skipped_read_error']} read errors)"
        )

    def _list_files(self) -> Set[str]:
        """
        Get file list by scanning filesystem with filters.

        Recursively walks the directory tree and applies filter configuration
        to exclude unwanted files.

        Returns:
            Set of relative file paths

        Raises:
            FileCollectionError: If filesystem scan fails
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
            raise FileCollectionError(f"Failed to scan filesystem: {e}") from e

        return files

    def get_file_hashes(self, files: List[Path]) -> Dict[str, str]:
        """
        Compute content hashes for files.

        Uses MD5 hashing for fast content comparison to detect changes
        since last index.

        Args:
            files: List of file paths (relative to project root)

        Returns:
            Dict mapping path string to MD5 hash of file contents
        """
        hashes = {}

        for file_path in files:
            # Convert to Path if string
            if isinstance(file_path, str):
                file_path = Path(file_path)

            # Build absolute path
            full_path = self._project_path / file_path

            # Skip non-existent files
            if not full_path.exists() or not full_path.is_file():
                logger.debug(f"Skipping non-existent file for hashing: {file_path}")
                continue

            # Compute MD5 hash
            try:
                md5_hash = hashlib.md5()
                with open(full_path, 'rb') as f:
                    # Read in chunks to handle large files efficiently
                    for chunk in iter(lambda: f.read(8192), b''):
                        md5_hash.update(chunk)

                hashes[str(file_path)] = md5_hash.hexdigest()

            except Exception as e:
                logger.debug(f"Failed to hash file {file_path}: {e}")
                # Continue processing other files even if one fails

        logger.debug(f"Computed hashes for {len(hashes)}/{len(files)} files")
        return hashes

    def get_file_sizes(self, files: List[Path]) -> Dict[str, int]:
        """
        Return dict mapping path string to file size in bytes.

        Used for metrics calculation to estimate indexing work.

        Args:
            files: List of file paths (relative to project root)

        Returns:
            Dict mapping path string to file size in bytes
        """
        sizes = {}
        for file_path in files:
            if isinstance(file_path, str):
                file_path = Path(file_path)
            full_path = self._project_path / file_path
            try:
                if full_path.exists() and full_path.is_file():
                    sizes[str(file_path)] = full_path.stat().st_size
            except Exception:
                pass
        return sizes
