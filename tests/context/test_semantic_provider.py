"""
Tests for LanceDBSearchProvider optimizations.

Tests cover:
- IndexingMetrics dataclass
- Super-batch processing logic
- Conditional FTS rebuild
- Config integration
"""

from typing import List
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path

import pytest

from src.context.protocols import CodeChunk, CodeChunkerProtocol, EmbeddingFunctionProtocol
from src.context.semantic.config import SemanticIndexConfig
from src.context.semantic.provider import (
    IndexingMetrics,
    LanceDBSearchProvider,
)


# --- Test Doubles ---


class MockChunker:
    """Test double for CodeChunkerProtocol."""

    def __init__(self, chunks_per_file: int = 3):
        self.chunks_per_file = chunks_per_file
        self.chunk_calls = []

    def chunk(self, file_path: str, content: str) -> List[CodeChunk]:
        """Return fixed number of chunks per file."""
        self.chunk_calls.append((file_path, content))
        lines = content.splitlines()
        num_lines = len(lines)

        if num_lines == 0:
            return []

        # Create evenly distributed chunks
        chunk_size = max(1, num_lines // self.chunks_per_file)
        chunks = []

        for i in range(self.chunks_per_file):
            start = i * chunk_size + 1
            end = min((i + 1) * chunk_size, num_lines)
            if start <= num_lines:
                chunks.append(CodeChunk(
                    start_line=start,
                    end_line=end,
                    file_path=file_path
                ))

        return chunks


class MockEmbeddingFunction:
    """Test double for embedding function."""

    def __init__(self, dims: int = 384):
        self._dims = dims
        self.call_count = 0
        self.texts_embedded = []

    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate fake embeddings (all zeros)."""
        self.call_count += 1
        self.texts_embedded.extend(texts)
        return [[0.0] * self._dims for _ in texts]

    def ndims(self) -> int:
        return self._dims


# --- IndexingMetrics Tests ---


class TestIndexingMetrics:
    """Test IndexingMetrics dataclass."""

    def test_default_values(self):
        """All values should default to zero."""
        metrics = IndexingMetrics()
        assert metrics.files_processed == 0
        assert metrics.chunks_added == 0
        assert metrics.chunks_skipped == 0
        assert metrics.embedding_time_seconds == 0.0
        assert metrics.db_write_time_seconds == 0.0
        assert metrics.total_time_seconds == 0.0

    def test_chunks_per_second_with_time(self):
        """Should calculate throughput correctly."""
        metrics = IndexingMetrics(
            chunks_added=100,
            embedding_time_seconds=2.0,
        )
        assert metrics.chunks_per_second == 50.0

    def test_chunks_per_second_zero_time(self):
        """Should return 0 when embedding time is 0."""
        metrics = IndexingMetrics(
            chunks_added=100,
            embedding_time_seconds=0.0,
        )
        assert metrics.chunks_per_second == 0.0

    def test_chunks_per_second_small_time(self):
        """Should handle very small embedding times."""
        metrics = IndexingMetrics(
            chunks_added=1000,
            embedding_time_seconds=0.001,
        )
        assert metrics.chunks_per_second == 1_000_000.0


# --- Provider Config Integration Tests ---


class TestProviderConfigIntegration:
    """Test that provider correctly uses config values."""

    def test_provider_uses_default_config(self):
        """Provider should use default config when none provided."""
        chunker = MockChunker()
        provider = LanceDBSearchProvider(
            project_path=Path("."),
            chunker=chunker,
        )
        assert provider._config.batch_size == 256
        assert provider._config.max_text_length == 512

    def test_provider_uses_custom_config(self):
        """Provider should use provided config."""
        chunker = MockChunker()
        config = SemanticIndexConfig(
            batch_size=128,
            max_text_length=1024,
            super_batch_size=512,
        )
        provider = LanceDBSearchProvider(
            project_path=Path("."),
            chunker=chunker,
            config=config,
        )
        assert provider._config.batch_size == 128
        assert provider._config.max_text_length == 1024
        assert provider._config.super_batch_size == 512

    def test_provider_db_path_from_config(self):
        """Provider should use db_dir_name from config."""
        chunker = MockChunker()
        config = SemanticIndexConfig(db_dir_name=".custom_db")
        provider = LanceDBSearchProvider(
            project_path=Path("/project"),
            chunker=chunker,
            config=config,
        )
        assert provider._db_path.name == ".custom_db"

    def test_provider_lock_timeout_from_config(self):
        """Provider should use lock_timeout from config."""
        chunker = MockChunker()
        config = SemanticIndexConfig(lock_timeout=600)
        provider = LanceDBSearchProvider(
            project_path=Path("."),
            chunker=chunker,
            config=config,
        )
        assert provider._lock_timeout == 600


# --- FTS Rebuild Tests ---


class TestMaybeRebuildFts:
    """Test conditional FTS rebuild logic."""

    def setup_method(self):
        """Create provider with mock dependencies."""
        self.chunker = MockChunker()
        self.config = SemanticIndexConfig(fts_rebuild_threshold=100)
        self.provider = LanceDBSearchProvider(
            project_path=Path("."),
            chunker=self.chunker,
            config=self.config,
        )

    def test_skips_rebuild_below_threshold(self):
        """Should skip FTS rebuild when chunks_added < threshold."""
        mock_table = Mock()

        self.provider._maybe_rebuild_fts(mock_table, chunks_added=50)

        mock_table.create_fts_index.assert_not_called()

    def test_rebuilds_at_threshold(self):
        """Should rebuild FTS when chunks_added >= threshold."""
        mock_table = Mock()
        mock_table.count_rows.return_value = 1000

        self.provider._maybe_rebuild_fts(mock_table, chunks_added=100)

        # Now tries incremental first (replace=False)
        mock_table.create_fts_index.assert_called_once_with("content", replace=False)

    def test_rebuilds_above_threshold(self):
        """Should rebuild FTS when chunks_added > threshold."""
        mock_table = Mock()
        mock_table.count_rows.return_value = 1000

        self.provider._maybe_rebuild_fts(mock_table, chunks_added=500)

        mock_table.create_fts_index.assert_called_once()

    def test_force_ignores_threshold(self):
        """Should rebuild FTS when force=True regardless of threshold."""
        mock_table = Mock()
        mock_table.count_rows.return_value = 100

        self.provider._maybe_rebuild_fts(mock_table, chunks_added=10, force=True)

        mock_table.create_fts_index.assert_called_once()

    def test_skips_empty_table(self):
        """Should skip FTS rebuild when table is empty."""
        mock_table = Mock()
        mock_table.count_rows.return_value = 0

        self.provider._maybe_rebuild_fts(mock_table, chunks_added=100)

        mock_table.create_fts_index.assert_not_called()

    def test_handles_fts_error_gracefully(self):
        """Should log warning but not raise on FTS error."""
        mock_table = Mock()
        mock_table.count_rows.return_value = 100
        mock_table.create_fts_index.side_effect = Exception("FTS error")

        # Should not raise
        self.provider._maybe_rebuild_fts(mock_table, chunks_added=100)


# --- Super Batch Processing Tests ---


class TestProcessSuperBatch:
    """Test super-batch processing logic."""

    def setup_method(self):
        """Create provider with mock dependencies."""
        self.chunker = MockChunker()
        self.config = SemanticIndexConfig.for_testing()
        self.provider = LanceDBSearchProvider(
            project_path=Path("."),
            chunker=self.chunker,
            config=self.config,
        )
        self.mock_embedding = MockEmbeddingFunction()
        self.provider._embedding_func = self.mock_embedding

    def test_empty_chunks_returns_zeros(self):
        """Should return zero metrics for empty chunks."""
        mock_table = Mock()

        result = self.provider._process_super_batch(mock_table, [])

        assert result["added"] == 0
        assert result["embed_time"] == 0.0
        assert result["db_time"] == 0.0

    def test_embeds_all_chunks(self):
        """Should generate embeddings for all chunks."""
        mock_table = Mock()
        chunks = [
            {"content": "chunk 1"},
            {"content": "chunk 2"},
            {"content": "chunk 3"},
        ]

        self.provider._process_super_batch(mock_table, chunks)

        assert self.mock_embedding.call_count == 1
        assert len(self.mock_embedding.texts_embedded) == 3

    def test_adds_vectors_to_chunks(self):
        """Should attach vector to each chunk dict."""
        mock_table = Mock()
        chunks = [{"content": "test"}]

        self.provider._process_super_batch(mock_table, chunks)

        assert "vector" in chunks[0]
        assert len(chunks[0]["vector"]) == 384

    def test_adds_chunks_to_table(self):
        """Should call table.add with chunks."""
        mock_table = Mock()
        chunks = [{"content": f"chunk {i}"} for i in range(10)]

        result = self.provider._process_super_batch(mock_table, chunks)

        assert mock_table.add.called
        assert result["added"] == 10

    def test_batches_large_inserts(self):
        """Should batch inserts for large chunk counts."""
        mock_table = Mock()
        # Create more than DB_BATCH_SIZE (1000) chunks
        chunks = [{"content": f"chunk {i}"} for i in range(1500)]

        self.provider._process_super_batch(mock_table, chunks)

        # Should be called twice (1000 + 500)
        assert mock_table.add.call_count == 2

    def test_returns_timing_metrics(self):
        """Should return timing information."""
        mock_table = Mock()
        chunks = [{"content": "test"}]

        result = self.provider._process_super_batch(mock_table, chunks)

        assert "embed_time" in result
        assert "db_time" in result
        assert result["embed_time"] >= 0
        assert result["db_time"] >= 0

    def test_propagates_table_errors(self):
        """Should propagate table.add errors."""
        mock_table = Mock()
        mock_table.add.side_effect = Exception("DB error")
        chunks = [{"content": "test"}]

        with pytest.raises(Exception, match="DB error"):
            self.provider._process_super_batch(mock_table, chunks)


# --- Embedding Function Injection Tests ---


class TestEmbeddingFunctionInjection:
    """Test that embedding function can be injected for testing."""

    def test_accepts_injected_embedding_func(self):
        """Provider should accept injected embedding function."""
        chunker = MockChunker()
        mock_embed = MockEmbeddingFunction(dims=384)

        provider = LanceDBSearchProvider(
            project_path=Path("."),
            chunker=chunker,
            embedding_func=mock_embed,
        )

        assert provider._embedding_func is mock_embed

    def test_none_embedding_func_lazy_loads(self):
        """Provider should lazy-load embedding func when None provided."""
        chunker = MockChunker()

        provider = LanceDBSearchProvider(
            project_path=Path("."),
            chunker=chunker,
            embedding_func=None,  # Explicit None
        )

        # Should be None until _ensure_schema is called
        assert provider._embedding_func is None

    def test_mock_embedding_satisfies_protocol(self):
        """MockEmbeddingFunction should satisfy EmbeddingFunctionProtocol."""
        mock_embed = MockEmbeddingFunction()

        # Protocol check
        assert isinstance(mock_embed, EmbeddingFunctionProtocol)

    def test_injected_embedding_used_in_super_batch(self):
        """Injected embedding function should be used during processing."""
        chunker = MockChunker()
        mock_embed = MockEmbeddingFunction(dims=384)
        config = SemanticIndexConfig.for_testing()

        provider = LanceDBSearchProvider(
            project_path=Path("."),
            chunker=chunker,
            config=config,
            embedding_func=mock_embed,
        )

        mock_table = Mock()
        chunks = [{"content": "test chunk"}]

        provider._process_super_batch(mock_table, chunks)

        # Verify our mock was called
        assert mock_embed.call_count == 1
        assert "test chunk" in mock_embed.texts_embedded

    def test_injected_embedding_skips_lazy_load(self):
        """When embedding is injected, _ensure_schema should not lazy load."""
        chunker = MockChunker()
        mock_embed = MockEmbeddingFunction(dims=384)

        provider = LanceDBSearchProvider(
            project_path=Path("."),
            chunker=chunker,
            embedding_func=mock_embed,
        )

        # Mock the factory to ensure it's not called
        with patch("src.context.semantic.provider._create_embedding_func") as mock_factory:
            # This would normally trigger lazy loading
            provider._code_schema = None  # Reset to trigger _ensure_schema logic
            provider._ensure_schema()

            # Factory should NOT be called since we injected
            mock_factory.assert_not_called()

        # Our injected func should still be there
        assert provider._embedding_func is mock_embed


# --- FTS Incremental Update Tests ---


class TestFTSIncrementalUpdate:
    """Test FTS incremental indexing behavior."""

    def setup_method(self):
        """Create provider with mock dependencies."""
        self.chunker = MockChunker()
        self.config = SemanticIndexConfig(fts_rebuild_threshold=100)
        self.provider = LanceDBSearchProvider(
            project_path=Path("."),
            chunker=self.chunker,
            config=self.config,
        )

    def test_tries_incremental_first(self):
        """Should attempt incremental FTS update (replace=False) first."""
        mock_table = Mock()
        mock_table.count_rows.return_value = 1000

        self.provider._maybe_rebuild_fts(mock_table, chunks_added=100)

        # Should have called with replace=False first
        mock_table.create_fts_index.assert_called_once_with("content", replace=False)

    def test_falls_back_to_replace_on_error(self):
        """Should fall back to replace=True when incremental fails."""
        mock_table = Mock()
        mock_table.count_rows.return_value = 1000

        # First call fails, second succeeds
        mock_table.create_fts_index.side_effect = [
            Exception("Incremental not supported"),
            None
        ]

        self.provider._maybe_rebuild_fts(mock_table, chunks_added=100)

        # Should have called twice: first with replace=False, then replace=True
        assert mock_table.create_fts_index.call_count == 2
        mock_table.create_fts_index.assert_any_call("content", replace=False)
        mock_table.create_fts_index.assert_any_call("content", replace=True)

    def test_skips_update_when_index_already_exists(self):
        """Should not fail when index already exists message."""
        mock_table = Mock()
        mock_table.count_rows.return_value = 1000
        mock_table.create_fts_index.side_effect = Exception("Index already exists")

        # Should not raise
        self.provider._maybe_rebuild_fts(mock_table, chunks_added=100)

        # Should only call once (no fallback needed for "already exists")
        assert mock_table.create_fts_index.call_count == 1


# --- Cleanup Deleted Files Tests ---


class TestCleanupDeletedFiles:
    """Test cleanup_deleted_files method."""

    def setup_method(self):
        """Create provider with mock dependencies."""
        self.chunker = MockChunker()
        self.config = SemanticIndexConfig.for_testing()
        self.provider = LanceDBSearchProvider(
            project_path=Path("."),
            chunker=self.chunker,
            config=self.config,
        )

    def test_returns_zero_when_not_indexed(self):
        """Should return 0 when index doesn't exist."""
        # Mock is_indexed to return False
        self.provider.is_indexed = Mock(return_value=False)

        result = self.provider.cleanup_deleted_files({"file1.py", "file2.py"})

        assert result == 0

    def test_returns_zero_when_no_stale_entries(self):
        """Should return 0 when all indexed files still exist."""
        # Setup mocks
        self.provider.is_indexed = Mock(return_value=True)
        self.provider._ensure_db = Mock()

        mock_table = Mock()
        mock_batch = Mock()
        mock_df = Mock()
        mock_df.__getitem__ = Mock(return_value=Mock(tolist=Mock(return_value=["file1.py", "file2.py"])))
        mock_batch.to_pandas.return_value = mock_df
        mock_table.search.return_value.select.return_value.to_batches.return_value = [mock_batch]

        mock_db = Mock()
        mock_db.open_table.return_value = mock_table
        self.provider._db = mock_db

        # All indexed files are in current_files
        result = self.provider.cleanup_deleted_files({"file1.py", "file2.py"})

        assert result == 0
        mock_table.delete.assert_not_called()

    def test_removes_stale_entries(self):
        """Should remove entries for deleted files."""
        # Setup mocks
        self.provider.is_indexed = Mock(return_value=True)
        self.provider._ensure_db = Mock()

        mock_table = Mock()
        mock_batch = Mock()
        mock_df = Mock()
        # Index has 3 files, but only 1 exists
        mock_df.__getitem__ = Mock(return_value=Mock(tolist=Mock(
            return_value=["file1.py", "deleted1.py", "deleted2.py"]
        )))
        mock_batch.to_pandas.return_value = mock_df
        mock_table.search.return_value.select.return_value.to_batches.return_value = [mock_batch]

        mock_db = Mock()
        mock_db.open_table.return_value = mock_table
        self.provider._db = mock_db

        # Only file1.py exists
        result = self.provider.cleanup_deleted_files({"file1.py"})

        assert result == 2  # 2 deleted files
        mock_table.delete.assert_called_once()
        mock_table.cleanup_old_versions.assert_called_once()

    def test_batches_large_deletions(self):
        """Should batch deletions for large numbers of stale files."""
        # Setup mocks
        self.provider.is_indexed = Mock(return_value=True)
        self.provider._ensure_db = Mock()

        mock_table = Mock()
        mock_batch = Mock()
        mock_df = Mock()
        # Index has 250 files to delete (should be split into 3 batches of 100)
        stale_files = [f"deleted{i}.py" for i in range(250)]
        mock_df.__getitem__ = Mock(return_value=Mock(tolist=Mock(
            return_value=["existing.py"] + stale_files
        )))
        mock_batch.to_pandas.return_value = mock_df
        mock_table.search.return_value.select.return_value.to_batches.return_value = [mock_batch]

        mock_db = Mock()
        mock_db.open_table.return_value = mock_table
        self.provider._db = mock_db

        # Only 1 file exists
        result = self.provider.cleanup_deleted_files({"existing.py"})

        assert result == 250
        # Should be called 3 times (100 + 100 + 50)
        assert mock_table.delete.call_count == 3

    def test_handles_sql_injection_in_paths(self):
        """Should safely escape single quotes in file paths."""
        # Setup mocks
        self.provider.is_indexed = Mock(return_value=True)
        self.provider._ensure_db = Mock()

        mock_table = Mock()
        mock_batch = Mock()
        mock_df = Mock()
        # File path with single quote (SQL injection attempt)
        mock_df.__getitem__ = Mock(return_value=Mock(tolist=Mock(
            return_value=["normal.py", "file'with'quotes.py"]
        )))
        mock_batch.to_pandas.return_value = mock_df
        mock_table.search.return_value.select.return_value.to_batches.return_value = [mock_batch]

        mock_db = Mock()
        mock_db.open_table.return_value = mock_table
        self.provider._db = mock_db

        # Only normal file exists - file with quotes should be removed
        result = self.provider.cleanup_deleted_files({"normal.py"})

        assert result == 1
        # Verify the SQL was properly escaped (single quote doubled)
        call_args = mock_table.delete.call_args[0][0]
        assert "''" in call_args  # Single quotes should be escaped

    def test_continues_on_delete_error(self):
        """Should continue deleting other batches if one batch fails."""
        # Setup mocks
        self.provider.is_indexed = Mock(return_value=True)
        self.provider._ensure_db = Mock()

        mock_table = Mock()
        mock_batch = Mock()
        mock_df = Mock()
        stale_files = [f"deleted{i}.py" for i in range(150)]
        mock_df.__getitem__ = Mock(return_value=Mock(tolist=Mock(
            return_value=stale_files
        )))
        mock_batch.to_pandas.return_value = mock_df
        mock_table.search.return_value.select.return_value.to_batches.return_value = [mock_batch]

        # First delete fails, second succeeds
        mock_table.delete.side_effect = [Exception("Delete failed"), None]

        mock_db = Mock()
        mock_db.open_table.return_value = mock_table
        self.provider._db = mock_db

        # No files exist
        result = self.provider.cleanup_deleted_files(set())

        # Should have tried both batches, only second succeeded
        assert mock_table.delete.call_count == 2
        assert result == 50  # Only second batch (50 files) succeeded
