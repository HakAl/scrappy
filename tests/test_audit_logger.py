"""
Tests for the AuditLogger crash-safe persistence functionality.
"""

import json
import threading
import pytest
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock

from scrappy.agent.audit import AuditLogger
from scrappy.infrastructure.paths import TempPathProvider


class TestAuditLoggerBasics:
    """Test basic audit logging functionality."""

    def test_log_action(self):
        """Test logging an action adds entry to log."""
        logger = AuditLogger()
        logger.log_action("read_file", {"path": "test.py"}, "file contents", True)

        assert len(logger.log) == 1
        entry = logger.log[0]
        assert entry['action'] == "read_file"
        assert entry['parameters'] == {"path": "test.py"}
        assert entry['result'] == "file contents"
        assert entry['approved'] is True
        assert 'timestamp' in entry

    def test_log_action_truncates_long_results(self):
        """Test that long results are truncated."""
        logger = AuditLogger(max_result_length=10)
        long_result = "a" * 100
        logger.log_action("test", {}, long_result, True)

        assert len(logger.log[0]['result']) == 10

    def test_clear_log(self):
        """Test clearing the log."""
        logger = AuditLogger()
        logger.log_action("test", {}, "result", True)
        logger._task_info = {"task": "test"}

        logger.clear_log()

        assert logger.log == []
        assert logger._task_info == {}

    def test_log_action_with_blocked_flag(self):
        """Test logging a blocked action includes blocked field."""
        logger = AuditLogger()
        logger.log_action(
            "write_file",
            {"path": "test.py", "content": "test"},
            "Action was blocked as duplicate",
            approved=True,
            blocked=True,
        )

        assert len(logger.log) == 1
        entry = logger.log[0]
        assert entry['action'] == "write_file"
        assert entry['blocked'] is True
        assert entry['approved'] is True

    def test_log_action_without_blocked_flag_has_no_blocked_field(self):
        """Test normal action does not include blocked field."""
        logger = AuditLogger()
        logger.log_action("read_file", {"path": "test.py"}, "contents", True)

        entry = logger.log[0]
        assert 'blocked' not in entry  # Should not be present for normal actions


class TestAutoSave:
    """Test automatic incremental saving."""

    def test_set_task_info(self, tmp_path):
        """Test setting task info stores metadata."""
        path_provider = TempPathProvider(tmp_path)
        logger = AuditLogger(path_provider=path_provider)
        logger.enable_auto_save()
        logger.set_task_info("Test task", 10, False)

        assert logger._task_info['task'] == "Test task"
        assert logger._task_info['max_iterations'] == 10
        assert logger._task_info['auto_confirm'] is False
        assert 'started_at' in logger._task_info

    def test_set_task_info_saves_immediately(self, tmp_path):
        """Test that setting task info triggers save."""
        path_provider = TempPathProvider(tmp_path)
        logger = AuditLogger(path_provider=path_provider)
        logger.enable_auto_save()
        logger.set_task_info("Test task", 10, False)

        audit_file = path_provider.audit_file()
        assert audit_file.exists()

        with open(audit_file) as f:
            data = json.load(f)

        assert data['task_info']['task'] == "Test task"
        assert data['total_actions'] == 0
        assert data['status'] == 'in_progress'

    def test_log_action_saves_incrementally(self, tmp_path):
        """Test that each action triggers a save."""
        path_provider = TempPathProvider(tmp_path)
        logger = AuditLogger(path_provider=path_provider)
        logger.enable_auto_save()
        logger.set_task_info("Test task", 10, False)

        # First action
        logger.log_action("read_file", {"path": "a.py"}, "content a", True)

        audit_file = path_provider.audit_file()
        with open(audit_file) as f:
            data = json.load(f)
        assert data['total_actions'] == 1
        assert len(data['actions']) == 1

        # Second action
        logger.log_action("write_file", {"path": "b.py", "content": "test"}, "success", True)

        with open(audit_file) as f:
            data = json.load(f)
        assert data['total_actions'] == 2
        assert len(data['actions']) == 2
        assert data['actions'][1]['action'] == "write_file"

    def test_save_builds_correct_structure(self, tmp_path):
        """Test that save() produces correct data structure."""
        path_provider = TempPathProvider(tmp_path)
        logger = AuditLogger(path_provider=path_provider)
        logger._task_info = {
            'task': 'Test task',
            'started_at': '2024-01-01T00:00:00'
        }
        logger.log_action("test", {}, "result", True)

        path = logger.save()

        with open(path) as f:
            data = json.load(f)

        assert 'task_info' in data
        assert 'actions' in data
        assert 'saved_at' in data
        assert 'total_actions' in data
        assert 'status' in data
        assert data['task_info']['task'] == 'Test task'
        assert len(data['actions']) == 1
        assert data['total_actions'] == 1

    def test_mark_complete_success(self, tmp_path):
        """Test marking task as complete successfully."""
        path_provider = TempPathProvider(tmp_path)
        logger = AuditLogger(path_provider=path_provider)
        logger.enable_auto_save()
        logger.set_task_info("Test task", 10, False)

        logger.mark_complete(True, "Task completed successfully")

        audit_file = path_provider.audit_file()
        with open(audit_file) as f:
            data = json.load(f)

        assert data['task_info']['completed'] is True
        assert data['task_info']['success'] is True
        assert data['task_info']['final_result'] == "Task completed successfully"
        assert 'completed_at' in data['task_info']
        assert data['status'] == 'completed'

    def test_mark_complete_failure(self, tmp_path):
        """Test marking task as complete with failure."""
        path_provider = TempPathProvider(tmp_path)
        logger = AuditLogger(path_provider=path_provider)
        logger.enable_auto_save()
        logger.set_task_info("Test task", 10, False)

        logger.mark_complete(False, "Max iterations reached")

        with open(path_provider.audit_file()) as f:
            data = json.load(f)

        assert data['task_info']['completed'] is True
        assert data['task_info']['success'] is False
        assert data['task_info']['final_result'] == "Max iterations reached"
        assert data['status'] == 'completed'


class TestCrashHandlers:
    """Test crash handler registration and execution."""

    def test_on_exit_saves_log(self, tmp_path):
        """Test that _on_exit saves the audit log."""
        path_provider = TempPathProvider(tmp_path)

        logger = AuditLogger(path_provider=path_provider)
        logger.enable_auto_save()
        logger.set_task_info("Test task", 10, False)
        logger.log_action("test", {}, "result", True)

        # Simulate exit
        logger._on_exit()

        audit_file = path_provider.audit_file()
        assert audit_file.exists()

        with open(audit_file) as f:
            data = json.load(f)
        assert len(data['actions']) == 1


    def test_enable_auto_save_works_from_main_thread(self, tmp_path):
        """Signal registration should work when called from main thread."""
        path_provider = TempPathProvider(tmp_path)
        audit_logger = AuditLogger(path_provider=path_provider)

        # This should work fine from main thread
        audit_logger.enable_auto_save()

        # Verify handlers were registered
        assert audit_logger._crash_handlers_registered


class TestCrashRecovery:
    """Test scenarios that simulate crashes."""

    def test_partial_execution_saved(self, tmp_path):
        """Test that partial execution is saved on crash."""
        path_provider = TempPathProvider(tmp_path)

        logger = AuditLogger(path_provider=path_provider)
        logger.enable_auto_save()
        logger.set_task_info("Create API endpoint", 10, True)

        # Simulate partial execution
        logger.log_action("read_file", {"path": "app.py"}, "existing code", True)
        logger.log_action("write_file", {"path": "api.py"}, "created", True)
        # Crash happens here - no mark_complete called

        # Verify file exists with partial state
        with open(path_provider.audit_file()) as f:
            data = json.load(f)

        assert data['task_info']['task'] == "Create API endpoint"
        assert data['total_actions'] == 2
        assert data['status'] == 'in_progress'  # Not completed
        assert 'completed' not in data['task_info']

    def test_error_state_saved(self, tmp_path):
        """Test that error state is saved."""
        path_provider = TempPathProvider(tmp_path)

        logger = AuditLogger(path_provider=path_provider)
        logger.enable_auto_save()
        logger.set_task_info("Fix bug", 5, False)

        logger.log_action("read_file", {"path": "bug.py"}, "code", True)
        logger.mark_complete(False, "Error: Network timeout")

        with open(path_provider.audit_file()) as f:
            data = json.load(f)

        assert data['task_info']['success'] is False
        assert "Network timeout" in data['task_info']['final_result']
        assert data['status'] == 'completed'

    def test_keyboard_interrupt_state_saved(self, tmp_path):
        """Test that keyboard interrupt state is saved."""
        path_provider = TempPathProvider(tmp_path)

        logger = AuditLogger(path_provider=path_provider)
        logger.enable_auto_save()
        logger.set_task_info("Long running task", 50, True)

        logger.log_action("write_file", {"path": "part1.py"}, "created", True)
        logger.log_action("write_file", {"path": "part2.py"}, "created", True)
        logger.mark_complete(False, "Interrupted by user (KeyboardInterrupt)")

        with open(path_provider.audit_file()) as f:
            data = json.load(f)

        assert data['total_actions'] == 2
        assert "Interrupted" in data['task_info']['final_result']
        assert data['status'] == 'completed'

    def test_audit_file_can_be_loaded_for_retry(self, tmp_path):
        """Test that saved audit can be loaded to understand what was done."""
        path_provider = TempPathProvider(tmp_path)

        logger = AuditLogger(path_provider=path_provider)
        logger.enable_auto_save()
        logger.set_task_info("Multi-step task", 10, False)

        # Simulate partial work
        logger.log_action("list_files", {"path": "."}, "file1.py\nfile2.py", True)
        logger.log_action("read_file", {"path": "file1.py"}, "def foo(): pass", True)
        logger.log_action("write_file", {"path": "file1.py"}, "updated", True)
        # Crash before write_file on file2.py

        # Load and analyze what was done
        with open(path_provider.audit_file()) as f:
            data = json.load(f)

        actions = [a['action'] for a in data['actions']]
        assert actions == ['list_files', 'read_file', 'write_file']

        # Can see last action was write_file on file1.py
        last_action = data['actions'][-1]
        assert last_action['action'] == 'write_file'
        assert last_action['parameters']['path'] == 'file1.py'


class TestLegacyCompatibility:
    """Test backward compatibility with old audit log format."""

    def test_save_method_still_works(self, tmp_path):
        """Test that save() method still works as before."""
        path_provider = TempPathProvider(tmp_path)
        logger = AuditLogger(path_provider=path_provider)
        logger.log_action("test", {}, "result", True)

        path = logger.save()

        assert "audit.json" in path
        assert Path(path).exists()

    def test_save_uses_custom_filename(self, tmp_path):
        """Test that save() accepts custom filename."""
        logger = AuditLogger()
        logger.log_action("test", {}, "result", True)

        path = logger.save(tmp_path, "custom_audit.json")

        assert "custom_audit.json" in path
        assert (tmp_path / "custom_audit.json").exists()

    def test_get_log_returns_list_of_dicts(self):
        """Test that get_log() returns list of action dicts."""
        logger = AuditLogger()
        logger.log_action("action1", {}, "result1", True)
        logger.log_action("action2", {}, "result2", False)

        log = logger.get_log()

        assert isinstance(log, list)
        assert len(log) == 2
        assert all(isinstance(entry, dict) for entry in log)
