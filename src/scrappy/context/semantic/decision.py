"""
Decision logic for semantic search indexing.

Single responsibility: Make indexing decisions based on thresholds and metrics.
"""

from datetime import datetime, timedelta
from typing import Optional

from ..protocols import (
    IndexState,
    ChangeMetrics,
    IndexingDecision,
    IndexingDecisionProtocol,
)
from .config import SemanticIndexConfig


class ThresholdDecisionMaker:
    """
    Makes indexing decisions based on configurable thresholds.

    Single responsibility: Decide whether to perform full index, incremental update, or skip.

    Decision logic:
    - FULL_INDEX if:
        * No saved state exists (first run)
        * Saved state older than max_index_age_days
        * Chunk count changed by more than reindex_chunk_change_percent
    - INCREMENTAL_UPDATE if:
        * Saved state exists and is recent
        * Changes detected (estimated_chunks > 0)
    - SKIP if:
        * Saved state exists and is recent
        * No changes detected
    """

    def __init__(self, config: SemanticIndexConfig) -> None:
        """
        Initialize decision maker with configuration.

        Args:
            config: Configuration containing threshold values
        """
        self._config = config

    def decide(
        self,
        saved_state: Optional[IndexState],
        current_metrics: ChangeMetrics,
    ) -> IndexingDecision:
        """
        Decide what indexing action to take.

        Args:
            saved_state: Previously saved index state (None if first run)
            current_metrics: Metrics about current changes

        Returns:
            IndexingDecision enum value (FULL_INDEX, INCREMENTAL_UPDATE, or SKIP)
        """
        # First run: always full index
        if saved_state is None:
            return IndexingDecision.FULL_INDEX

        # Check if state is too old
        if self._is_state_too_old(saved_state):
            return IndexingDecision.FULL_INDEX

        # Check if chunk count changed significantly
        if self._chunk_change_exceeds_threshold(saved_state, current_metrics):
            return IndexingDecision.FULL_INDEX

        # No changes detected
        if current_metrics.estimated_chunks == 0:
            return IndexingDecision.SKIP

        # State exists, recent, and changes detected
        return IndexingDecision.INCREMENTAL_UPDATE

    def should_show_progress(self, metrics: ChangeMetrics) -> bool:
        """
        Determine if progress bar should be shown based on estimated work.

        Args:
            metrics: Change metrics containing estimated chunk count

        Returns:
            True if estimated chunks exceed show_progress_chunks threshold
        """
        return metrics.estimated_chunks > self._config.show_progress_chunks

    def _is_state_too_old(self, state: IndexState) -> bool:
        """
        Check if saved state is older than max_index_age_days.

        Args:
            state: Index state to check

        Returns:
            True if state is too old and requires re-indexing
        """
        max_age = timedelta(days=self._config.max_index_age_days)
        age = datetime.now() - state.last_indexed
        return age > max_age

    def _chunk_change_exceeds_threshold(
        self,
        state: IndexState,
        metrics: ChangeMetrics,
    ) -> bool:
        """
        Check if chunk count changed by more than threshold percentage.

        Args:
            state: Previous index state
            metrics: Current change metrics

        Returns:
            True if chunk change exceeds reindex_chunk_change_percent
        """
        if state.total_chunks == 0:
            # No previous chunks, but we have new ones
            return metrics.estimated_chunks > 0

        # Calculate percentage change
        # estimated_chunks represents new/modified chunks, not total
        # Compare against previous total
        change_ratio = metrics.estimated_chunks / state.total_chunks
        return change_ratio > self._config.reindex_chunk_change_percent
