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

from scrappy.context.protocols import CodeChunk, CodeChunkerProtocol, EmbeddingFunctionProtocol
from scrappy.context.semantic.config import SemanticIndexConfig
from scrappy.context.semantic.provider import (
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


# --- State Persistence Tests ---


class TestNormalizePath:
    """Test path normalization and security."""

    def setup_method(self):
        """Create provider with mock dependencies."""
        self.chunker = MockChunker()
        self.config = SemanticIndexConfig.for_testing()
        self.provider = LanceDBSearchProvider(
            project_path=Path(".").resolve(),
            chunker=self.chunker,
            config=self.config,
        )

    def test_normalize_relative_path(self):
        """Should normalize relative path to POSIX style."""
        # Create a real file to normalize
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            provider = LanceDBSearchProvider(
                project_path=Path(tmpdir),
                chunker=self.chunker,
                config=self.config,
            )
            # Create a test file
            test_file = Path(tmpdir) / "src" / "main.py"
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.write_text("# test")

            result = provider._normalize_path("src/main.py")
            assert result == "src/main.py"

    def test_normalize_path_outside_project_raises(self):
        """Should raise ValueError for paths outside project root."""
        from scrappy.context.semantic.provider import IndexingError

        # Attempt to access parent directory
        with pytest.raises(ValueError, match="Security"):
            self.provider._normalize_path("../../../etc/passwd")

    def test_normalize_windows_path(self):
        """Should normalize paths to POSIX style."""
        import tempfile
        import sys

        with tempfile.TemporaryDirectory() as tmpdir:
            provider = LanceDBSearchProvider(
                project_path=Path(tmpdir),
                chunker=self.chunker,
                config=self.config,
            )
            # Create test file
            test_file = Path(tmpdir) / "src" / "main.py"
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.write_text("# test")

            # Test with forward slashes (works on all platforms)
            result = provider._normalize_path("src/main.py")
            assert result == "src/main.py"

            # On Windows, also test that backslashes are normalized to forward slashes
            if sys.platform == "win32":
                result = provider._normalize_path("src\\main.py")
                assert result == "src/main.py"


class TestComputeHash:
    """Test hash computation."""

    def setup_method(self):
        """Create provider with mock dependencies."""
        self.chunker = MockChunker()
        self.config = SemanticIndexConfig.for_testing()
        self.provider = LanceDBSearchProvider(
            project_path=Path("."),
            chunker=self.chunker,
            config=self.config,
        )

    def test_compute_hash_returns_md5(self):
        """Should return MD5 hash of content."""
        import hashlib
        content = "test content"
        expected = hashlib.md5(content.encode("utf-8")).hexdigest()

        result = self.provider._compute_hash(content)

        assert result == expected
        assert len(result) == 32  # MD5 hex digest length

    def test_compute_hash_different_content_different_hash(self):
        """Different content should produce different hashes."""
        hash1 = self.provider._compute_hash("content 1")
        hash2 = self.provider._compute_hash("content 2")

        assert hash1 != hash2

    def test_compute_hash_same_content_same_hash(self):
        """Same content should produce same hash."""
        hash1 = self.provider._compute_hash("same content")
        hash2 = self.provider._compute_hash("same content")

        assert hash1 == hash2

    def test_compute_hash_empty_string(self):
        """Should handle empty string."""
        result = self.provider._compute_hash("")
        assert len(result) == 32


class TestIsIndexed:
    """Test is_indexed method."""

    def setup_method(self):
        """Create provider with mock dependencies."""
        self.chunker = MockChunker()
        self.config = SemanticIndexConfig.for_testing()
        self.provider = LanceDBSearchProvider(
            project_path=Path("."),
            chunker=self.chunker,
            config=self.config,
        )

    def test_is_indexed_returns_true_when_table_exists(self):
        """Should return True when code_chunks table exists."""
        mock_db = Mock()
        mock_db.table_names.return_value = ["code_chunks"]
        self.provider._db = mock_db

        result = self.provider.is_indexed()

        assert result is True

    def test_is_indexed_returns_false_when_table_missing(self):
        """Should return False when code_chunks table doesn't exist."""
        mock_db = Mock()
        mock_db.table_names.return_value = ["other_table"]
        self.provider._db = mock_db

        result = self.provider.is_indexed()

        assert result is False

    def test_is_indexed_returns_false_on_error(self):
        """Should return False when error occurs."""
        self.provider._ensure_db = Mock(side_effect=Exception("DB error"))

        result = self.provider.is_indexed()

        assert result is False


class TestClearIndex:
    """Test clear_index method."""

    def setup_method(self):
        """Create provider with mock dependencies."""
        self.chunker = MockChunker()
        self.config = SemanticIndexConfig.for_testing()
        self.provider = LanceDBSearchProvider(
            project_path=Path("."),
            chunker=self.chunker,
            config=self.config,
        )

    @patch('scrappy.context.semantic.provider.fasteners')
    def test_clear_index_drops_table(self, mock_fasteners):
        """Should drop the code_chunks table."""
        mock_lock = Mock()
        mock_lock.acquire.return_value = True
        mock_fasteners.InterProcessLock.return_value = mock_lock

        mock_db = Mock()
        mock_db.table_names.return_value = ["code_chunks"]
        self.provider._db = mock_db
        self.provider._ensure_db = Mock()

        self.provider.clear_index()

        mock_db.drop_table.assert_called_once_with("code_chunks")

    @patch('scrappy.context.semantic.provider.fasteners')
    def test_clear_index_does_nothing_when_no_table(self, mock_fasteners):
        """Should not fail when table doesn't exist."""
        mock_lock = Mock()
        mock_lock.acquire.return_value = True
        mock_fasteners.InterProcessLock.return_value = mock_lock

        mock_db = Mock()
        mock_db.table_names.return_value = []
        self.provider._db = mock_db
        self.provider._ensure_db = Mock()

        self.provider.clear_index()

        mock_db.drop_table.assert_not_called()


class TestRemoveFiles:
    """Test remove_files method."""

    def setup_method(self):
        """Create provider with mock dependencies."""
        self.chunker = MockChunker()
        self.config = SemanticIndexConfig.for_testing()
        self.provider = LanceDBSearchProvider(
            project_path=Path("."),
            chunker=self.chunker,
            config=self.config,
        )

    def test_remove_files_returns_zero_for_empty_set(self):
        """Should return 0 when no files to remove."""
        result = self.provider.remove_files(set())
        assert result == 0

    def test_remove_files_returns_zero_when_not_indexed(self):
        """Should return 0 when index doesn't exist."""
        self.provider.is_indexed = Mock(return_value=False)

        result = self.provider.remove_files({"file1.py", "file2.py"})

        assert result == 0

    @patch('scrappy.context.semantic.provider.fasteners')
    def test_remove_files_deletes_specified_files(self, mock_fasteners):
        """Should delete specified files from index."""
        mock_lock = Mock()
        mock_lock.acquire.return_value = True
        mock_fasteners.InterProcessLock.return_value = mock_lock

        self.provider.is_indexed = Mock(return_value=True)
        self.provider._ensure_db = Mock()

        mock_table = Mock()
        mock_db = Mock()
        mock_db.open_table.return_value = mock_table
        self.provider._db = mock_db

        result = self.provider.remove_files({"file1.py", "file2.py"})

        assert result == 2
        mock_table.delete.assert_called_once()

    @patch('scrappy.context.semantic.provider.fasteners')
    def test_remove_files_batches_large_deletions(self, mock_fasteners):
        """Should batch deletions for large file sets."""
        mock_lock = Mock()
        mock_lock.acquire.return_value = True
        mock_fasteners.InterProcessLock.return_value = mock_lock

        self.provider.is_indexed = Mock(return_value=True)
        self.provider._ensure_db = Mock()

        mock_table = Mock()
        mock_db = Mock()
        mock_db.open_table.return_value = mock_table
        self.provider._db = mock_db

        # 250 files should be split into 3 batches
        files = {f"file{i}.py" for i in range(250)}
        result = self.provider.remove_files(files)

        assert result == 250
        assert mock_table.delete.call_count == 3


class TestSetProgressReporter:
    """Test set_progress_reporter method."""

    def test_set_progress_reporter_updates_reporter(self):
        """Should update the progress reporter."""
        chunker = MockChunker()
        provider = LanceDBSearchProvider(
            project_path=Path("."),
            chunker=chunker,
        )

        mock_reporter = Mock()
        provider.set_progress_reporter(mock_reporter)

        assert provider._progress is mock_reporter


class TestBuildResultFromRaw:
    """Test _build_result_from_raw method."""

    def setup_method(self):
        """Create provider with mock dependencies."""
        self.chunker = MockChunker()
        self.config = SemanticIndexConfig.for_testing()
        self.provider = LanceDBSearchProvider(
            project_path=Path("."),
            chunker=self.chunker,
            config=self.config,
        )

    def test_build_result_from_raw_empty_results(self):
        """Should handle empty results."""
        result = self.provider._build_result_from_raw([], max_tokens=4000)

        assert result.chunks == []
        assert result.tokens_used == 0
        assert result.limit_hit is None

    def test_build_result_from_raw_deduplicates(self):
        """Should deduplicate chunks by file_path and start_line."""
        results = [
            {'file_path': 'a.py', 'start_line': 1, 'end_line': 10, 'content': 'chunk1', '_score': 0.9},
            {'file_path': 'a.py', 'start_line': 1, 'end_line': 10, 'content': 'chunk1', '_score': 0.8},  # duplicate
            {'file_path': 'b.py', 'start_line': 1, 'end_line': 5, 'content': 'chunk2', '_score': 0.7},
        ]

        result = self.provider._build_result_from_raw(results, max_tokens=4000)

        assert len(result.chunks) == 2

    def test_build_result_from_raw_respects_token_limit(self):
        """Should stop when token limit is reached."""
        # Each chunk is ~7 chars = ~2 tokens
        results = [
            {'file_path': f'file{i}.py', 'start_line': 1, 'end_line': 5, 'content': 'x' * 100, '_score': 0.9}
            for i in range(10)
        ]

        # Allow only ~100 tokens (300 chars at 3 chars/token)
        result = self.provider._build_result_from_raw(results, max_tokens=100)

        assert len(result.chunks) < 10
        assert result.limit_hit == 'token_limit'


class TestBuildResultFromRanked:
    """Test _build_result_from_ranked method."""

    def setup_method(self):
        """Create provider with mock dependencies."""
        self.chunker = MockChunker()
        self.config = SemanticIndexConfig.for_testing()
        self.provider = LanceDBSearchProvider(
            project_path=Path("."),
            chunker=self.chunker,
            config=self.config,
        )

    def test_build_result_from_ranked_empty_chunks(self):
        """Should handle empty chunk list."""
        from scrappy.context.protocols import ScoredChunk

        result = self.provider._build_result_from_ranked([], max_tokens=4000)

        assert result.chunks == []
        assert result.tokens_used == 0

    def test_build_result_from_ranked_includes_score(self):
        """Should include final_score in result."""
        from scrappy.context.protocols import ScoredChunk

        chunks = [
            ScoredChunk(
                file_path='test.py',
                start_line=1,
                end_line=10,
                content='test content',
                vector_score=0.8,
                fts_score=0.5,
                final_score=0.75,
            )
        ]

        result = self.provider._build_result_from_ranked(chunks, max_tokens=4000)

        assert len(result.chunks) == 1
        assert result.chunks[0]['score'] == 0.75

    def test_build_result_from_ranked_respects_token_limit(self):
        """Should stop when token limit is reached."""
        from scrappy.context.protocols import ScoredChunk

        chunks = [
            ScoredChunk(
                file_path=f'file{i}.py',
                start_line=1,
                end_line=10,
                content='x' * 100,
                vector_score=0.8,
                fts_score=0.5,
                final_score=0.75,
            )
            for i in range(10)
        ]

        result = self.provider._build_result_from_ranked(chunks, max_tokens=100)

        assert len(result.chunks) < 10
        assert result.limit_hit == 'token_limit'


class TestConvertToScoredChunks:
    """Test _convert_to_scored_chunks method."""

    def setup_method(self):
        """Create provider with mock dependencies."""
        self.chunker = MockChunker()
        self.config = SemanticIndexConfig.for_testing()
        self.provider = LanceDBSearchProvider(
            project_path=Path("."),
            chunker=self.chunker,
            config=self.config,
        )

    def test_convert_empty_results(self):
        """Should handle empty results."""
        result = self.provider._convert_to_scored_chunks([])
        assert result == []

    def test_convert_deduplicates_by_chunk_id(self):
        """Should deduplicate results by file_path and start_line."""
        results = [
            {'file_path': 'a.py', 'start_line': 1, 'end_line': 10, 'content': 'c1', '_distance': 0.1, '_score': 0.9},
            {'file_path': 'a.py', 'start_line': 1, 'end_line': 10, 'content': 'c1', '_distance': 0.2, '_score': 0.8},
        ]

        chunks = self.provider._convert_to_scored_chunks(results)

        assert len(chunks) == 1

    def test_convert_computes_vector_score_from_distance(self):
        """Should convert L2 distance to similarity score."""
        import math
        results = [
            {'file_path': 'a.py', 'start_line': 1, 'end_line': 10, 'content': 'c', '_distance': 0.5, '_score': 0.0},
        ]

        chunks = self.provider._convert_to_scored_chunks(results)

        expected_score = math.exp(-0.5)
        assert abs(chunks[0].vector_score - expected_score) < 0.001

    def test_convert_extracts_fts_score(self):
        """Should extract FTS score from results."""
        results = [
            {'file_path': 'a.py', 'start_line': 1, 'end_line': 10, 'content': 'c', '_distance': 0.0, '_score': 0.75},
        ]

        chunks = self.provider._convert_to_scored_chunks(results)

        assert chunks[0].fts_score == 0.75


class TestEnsureDb:
    """Test _ensure_db method."""

    def setup_method(self):
        """Create provider with mock dependencies."""
        self.chunker = MockChunker()
        self.config = SemanticIndexConfig.for_testing()

    @patch('scrappy.context.semantic.provider.lancedb')
    def test_ensure_db_creates_directory(self, mock_lancedb):
        """Should create database directory if it doesn't exist."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            provider = LanceDBSearchProvider(
                project_path=Path(tmpdir),
                chunker=self.chunker,
                config=self.config,
            )

            # Initially _db is None
            assert provider._db is None

            provider._ensure_db()

            # Directory should be created (using provider's actual db_path)
            assert provider._db_path.exists()
            mock_lancedb.connect.assert_called_once()

    @patch('scrappy.context.semantic.provider.lancedb')
    def test_ensure_db_only_connects_once(self, mock_lancedb):
        """Should only connect once on subsequent calls."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            provider = LanceDBSearchProvider(
                project_path=Path(tmpdir),
                chunker=self.chunker,
                config=self.config,
            )

            provider._ensure_db()
            provider._ensure_db()
            provider._ensure_db()

            # Should only connect once
            assert mock_lancedb.connect.call_count == 1


class TestEnsureSchema:
    """Test _ensure_schema method."""

    def setup_method(self):
        """Create provider with mock dependencies."""
        self.chunker = MockChunker()
        self.config = SemanticIndexConfig.for_testing()

    def test_ensure_schema_uses_injected_embedding(self):
        """Should use injected embedding function without creating new one."""
        mock_embed = MockEmbeddingFunction(dims=384)
        provider = LanceDBSearchProvider(
            project_path=Path("."),
            chunker=self.chunker,
            config=self.config,
            embedding_func=mock_embed,
        )

        provider._ensure_schema()

        # Should still be using the injected mock
        assert provider._embedding_func is mock_embed
        # Schema should be initialized
        assert provider._code_schema is not None

    @patch('scrappy.context.semantic.provider._create_embedding_func')
    @patch('scrappy.context.semantic.provider._create_code_schema')
    def test_ensure_schema_lazy_loads_embedding(self, mock_schema, mock_embed_func):
        """Should lazy-load embedding function when not injected."""
        mock_embed = MockEmbeddingFunction()
        mock_embed_func.return_value = mock_embed
        mock_schema.return_value = Mock()

        provider = LanceDBSearchProvider(
            project_path=Path("."),
            chunker=self.chunker,
            config=self.config,
            embedding_func=None,  # Not injected
        )

        provider._ensure_schema()

        mock_embed_func.assert_called_once()
        mock_schema.assert_called_once()

    @patch('scrappy.context.semantic.provider._create_embedding_func')
    def test_ensure_schema_raises_indexing_error_on_failure(self, mock_embed_func):
        """Should raise IndexingError when initialization fails."""
        from scrappy.context.semantic.provider import IndexingError

        mock_embed_func.side_effect = Exception("Model not found")

        provider = LanceDBSearchProvider(
            project_path=Path("."),
            chunker=self.chunker,
            config=self.config,
            embedding_func=None,
        )

        with pytest.raises(IndexingError, match="Failed to initialize embedding function"):
            provider._ensure_schema()


class TestSafeDbContext:
    """Test _safe_db_context context manager."""

    def setup_method(self):
        """Create provider with mock dependencies."""
        self.chunker = MockChunker()
        self.config = SemanticIndexConfig.for_testing()
        self.provider = LanceDBSearchProvider(
            project_path=Path("."),
            chunker=self.chunker,
            config=self.config,
        )

    @patch('scrappy.context.semantic.provider.fasteners')
    def test_safe_db_context_acquires_lock(self, mock_fasteners):
        """Should acquire and release lock."""
        mock_lock = Mock()
        mock_lock.acquire.return_value = True
        mock_fasteners.InterProcessLock.return_value = mock_lock

        with self.provider._safe_db_context():
            pass

        mock_lock.acquire.assert_called_once()
        mock_lock.release.assert_called_once()

    @patch('scrappy.context.semantic.provider.fasteners')
    def test_safe_db_context_raises_on_lock_failure(self, mock_fasteners):
        """Should raise IndexingError when lock cannot be acquired."""
        from scrappy.context.semantic.provider import IndexingError

        mock_lock = Mock()
        mock_lock.acquire.return_value = False
        mock_fasteners.InterProcessLock.return_value = mock_lock

        with pytest.raises(IndexingError, match="Database locked"):
            with self.provider._safe_db_context():
                pass

    @patch('scrappy.context.semantic.provider.fasteners')
    def test_safe_db_context_propagates_exceptions(self, mock_fasteners):
        """Should propagate exceptions without wrapping."""
        mock_lock = Mock()
        mock_lock.acquire.return_value = True
        mock_fasteners.InterProcessLock.return_value = mock_lock

        # Exceptions should propagate as-is, not be wrapped
        with pytest.raises(ValueError, match="test error"):
            with self.provider._safe_db_context():
                raise ValueError("test error")

    @patch('scrappy.context.semantic.provider.fasteners')
    def test_safe_db_context_releases_lock_on_error(self, mock_fasteners):
        """Should release lock even when exception occurs."""
        mock_lock = Mock()
        mock_lock.acquire.return_value = True
        mock_fasteners.InterProcessLock.return_value = mock_lock

        try:
            with self.provider._safe_db_context():
                raise ValueError("Test error")
        except ValueError:
            pass

        mock_lock.release.assert_called_once()


class TestIndexFiles:
    """Test index_files method."""

    def setup_method(self):
        """Create provider with mock dependencies."""
        self.chunker = MockChunker()
        self.config = SemanticIndexConfig.for_testing()
        self.mock_embed = MockEmbeddingFunction()
        self.provider = LanceDBSearchProvider(
            project_path=Path(".").resolve(),
            chunker=self.chunker,
            config=self.config,
            embedding_func=self.mock_embed,
        )

    def test_index_files_returns_early_for_empty_files(self):
        """Should return early when no files provided."""
        self.provider._ensure_db = Mock()

        self.provider.index_files({})

        # Should not attempt DB operations
        self.provider._ensure_db.assert_not_called()

    @patch('scrappy.context.semantic.provider.fasteners')
    def test_index_files_creates_table_when_not_exists(self, mock_fasteners):
        """Should create new table when it doesn't exist."""
        import tempfile

        mock_lock = Mock()
        mock_lock.acquire.return_value = True
        mock_fasteners.InterProcessLock.return_value = mock_lock

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("def hello(): pass")

            provider = LanceDBSearchProvider(
                project_path=Path(tmpdir),
                chunker=self.chunker,
                config=self.config,
                embedding_func=self.mock_embed,
            )

            mock_db = Mock()
            mock_db.table_names.return_value = []  # No tables
            mock_table = Mock()
            mock_db.create_table.return_value = mock_table
            provider._db = mock_db

            provider.index_files({"test.py": "def hello(): pass"})

            mock_db.create_table.assert_called_once()

    def test_index_files_skips_unsafe_paths_before_lock(self):
        """Should skip files with unsafe paths before acquiring lock."""
        # Mock to verify _ensure_db is not called
        self.provider._ensure_db = Mock()

        # Try to index file outside project root
        self.provider.index_files({"../../../etc/passwd": "content"})

        # Should return early before any DB operations
        self.provider._ensure_db.assert_not_called()


class TestSearch:
    """Test search method."""

    def setup_method(self):
        """Create provider with mock dependencies."""
        self.chunker = MockChunker()
        self.config = SemanticIndexConfig.for_testing()
        self.mock_embed = MockEmbeddingFunction()
        self.provider = LanceDBSearchProvider(
            project_path=Path("."),
            chunker=self.chunker,
            config=self.config,
            embedding_func=self.mock_embed,
        )

    def test_search_returns_empty_when_not_indexed(self):
        """Should return empty result when not indexed."""
        self.provider.is_indexed = Mock(return_value=False)

        result = self.provider.search("test query")

        assert result.chunks == []
        assert result.tokens_used == 0

    def test_search_performs_hybrid_search(self):
        """Should perform hybrid search with vector and text."""
        self.provider.is_indexed = Mock(return_value=True)
        self.provider._ensure_schema = Mock()

        mock_table = Mock()
        mock_search = Mock()
        mock_search.vector.return_value = mock_search
        mock_search.text.return_value = mock_search
        mock_search.limit.return_value = mock_search
        mock_search.to_list.return_value = [
            {'file_path': 'test.py', 'start_line': 1, 'end_line': 10, 'content': 'test', '_distance': 0.1, '_score': 0.5}
        ]
        mock_table.search.return_value = mock_search

        mock_db = Mock()
        mock_db.open_table.return_value = mock_table
        self.provider._db = mock_db

        result = self.provider.search("test query")

        mock_table.search.assert_called_with(query_type="hybrid")
        assert len(result.chunks) == 1

    def test_search_falls_back_to_vector_on_hybrid_failure(self):
        """Should fall back to vector search when hybrid fails."""
        self.provider.is_indexed = Mock(return_value=True)
        self.provider._ensure_schema = Mock()

        mock_table = Mock()
        mock_hybrid_search = Mock()
        mock_hybrid_search.vector.return_value = mock_hybrid_search
        mock_hybrid_search.text.side_effect = Exception("FTS not available")

        mock_vector_search = Mock()
        mock_vector_search.limit.return_value = mock_vector_search
        mock_vector_search.to_list.return_value = [
            {'file_path': 'test.py', 'start_line': 1, 'end_line': 10, 'content': 'test', '_distance': 0.1, '_score': 0.0}
        ]

        def search_side_effect(*args, **kwargs):
            if kwargs.get('query_type') == 'hybrid':
                return mock_hybrid_search
            return mock_vector_search

        mock_table.search.side_effect = search_side_effect

        mock_db = Mock()
        mock_db.open_table.return_value = mock_table
        self.provider._db = mock_db

        result = self.provider.search("test query")

        assert len(result.chunks) == 1

    def test_search_propagates_fatal_errors(self):
        """Should not catch fatal errors like KeyboardInterrupt."""
        self.provider.is_indexed = Mock(return_value=True)
        self.provider._ensure_schema = Mock()

        mock_table = Mock()
        mock_search = Mock()
        mock_search.vector.return_value = mock_search
        mock_search.text.side_effect = KeyboardInterrupt()
        mock_table.search.return_value = mock_search

        mock_db = Mock()
        mock_db.open_table.return_value = mock_table
        self.provider._db = mock_db

        with pytest.raises(KeyboardInterrupt):
            self.provider.search("test query")

    def test_search_with_ranker(self):
        """Should use ranker when provided."""
        from scrappy.context.semantic.ranker import DefaultResultRanker

        ranker = DefaultResultRanker()
        provider = LanceDBSearchProvider(
            project_path=Path("."),
            chunker=self.chunker,
            config=self.config,
            embedding_func=self.mock_embed,
            ranker=ranker,
        )

        provider.is_indexed = Mock(return_value=True)
        provider._ensure_schema = Mock()

        mock_table = Mock()
        mock_search = Mock()
        mock_search.vector.return_value = mock_search
        mock_search.text.return_value = mock_search
        mock_search.limit.return_value = mock_search
        mock_search.to_list.return_value = [
            {'file_path': 'test.py', 'start_line': 1, 'end_line': 10, 'content': 'test content', '_distance': 0.1, '_score': 0.5}
        ]
        mock_table.search.return_value = mock_search

        mock_db = Mock()
        mock_db.open_table.return_value = mock_table
        provider._db = mock_db

        result = provider.search("test query")

        assert len(result.chunks) == 1
        assert 'score' in result.chunks[0]


class TestMaybeRebuildFtsThreshold:
    """Test FTS rebuild threshold behavior."""

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
        """Should skip FTS rebuild when cumulative chunks below threshold."""
        mock_table = Mock()
        mock_table.count_rows.return_value = 1000

        self.provider._maybe_rebuild_fts(mock_table, chunks_added=50)

        # Should not try to create FTS index (below threshold)
        mock_table.create_fts_index.assert_not_called()
        # Cumulative counter should be updated
        assert self.provider._chunks_since_fts_rebuild == 50

    def test_rebuilds_at_threshold(self):
        """Should rebuild FTS when cumulative chunks at threshold."""
        mock_table = Mock()
        mock_table.count_rows.return_value = 1000

        self.provider._maybe_rebuild_fts(mock_table, chunks_added=100)

        mock_table.create_fts_index.assert_called()
        # Counter should be reset after rebuild
        assert self.provider._chunks_since_fts_rebuild == 0

    def test_cumulative_threshold_triggers_rebuild(self):
        """Should rebuild FTS when cumulative chunks reach threshold across batches."""
        mock_table = Mock()
        mock_table.count_rows.return_value = 1000

        # First batch: 50 chunks - below threshold
        self.provider._maybe_rebuild_fts(mock_table, chunks_added=50)
        mock_table.create_fts_index.assert_not_called()
        assert self.provider._chunks_since_fts_rebuild == 50

        # Second batch: 50 more chunks - cumulative 100 reaches threshold
        self.provider._maybe_rebuild_fts(mock_table, chunks_added=50)
        mock_table.create_fts_index.assert_called()
        assert self.provider._chunks_since_fts_rebuild == 0

    def test_force_rebuild_ignores_threshold(self):
        """Should rebuild FTS when force=True regardless of threshold."""
        mock_table = Mock()
        mock_table.count_rows.return_value = 1000

        self.provider._maybe_rebuild_fts(mock_table, chunks_added=10, force=True)

        mock_table.create_fts_index.assert_called()
        # Counter should be reset after rebuild
        assert self.provider._chunks_since_fts_rebuild == 0


class TestAddFilesInBatches:
    """Test _add_files_in_batches method."""

    def setup_method(self):
        """Create provider with mock dependencies."""
        self.chunker = MockChunker()
        self.config = SemanticIndexConfig.for_testing()
        self.mock_embed = MockEmbeddingFunction()
        self.provider = LanceDBSearchProvider(
            project_path=Path("."),
            chunker=self.chunker,
            config=self.config,
            embedding_func=self.mock_embed,
        )

    def test_returns_metrics(self):
        """Should return IndexingMetrics with counts."""
        mock_table = Mock()

        files = {"test.py": "def hello():\n    pass\n    return\n"}
        metrics = self.provider._add_files_in_batches(mock_table, files)

        assert isinstance(metrics, IndexingMetrics)
        assert metrics.files_processed == 1
        assert metrics.chunks_added >= 0

    def test_reports_progress(self):
        """Should report progress if reporter is set."""
        mock_table = Mock()
        mock_progress = Mock()
        self.provider._progress = mock_progress

        files = {"test.py": "def hello():\n    pass\n    return\n"}
        self.provider._add_files_in_batches(mock_table, files)

        # Progress should have been updated
        mock_progress.update.assert_called()


class TestIndexStatePersistence:
    """Test save_index_state and get_current_stats methods."""

    def setup_method(self):
        """Create provider with mock dependencies."""
        self.chunker = MockChunker()
        self.config = SemanticIndexConfig.for_testing()
        self.provider = LanceDBSearchProvider(
            project_path=Path("."),
            chunker=self.chunker,
            config=self.config,
        )

    def test_get_current_stats_returns_zero_when_not_indexed(self):
        """Should return (0, 0) when index doesn't exist."""
        self.provider.is_indexed = Mock(return_value=False)

        total_chunks, total_files = self.provider.get_current_stats()

        assert total_chunks == 0
        assert total_files == 0

    def test_get_current_stats_returns_actual_counts(self):
        """Should return actual counts from index."""
        self.provider.is_indexed = Mock(return_value=True)
        self.provider._ensure_db = Mock()

        mock_table = Mock()
        mock_table.count_rows.return_value = 150  # 150 chunks

        mock_batch = Mock()
        mock_df = Mock()
        # 3 unique files - need to mock the file_path column access and tolist()
        mock_column = Mock()
        mock_column.tolist.return_value = ["file1.py", "file2.py", "file1.py", "file3.py"]  # 3 unique
        mock_df.__getitem__ = Mock(return_value=mock_column)
        mock_batch.to_pandas.return_value = mock_df
        mock_table.search.return_value.select.return_value.to_batches.return_value = [mock_batch]

        mock_db = Mock()
        mock_db.open_table.return_value = mock_table
        self.provider._db = mock_db

        total_chunks, total_files = self.provider.get_current_stats()

        assert total_chunks == 150
        assert total_files == 3

    def test_get_current_stats_handles_errors_gracefully(self):
        """Should return (0, 0) on error."""
        self.provider.is_indexed = Mock(return_value=True)
        self.provider._ensure_db = Mock(side_effect=Exception("DB error"))

        total_chunks, total_files = self.provider.get_current_stats()

        assert total_chunks == 0
        assert total_files == 0



