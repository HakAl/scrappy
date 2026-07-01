"""
Tests proving that fingerprinting runs unnecessarily on every app start.

These tests FAIL with current code and should PASS after the fix.

The bug: SemanticSearchManager.index_files() calls get_file_hashes() (expensive)
BEFORE checking if indexing can be skipped. This means every app start:
1. Scans filesystem for all files
2. Computes MD5 hash of ALL source files (reads every file from disk)
3. THEN decides "nothing changed, skip indexing"

The fix: Add early bailout before expensive fingerprinting when:
- Saved state exists
- State is not too old
- Quick staleness check passes
"""
import pytest
from datetime import datetime, timedelta
from pathlib import Path

from scrappy.context.semantic_manager import SemanticSearchManager
from scrappy.context.protocols import IndexState, IndexingDecision


class SpyFileCollector:
    """
    File collector that tracks which methods are called and in what order.

    Used to prove that expensive operations happen even when they shouldn't.
    """

    def __init__(self, files=None):
        self._files = files or {"test.py": "print('hello')"}
        self.call_log = []  # Track order of calls
        self.collect_file_paths_called = False
        self.get_file_hashes_called = False
        self.get_file_sizes_called = False
        self.collect_files_batched_called = False

    def collect_files(self):
        self.call_log.append("collect_files")
        return self._files

    def collect_files_batched(self, batch_size=50):
        self.call_log.append("collect_files_batched")
        self.collect_files_batched_called = True
        yield self._files

    def collect_file_paths(self):
        """Scans filesystem - moderately expensive."""
        self.call_log.append("collect_file_paths")
        self.collect_file_paths_called = True
        return [Path(p) for p in self._files.keys()]

    def get_file_hashes(self, files):
        """Hashes all files - EXPENSIVE operation that reads every file."""
        self.call_log.append("get_file_hashes")
        self.get_file_hashes_called = True
        return {str(f): f"hash_{f}" for f in files}

    def get_file_sizes(self, files):
        """Gets file sizes - moderately expensive."""
        self.call_log.append("get_file_sizes")
        self.get_file_sizes_called = True
        return {str(f): 100 for f in files}


class MockSearchProvider:
    """Mock search provider that tracks indexing calls."""

    def __init__(self):
        self._indexed = True  # Already indexed
        self._files_indexed = {}
        self.index_files_called = False

    def is_indexed(self):
        return self._indexed

    def index_files(self, files, is_batch=False):
        self.index_files_called = True
        self._files_indexed.update(files)

    def set_progress_reporter(self, reporter):
        pass

    def save_index_state(self, state_manager):
        pass


class MockStateManager:
    """Mock state manager with configurable saved state."""

    def __init__(self, saved_state=None):
        self._state = saved_state
        self.load_called = False
        self.save_called = False

    def load(self):
        self.load_called = True
        return self._state

    def save(self, state):
        self.save_called = True
        self._state = state


class MockDecisionMaker:
    """Mock decision maker with configurable decision."""

    def __init__(self, decision=IndexingDecision.SKIP):
        self._decision = decision
        self.decide_called = False
        self.received_state = None
        self.received_metrics = None

    def decide(self, saved_state, current_metrics):
        self.decide_called = True
        self.received_state = saved_state
        self.received_metrics = current_metrics
        return self._decision


class MockStalenessChecker:
    """
    Mock staleness checker for testing early bailout behavior.

    Configurable to return True (changes detected) or False (no changes).
    """

    def __init__(self, has_changes=False):
        """
        Args:
            has_changes: If True, quick_check() returns True (changes detected).
                        If False, quick_check() returns False (no changes - skip indexing).
        """
        self._has_changes = has_changes
        self.quick_check_called = False
        self.update_fingerprints_called = False
        self.has_fingerprints_called = False

    def quick_check(self) -> bool:
        """
        Returns True if changes detected, False if no changes.

        When this returns False, index_files() should bail out early
        without doing expensive fingerprinting.
        """
        self.quick_check_called = True
        return self._has_changes

    def has_fingerprints(self) -> bool:
        """Check if fingerprints exist."""
        self.has_fingerprints_called = True
        return True

    def update_fingerprints(self, staleness_report=None) -> None:
        """Update stored fingerprints."""
        self.update_fingerprints_called = True


class MockInitializer:
    """Mock initializer that immediately completes with a provider."""

    def __init__(self, provider):
        self._provider = provider
        self._complete = True

    def start(self):
        pass

    def is_complete(self):
        return self._complete

    def get_result(self):
        return self._provider

    def get_error(self):
        return None

    def get_status(self):
        return "Complete"


def create_fresh_index_state(file_hashes=None):
    """Create a fresh IndexState that was just indexed (not stale)."""
    return IndexState(
        last_indexed=datetime.now() - timedelta(minutes=5),  # 5 mins ago - fresh
        total_chunks=100,
        total_files=10,
        index_version="1.0",
        file_hashes=file_hashes or {"test.py": "hash_test.py"},
    )


class TestFingerprintingOptimization:
    """
    Tests proving that expensive fingerprinting should be skipped when index is fresh.

    These tests document the expected behavior after the fix.
    Currently they FAIL because the bug exists.
    """

    @pytest.mark.unit
    def test_get_file_hashes_not_called_when_decision_is_skip(self, temp_project_dir):
        """
        CRITICAL: get_file_hashes() should NOT be called if we're going to skip anyway.

        Current behavior (BUG): get_file_hashes() is called BEFORE decision is made
        Expected behavior: Early bailout BEFORE expensive hashing when skip is likely

        This test FAILS with current code, PASSES after fix.
        """
        # Setup: Fresh index state exists, staleness checker says no changes
        saved_state = create_fresh_index_state()
        state_manager = MockStateManager(saved_state=saved_state)
        decision_maker = MockDecisionMaker(decision=IndexingDecision.SKIP)
        staleness_checker = MockStalenessChecker(has_changes=False)  # No changes detected

        provider = MockSearchProvider()
        initializer = MockInitializer(provider)

        manager = SemanticSearchManager(
            project_path=temp_project_dir,
            initializer=initializer,
            state_manager=state_manager,
            decision_maker=decision_maker,
            staleness_checker=staleness_checker,
        )

        spy_collector = SpyFileCollector()
        manager.index_files(spy_collector)

        # ASSERTION: Quick check should be called for early bailout
        assert staleness_checker.quick_check_called, (
            "quick_check() should be called to detect changes quickly"
        )

        # ASSERTION: If quick_check returns False (no changes), skip expensive ops
        assert not spy_collector.get_file_hashes_called, (
            "BUG: get_file_hashes() was called even though quick_check found no changes. "
            "Expensive fingerprinting should be skipped when index is fresh and unchanged."
        )

    @pytest.mark.unit
    def test_expensive_operations_skipped_when_index_fresh_and_unchanged(self, temp_project_dir):
        """
        When saved state is fresh and files haven't changed, skip ALL expensive ops.

        Expected call sequence for fresh unchanged index:
        1. Load saved state (cheap)
        2. Quick staleness check (cheap)
        3. Return early - no hashing, no indexing

        This test FAILS with current code, PASSES after fix.
        """
        saved_state = create_fresh_index_state()
        state_manager = MockStateManager(saved_state=saved_state)
        decision_maker = MockDecisionMaker(decision=IndexingDecision.SKIP)
        staleness_checker = MockStalenessChecker(has_changes=False)  # No changes detected

        provider = MockSearchProvider()
        initializer = MockInitializer(provider)

        manager = SemanticSearchManager(
            project_path=temp_project_dir,
            initializer=initializer,
            state_manager=state_manager,
            decision_maker=decision_maker,
            staleness_checker=staleness_checker,
        )

        spy_collector = SpyFileCollector()
        manager.index_files(spy_collector)

        # With fresh unchanged index, none of these expensive ops should happen
        assert not spy_collector.get_file_hashes_called, (
            "get_file_hashes should not be called for fresh unchanged index"
        )
        assert not spy_collector.collect_files_batched_called, (
            "collect_files_batched should not be called when skipping"
        )
        assert not provider.index_files_called, (
            "provider.index_files should not be called when skipping"
        )

    @pytest.mark.unit
    def test_quick_check_used_for_early_bailout(self, temp_project_dir):
        """
        Verify that quick_check() is used for early bailout when no changes detected.

        After the fix, the call sequence should be:
        1. Load saved state
        2. Call quick_check() - returns False (no changes)
        3. Return early - no hashing, no decision maker called

        This test PASSES after fix.
        """
        saved_state = create_fresh_index_state()
        state_manager = MockStateManager(saved_state=saved_state)
        decision_maker = MockDecisionMaker(decision=IndexingDecision.SKIP)
        staleness_checker = MockStalenessChecker(has_changes=False)  # No changes

        provider = MockSearchProvider()
        initializer = MockInitializer(provider)

        manager = SemanticSearchManager(
            project_path=temp_project_dir,
            initializer=initializer,
            state_manager=state_manager,
            decision_maker=decision_maker,
            staleness_checker=staleness_checker,
        )

        spy_collector = SpyFileCollector()
        manager.index_files(spy_collector)

        # Quick check should be called
        assert staleness_checker.quick_check_called, (
            "quick_check() should be called for early bailout"
        )

        # With no changes detected, we should NOT do expensive operations
        assert not spy_collector.get_file_hashes_called, (
            "get_file_hashes should not be called when quick_check returns False"
        )

        # Decision maker should NOT be called (early bailout skips it)
        assert not decision_maker.decide_called, (
            "Decision maker should not be called when quick_check returns False (early bailout)"
        )

    @pytest.mark.unit
    def test_hashing_still_happens_when_needed_for_incremental(self, temp_project_dir):
        """
        Ensure hashing DOES happen when quick_check detects changes.

        When quick_check() returns True (changes detected), we proceed with
        full fingerprinting to determine what changed.

        This test should PASS with both current and fixed code.
        """
        saved_state = create_fresh_index_state()
        state_manager = MockStateManager(saved_state=saved_state)
        # Decision is INCREMENTAL_UPDATE - we need to know what changed
        decision_maker = MockDecisionMaker(decision=IndexingDecision.INCREMENTAL_UPDATE)
        # Quick check detects changes - proceed to full verification
        staleness_checker = MockStalenessChecker(has_changes=True)

        provider = MockSearchProvider()
        initializer = MockInitializer(provider)

        manager = SemanticSearchManager(
            project_path=temp_project_dir,
            initializer=initializer,
            state_manager=state_manager,
            decision_maker=decision_maker,
            staleness_checker=staleness_checker,
        )

        spy_collector = SpyFileCollector()
        manager.index_files(spy_collector)

        # Quick check detected changes, so we should proceed to full verification
        assert staleness_checker.quick_check_called, (
            "quick_check() should be called first"
        )

        # For incremental updates, we DO need to hash to find changed files
        # This is acceptable - the optimization only applies when quick_check returns False
        assert spy_collector.get_file_hashes_called or spy_collector.collect_files_batched_called, (
            "For INCREMENTAL_UPDATE, we need either hashes or actual indexing"
        )



class TestStartupFingerprintingBehavior:
    """
    Tests simulating actual app startup behavior.

    These tests prove that every app start triggers expensive fingerprinting
    even when the index is completely up-to-date.
    """

    @pytest.mark.unit
    def test_simulated_app_restart_with_fresh_index(self, temp_project_dir):
        """
        Simulate app restart when index was just built.

        Scenario:
        1. User runs app, index is built
        2. User closes app
        3. User reopens app immediately (no file changes)
        4. FIXED: quick_check() returns False, early bailout, no hashing

        This test PASSES after fix.
        """
        # Simulate state from previous run (just indexed, nothing changed)
        saved_state = create_fresh_index_state(
            file_hashes={
                "src/main.py": "abc123",
                "src/utils.py": "def456",
                "tests/test_main.py": "ghi789",
            }
        )

        state_manager = MockStateManager(saved_state=saved_state)
        decision_maker = MockDecisionMaker(decision=IndexingDecision.SKIP)
        staleness_checker = MockStalenessChecker(has_changes=False)  # No changes since last run

        provider = MockSearchProvider()
        initializer = MockInitializer(provider)

        # This simulates what happens on app start
        manager = SemanticSearchManager(
            project_path=temp_project_dir,
            initializer=initializer,
            state_manager=state_manager,
            decision_maker=decision_maker,
            staleness_checker=staleness_checker,
        )

        spy_collector = SpyFileCollector(files={
            "src/main.py": "# main code",
            "src/utils.py": "# utils code",
            "tests/test_main.py": "# test code",
        })

        # This is called on app startup via background init callback
        manager.index_files(spy_collector)

        # FIXED: With staleness checker, we use quick_check() for early bailout
        assert staleness_checker.quick_check_called, (
            "quick_check() should be called for early bailout"
        )
        assert not spy_collector.get_file_hashes_called, (
            "App restart with unchanged files should NOT trigger fingerprinting. "
            f"Operations performed: {spy_collector.call_log}"
        )

    @pytest.mark.unit
    def test_multiple_restarts_no_wasted_work(self, temp_project_dir):
        """
        Verify that multiple restarts do NOT trigger redundant hashing.

        If a user restarts the app 10 times without changing files,
        we should use quick_check() and skip hashing every time.

        This test PASSES after fix.
        """
        saved_state = create_fresh_index_state()

        provider = MockSearchProvider()
        initializer = MockInitializer(provider)

        hash_call_count = 0
        quick_check_count = 0

        # Simulate 3 app restarts
        for restart_num in range(3):
            state_manager = MockStateManager(saved_state=saved_state)
            decision_maker = MockDecisionMaker(decision=IndexingDecision.SKIP)
            staleness_checker = MockStalenessChecker(has_changes=False)  # No changes

            manager = SemanticSearchManager(
                project_path=temp_project_dir,
                initializer=initializer,
                state_manager=state_manager,
                decision_maker=decision_maker,
                staleness_checker=staleness_checker,
            )

            spy_collector = SpyFileCollector()
            manager.index_files(spy_collector)

            if spy_collector.get_file_hashes_called:
                hash_call_count += 1
            if staleness_checker.quick_check_called:
                quick_check_count += 1

        # FIXED: quick_check should be called every time (fast)
        assert quick_check_count == 3, (
            f"quick_check should be called on every restart, got {quick_check_count}"
        )

        # FIXED: hash_call_count should be 0 (skip hashing when unchanged)
        assert hash_call_count == 0, (
            f"Files were hashed {hash_call_count} times across 3 restarts "
            f"even though nothing changed. Expected 0 hash operations."
        )
