"""
Tests for ChangeMetricsCalculator.

Tests behavior of change detection and chunk estimation between index states.
"""

from pathlib import Path
from datetime import datetime

from scrappy.context.protocols import IndexState
from scrappy.context.semantic.metrics import ChangeMetricsCalculator
from scrappy.context.semantic.config import SemanticIndexConfig


class TestChangeMetricsCalculator:
    """Test ChangeMetricsCalculator behavior."""

    def test_first_run_all_files_new(self):
        """On first run with no saved state, all files should be counted as new."""
        config = SemanticIndexConfig(avg_chunk_bytes=400)
        calculator = ChangeMetricsCalculator(config)

        current_files = [
            Path("file1.py"),
            Path("file2.py"),
            Path("file3.py"),
        ]
        current_hashes = {
            "file1.py": "hash1",
            "file2.py": "hash2",
            "file3.py": "hash3",
        }
        current_sizes = {
            "file1.py": 1000,
            "file2.py": 2000,
            "file3.py": 1500,
        }

        metrics = calculator.calculate(
            saved_state=None,
            current_files=current_files,
            current_hashes=current_hashes,
            current_sizes=current_sizes,
        )

        assert metrics.new_files == 3
        assert metrics.modified_files == 0
        assert metrics.deleted_files == 0
        assert metrics.total_bytes_changed == 4500
        assert metrics.estimated_chunks == 11  # 4500 // 400 = 11

    def test_detects_new_files(self):
        """Should detect files added since last index."""
        config = SemanticIndexConfig(avg_chunk_bytes=400)
        calculator = ChangeMetricsCalculator(config)

        saved_state = IndexState(
            last_indexed=datetime.now(),
            total_chunks=10,
            total_files=2,
            index_version="1.0",
            file_hashes={
                "file1.py": "hash1",
                "file2.py": "hash2",
            },
        )

        current_files = [
            Path("file1.py"),
            Path("file2.py"),
            Path("file3.py"),  # NEW
            Path("file4.py"),  # NEW
        ]
        current_hashes = {
            "file1.py": "hash1",  # unchanged
            "file2.py": "hash2",  # unchanged
            "file3.py": "hash3",  # new
            "file4.py": "hash4",  # new
        }
        current_sizes = {
            "file1.py": 1000,
            "file2.py": 1000,
            "file3.py": 800,   # new file
            "file4.py": 1200,  # new file
        }

        metrics = calculator.calculate(
            saved_state=saved_state,
            current_files=current_files,
            current_hashes=current_hashes,
            current_sizes=current_sizes,
        )

        assert metrics.new_files == 2
        assert metrics.modified_files == 0
        assert metrics.deleted_files == 0
        assert metrics.total_bytes_changed == 2000  # 800 + 1200
        assert metrics.estimated_chunks == 5  # 2000 // 400

    def test_detects_modified_files(self):
        """Should detect files whose content hash changed."""
        config = SemanticIndexConfig(avg_chunk_bytes=400)
        calculator = ChangeMetricsCalculator(config)

        saved_state = IndexState(
            last_indexed=datetime.now(),
            total_chunks=10,
            total_files=3,
            index_version="1.0",
            file_hashes={
                "file1.py": "hash1_old",
                "file2.py": "hash2",
                "file3.py": "hash3_old",
            },
        )

        current_files = [
            Path("file1.py"),
            Path("file2.py"),
            Path("file3.py"),
        ]
        current_hashes = {
            "file1.py": "hash1_new",  # MODIFIED
            "file2.py": "hash2",      # unchanged
            "file3.py": "hash3_new",  # MODIFIED
        }
        current_sizes = {
            "file1.py": 1200,
            "file2.py": 1000,
            "file3.py": 800,
        }

        metrics = calculator.calculate(
            saved_state=saved_state,
            current_files=current_files,
            current_hashes=current_hashes,
            current_sizes=current_sizes,
        )

        assert metrics.new_files == 0
        assert metrics.modified_files == 2
        assert metrics.deleted_files == 0
        assert metrics.total_bytes_changed == 2000  # 1200 + 800
        assert metrics.estimated_chunks == 5

    def test_detects_deleted_files(self):
        """Should detect files removed since last index."""
        config = SemanticIndexConfig(avg_chunk_bytes=400)
        calculator = ChangeMetricsCalculator(config)

        saved_state = IndexState(
            last_indexed=datetime.now(),
            total_chunks=15,
            total_files=5,
            index_version="1.0",
            file_hashes={
                "file1.py": "hash1",
                "file2.py": "hash2",
                "file3.py": "hash3",
                "file4.py": "hash4",
                "file5.py": "hash5",
            },
        )

        current_files = [
            Path("file1.py"),
            Path("file2.py"),
            # file3.py DELETED
            # file4.py DELETED
            # file5.py DELETED
        ]
        current_hashes = {
            "file1.py": "hash1",
            "file2.py": "hash2",
        }
        current_sizes = {
            "file1.py": 1000,
            "file2.py": 1000,
        }

        metrics = calculator.calculate(
            saved_state=saved_state,
            current_files=current_files,
            current_hashes=current_hashes,
            current_sizes=current_sizes,
        )

        assert metrics.new_files == 0
        assert metrics.modified_files == 0
        assert metrics.deleted_files == 3
        assert metrics.total_bytes_changed == 0  # Deleted files don't add bytes
        assert metrics.estimated_chunks == 0

    def test_detects_mixed_changes(self):
        """Should handle new, modified, and deleted files together."""
        config = SemanticIndexConfig(avg_chunk_bytes=500)
        calculator = ChangeMetricsCalculator(config)

        saved_state = IndexState(
            last_indexed=datetime.now(),
            total_chunks=10,
            total_files=3,
            index_version="1.0",
            file_hashes={
                "file1.py": "hash1",
                "file2.py": "hash2_old",
                "file3.py": "hash3",
            },
        )

        current_files = [
            Path("file1.py"),  # unchanged
            Path("file2.py"),  # modified
            # file3.py DELETED
            Path("file4.py"),  # NEW
        ]
        current_hashes = {
            "file1.py": "hash1",
            "file2.py": "hash2_new",  # MODIFIED
            "file4.py": "hash4",      # NEW
        }
        current_sizes = {
            "file1.py": 1000,
            "file2.py": 1500,  # modified
            "file4.py": 2000,  # new
        }

        metrics = calculator.calculate(
            saved_state=saved_state,
            current_files=current_files,
            current_hashes=current_hashes,
            current_sizes=current_sizes,
        )

        assert metrics.new_files == 1
        assert metrics.modified_files == 1
        assert metrics.deleted_files == 1
        assert metrics.total_bytes_changed == 3500  # 1500 + 2000
        assert metrics.estimated_chunks == 7  # 3500 // 500

    def test_chunk_estimation_accuracy(self):
        """Chunk estimation should respect configured avg_chunk_bytes."""
        test_cases = [
            # (avg_chunk_bytes, total_bytes, expected_chunks)
            (400, 1000, 2),     # 1000 // 400 = 2
            (400, 800, 2),      # 800 // 400 = 2
            (400, 400, 1),      # 400 // 400 = 1
            (400, 200, 1),      # 200 // 400 = 0, but min is 1
            (500, 2500, 5),     # 2500 // 500 = 5
            (1000, 5000, 5),    # 5000 // 1000 = 5
        ]

        for avg_chunk_bytes, total_bytes, expected_chunks in test_cases:
            config = SemanticIndexConfig(avg_chunk_bytes=avg_chunk_bytes)
            calculator = ChangeMetricsCalculator(config)

            current_files = [Path("file1.py")]
            current_hashes = {"file1.py": "hash1"}
            current_sizes = {"file1.py": total_bytes}

            metrics = calculator.calculate(
                saved_state=None,
                current_files=current_files,
                current_hashes=current_hashes,
                current_sizes=current_sizes,
            )

            assert metrics.estimated_chunks == expected_chunks, (
                f"avg_chunk_bytes={avg_chunk_bytes}, total_bytes={total_bytes}: "
                f"expected {expected_chunks}, got {metrics.estimated_chunks}"
            )

    def test_empty_state_produces_zero_chunks(self):
        """No files should result in zero chunks estimated."""
        config = SemanticIndexConfig(avg_chunk_bytes=400)
        calculator = ChangeMetricsCalculator(config)

        metrics = calculator.calculate(
            saved_state=None,
            current_files=[],
            current_hashes={},
            current_sizes={},
        )

        assert metrics.new_files == 0
        assert metrics.modified_files == 0
        assert metrics.deleted_files == 0
        assert metrics.total_bytes_changed == 0
        assert metrics.estimated_chunks == 0

    def test_no_changes_produces_zero_chunks(self):
        """Unchanged files should result in zero chunks estimated."""
        config = SemanticIndexConfig(avg_chunk_bytes=400)
        calculator = ChangeMetricsCalculator(config)

        saved_state = IndexState(
            last_indexed=datetime.now(),
            total_chunks=10,
            total_files=2,
            index_version="1.0",
            file_hashes={
                "file1.py": "hash1",
                "file2.py": "hash2",
            },
        )

        current_files = [
            Path("file1.py"),
            Path("file2.py"),
        ]
        current_hashes = {
            "file1.py": "hash1",  # unchanged
            "file2.py": "hash2",  # unchanged
        }
        current_sizes = {
            "file1.py": 1000,
            "file2.py": 2000,
        }

        metrics = calculator.calculate(
            saved_state=saved_state,
            current_files=current_files,
            current_hashes=current_hashes,
            current_sizes=current_sizes,
        )

        assert metrics.new_files == 0
        assert metrics.modified_files == 0
        assert metrics.deleted_files == 0
        assert metrics.total_bytes_changed == 0
        assert metrics.estimated_chunks == 0

    def test_handles_zero_avg_chunk_bytes(self):
        """Should handle invalid avg_chunk_bytes gracefully."""
        config = SemanticIndexConfig(avg_chunk_bytes=0)
        calculator = ChangeMetricsCalculator(config)

        current_files = [Path("file1.py")]
        current_hashes = {"file1.py": "hash1"}
        current_sizes = {"file1.py": 1000}

        metrics = calculator.calculate(
            saved_state=None,
            current_files=current_files,
            current_hashes=current_hashes,
            current_sizes=current_sizes,
        )

        # Should use default 400 and not crash
        assert metrics.estimated_chunks == 2  # 1000 // 400 = 2
        assert metrics.total_bytes_changed == 1000

    def test_handles_negative_avg_chunk_bytes(self):
        """Should handle negative avg_chunk_bytes gracefully."""
        config = SemanticIndexConfig(avg_chunk_bytes=-100)
        calculator = ChangeMetricsCalculator(config)

        current_files = [Path("file1.py")]
        current_hashes = {"file1.py": "hash1"}
        current_sizes = {"file1.py": 1000}

        metrics = calculator.calculate(
            saved_state=None,
            current_files=current_files,
            current_hashes=current_hashes,
            current_sizes=current_sizes,
        )

        # Should use default 400 and not crash
        assert metrics.estimated_chunks == 2  # 1000 // 400 = 2
        assert metrics.total_bytes_changed == 1000

    def test_handles_missing_file_size(self):
        """Should handle missing file sizes gracefully."""
        config = SemanticIndexConfig(avg_chunk_bytes=400)
        calculator = ChangeMetricsCalculator(config)

        current_files = [
            Path("file1.py"),
            Path("file2.py"),
        ]
        current_hashes = {
            "file1.py": "hash1",
            "file2.py": "hash2",
        }
        current_sizes = {
            "file1.py": 1000,
            # file2.py size missing
        }

        metrics = calculator.calculate(
            saved_state=None,
            current_files=current_files,
            current_hashes=current_hashes,
            current_sizes=current_sizes,
        )

        assert metrics.new_files == 2
        assert metrics.total_bytes_changed == 1000  # Only file1
        assert metrics.estimated_chunks == 2  # 1000 // 400

    def test_large_file_estimation(self):
        """Should handle large files correctly."""
        config = SemanticIndexConfig(avg_chunk_bytes=400)
        calculator = ChangeMetricsCalculator(config)

        # 10 MB file
        large_file_size = 10 * 1024 * 1024

        current_files = [Path("large_file.py")]
        current_hashes = {"large_file.py": "hash1"}
        current_sizes = {"large_file.py": large_file_size}

        metrics = calculator.calculate(
            saved_state=None,
            current_files=current_files,
            current_hashes=current_hashes,
            current_sizes=current_sizes,
        )

        expected_chunks = large_file_size // 400
        assert metrics.estimated_chunks == expected_chunks
        assert metrics.total_bytes_changed == large_file_size
