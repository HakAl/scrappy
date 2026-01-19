"""
Configuration for semantic search indexing.

Provides injectable configuration for the semantic search provider,
following dependency injection principles for testability.
"""

from dataclasses import dataclass
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SemanticIndexConfig:
    """
    Configuration for semantic search indexing.

    All parameters are injectable for testing and tuning.
    Defaults are optimized for BGE-small-en-v1.5 model.

    Attributes:
        embedding_model: Explicit embedding model selection (bge-small, nomic, jina)
                        None for auto-detection (highest quality available)
        batch_size: Chunks per embedding batch (256 optimal for BGE-small)
        max_text_length: Maximum text length per chunk (512 optimal for BGE-small context)
        min_chunk_size: Minimum chunk size to index (skip noise)
        super_batch_size: Max chunks before DB flush (memory safety)
        fts_rebuild_threshold: Min chunks added before FTS rebuild
        db_dir_name: Base database directory name
        lock_timeout: Lock acquisition timeout in seconds
        avg_chunk_bytes: Average bytes per chunk (for chunk count estimation)
        show_progress_chunks: Show progress bar if estimated chunks exceed this
        max_index_age_days: Force full re-index if older than this
        reindex_chunk_change_percent: Force re-index if chunks change by this percent
        debounce_ms: Minimum milliseconds between staleness checks
        fingerprint_file: Path to fingerprint storage file
    """

    # Embedding model selection (None = auto-detect best available)
    # Valid values: "bge-small", "nomic", "jina", or None
    # Can be overridden by SEMANTIC_INDEX_EMBEDDING_MODEL env var
    embedding_model: Optional[str] = None

    # Embedding settings
    batch_size: int = 256
    max_text_length: int = 512
    min_chunk_size: int = 20

    # Memory safety
    super_batch_size: int = 2048

    # FTS settings
    fts_rebuild_threshold: int = 100

    # Database settings (base path, model-specific suffix added automatically)
    db_dir_name: str = ".scrappy/lancedb"
    lock_timeout: int = 300

    # Chunk estimation (for progress decisions)
    avg_chunk_bytes: int = 400  # Average bytes per chunk (for estimation)

    # Progress thresholds
    show_progress_chunks: int = 20  # Show progress bar if estimated chunks exceed this
    max_index_age_days: int = 7  # Force full re-index if older than this
    reindex_chunk_change_percent: float = 0.25  # Force re-index if chunks change by this %

    # Staleness detection
    debounce_ms: int = 300  # Minimum milliseconds between staleness checks
    fingerprint_file: str = ".scrappy/fingerprints.json"  # Path to fingerprint storage

    def get_embedding_model(self) -> Optional[str]:
        """
        Get the configured embedding model, checking env var override.

        Priority: env var > instance attribute

        Returns:
            Model id string (bge-small, nomic, jina) or None for auto-detect
        """
        env_model = os.environ.get("SEMANTIC_INDEX_EMBEDDING_MODEL")
        if env_model:
            return env_model.strip().lower()
        return self.embedding_model

    def get_db_dir_for_model(self, model_id: str) -> str:
        """
        Get the database directory path for a specific model.

        Each model gets its own subdirectory to avoid dimension conflicts.

        Args:
            model_id: Embedding model identifier (e.g., "bge-small")

        Returns:
            Database directory path (e.g., ".scrappy/lancedb/bge-small")
        """
        return f"{self.db_dir_name}/{model_id}"

    @classmethod
    def from_memory_adaptive(cls) -> "SemanticIndexConfig":
        """
        Create config adaptive to available RAM.

        Adjusts super_batch_size based on available memory to prevent OOM.
        Falls back to conservative defaults if psutil is not available.

        Returns:
            SemanticIndexConfig with memory-adaptive settings
        """
        try:
            import psutil
            available_gb = psutil.virtual_memory().available / (1024 ** 3)
            # ~400 chunks per GB available (conservative estimate)
            # Each chunk with embedding is ~2KB in memory
            super_batch = min(2048, max(512, int(available_gb * 400)))
            logger.debug(f"Memory-adaptive config: {available_gb:.1f}GB available, super_batch={super_batch}")
        except ImportError:
            logger.debug("psutil not available, using conservative super_batch_size")
            super_batch = 1024

        return cls(super_batch_size=super_batch)

    @classmethod
    def for_testing(cls) -> "SemanticIndexConfig":
        """
        Create config optimized for testing.

        Uses smaller batch sizes for faster tests.

        Returns:
            SemanticIndexConfig with test-friendly settings
        """
        return cls(
            batch_size=16,
            super_batch_size=64,
            fts_rebuild_threshold=10,
        )
