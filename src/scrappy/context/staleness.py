"""
Staleness detection via file fingerprinting.

Detects file changes by comparing fingerprints (mtime_ns + size) against stored state.

Three-layer detection strategy:
1. Trust stored fingerprints on load (fastest - no I/O)
2. Quick hybrid check: directory mtimes + sample file fingerprints (fast)
3. Full file scan (slow - only when needed)

Known limitations addressed:
- Uses nanosecond precision (st_mtime_ns) for better change detection
- Samples file fingerprints during quick check (dir mtime misses content edits)
- Logs warnings on OSError instead of silent skip
- Detects clock drift and forces full scan when detected
"""

import json
import logging
import random
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

from .protocols import StalenessReport, TimeProviderProtocol, FingerprintScannerProtocol
from .semantic.config import SemanticIndexConfig
from .semantic.file_collector import IndexFilterConfig

logger = logging.getLogger(__name__)

# Number of files to sample during quick_check for content change detection
QUICK_CHECK_SAMPLE_SIZE = 20


class SystemTimeProvider:
    """Production time provider using system time."""

    def now_ms(self) -> float:
        """Get current system time in milliseconds."""
        return time.time() * 1000


class FileSystemScanner:
    """Production file scanner using real file system with filtering."""

    def __init__(self, root: Path, filter_config: Optional[IndexFilterConfig] = None):
        """
        Initialize file system scanner.

        Args:
            root: Root directory for scanning
            filter_config: Filter config to skip .git, node_modules, etc.
        """
        self.root = root
        self._filter_config = filter_config or IndexFilterConfig()

    def scan_files(self, root: Path) -> Set[str]:
        """Scan directory for indexable files, returning relative paths.

        Uses IndexFilterConfig to skip directories like .git, node_modules, etc.
        This matches the filtering used by SemanticFileCollector.
        """
        files = set()
        for path in root.rglob('*'):
            if path.is_file():
                try:
                    # Apply same filtering as SemanticFileCollector
                    if self._filter_config.should_skip_by_path(path, root):
                        continue
                    rel_path = path.relative_to(root)
                    files.add(str(rel_path).replace('\\', '/'))
                except OSError as e:
                    logger.warning(f"Could not access file {path}: {e}")
                    continue
                except ValueError:
                    # File outside root - skip silently
                    continue
        return files

    def scan_directory_mtimes(self, root: Path) -> Dict[str, float]:
        """Scan directory mtimes for quick change detection.

        Only scans directories (not files) to quickly detect structural changes.
        Directory mtime changes when files are added/removed within it.

        Note: Directory mtime does NOT change when file contents are modified,
        only when files are added/deleted. Use sample_file_fingerprints() to
        catch content changes.

        Returns:
            Dict mapping directory path to mtime (nanoseconds)
        """
        mtimes = {}
        try:
            # Include root directory - use nanosecond precision
            mtimes['.'] = root.stat().st_mtime_ns
        except OSError as e:
            logger.warning(f"Could not stat root directory {root}: {e}")

        for path in root.rglob('*'):
            if path.is_dir():
                try:
                    # Skip filtered directories
                    if self._filter_config.should_skip_by_path(path, root):
                        continue
                    rel_path = path.relative_to(root)
                    mtimes[str(rel_path).replace('\\', '/')] = path.stat().st_mtime_ns
                except OSError as e:
                    logger.warning(f"Could not stat directory {path}: {e}")
                    continue
                except ValueError:
                    continue
        return mtimes

    def get_mtime_ns(self, file_path: Path) -> int:
        """Get file modification time in nanoseconds for maximum precision."""
        return file_path.stat().st_mtime_ns

    def get_size(self, file_path: Path) -> int:
        """Get file size in bytes."""
        return file_path.stat().st_size

    def get_fingerprint(self, file_path: Path) -> tuple:
        """Get file fingerprint (mtime_ns, size) tuple."""
        stat = file_path.stat()
        return (stat.st_mtime_ns, stat.st_size)


class StalenessChecker:
    """
    Detects file changes via three-layer fingerprinting strategy.

    Layer 1 (fastest): Trust stored fingerprints - no scan on app start
    Layer 2 (fast): Quick directory mtime check - detect structural changes
    Layer 3 (slow): Full file scan - only when directories changed or forced

    Example:
        checker = StalenessChecker(root_path=Path('/project'), config=config)

        # Layer 1: Check if we have stored state
        if not checker.has_fingerprints():
            # First run - need full scan
            report = checker.check_staleness(force=True)
        else:
            # Layer 2: Quick directory check
            if checker.quick_check():
                # Directories changed - do full scan
                report = checker.check_staleness()
            else:
                # No changes detected
                report = StalenessReport(added=set(), modified=set(), deleted=set())
    """

    def __init__(
        self,
        root_path: Path,
        config: SemanticIndexConfig,
        time_provider: Optional[TimeProviderProtocol] = None,
        file_scanner: Optional[FingerprintScannerProtocol] = None,
    ):
        """
        Initialize staleness checker.

        Args:
            root_path: Root directory to monitor
            config: Configuration with debounce settings and fingerprint file path
            time_provider: Time provider for debounce (default: SystemTimeProvider)
            file_scanner: File scanner for accessing file system (default: FileSystemScanner)
        """
        self.root_path = root_path
        self.config = config
        self.time_provider = time_provider or SystemTimeProvider()
        self.file_scanner = file_scanner or FileSystemScanner(root_path, IndexFilterConfig())

        self._fingerprints: Dict[str, tuple] = {}
        self._dir_mtimes: Dict[str, float] = {}  # Directory mtimes for quick check
        self._last_check_time: float = 0
        self._fingerprint_path = root_path / config.fingerprint_file

        # Load fingerprints if available (Layer 1: trust stored state)
        self._load_fingerprints()

    def get_fingerprints(self) -> Dict[str, tuple]:
        """
        Get current stored fingerprints.

        Returns:
            Dict mapping file paths to fingerprint tuples (mtime, size)
        """
        return self._fingerprints.copy()

    def has_fingerprints(self) -> bool:
        """
        Layer 1: Check if we have stored fingerprints.

        If True, we can trust the stored state and use quick_check().
        If False, need a full scan to establish baseline.

        Returns:
            True if fingerprints are loaded from disk
        """
        return len(self._fingerprints) > 0

    def quick_check(self) -> bool:
        """
        Layer 2: Quick hybrid check (directory mtimes + file sampling).

        Two-phase check:
        1. Compare directory mtimes to detect structural changes (add/delete)
        2. Sample a subset of file fingerprints to detect content changes

        Directory mtime alone misses file content modifications - this hybrid
        approach catches both structural and content changes efficiently.

        Returns:
            True if changes detected (need full scan), False if unchanged
        """
        if not self._dir_mtimes:
            # No stored directory mtimes - need full scan
            logger.debug("No stored directory mtimes, need full scan")
            return True

        # Phase 1: Directory mtime check (catches add/delete)
        current_mtimes = self.file_scanner.scan_directory_mtimes(self.root_path)

        # Check for new or removed directories
        stored_dirs = set(self._dir_mtimes.keys())
        current_dirs = set(current_mtimes.keys())

        if stored_dirs != current_dirs:
            added = current_dirs - stored_dirs
            removed = stored_dirs - current_dirs
            logger.debug(f"Directory structure changed: +{len(added)} -{len(removed)}")
            return True

        # Check for mtime changes in existing directories
        for dir_path, stored_mtime in self._dir_mtimes.items():
            current_mtime = current_mtimes.get(dir_path)
            if current_mtime is not None and current_mtime != stored_mtime:
                logger.debug(f"Directory mtime changed: {dir_path}")
                return True

        # Phase 2: Sample file fingerprints (catches content edits)
        # Directory mtime doesn't change when file contents are modified,
        # so we sample a random subset of files to detect these changes.
        if self._sample_files_changed():
            logger.debug("Sampled file fingerprints changed")
            return True

        logger.debug("Quick check passed - no changes detected")
        return False

    def _sample_files_changed(self) -> bool:
        """
        Sample a subset of stored fingerprints to detect content changes.

        Randomly samples up to QUICK_CHECK_SAMPLE_SIZE files and compares
        their current fingerprints against stored values.

        Returns:
            True if any sampled file has changed, False otherwise
        """
        if not self._fingerprints:
            return False

        # Sample random files to check
        file_paths = list(self._fingerprints.keys())
        sample_size = min(QUICK_CHECK_SAMPLE_SIZE, len(file_paths))
        sampled_files = random.sample(file_paths, sample_size)

        for file_path in sampled_files:
            full_path = self.root_path / file_path
            try:
                current_fp = self.file_scanner.get_fingerprint(full_path)
                stored_fp = self._fingerprints[file_path]

                if current_fp != stored_fp:
                    logger.debug(f"Sampled file changed: {file_path}")
                    return True
            except (OSError, FileNotFoundError):
                # File disappeared or unreadable - definitely changed
                logger.debug(f"Sampled file missing/unreadable: {file_path}")
                return True

        return False

    def check_staleness(self, force: bool = False) -> StalenessReport:
        """
        Layer 3: Full file scan for staleness detection.

        Compares current file system state against stored fingerprints.
        Respects debounce timing to avoid rapid re-checks (unless forced).

        Args:
            force: If True, skip debounce check (for explicit refresh)

        Returns:
            StalenessReport with sets of added/modified/deleted files
        """
        current_time = self.time_provider.now_ms()

        # Clock drift detection: if system clock went backward, force full scan
        # This prevents stale data when timestamps become unreliable
        if self._last_check_time > 0 and current_time < self._last_check_time:
            logger.warning(
                f"System clock drifted backward "
                f"(last={self._last_check_time}, now={current_time}), forcing full scan"
            )
            force = True

        time_since_last_check = current_time - self._last_check_time

        # Debounce: skip check if too soon since last check (unless forced)
        if not force and time_since_last_check < self.config.debounce_ms and self._last_check_time > 0:
            return StalenessReport(added=set(), modified=set(), deleted=set())

        self._last_check_time = current_time
        logger.debug("Performing full staleness scan...")

        # Get current file system state
        current_files = self.file_scanner.scan_files(self.root_path)
        stored_files = set(self._fingerprints.keys())

        # Detect changes
        added = current_files - stored_files
        deleted = stored_files - current_files
        modified = set()

        # Check for modifications in existing files
        for file_path in current_files & stored_files:
            full_path = self.root_path / file_path
            try:
                current_fingerprint = self.file_scanner.get_fingerprint(full_path)
                stored_fingerprint = self._fingerprints[file_path]

                if current_fingerprint != stored_fingerprint:
                    modified.add(file_path)
            except (OSError, FileNotFoundError) as e:
                # File disappeared during check - treat as deleted
                logger.warning(f"File became inaccessible during scan: {file_path}: {e}")
                deleted.add(file_path)

        return StalenessReport(added=added, modified=modified, deleted=deleted)

    def update_fingerprints(self, staleness_report: Optional[StalenessReport] = None) -> None:
        """
        Update stored fingerprints and directory mtimes to current state.

        Args:
            staleness_report: Optional report of changes from check_staleness().
                             If provided, only updates fingerprints for files in the report
                             (incremental update). If None, scans all files (full update).

        Should be called after successfully re-indexing changed files.
        Persists both file fingerprints and directory mtimes to disk.
        Fingerprints use nanosecond precision for maximum change detection.
        """
        if staleness_report is None:
            # Full update: scan all files and rebuild fingerprints from scratch
            logger.debug("Updating fingerprints (full scan)...")
            current_files = self.file_scanner.scan_files(self.root_path)

            # Build new fingerprint map using nanosecond-precision timestamps
            new_fingerprints: Dict[str, tuple] = {}
            for file_path in current_files:
                full_path = self.root_path / file_path
                try:
                    new_fingerprints[file_path] = self.file_scanner.get_fingerprint(full_path)
                except (OSError, FileNotFoundError) as e:
                    logger.warning(f"Could not fingerprint {file_path}: {e}")
                    continue

            self._fingerprints = new_fingerprints

            # Also capture directory mtimes for quick_check()
            self._dir_mtimes = self.file_scanner.scan_directory_mtimes(self.root_path)

            self._save_fingerprints()
            logger.debug(f"Saved {len(self._fingerprints)} file fingerprints, {len(self._dir_mtimes)} directory mtimes")
        else:
            # Incremental update: only update fingerprints for changed files
            logger.debug(
                f"Updating fingerprints (incremental): "
                f"+{len(staleness_report.added)} ~{len(staleness_report.modified)} -{len(staleness_report.deleted)}"
            )

            # Remove deleted files from fingerprints
            for file_path in staleness_report.deleted:
                self._fingerprints.pop(file_path, None)

            # Update fingerprints for added and modified files
            changed_files = staleness_report.added | staleness_report.modified
            for file_path in changed_files:
                full_path = self.root_path / file_path
                try:
                    self._fingerprints[file_path] = self.file_scanner.get_fingerprint(full_path)
                except (OSError, FileNotFoundError) as e:
                    logger.warning(f"Could not fingerprint {file_path}: {e}")
                    continue

            # Update directory mtimes incrementally by only scanning affected directories
            # Extract unique directory paths from changed files
            affected_dirs = set()
            for file_path in changed_files | staleness_report.deleted:
                # Get all parent directories of this file
                parts = Path(file_path).parts
                for i in range(len(parts)):
                    dir_path = str(Path(*parts[:i])).replace('\\', '/') if i > 0 else '.'
                    affected_dirs.add(dir_path)

            # Update mtimes for affected directories
            for dir_path in affected_dirs:
                dir_full_path = self.root_path / dir_path if dir_path != '.' else self.root_path
                try:
                    self._dir_mtimes[dir_path] = dir_full_path.stat().st_mtime_ns
                except (OSError, FileNotFoundError) as e:
                    logger.warning(f"Could not stat directory {dir_path}: {e}")
                    # Remove from tracking if directory no longer exists
                    self._dir_mtimes.pop(dir_path, None)
                    continue

            self._save_fingerprints()
            logger.debug(
                f"Incrementally updated {len(changed_files)} file fingerprints, "
                f"removed {len(staleness_report.deleted)}, "
                f"updated {len(affected_dirs)} directory mtimes"
            )

    def _load_fingerprints(self) -> None:
        """Load fingerprints and directory mtimes from disk if available."""
        if not self._fingerprint_path.exists():
            return

        try:
            with open(self._fingerprint_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

                # Handle both old format (just fingerprints) and new format (with dir_mtimes)
                if 'files' in data:
                    # New format
                    self._fingerprints = {
                        path: tuple(fp) for path, fp in data.get('files', {}).items()
                    }
                    self._dir_mtimes = data.get('directories', {})
                else:
                    # Old format - just fingerprints dict
                    self._fingerprints = {
                        path: tuple(fp) for path, fp in data.items()
                    }
                    self._dir_mtimes = {}

                logger.debug(f"Loaded {len(self._fingerprints)} fingerprints, {len(self._dir_mtimes)} dir mtimes")
        except (OSError, json.JSONDecodeError, ValueError) as e:
            # If load fails, start fresh
            logger.debug(f"Failed to load fingerprints: {e}")
            self._fingerprints = {}
            self._dir_mtimes = {}

    def _save_fingerprints(self) -> None:
        """Save fingerprints and directory mtimes to disk."""
        # Ensure parent directory exists
        self._fingerprint_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # New format: includes both files and directories
            data = {
                'files': self._fingerprints,
                'directories': self._dir_mtimes,
            }
            with open(self._fingerprint_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except OSError as e:
            # If save fails, continue without persistence
            logger.debug(f"Failed to save fingerprints: {e}")
