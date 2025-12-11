"""
Tests for StalenessChecker.

Tests cover:
- New file detected as stale
- Modified file detected as stale
- Deleted file detected
- Debounce prevents rapid checks
- Debounce allows check after settle time
- Fingerprint performance for large file counts
"""

from pathlib import Path
from typing import Dict, Set
import pytest

from scrappy.context.staleness import StalenessChecker
from scrappy.context.protocols import (
    StalenessReport,
    TimeProviderProtocol,
    FingerprintScannerProtocol,
)
from scrappy.context.semantic.config import SemanticIndexConfig


class FakeTimeProvider:
    """Test double for time provider with controllable time."""

    def __init__(self, initial_time: float = 0.0):
        """
        Initialize with controllable time.

        Args:
            initial_time: Starting time in milliseconds
        """
        self._current_time = initial_time

    def now_ms(self) -> float:
        """Return current fake time in milliseconds."""
        return self._current_time

    def advance(self, milliseconds: float) -> None:
        """
        Advance time by specified milliseconds.

        Args:
            milliseconds: Amount to advance time
        """
        self._current_time += milliseconds


class FakeFileScanner:
    """Test double for file scanner with controllable file state."""

    def __init__(self):
        """Initialize with empty file state."""
        self._files: Dict[str, tuple] = {}  # path -> (mtime, size)

    def add_file(self, rel_path: str, mtime: float, size: int) -> None:
        """
        Add file to scanner state.

        Args:
            rel_path: Relative file path
            mtime: Modification time
            size: File size in bytes
        """
        self._files[rel_path] = (mtime, size)

    def remove_file(self, rel_path: str) -> None:
        """
        Remove file from scanner state.

        Args:
            rel_path: Relative file path to remove
        """
        self._files.pop(rel_path, None)

    def modify_file(self, rel_path: str, mtime: float, size: int) -> None:
        """
        Modify existing file.

        Args:
            rel_path: Relative file path
            mtime: New modification time
            size: New file size
        """
        self._files[rel_path] = (mtime, size)

    def scan_files(self, root: Path) -> Set[str]:
        """Return set of file paths."""
        return set(self._files.keys())

    def get_mtime(self, file_path: Path) -> float:
        """Get file modification time."""
        # Extract relative path from the full path
        # If file_path is like Path('/fake/project/src/file.py'), extract 'src/file.py'
        path_str = str(file_path).replace('\\', '/')
        # Try to find matching file by checking if path ends with stored rel_path
        for rel_path in self._files.keys():
            if path_str.endswith(rel_path):
                return self._files[rel_path][0]
        raise FileNotFoundError(f"File not found: {file_path}")

    def get_size(self, file_path: Path) -> int:
        """Get file size in bytes."""
        # Extract relative path from the full path
        path_str = str(file_path).replace('\\', '/')
        # Try to find matching file by checking if path ends with stored rel_path
        for rel_path in self._files.keys():
            if path_str.endswith(rel_path):
                return self._files[rel_path][1]
        raise FileNotFoundError(f"File not found: {file_path}")

    def scan_directory_mtimes(self, root: Path) -> Dict[str, float]:
        """Return dict of directory mtimes derived from files."""
        # For testing, derive directories from file paths
        # Use a fixed mtime for simplicity
        dirs = {'.': 1000.0}  # Root directory
        for rel_path in self._files.keys():
            parts = rel_path.replace('\\', '/').split('/')
            # Add all parent directories
            for i in range(1, len(parts)):
                dir_path = '/'.join(parts[:i])
                if dir_path not in dirs:
                    dirs[dir_path] = 1000.0
        return dirs

    def get_mtime_ns(self, file_path: Path) -> int:
        """Get file modification time in nanoseconds."""
        # Convert stored float mtime to nanoseconds (for test compatibility)
        mtime = self.get_mtime(file_path)
        return int(mtime * 1_000_000_000)

    def get_fingerprint(self, file_path: Path) -> tuple:
        """Get file fingerprint as (mtime_ns, size) tuple."""
        path_str = str(file_path).replace('\\', '/')
        for rel_path in self._files.keys():
            if path_str.endswith(rel_path):
                mtime, size = self._files[rel_path]
                # Return nanosecond-precision fingerprint
                return (int(mtime * 1_000_000_000), size)
        raise FileNotFoundError(f"File not found: {file_path}")


class TestStalenessCheckerNewFiles:
    """Test detection of new files."""

    @pytest.fixture
    def time_provider(self):
        """Create fake time provider."""
        return FakeTimeProvider(initial_time=1000.0)

    @pytest.fixture
    def file_scanner(self):
        """Create fake file scanner."""
        return FakeFileScanner()

    @pytest.fixture
    def config(self, tmp_path):
        """Create test config with no debounce and unique fingerprint file."""
        fingerprint_file = str(tmp_path / "fingerprints.json")
        return SemanticIndexConfig(debounce_ms=0, fingerprint_file=fingerprint_file)

    @pytest.fixture
    def checker(self, time_provider, file_scanner, config, tmp_path):
        """Create staleness checker with test doubles."""
        return StalenessChecker(
            root_path=tmp_path,
            config=config,
            time_provider=time_provider,
            file_scanner=file_scanner,
        )

    def test_new_file_detected_as_added(self, checker, file_scanner):
        """New file should be detected as added."""
        # Initial state: no files
        report = checker.check_staleness()
        assert not report.is_stale

        # Add new file
        file_scanner.add_file('src/new_file.py', mtime=1234.0, size=100)

        # Check staleness
        report = checker.check_staleness()
        assert report.is_stale
        assert 'src/new_file.py' in report.added
        assert len(report.modified) == 0
        assert len(report.deleted) == 0
        assert report.total_changes == 1

    def test_multiple_new_files_detected(self, checker, file_scanner):
        """Multiple new files should all be detected."""
        # Add multiple files
        file_scanner.add_file('src/file1.py', mtime=1000.0, size=100)
        file_scanner.add_file('src/file2.py', mtime=1001.0, size=200)
        file_scanner.add_file('tests/test_file.py', mtime=1002.0, size=150)

        report = checker.check_staleness()
        assert report.is_stale
        assert len(report.added) == 3
        assert 'src/file1.py' in report.added
        assert 'src/file2.py' in report.added
        assert 'tests/test_file.py' in report.added


class TestStalenessCheckerModifiedFiles:
    """Test detection of modified files."""

    @pytest.fixture
    def time_provider(self):
        """Create fake time provider."""
        return FakeTimeProvider(initial_time=1000.0)

    @pytest.fixture
    def file_scanner(self):
        """Create fake file scanner."""
        scanner = FakeFileScanner()
        # Start with existing files
        scanner.add_file('src/existing.py', mtime=1000.0, size=100)
        scanner.add_file('src/another.py', mtime=1000.0, size=200)
        return scanner

    @pytest.fixture
    def config(self, tmp_path):
        """Create test config with no debounce and unique fingerprint file."""
        fingerprint_file = str(tmp_path / "fingerprints.json")
        return SemanticIndexConfig(debounce_ms=0, fingerprint_file=fingerprint_file)

    @pytest.fixture
    def checker(self, time_provider, file_scanner, config, tmp_path):
        """Create staleness checker with existing files."""
        checker = StalenessChecker(
            root_path=tmp_path,
            config=config,
            time_provider=time_provider,
            file_scanner=file_scanner,
        )
        # Update fingerprints to establish baseline
        checker.update_fingerprints()
        return checker

    def test_modified_file_detected_by_mtime_change(self, checker, file_scanner):
        """File modification should be detected when mtime changes."""
        # Modify file (change mtime, keep size same)
        file_scanner.modify_file('src/existing.py', mtime=2000.0, size=100)

        report = checker.check_staleness()
        assert report.is_stale
        assert 'src/existing.py' in report.modified
        assert len(report.added) == 0
        assert len(report.deleted) == 0

    def test_modified_file_detected_by_size_change(self, checker, file_scanner):
        """File modification should be detected when size changes."""
        # Modify file (change size, keep mtime same)
        file_scanner.modify_file('src/existing.py', mtime=1000.0, size=500)

        report = checker.check_staleness()
        assert report.is_stale
        assert 'src/existing.py' in report.modified

    def test_modified_file_detected_by_both_changes(self, checker, file_scanner):
        """File modification should be detected when both mtime and size change."""
        # Modify file (change both)
        file_scanner.modify_file('src/existing.py', mtime=2000.0, size=500)

        report = checker.check_staleness()
        assert report.is_stale
        assert 'src/existing.py' in report.modified

    def test_multiple_modified_files_detected(self, checker, file_scanner):
        """Multiple modified files should all be detected."""
        file_scanner.modify_file('src/existing.py', mtime=2000.0, size=100)
        file_scanner.modify_file('src/another.py', mtime=2001.0, size=200)

        report = checker.check_staleness()
        assert len(report.modified) == 2
        assert 'src/existing.py' in report.modified
        assert 'src/another.py' in report.modified

    def test_no_modification_detected_when_fingerprint_unchanged(self, checker):
        """No modification should be detected if fingerprint unchanged."""
        # Check without modifying anything
        report = checker.check_staleness()
        assert not report.is_stale
        assert len(report.modified) == 0


class TestStalenessCheckerDeletedFiles:
    """Test detection of deleted files."""

    @pytest.fixture
    def time_provider(self):
        """Create fake time provider."""
        return FakeTimeProvider(initial_time=1000.0)

    @pytest.fixture
    def file_scanner(self):
        """Create fake file scanner."""
        scanner = FakeFileScanner()
        # Start with existing files
        scanner.add_file('src/file1.py', mtime=1000.0, size=100)
        scanner.add_file('src/file2.py', mtime=1000.0, size=200)
        return scanner

    @pytest.fixture
    def config(self, tmp_path):
        """Create test config with no debounce and unique fingerprint file."""
        fingerprint_file = str(tmp_path / "fingerprints.json")
        return SemanticIndexConfig(debounce_ms=0, fingerprint_file=fingerprint_file)

    @pytest.fixture
    def checker(self, time_provider, file_scanner, config, tmp_path):
        """Create staleness checker with existing files."""
        checker = StalenessChecker(
            root_path=tmp_path,
            config=config,
            time_provider=time_provider,
            file_scanner=file_scanner,
        )
        # Update fingerprints to establish baseline
        checker.update_fingerprints()
        return checker

    def test_deleted_file_detected(self, checker, file_scanner):
        """Deleted file should be detected."""
        # Remove file
        file_scanner.remove_file('src/file1.py')

        report = checker.check_staleness()
        assert report.is_stale
        assert 'src/file1.py' in report.deleted
        assert len(report.added) == 0
        assert len(report.modified) == 0

    def test_multiple_deleted_files_detected(self, checker, file_scanner):
        """Multiple deleted files should all be detected."""
        file_scanner.remove_file('src/file1.py')
        file_scanner.remove_file('src/file2.py')

        report = checker.check_staleness()
        assert len(report.deleted) == 2
        assert 'src/file1.py' in report.deleted
        assert 'src/file2.py' in report.deleted


class TestStalenessCheckerMixedChanges:
    """Test detection of mixed changes (added + modified + deleted)."""

    @pytest.fixture
    def time_provider(self):
        """Create fake time provider."""
        return FakeTimeProvider(initial_time=1000.0)

    @pytest.fixture
    def file_scanner(self):
        """Create fake file scanner."""
        scanner = FakeFileScanner()
        # Start with some existing files
        scanner.add_file('src/existing.py', mtime=1000.0, size=100)
        scanner.add_file('src/to_delete.py', mtime=1000.0, size=200)
        return scanner

    @pytest.fixture
    def config(self, tmp_path):
        """Create test config with no debounce and unique fingerprint file."""
        fingerprint_file = str(tmp_path / "fingerprints.json")
        return SemanticIndexConfig(debounce_ms=0, fingerprint_file=fingerprint_file)

    @pytest.fixture
    def checker(self, time_provider, file_scanner, config, tmp_path):
        """Create staleness checker with existing files."""
        checker = StalenessChecker(
            root_path=tmp_path,
            config=config,
            time_provider=time_provider,
            file_scanner=file_scanner,
        )
        # Update fingerprints to establish baseline
        checker.update_fingerprints()
        return checker

    def test_mixed_changes_all_detected(self, checker, file_scanner):
        """Added, modified, and deleted files should all be detected together."""
        # Add new file
        file_scanner.add_file('src/new_file.py', mtime=1500.0, size=150)

        # Modify existing file
        file_scanner.modify_file('src/existing.py', mtime=1500.0, size=300)

        # Delete file
        file_scanner.remove_file('src/to_delete.py')

        report = checker.check_staleness()
        assert report.is_stale
        assert 'src/new_file.py' in report.added
        assert 'src/existing.py' in report.modified
        assert 'src/to_delete.py' in report.deleted
        assert report.total_changes == 3

    def test_total_changes_sums_all_change_types(self, checker, file_scanner):
        """total_changes should sum all change types."""
        file_scanner.add_file('src/new1.py', mtime=1500.0, size=100)
        file_scanner.add_file('src/new2.py', mtime=1500.0, size=100)
        file_scanner.modify_file('src/existing.py', mtime=1500.0, size=200)
        file_scanner.remove_file('src/to_delete.py')

        report = checker.check_staleness()
        assert report.total_changes == 4  # 2 added + 1 modified + 1 deleted


class TestStalenessCheckerDebounce:
    """Test debounce behavior."""

    @pytest.fixture
    def time_provider(self):
        """Create fake time provider."""
        return FakeTimeProvider(initial_time=1000.0)

    @pytest.fixture
    def file_scanner(self):
        """Create fake file scanner."""
        return FakeFileScanner()

    @pytest.fixture
    def config(self, tmp_path):
        """Create test config with 300ms debounce and unique fingerprint file."""
        fingerprint_file = str(tmp_path / "fingerprints.json")
        return SemanticIndexConfig(debounce_ms=300, fingerprint_file=fingerprint_file)

    @pytest.fixture
    def checker(self, time_provider, file_scanner, config, tmp_path):
        """Create staleness checker with debounce enabled."""
        return StalenessChecker(
            root_path=tmp_path,
            config=config,
            time_provider=time_provider,
            file_scanner=file_scanner,
        )

    def test_debounce_prevents_rapid_checks(self, checker, file_scanner, time_provider):
        """Rapid checks within debounce period should return empty report."""
        # First check - should succeed
        file_scanner.add_file('src/new_file.py', mtime=1000.0, size=100)
        report1 = checker.check_staleness()
        assert report1.is_stale
        assert 'src/new_file.py' in report1.added

        # Add another file and check immediately (within debounce period)
        time_provider.advance(100)  # Only 100ms elapsed
        file_scanner.add_file('src/another_file.py', mtime=1100.0, size=200)
        report2 = checker.check_staleness()

        # Should return empty report due to debounce
        assert not report2.is_stale
        assert len(report2.added) == 0
        assert len(report2.modified) == 0
        assert len(report2.deleted) == 0

    def test_debounce_allows_check_after_settle_time(self, checker, file_scanner, time_provider):
        """Check after debounce period should succeed."""
        # First check
        file_scanner.add_file('src/file1.py', mtime=1000.0, size=100)
        report1 = checker.check_staleness()
        assert report1.is_stale

        # Wait for debounce period to elapse
        time_provider.advance(400)  # 400ms > 300ms debounce

        # Add another file and check
        file_scanner.add_file('src/file2.py', mtime=1400.0, size=200)
        report2 = checker.check_staleness()

        # Should detect new file after debounce period
        assert report2.is_stale
        assert 'src/file2.py' in report2.added

    def test_debounce_exact_boundary(self, checker, file_scanner, time_provider):
        """Check at exact debounce boundary should be allowed."""
        # First check
        file_scanner.add_file('src/file1.py', mtime=1000.0, size=100)
        report1 = checker.check_staleness()
        assert report1.is_stale

        # Wait exactly debounce period
        time_provider.advance(300)  # Exactly 300ms

        # Check again - should succeed (>= debounce_ms)
        file_scanner.add_file('src/file2.py', mtime=1300.0, size=200)
        report2 = checker.check_staleness()

        assert report2.is_stale
        assert 'src/file2.py' in report2.added


class TestStalenessCheckerUpdateFingerprints:
    """Test fingerprint update behavior."""

    @pytest.fixture
    def time_provider(self):
        """Create fake time provider."""
        return FakeTimeProvider(initial_time=1000.0)

    @pytest.fixture
    def file_scanner(self):
        """Create fake file scanner."""
        scanner = FakeFileScanner()
        scanner.add_file('src/file1.py', mtime=1000.0, size=100)
        scanner.add_file('src/file2.py', mtime=1000.0, size=200)
        return scanner

    @pytest.fixture
    def config(self, tmp_path):
        """Create test config with no debounce and unique fingerprint file."""
        fingerprint_file = str(tmp_path / "fingerprints.json")
        return SemanticIndexConfig(debounce_ms=0, fingerprint_file=fingerprint_file)

    @pytest.fixture
    def checker(self, time_provider, file_scanner, config, tmp_path):
        """Create staleness checker."""
        return StalenessChecker(
            root_path=tmp_path,
            config=config,
            time_provider=time_provider,
            file_scanner=file_scanner,
        )

    def test_update_fingerprints_establishes_baseline(self, checker, file_scanner):
        """update_fingerprints should establish baseline for staleness checks."""
        # Initial check shows all files as new
        report1 = checker.check_staleness()
        assert len(report1.added) == 2

        # Update fingerprints
        checker.update_fingerprints()

        # Now files should not be detected as new
        report2 = checker.check_staleness()
        assert not report2.is_stale
        assert len(report2.added) == 0

    def test_update_fingerprints_captures_current_state(self, checker, file_scanner):
        """update_fingerprints should capture current file state."""
        # Update fingerprints
        checker.update_fingerprints()

        # Verify fingerprints were captured (mtime in nanoseconds)
        fingerprints = checker.get_fingerprints()
        assert len(fingerprints) == 2
        assert 'src/file1.py' in fingerprints
        assert fingerprints['src/file1.py'] == (1_000_000_000_000, 100)  # 1000.0 sec in ns
        assert 'src/file2.py' in fingerprints
        assert fingerprints['src/file2.py'] == (1_000_000_000_000, 200)  # 1000.0 sec in ns

    def test_update_fingerprints_resets_baseline_after_changes(self, checker, file_scanner):
        """update_fingerprints should reset baseline after detecting changes."""
        # Establish baseline
        checker.update_fingerprints()

        # Modify file
        file_scanner.modify_file('src/file1.py', mtime=2000.0, size=150)

        # Detect change
        report1 = checker.check_staleness()
        assert 'src/file1.py' in report1.modified

        # Update fingerprints to new baseline
        checker.update_fingerprints()

        # File should no longer be detected as modified
        report2 = checker.check_staleness()
        assert not report2.is_stale
        assert len(report2.modified) == 0

        # Verify new fingerprint (mtime in nanoseconds)
        fingerprints = checker.get_fingerprints()
        assert fingerprints['src/file1.py'] == (2_000_000_000_000, 150)  # 2000.0 sec in ns


class TestStalenessCheckerPerformance:
    """Test performance characteristics."""

    @pytest.fixture
    def time_provider(self):
        """Create fake time provider."""
        return FakeTimeProvider(initial_time=1000.0)

    @pytest.fixture
    def file_scanner(self):
        """Create fake file scanner with many files."""
        scanner = FakeFileScanner()
        # Add 1000 files
        for i in range(1000):
            scanner.add_file(f'src/file_{i}.py', mtime=1000.0 + i, size=100 + i)
        return scanner

    @pytest.fixture
    def config(self, tmp_path):
        """Create test config with no debounce and unique fingerprint file."""
        fingerprint_file = str(tmp_path / "fingerprints.json")
        return SemanticIndexConfig(debounce_ms=0, fingerprint_file=fingerprint_file)

    @pytest.fixture
    def checker(self, time_provider, file_scanner, config, tmp_path):
        """Create staleness checker with many files."""
        return StalenessChecker(
            root_path=tmp_path,
            config=config,
            time_provider=time_provider,
            file_scanner=file_scanner,
        )

    def test_fingerprinting_handles_large_file_count(self, checker):
        """Fingerprinting should handle 1000 files efficiently."""
        import time

        start = time.perf_counter()
        checker.update_fingerprints()
        end = time.perf_counter()

        elapsed_ms = (end - start) * 1000

        # Should complete in reasonable time (< 100ms for test doubles)
        # This tests that the algorithm is O(n) not O(n^2)
        assert elapsed_ms < 100

        # Verify all files were fingerprinted
        fingerprints = checker.get_fingerprints()
        assert len(fingerprints) == 1000

    def test_staleness_check_handles_large_file_count(self, checker, file_scanner):
        """Staleness check should handle 1000 files efficiently."""
        import time

        # Establish baseline
        checker.update_fingerprints()

        # Modify a few files
        file_scanner.modify_file('src/file_100.py', mtime=2000.0, size=200)
        file_scanner.modify_file('src/file_500.py', mtime=2000.0, size=200)

        # Check staleness
        start = time.perf_counter()
        report = checker.check_staleness()
        end = time.perf_counter()

        elapsed_ms = (end - start) * 1000

        # Should complete in reasonable time (< 100ms for test doubles)
        assert elapsed_ms < 100

        # Verify correct files detected
        assert len(report.modified) == 2
        assert 'src/file_100.py' in report.modified
        assert 'src/file_500.py' in report.modified


class TestStalenessIntegration:
    """Integration tests for staleness-triggered re-indexing."""

    @pytest.fixture
    def time_provider(self):
        """Create fake time provider."""
        return FakeTimeProvider(initial_time=1000.0)

    @pytest.fixture
    def file_scanner(self):
        """Create fake file scanner with initial files."""
        scanner = FakeFileScanner()
        scanner.add_file('src/existing.py', mtime=1000.0, size=100)
        return scanner

    @pytest.fixture
    def config(self, tmp_path):
        """Create test config."""
        fingerprint_file = str(tmp_path / "fingerprints.json")
        return SemanticIndexConfig(debounce_ms=0, fingerprint_file=fingerprint_file)

    @pytest.fixture
    def checker(self, time_provider, file_scanner, config, tmp_path):
        """Create staleness checker with baseline established."""
        checker = StalenessChecker(
            root_path=tmp_path,
            config=config,
            time_provider=time_provider,
            file_scanner=file_scanner,
        )
        checker.update_fingerprints()
        return checker

    def test_stale_triggers_blocking_reindex(self, checker, file_scanner):
        """
        Integration test: staleness detection should trigger blocking re-index.

        Verifies the full flow:
        1. File modification detected as stale
        2. StalenessReport contains correct changed files
        3. Report can be used to trigger re-indexing
        """
        # Modify a file
        file_scanner.modify_file('src/existing.py', mtime=2000.0, size=200)

        # Add a new file
        file_scanner.add_file('src/new_file.py', mtime=2000.0, size=150)

        # Check staleness
        report = checker.check_staleness()

        # Verify staleness detected
        assert report.is_stale
        assert 'src/existing.py' in report.modified
        assert 'src/new_file.py' in report.added

        # Simulate what ensure_file_index would do:
        # Get changed files for re-indexing
        changed_files = report.added | report.modified
        assert len(changed_files) == 2
        assert 'src/existing.py' in changed_files
        assert 'src/new_file.py' in changed_files

        # After re-indexing, update fingerprints
        checker.update_fingerprints()

        # Verify no longer stale
        report2 = checker.check_staleness()
        assert not report2.is_stale

    def test_stale_deleted_files_detected_for_removal(self, checker, file_scanner):
        """
        Integration test: deleted files should be detected for index removal.

        Verifies:
        1. File deletion detected as stale
        2. Deleted files available in report for index cleanup
        """
        # Delete a file
        file_scanner.remove_file('src/existing.py')

        # Check staleness
        report = checker.check_staleness()

        # Verify deletion detected
        assert report.is_stale
        assert 'src/existing.py' in report.deleted

        # Simulate what ensure_file_index would do:
        # Pass deleted files to remove_deleted_files
        deleted_files = report.deleted
        assert len(deleted_files) == 1
        assert 'src/existing.py' in deleted_files

        # After removal, update fingerprints
        checker.update_fingerprints()

        # Verify no longer stale
        report2 = checker.check_staleness()
        assert not report2.is_stale


class TestStalenessReport:
    """Test StalenessReport dataclass behavior."""

    def test_is_stale_true_when_files_added(self):
        """is_stale should be True when files added."""
        report = StalenessReport(added={'file.py'}, modified=set(), deleted=set())
        assert report.is_stale

    def test_is_stale_true_when_files_modified(self):
        """is_stale should be True when files modified."""
        report = StalenessReport(added=set(), modified={'file.py'}, deleted=set())
        assert report.is_stale

    def test_is_stale_true_when_files_deleted(self):
        """is_stale should be True when files deleted."""
        report = StalenessReport(added=set(), modified=set(), deleted={'file.py'})
        assert report.is_stale

    def test_is_stale_false_when_no_changes(self):
        """is_stale should be False when no changes."""
        report = StalenessReport(added=set(), modified=set(), deleted=set())
        assert not report.is_stale

    def test_total_changes_sums_all_types(self):
        """total_changes should sum all change types."""
        report = StalenessReport(
            added={'file1.py', 'file2.py'},
            modified={'file3.py'},
            deleted={'file4.py', 'file5.py', 'file6.py'}
        )
        assert report.total_changes == 6  # 2 + 1 + 3
