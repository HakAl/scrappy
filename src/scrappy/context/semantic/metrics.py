"""
Change metrics calculation for semantic indexing.

Single responsibility: Calculate what changed since last index and estimate
the impact on chunk counts.
"""

from pathlib import Path
from typing import Dict, List, Optional
import logging

from ..protocols import IndexState, ChangeMetrics
from .config import SemanticIndexConfig

logger = logging.getLogger(__name__)


class ChangeMetricsCalculator:
    """
    Calculates change metrics between saved index state and current files.

    Single responsibility: Determine new/modified/deleted files and estimate
    the number of chunks that will be affected.

    Uses SemanticIndexConfig.avg_chunk_bytes for chunk estimation.
    """

    def __init__(self, config: SemanticIndexConfig):
        """
        Initialize calculator with configuration.

        Args:
            config: Configuration containing avg_chunk_bytes for estimation
        """
        self._config = config

    def calculate(
        self,
        saved_state: Optional[IndexState],
        current_files: List[Path],
        current_hashes: Dict[str, str],
        current_sizes: Dict[str, int],
    ) -> ChangeMetrics:
        """
        Calculate what changed since last index.

        Args:
            saved_state: Previously saved index state (None on first run)
            current_files: List of current file paths
            current_hashes: Dict mapping path string to content hash
            current_sizes: Dict mapping path string to file size in bytes

        Returns:
            ChangeMetrics with counts and chunk estimation
        """
        if saved_state is None:
            # First run - all files are new
            total_bytes = sum(current_sizes.values())
            estimated_chunks = self._estimate_chunks(total_bytes)
            all_paths = {str(f) for f in current_files}
            return ChangeMetrics(
                new_files=len(current_files),
                modified_files=0,
                deleted_files=0,
                estimated_chunks=estimated_chunks,
                total_bytes_changed=total_bytes,
                added_paths=all_paths,
                modified_paths=set(),
                deleted_paths=set(),
            )

        # Compare current state to saved state
        saved_paths = set(saved_state.file_hashes.keys())
        current_paths = {str(f) for f in current_files}

        # Detect new files
        new_paths = current_paths - saved_paths
        new_files_count = len(new_paths)

        # Detect deleted files
        deleted_paths = saved_paths - current_paths
        deleted_files_count = len(deleted_paths)

        # Detect modified files (hash changed)
        modified_paths = set()
        for path in current_paths & saved_paths:
            if current_hashes.get(path) != saved_state.file_hashes.get(path):
                modified_paths.add(path)
        modified_files_count = len(modified_paths)

        # Calculate total bytes changed
        total_bytes_changed = 0

        # Add bytes from new files
        for path in new_paths:
            total_bytes_changed += current_sizes.get(path, 0)

        # Add bytes from modified files
        for path in modified_paths:
            total_bytes_changed += current_sizes.get(path, 0)

        # Estimate chunks
        estimated_chunks = self._estimate_chunks(total_bytes_changed)

        logger.debug(
            f"Change metrics: {new_files_count} new, {modified_files_count} modified, "
            f"{deleted_files_count} deleted, ~{estimated_chunks} chunks, "
            f"{total_bytes_changed} bytes"
        )

        return ChangeMetrics(
            new_files=new_files_count,
            modified_files=modified_files_count,
            deleted_files=deleted_files_count,
            estimated_chunks=estimated_chunks,
            total_bytes_changed=total_bytes_changed,
            added_paths=new_paths,
            modified_paths=modified_paths,
            deleted_paths=deleted_paths,
        )

    def _estimate_chunks(self, total_bytes: int) -> int:
        """
        Estimate number of chunks from total bytes.

        Uses avg_chunk_bytes from config for estimation.

        Args:
            total_bytes: Total bytes to estimate chunks for

        Returns:
            Estimated chunk count
        """
        if total_bytes == 0:
            return 0

        # Avoid division by zero
        if self._config.avg_chunk_bytes <= 0:
            logger.warning(
                f"Invalid avg_chunk_bytes: {self._config.avg_chunk_bytes}, "
                "using default 400"
            )
            avg_chunk_bytes = 400
        else:
            avg_chunk_bytes = self._config.avg_chunk_bytes

        estimated = max(1, total_bytes // avg_chunk_bytes)
        return estimated
