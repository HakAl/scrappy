"""
Tests for SessionManager.

Focuses on proving BEHAVIOR works, not structure.
Following CLAUDE.md guidelines:
- Tests prove features work, not just that code runs
- Edge cases covered (missing files, corrupted JSON, permission errors)
- Minimal mocking (using temporary directories for file operations)
- Tests would fail if feature breaks
"""

import pytest
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from src.orchestrator.session import SessionManager
from src.orchestrator.memory import WorkingMemory


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    # Cleanup
    try:
        shutil.rmtree(temp_path)
    except:
        pass  # Ignore cleanup errors on Windows


class TestSessionSaving:
    """Test that session saving actually persists data correctly."""

    def test_save_creates_session_file(self, temp_dir):
        """Saving a session should create a JSON file."""
        manager = SessionManager(temp_dir)
        memory = WorkingMemory()
        task_history = []
        session_start = datetime.now()

        path = manager.save_session(memory, task_history, session_start)

        assert manager.session_file.exists()
        assert str(manager.session_file) in path

    def test_save_includes_all_required_fields(self, temp_dir):
        """Saved session should include all required data."""
        manager = SessionManager(temp_dir)
        memory = WorkingMemory()
        memory.remember_file_read('/test/file.py', 'content', 10)
        task_history = [{'task': 'test'}]
        session_start = datetime.now()
        conversation = [{'role': 'user', 'content': 'test'}]

        manager.save_session(memory, task_history, session_start, conversation)

        # Read the saved file
        with open(manager.session_file) as f:
            data = json.load(f)

        assert 'saved_at' in data
        assert 'session_start' in data
        assert 'task_history' in data
        assert 'conversation_history' in data
        assert 'file_reads' in data  # From working memory

    def test_save_preserves_working_memory_data(self, temp_dir):
        """Saved session should preserve working memory contents."""
        manager = SessionManager(temp_dir)
        memory = WorkingMemory()
        memory.remember_file_read('/test/file.py', 'content', 10)
        memory.remember_search('test query', ['result1', 'result2'])
        memory.add_discovery('Found something', 'file.py:10')

        manager.save_session(memory, [], datetime.now())

        # Read back and verify
        with open(manager.session_file) as f:
            data = json.load(f)

        assert len(data['file_reads']) > 0
        assert len(data['search_results']) > 0
        assert len(data['discoveries']) > 0

    def test_save_returns_file_path(self, temp_dir):
        """save_session should return path to saved file."""
        manager = SessionManager(temp_dir)
        memory = WorkingMemory()

        path = manager.save_session(memory, [], datetime.now())

        assert path is not None
        assert 'session.json' in path
        assert '.scrappy' in path

    def test_save_overwrites_existing_session(self, temp_dir):
        """Saving multiple times should overwrite previous session."""
        manager = SessionManager(temp_dir)
        memory1 = WorkingMemory()
        memory1.remember_file_read('file1.py', 'content1', 5)

        manager.save_session(memory1, [], datetime.now())

        # Save again with different data
        memory2 = WorkingMemory()
        memory2.remember_file_read('file2.py', 'content2', 10)

        manager.save_session(memory2, [], datetime.now())

        # Read back - should have second session's data
        with open(manager.session_file) as f:
            data = json.load(f)

        assert len(data['file_reads']) == 1
        assert 'file2.py' in str(data['file_reads'])


class TestSessionLoading:
    """Test that session loading actually restores data correctly."""

    def test_load_returns_no_session_when_missing(self, temp_dir):
        """Loading when no session exists should return appropriate status."""
        manager = SessionManager(temp_dir)

        result = manager.load_session()

        assert result['status'] == 'no_session'
        assert 'message' in result

    def test_load_returns_loaded_status_when_exists(self, temp_dir):
        """Loading existing session should return 'loaded' status."""
        manager = SessionManager(temp_dir)
        memory = WorkingMemory()
        manager.save_session(memory, [], datetime.now())

        result = manager.load_session()

        assert result['status'] == 'loaded'

    def test_load_rehydrates_working_memory(self, temp_dir):
        """Loading should restore WorkingMemory with all data."""
        manager = SessionManager(temp_dir)
        memory = WorkingMemory()
        memory.remember_file_read('/test/file.py', 'test content', 20)
        memory.remember_search('query', ['result'])
        manager.save_session(memory, [], datetime.now())

        result = manager.load_session()

        restored_memory = result['working_memory']
        assert isinstance(restored_memory, WorkingMemory)
        assert len(restored_memory.file_reads) == 1
        assert len(restored_memory.search_results) == 1

    def test_load_returns_task_history(self, temp_dir):
        """Loading should return task history."""
        manager = SessionManager(temp_dir)
        memory = WorkingMemory()
        tasks = [
            {'provider': 'cerebras', 'tokens': 100},
            {'provider': 'groq', 'tokens': 200}
        ]
        manager.save_session(memory, tasks, datetime.now())

        result = manager.load_session()

        assert result['task_history'] == tasks
        assert len(result['task_history']) == 2

    def test_load_returns_conversation_history(self, temp_dir):
        """Loading should return conversation history."""
        manager = SessionManager(temp_dir)
        memory = WorkingMemory()
        conversation = [
            {'role': 'user', 'content': 'Hello'},
            {'role': 'assistant', 'content': 'Hi'}
        ]
        manager.save_session(memory, [], datetime.now(), conversation)

        result = manager.load_session()

        assert result['conversation_history'] == conversation
        assert len(result['conversation_history']) == 2

    def test_load_returns_restoration_counts(self, temp_dir):
        """Loading should return counts of restored items."""
        manager = SessionManager(temp_dir)
        memory = WorkingMemory()
        memory.remember_file_read('file1.py', 'content', 10)
        memory.remember_file_read('file2.py', 'content', 20)
        memory.remember_search('query', ['result'])
        manager.save_session(memory, [{'task': 1}], datetime.now())

        result = manager.load_session()

        assert result['files_restored'] == 2
        assert result['searches_restored'] == 1
        assert result['tasks_restored'] == 1


class TestSessionClearing:
    """Test that session clearing actually removes data."""

    def test_clear_deletes_session_file(self, temp_dir):
        """clear_session should delete the session file."""
        manager = SessionManager(temp_dir)
        memory = WorkingMemory()
        manager.save_session(memory, [], datetime.now())

        assert manager.session_file.exists()

        manager.clear_session()

        assert not manager.session_file.exists()

    def test_clear_when_no_session_does_not_error(self, temp_dir):
        """Clearing when no session exists should not raise error."""
        manager = SessionManager(temp_dir)

        # Should not crash
        manager.clear_session()

        assert not manager.session_file.exists()


class TestSessionChecking:
    """Test session existence checking."""

    def test_has_session_returns_false_when_no_session(self, temp_dir):
        """has_session should return False when no session exists."""
        manager = SessionManager(temp_dir)

        assert manager.has_session() is False

    def test_has_session_returns_true_when_session_exists(self, temp_dir):
        """has_session should return True when session exists."""
        manager = SessionManager(temp_dir)
        memory = WorkingMemory()
        manager.save_session(memory, [], datetime.now())

        assert manager.has_session() is True

    def test_get_session_info_returns_exists_false_when_missing(self, temp_dir):
        """get_session_info should indicate session doesn't exist."""
        manager = SessionManager(temp_dir)

        info = manager.get_session_info()

        assert info['exists'] is False

    def test_get_session_info_returns_metadata_when_exists(self, temp_dir):
        """get_session_info should return session metadata."""
        manager = SessionManager(temp_dir)
        memory = WorkingMemory()
        manager.save_session(memory, [], datetime.now())

        info = manager.get_session_info()

        assert info['exists'] is True
        assert 'saved_at' in info
        assert 'session_start' in info


class TestEdgeCases:
    """Test boundary conditions and edge cases."""

    def test_handles_empty_task_history(self, temp_dir):
        """Should handle empty task history correctly."""
        manager = SessionManager(temp_dir)
        memory = WorkingMemory()
        manager.save_session(memory, [], datetime.now())

        result = manager.load_session()

        assert result['task_history'] == []
        assert result['tasks_restored'] == 0

    def test_handles_empty_conversation_history(self, temp_dir):
        """Should handle empty conversation history correctly."""
        manager = SessionManager(temp_dir)
        memory = WorkingMemory()
        manager.save_session(memory, [], datetime.now(), [])

        result = manager.load_session()

        assert result['conversation_history'] == []

    def test_handles_missing_optional_fields(self, temp_dir):
        """Should handle session files missing optional fields in working memory dict."""
        manager = SessionManager(temp_dir)
        memory = WorkingMemory()

        # Save with minimal data
        manager.save_session(memory, [], datetime.now())

        # Manually modify to remove optional fields
        with open(manager.session_file, 'r') as f:
            data = json.load(f)

        # Remove optional conversation_history
        data.pop('conversation_history', None)

        with open(manager.session_file, 'w') as f:
            json.dump(data, f)

        result = manager.load_session()

        # Should load successfully with defaults for missing fields
        assert result['status'] == 'loaded'
        assert result.get('conversation_history', []) == []

    def test_handles_corrupted_json(self, temp_dir):
        """Should handle corrupted JSON gracefully."""
        manager = SessionManager(temp_dir)

        # Write invalid JSON
        with open(manager.session_file, 'w') as f:
            f.write('{ invalid json }')

        result = manager.load_session()

        assert result['status'] == 'error'
        assert 'message' in result

    def test_handles_large_session_data(self, temp_dir):
        """Should handle sessions with large amounts of data (respects LRU limits)."""
        manager = SessionManager(temp_dir)
        # WorkingMemory has max_file_cache=20, max_searches=10 by default
        memory = WorkingMemory()

        # Add lots of data - only the most recent will be kept due to LRU
        for i in range(100):
            memory.remember_file_read(f'file{i}.py', f'content{i}', i)
            memory.remember_search(f'query{i}', [f'result{i}'])

        tasks = [{'task': i} for i in range(100)]

        # Should save and load successfully
        manager.save_session(memory, tasks, datetime.now())
        result = manager.load_session()

        assert result['status'] == 'loaded'
        # WorkingMemory keeps only last 20 files (LRU cache)
        assert result['files_restored'] == 20
        # WorkingMemory keeps only last 10 searches
        assert result['searches_restored'] == 10
        # Task history has no limit
        assert result['tasks_restored'] == 100


class TestSaveErrorHandling:
    """Test error handling during save operations."""

    def test_save_raises_error_on_failure(self, temp_dir):
        """save_session should raise RuntimeError if save fails."""
        manager = SessionManager(temp_dir)

        # Create a directory where session file should be (causes write to fail)
        manager.session_file.mkdir(parents=True, exist_ok=True)

        memory = WorkingMemory()

        # Save should raise RuntimeError
        with pytest.raises(RuntimeError) as exc_info:
            manager.save_session(memory, [], datetime.now())

        assert 'Failed to save session' in str(exc_info.value)
