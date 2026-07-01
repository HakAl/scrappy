import json
import pytest
from unittest.mock import Mock, patch
from pathlib import Path
from datetime import datetime

from scrappy.orchestrator.session import SessionManager


# -----------------------------------------------------------------------------
# Mocks & Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def mock_working_memory_class():
    """
    Mocks the WorkingMemory class.

    We need to mock:
    1. The .to_dict() method on an instance.
    2. The .from_dict() class method.
    3. The attributes accessed on the instance returned by from_dict (for stats).
    """
    with patch('scrappy.orchestrator.session.WorkingMemory') as MockClass:
        # Setup the instance returned by from_dict
        mock_instance = Mock()
        mock_instance.file_reads = {"file1.txt": "content"}
        mock_instance.search_results = ["res1", "res2"]
        mock_instance.git_operations = []
        mock_instance.discoveries = ["d1"]

        # Setup to_dict result
        mock_instance.to_dict.return_value = {
            "file_reads": {"file1.txt": "content"},
            "search_results": ["res1", "res2"],
            "git_operations": [],
            "discoveries": ["d1"]
        }

        MockClass.from_dict.return_value = mock_instance
        yield MockClass


@pytest.fixture
def session_manager(tmp_path):
    """Creates a SessionManager instance using a temporary directory."""
    return SessionManager(project_path=tmp_path)


@pytest.fixture
def sample_data():
    """Standard data used across tests."""
    return {
        "task_history": [{"task": "test", "status": "done"}],
        "session_start": datetime(2023, 1, 1, 12, 0, 0),
        "conversation_history": [{"role": "user", "content": "hi"}]
    }


# -----------------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------------

class TestSessionManager:

    def test_init_sets_paths(self, tmp_path):
        """Test that initialization sets the correct file paths."""
        manager = SessionManager(tmp_path)
        assert manager.project_path == tmp_path
        assert manager.session_file == tmp_path / ".scrappy" / "session.json"

    def test_save_session_success(self, session_manager, mock_working_memory_class, sample_data):
        """Test successful saving of a session creates a valid JSON file."""
        # Arrange
        wm_instance = mock_working_memory_class.return_value
        # Ensure the mock instance has the to_dict method configured
        wm_instance.to_dict.return_value = {"some_memory_data": True}

        # Act
        file_path = session_manager.save_session(
            working_memory=wm_instance,
            task_history=sample_data['task_history'],
            session_start=sample_data['session_start'],
            conversation_history=sample_data['conversation_history']
        )

        # Assert
        assert Path(file_path).exists()

        with open(file_path, 'r') as f:
            saved_data = json.load(f)

        assert saved_data['some_memory_data'] is True
        assert saved_data['task_history'] == sample_data['task_history']
        assert saved_data['conversation_history'] == sample_data['conversation_history']
        assert saved_data['session_start'] == sample_data['session_start'].isoformat()
        assert 'saved_at' in saved_data

    def test_save_session_runtime_error(self, session_manager, mock_working_memory_class, sample_data):
        """Test that file write errors are caught and raised as RuntimeError."""
        wm_instance = mock_working_memory_class.return_value

        # Simulate a permission error or read-only file system
        with patch("builtins.open", side_effect=PermissionError("Access Denied")):
            with pytest.raises(RuntimeError) as exc:
                session_manager.save_session(
                    working_memory=wm_instance,
                    task_history=[],
                    session_start=datetime.now()
                )
            assert "Failed to save session" in str(exc.value)

    def test_load_session_success(self, session_manager, mock_working_memory_class):
        """Test loading a valid session file."""
        # Arrange: Create a fake session file
        data = {
            "file_reads": {},
            "task_history": ["task1"],
            "conversation_history": ["msg1"],
            "saved_at": "2023-01-01T12:00:00",
            "session_start": "2023-01-01T10:00:00"
        }
        with open(session_manager.session_file, 'w') as f:
            json.dump(data, f)

        # Act
        result = session_manager.load_session()

        # Assert
        assert result['status'] == 'loaded'
        assert result['task_history'] == ["task1"]
        assert result['conversation_history'] == ["msg1"]
        # Verify WorkingMemory.from_dict was called with the full data
        mock_working_memory_class.from_dict.assert_called_once_with(data)
        # Verify stats extraction (based on the mock fixture setup)
        assert result['files_restored'] == 1  # based on mock_working_memory_class fixture
        assert result['tasks_restored'] == 1

    def test_load_session_no_file(self, session_manager):
        """Test loading when no file exists."""
        result = session_manager.load_session()
        assert result['status'] == 'no_session'
        assert 'No previous session found' in result['message']

    def test_load_session_corrupt_json(self, session_manager):
        """Test loading a malformed JSON file."""
        # Arrange
        with open(session_manager.session_file, 'w') as f:
            f.write("{ incomplete json ")

        # Act
        result = session_manager.load_session()

        # Assert
        assert result['status'] == 'error'
        # JSONDecodeError usually
        assert result['message'] is not None

    def test_load_session_restoration_error(self, session_manager, mock_working_memory_class):
        """Test when WorkingMemory.from_dict raises an exception."""
        # Arrange
        with open(session_manager.session_file, 'w') as f:
            json.dump({}, f)

        mock_working_memory_class.from_dict.side_effect = ValueError("Invalid memory structure")

        # Act
        result = session_manager.load_session()

        # Assert
        assert result['status'] == 'error'
        assert "Invalid memory structure" in result['message']

    def test_clear_session(self, session_manager):
        """Test deleting the session file."""
        # Create file
        session_manager.session_file.touch()
        assert session_manager.session_file.exists()

        # Delete
        session_manager.clear_session()
        assert not session_manager.session_file.exists()

    def test_clear_session_non_existent(self, session_manager):
        """Test clearing a session that doesn't exist (should not raise)."""
        assert not session_manager.session_file.exists()
        session_manager.clear_session()  # Should pass silently

    def test_has_session(self, session_manager):
        """Test has_session boolean check."""
        assert not session_manager.has_session()
        session_manager.session_file.touch()
        assert session_manager.has_session()

    def test_get_session_info_success(self, session_manager):
        """Test peeking at session metadata without full load."""
        # Arrange
        data = {
            "saved_at": "now",
            "session_start": "start",
            "file_reads": {"a": 1, "b": 2},
            "search_results": [1, 2, 3],
            "discoveries": [],
            "task_history": ["t1"],
            "conversation_history": ["c1"]
        }
        with open(session_manager.session_file, 'w') as f:
            json.dump(data, f)

        # Act
        info = session_manager.get_session_info()

        # Assert
        assert info['exists'] is True
        assert info['file_count'] == 2
        assert info['search_count'] == 3
        assert info['task_count'] == 1
        assert info['has_conversation'] is True

    def test_get_session_info_no_file(self, session_manager):
        """Test getting info when file doesn't exist."""
        info = session_manager.get_session_info()
        assert info['exists'] is False

    def test_get_session_info_corrupt(self, session_manager):
        """Test getting info from corrupt file."""
        with open(session_manager.session_file, 'w') as f:
            f.write("Bad JSON")

        info = session_manager.get_session_info()
        assert info['exists'] is True
        assert info['error'] == 'Could not read session file'
