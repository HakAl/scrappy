"""
Configuration for semantic search indexing.

Provides injectable configuration for the semantic search provider,
following dependency injection principles for testability.
"""

from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class SemanticIndexConfig:
    """
    Configuration for semantic search indexing.

    All parameters are injectable for testing and tuning.
    Defaults are optimized for BGE-small-en-v1.5 model.

    Attributes:
        batch_size: Chunks per embedding batch (256 optimal for BGE-small)
        max_text_length: Maximum text length per chunk (512 optimal for BGE-small context)
        min_chunk_size: Minimum chunk size to index (skip noise)
        super_batch_size: Max chunks before DB flush (memory safety)
        fts_rebuild_threshold: Min chunks added before FTS rebuild
        db_dir_name: Database directory name
        lock_timeout: Lock acquisition timeout in seconds
    """

    # Embedding settings
    batch_size: int = 256
    max_text_length: int = 512
    min_chunk_size: int = 20

    # Memory safety
    super_batch_size: int = 2048

    # FTS settings
    fts_rebuild_threshold: int = 100

    # Database settings
    db_dir_name: str = ".lancedb"
    lock_timeout: int = 300

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
