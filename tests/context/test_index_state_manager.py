"""
Tests for LanceDBIndexStateManager.

Tests state persistence using LanceDB metadata table.
"""

import tempfile
from datetime import datetime
from pathlib import Path


from scrappy.context.protocols import IndexState
from scrappy.context.semantic.state import LanceDBIndexStateManager


class TestLanceDBIndexStateManager:
    """Test LanceDBIndexStateManager state persistence."""

    def test_save_and_load_roundtrip(self):
        """State persists correctly through save/load cycle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_db"
            manager = LanceDBIndexStateManager(db_path)

            # Create test state
            state = IndexState(
                last_indexed=datetime(2025, 1, 1, 12, 0, 0),
                total_chunks=100,
                total_files=10,
                index_version="1.0.0",
                file_hashes={"file1.py": "abc123", "file2.py": "def456"},
            )

            # Save state
            manager.save(state)

            # Load state
            loaded = manager.load()

            # Verify roundtrip
            assert loaded is not None
            assert loaded.last_indexed == state.last_indexed
            assert loaded.total_chunks == state.total_chunks
            assert loaded.total_files == state.total_files
            assert loaded.index_version == state.index_version
            assert loaded.file_hashes == state.file_hashes

    def test_load_returns_none_when_empty(self):
        """No state returns None on load."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_db"
            manager = LanceDBIndexStateManager(db_path)

            # Load from empty database
            result = manager.load()

            # Should return None when no state exists
            assert result is None

    def test_clear_removes_state(self):
        """clear() removes persisted state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_db"
            manager = LanceDBIndexStateManager(db_path)

            # Save state
            state = IndexState(
                last_indexed=datetime(2025, 1, 1, 12, 0, 0),
                total_chunks=50,
                total_files=5,
                index_version="1.0.0",
                file_hashes={"file1.py": "abc123"},
            )
            manager.save(state)

            # Verify state exists
            assert manager.load() is not None

            # Clear state
            manager.clear()

            # Verify state is removed
            result = manager.load()
            assert result is None

    def test_handles_corrupted_data(self):
        """Graceful degradation when data is corrupted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_db"
            manager = LanceDBIndexStateManager(db_path)

            # Save valid state first
            state = IndexState(
                last_indexed=datetime(2025, 1, 1, 12, 0, 0),
                total_chunks=100,
                total_files=10,
                index_version="1.0.0",
                file_hashes={"file1.py": "abc123"},
            )
            manager.save(state)

            # Now manually corrupt the data by writing invalid JSON
            import lancedb
            db = lancedb.connect(db_path)
            table = db.open_table("_index_meta")

            # Delete existing record
            table.delete("key = 'index_state'")

            # Add corrupted record
            corrupted_record = {
                "key": "index_state",
                "data": "{invalid json}",
            }
            table.add([corrupted_record])

            # Load should return None gracefully
            result = manager.load()
            assert result is None

    def test_save_updates_existing_state(self):
        """Saving twice updates the state instead of duplicating."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_db"
            manager = LanceDBIndexStateManager(db_path)

            # Save first state
            state1 = IndexState(
                last_indexed=datetime(2025, 1, 1, 12, 0, 0),
                total_chunks=100,
                total_files=10,
                index_version="1.0.0",
                file_hashes={"file1.py": "abc123"},
            )
            manager.save(state1)

            # Save second state with different values
            state2 = IndexState(
                last_indexed=datetime(2025, 1, 2, 12, 0, 0),
                total_chunks=200,
                total_files=20,
                index_version="1.0.0",
                file_hashes={"file1.py": "xyz789", "file3.py": "new456"},
            )
            manager.save(state2)

            # Load should return the second state
            loaded = manager.load()
            assert loaded is not None
            assert loaded.total_chunks == 200
            assert loaded.total_files == 20
            assert loaded.last_indexed == datetime(2025, 1, 2, 12, 0, 0)
            assert loaded.file_hashes == {"file1.py": "xyz789", "file3.py": "new456"}

    def test_handles_empty_file_hashes(self):
        """State can be saved and loaded with empty file_hashes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_db"
            manager = LanceDBIndexStateManager(db_path)

            # Save state with empty file_hashes
            state = IndexState(
                last_indexed=datetime(2025, 1, 1, 12, 0, 0),
                total_chunks=0,
                total_files=0,
                index_version="1.0.0",
                file_hashes={},
            )
            manager.save(state)

            # Load and verify
            loaded = manager.load()
            assert loaded is not None
            assert loaded.file_hashes == {}
            assert loaded.total_chunks == 0
            assert loaded.total_files == 0

    def test_clear_on_nonexistent_table_does_not_error(self):
        """clear() on empty database does not raise errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_db"
            manager = LanceDBIndexStateManager(db_path)

            # Clear on fresh database should not error
            manager.clear()

            # Verify database is still empty
            assert manager.load() is None
