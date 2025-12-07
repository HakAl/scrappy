"""
Tests for ThresholdDecisionMaker.

Validates decision logic for semantic search indexing based on thresholds.
"""

from datetime import datetime, timedelta
import pytest

from src.scrappy.context.protocols import (
    IndexState,
    ChangeMetrics,
    IndexingDecision,
)
from src.scrappy.context.semantic.config import SemanticIndexConfig
from src.scrappy.context.semantic.decision import ThresholdDecisionMaker


# --- Fixtures ---


@pytest.fixture
def config() -> SemanticIndexConfig:
    """Create test config with known thresholds."""
    return SemanticIndexConfig(
        show_progress_chunks=20,
        max_index_age_days=7,
        reindex_chunk_change_percent=0.25,
    )


@pytest.fixture
def decision_maker(config: SemanticIndexConfig) -> ThresholdDecisionMaker:
    """Create decision maker with test config."""
    return ThresholdDecisionMaker(config)


@pytest.fixture
def recent_state() -> IndexState:
    """Create a recent index state (1 day old)."""
    return IndexState(
        last_indexed=datetime.now() - timedelta(days=1),
        total_chunks=100,
        total_files=10,
        index_version="1.0.0",
        file_hashes={"file1.py": "hash1", "file2.py": "hash2"},
    )


@pytest.fixture
def old_state() -> IndexState:
    """Create an old index state (10 days old)."""
    return IndexState(
        last_indexed=datetime.now() - timedelta(days=10),
        total_chunks=100,
        total_files=10,
        index_version="1.0.0",
        file_hashes={"file1.py": "hash1", "file2.py": "hash2"},
    )


@pytest.fixture
def no_changes() -> ChangeMetrics:
    """Create metrics with no changes."""
    return ChangeMetrics(
        new_files=0,
        modified_files=0,
        deleted_files=0,
        estimated_chunks=0,
        total_bytes_changed=0,
    )


@pytest.fixture
def small_changes() -> ChangeMetrics:
    """Create metrics with small changes (10 chunks)."""
    return ChangeMetrics(
        new_files=1,
        modified_files=0,
        deleted_files=0,
        estimated_chunks=10,
        total_bytes_changed=4000,
    )


@pytest.fixture
def major_changes() -> ChangeMetrics:
    """Create metrics with major changes (30 chunks = 30% of 100)."""
    return ChangeMetrics(
        new_files=5,
        modified_files=2,
        deleted_files=0,
        estimated_chunks=30,
        total_bytes_changed=12000,
    )


# --- Test: decide() - FULL_INDEX cases ---


def test_full_index_when_no_saved_state(
    decision_maker: ThresholdDecisionMaker,
    small_changes: ChangeMetrics,
) -> None:
    """First run with no saved state should trigger full index."""
    decision = decision_maker.decide(
        saved_state=None,
        current_metrics=small_changes,
    )
    assert decision == IndexingDecision.FULL_INDEX


def test_full_index_when_state_too_old(
    decision_maker: ThresholdDecisionMaker,
    old_state: IndexState,
    small_changes: ChangeMetrics,
) -> None:
    """State older than max_index_age_days should trigger full index."""
    decision = decision_maker.decide(
        saved_state=old_state,
        current_metrics=small_changes,
    )
    assert decision == IndexingDecision.FULL_INDEX


def test_full_index_when_major_chunk_change(
    decision_maker: ThresholdDecisionMaker,
    recent_state: IndexState,
    major_changes: ChangeMetrics,
) -> None:
    """Chunk change exceeding threshold should trigger full index.

    30 estimated chunks / 100 total chunks = 30% change.
    Threshold is 25%, so this should trigger full re-index.
    """
    decision = decision_maker.decide(
        saved_state=recent_state,
        current_metrics=major_changes,
    )
    assert decision == IndexingDecision.FULL_INDEX


def test_full_index_when_chunk_change_at_threshold_boundary(
    decision_maker: ThresholdDecisionMaker,
    recent_state: IndexState,
) -> None:
    """Chunk change exactly at threshold should trigger full index."""
    # 26 chunks / 100 = 26%, just over 25% threshold
    boundary_metrics = ChangeMetrics(
        new_files=2,
        modified_files=1,
        deleted_files=0,
        estimated_chunks=26,
        total_bytes_changed=10400,
    )

    decision = decision_maker.decide(
        saved_state=recent_state,
        current_metrics=boundary_metrics,
    )
    assert decision == IndexingDecision.FULL_INDEX


def test_full_index_when_previous_chunks_zero_and_new_chunks_exist(
    decision_maker: ThresholdDecisionMaker,
    small_changes: ChangeMetrics,
) -> None:
    """Empty previous index with new chunks should trigger full index."""
    empty_state = IndexState(
        last_indexed=datetime.now() - timedelta(days=1),
        total_chunks=0,  # Empty index
        total_files=0,
        index_version="1.0.0",
        file_hashes={},
    )

    decision = decision_maker.decide(
        saved_state=empty_state,
        current_metrics=small_changes,
    )
    assert decision == IndexingDecision.FULL_INDEX


# --- Test: decide() - INCREMENTAL_UPDATE cases ---


def test_incremental_when_small_changes(
    decision_maker: ThresholdDecisionMaker,
    recent_state: IndexState,
    small_changes: ChangeMetrics,
) -> None:
    """Small changes to recent index should trigger incremental update.

    10 estimated chunks / 100 total chunks = 10% change.
    Below 25% threshold, so incremental update.
    """
    decision = decision_maker.decide(
        saved_state=recent_state,
        current_metrics=small_changes,
    )
    assert decision == IndexingDecision.INCREMENTAL_UPDATE


def test_incremental_when_just_below_threshold(
    decision_maker: ThresholdDecisionMaker,
    recent_state: IndexState,
) -> None:
    """Changes just below threshold should be incremental.

    24 chunks / 100 = 24%, just below 25% threshold.
    """
    below_threshold = ChangeMetrics(
        new_files=2,
        modified_files=1,
        deleted_files=0,
        estimated_chunks=24,
        total_bytes_changed=9600,
    )

    decision = decision_maker.decide(
        saved_state=recent_state,
        current_metrics=below_threshold,
    )
    assert decision == IndexingDecision.INCREMENTAL_UPDATE


def test_incremental_with_one_chunk_change(
    decision_maker: ThresholdDecisionMaker,
    recent_state: IndexState,
) -> None:
    """Single chunk change should be incremental."""
    tiny_change = ChangeMetrics(
        new_files=1,
        modified_files=0,
        deleted_files=0,
        estimated_chunks=1,
        total_bytes_changed=400,
    )

    decision = decision_maker.decide(
        saved_state=recent_state,
        current_metrics=tiny_change,
    )
    assert decision == IndexingDecision.INCREMENTAL_UPDATE


# --- Test: decide() - SKIP cases ---


def test_skip_when_no_changes(
    decision_maker: ThresholdDecisionMaker,
    recent_state: IndexState,
    no_changes: ChangeMetrics,
) -> None:
    """No changes to recent index should skip indexing."""
    decision = decision_maker.decide(
        saved_state=recent_state,
        current_metrics=no_changes,
    )
    assert decision == IndexingDecision.SKIP


def test_skip_when_zero_estimated_chunks(
    decision_maker: ThresholdDecisionMaker,
    recent_state: IndexState,
) -> None:
    """Zero estimated chunks should skip, even if files changed."""
    # Files might have changed but resulted in no new chunks
    # (e.g., whitespace-only changes)
    metrics = ChangeMetrics(
        new_files=0,
        modified_files=1,
        deleted_files=0,
        estimated_chunks=0,  # Key: no chunk changes
        total_bytes_changed=0,
    )

    decision = decision_maker.decide(
        saved_state=recent_state,
        current_metrics=metrics,
    )
    assert decision == IndexingDecision.SKIP


# --- Test: should_show_progress() ---


def test_should_show_progress_above_threshold(
    decision_maker: ThresholdDecisionMaker,
) -> None:
    """Progress should show when chunks exceed threshold.

    Threshold is 20, so 21 chunks should show progress.
    """
    metrics = ChangeMetrics(
        new_files=5,
        modified_files=0,
        deleted_files=0,
        estimated_chunks=21,
        total_bytes_changed=8400,
    )

    assert decision_maker.should_show_progress(metrics) is True


def test_should_not_show_progress_below_threshold(
    decision_maker: ThresholdDecisionMaker,
) -> None:
    """Progress should not show when chunks below threshold.

    Threshold is 20, so 19 chunks should not show progress.
    """
    metrics = ChangeMetrics(
        new_files=2,
        modified_files=0,
        deleted_files=0,
        estimated_chunks=19,
        total_bytes_changed=7600,
    )

    assert decision_maker.should_show_progress(metrics) is False


def test_should_not_show_progress_at_threshold(
    decision_maker: ThresholdDecisionMaker,
) -> None:
    """Progress should not show exactly at threshold.

    Uses > comparison, not >=, so 20 == 20 returns False.
    """
    metrics = ChangeMetrics(
        new_files=2,
        modified_files=0,
        deleted_files=0,
        estimated_chunks=20,  # Exactly at threshold
        total_bytes_changed=8000,
    )

    assert decision_maker.should_show_progress(metrics) is False


def test_should_not_show_progress_zero_chunks(
    decision_maker: ThresholdDecisionMaker,
    no_changes: ChangeMetrics,
) -> None:
    """No chunks should not show progress."""
    assert decision_maker.should_show_progress(no_changes) is False


def test_should_show_progress_large_workload(
    decision_maker: ThresholdDecisionMaker,
) -> None:
    """Large workload should definitely show progress."""
    large_metrics = ChangeMetrics(
        new_files=50,
        modified_files=20,
        deleted_files=5,
        estimated_chunks=500,
        total_bytes_changed=200000,
    )

    assert decision_maker.should_show_progress(large_metrics) is True


# --- Test: Edge Cases ---


def test_state_exactly_at_max_age(
    decision_maker: ThresholdDecisionMaker,
    small_changes: ChangeMetrics,
) -> None:
    """State just under max age boundary should not trigger full index.

    Uses > comparison, so age < max_age should be incremental.
    To avoid timing issues, use days=7 minus 1 hour.
    """
    just_under_max_age = IndexState(
        last_indexed=datetime.now() - timedelta(days=7, hours=-1),
        total_chunks=100,
        total_files=10,
        index_version="1.0.0",
        file_hashes={"file1.py": "hash1"},
    )

    decision = decision_maker.decide(
        saved_state=just_under_max_age,
        current_metrics=small_changes,
    )
    # Should be incremental since age is not > max_age
    assert decision == IndexingDecision.INCREMENTAL_UPDATE


def test_state_one_second_over_max_age(
    decision_maker: ThresholdDecisionMaker,
    small_changes: ChangeMetrics,
) -> None:
    """State just over max age should trigger full index."""
    just_over_max_age = IndexState(
        last_indexed=datetime.now() - timedelta(days=7, seconds=1),
        total_chunks=100,
        total_files=10,
        index_version="1.0.0",
        file_hashes={"file1.py": "hash1"},
    )

    decision = decision_maker.decide(
        saved_state=just_over_max_age,
        current_metrics=small_changes,
    )
    assert decision == IndexingDecision.FULL_INDEX


def test_custom_config_thresholds() -> None:
    """Decision maker should respect custom config values."""
    custom_config = SemanticIndexConfig(
        show_progress_chunks=100,  # High threshold
        max_index_age_days=1,      # Short max age
        reindex_chunk_change_percent=0.5,  # High change threshold
    )
    decision_maker = ThresholdDecisionMaker(custom_config)

    # 1 day old state should be too old with max_age_days=1
    state_1_day_old = IndexState(
        last_indexed=datetime.now() - timedelta(days=1, seconds=1),
        total_chunks=100,
        total_files=10,
        index_version="1.0.0",
        file_hashes={},
    )

    small_change = ChangeMetrics(
        new_files=1,
        modified_files=0,
        deleted_files=0,
        estimated_chunks=10,
        total_bytes_changed=4000,
    )

    decision = decision_maker.decide(state_1_day_old, small_change)
    assert decision == IndexingDecision.FULL_INDEX

    # 99 chunks should not show progress with threshold=100
    assert decision_maker.should_show_progress(
        ChangeMetrics(
            new_files=0,
            modified_files=0,
            deleted_files=0,
            estimated_chunks=99,
            total_bytes_changed=0,
        )
    ) is False

    # 101 chunks should show progress
    assert decision_maker.should_show_progress(
        ChangeMetrics(
            new_files=0,
            modified_files=0,
            deleted_files=0,
            estimated_chunks=101,
            total_bytes_changed=0,
        )
    ) is True
