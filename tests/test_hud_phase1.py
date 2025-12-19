"""
Tests for HUD Phase 1: Session-Scoped Task Storage + Turn Tracking.

Tests the foundation for the Heads-Up Display (HUD) system:
- InMemoryTaskStorage with initial_task seeding
- WorkingSet for tracking file reads/writes
- ToolContext HUD fields (task_storage, working_set, turn)
"""
import pytest
from pathlib import Path

from scrappy.protocols.tasks import (
    Task,
    TaskStatus,
    TaskPriority,
    InMemoryTaskStorage,
)
from scrappy.agent_tools.tools.base import (
    FileAccess,
    WorkingSet,
    ToolContext,
)


class TestInMemoryTaskStorageInitialTask:
    """Tests for InMemoryTaskStorage with initial_task seeding."""

    @pytest.mark.unit
    def test_initial_task_seeds_storage(self):
        """Initial task string should create first in-progress task."""
        storage = InMemoryTaskStorage(initial_task="Fix the login bug")

        tasks = storage.read_tasks()
        assert len(tasks) == 1
        assert tasks[0].description == "Fix the login bug"
        assert tasks[0].status == TaskStatus.IN_PROGRESS

    @pytest.mark.unit
    def test_initial_task_strips_whitespace(self):
        """Initial task should strip leading/trailing whitespace."""
        storage = InMemoryTaskStorage(initial_task="  Fix the bug  ")

        tasks = storage.read_tasks()
        assert tasks[0].description == "Fix the bug"

    @pytest.mark.unit
    def test_empty_initial_task_ignored(self):
        """Empty or whitespace-only initial_task should not create task."""
        storage1 = InMemoryTaskStorage(initial_task="")
        storage2 = InMemoryTaskStorage(initial_task="   ")
        storage3 = InMemoryTaskStorage(initial_task=None)

        assert storage1.read_tasks() == []
        assert storage2.read_tasks() == []
        assert storage3.read_tasks() == []

    @pytest.mark.unit
    def test_initial_task_with_existing_tasks(self):
        """Initial task should be prepended to existing tasks."""
        existing = [Task(description="Existing task", status=TaskStatus.PENDING)]
        storage = InMemoryTaskStorage(initial=existing, initial_task="New task")

        tasks = storage.read_tasks()
        assert len(tasks) == 2
        assert tasks[0].description == "New task"  # Prepended
        assert tasks[0].status == TaskStatus.IN_PROGRESS
        assert tasks[1].description == "Existing task"

    @pytest.mark.unit
    def test_storage_is_session_scoped(self):
        """Each new storage instance should be independent."""
        storage1 = InMemoryTaskStorage(initial_task="Task 1")
        storage2 = InMemoryTaskStorage(initial_task="Task 2")

        assert storage1.read_tasks()[0].description == "Task 1"
        assert storage2.read_tasks()[0].description == "Task 2"

        # Modifying one doesn't affect the other
        storage1.clear()
        assert storage1.read_tasks() == []
        assert len(storage2.read_tasks()) == 1


class TestWorkingSet:
    """Tests for WorkingSet file tracking."""

    @pytest.mark.unit
    def test_record_read_adds_file(self):
        """Recording a read should add file to working set."""
        ws = WorkingSet()
        ws.record_read("src/main.py", turn=1)

        recent = ws.get_recent()
        assert len(recent) == 1
        assert recent[0].path == "src/main.py"
        assert recent[0].read_turn == 1
        assert recent[0].write_turn is None

    @pytest.mark.unit
    def test_record_read_with_line_range(self):
        """Recording a read should track line range."""
        ws = WorkingSet()
        ws.record_read("src/main.py", turn=1, line_start=10, line_end=50)

        recent = ws.get_recent()
        assert recent[0].line_start == 10
        assert recent[0].line_end == 50

    @pytest.mark.unit
    def test_record_write_adds_file(self):
        """Recording a write should add file to working set."""
        ws = WorkingSet()
        ws.record_write("src/main.py", turn=2)

        recent = ws.get_recent()
        assert len(recent) == 1
        assert recent[0].path == "src/main.py"
        assert recent[0].write_turn == 2
        assert recent[0].read_turn is None

    @pytest.mark.unit
    def test_record_read_then_write_updates_same_file(self):
        """Reading then writing same file should update, not duplicate."""
        ws = WorkingSet()
        ws.record_read("src/main.py", turn=1, line_start=10, line_end=50)
        ws.record_write("src/main.py", turn=2)

        recent = ws.get_recent()
        assert len(recent) == 1
        assert recent[0].read_turn == 1
        assert recent[0].write_turn == 2
        assert recent[0].line_start == 10

    @pytest.mark.unit
    def test_get_recent_orders_by_recency(self):
        """get_recent should return most recently accessed first."""
        ws = WorkingSet()
        ws.record_read("first.py", turn=1)
        ws.record_read("second.py", turn=2)
        ws.record_read("third.py", turn=3)

        recent = ws.get_recent()
        assert recent[0].path == "third.py"
        assert recent[1].path == "second.py"
        assert recent[2].path == "first.py"

    @pytest.mark.unit
    def test_max_files_limit(self):
        """Working set should respect max_files limit."""
        ws = WorkingSet(max_files=3)

        for i in range(5):
            ws.record_read(f"file{i}.py", turn=i)

        recent = ws.get_recent()
        assert len(recent) == 3
        # Should have most recent files
        paths = [f.path for f in recent]
        assert "file4.py" in paths
        assert "file3.py" in paths
        assert "file2.py" in paths
        assert "file0.py" not in paths  # Dropped as oldest

    @pytest.mark.unit
    def test_remove_deleted_removes_file(self):
        """remove_deleted should remove file from working set."""
        ws = WorkingSet()
        ws.record_read("file.py", turn=1)
        ws.record_read("other.py", turn=2)

        ws.remove_deleted("file.py")

        recent = ws.get_recent()
        assert len(recent) == 1
        assert recent[0].path == "other.py"

    @pytest.mark.unit
    def test_remove_deleted_nonexistent_is_safe(self):
        """remove_deleted on nonexistent file should not error."""
        ws = WorkingSet()
        ws.remove_deleted("nonexistent.py")  # Should not raise


class TestFileAccess:
    """Tests for FileAccess dataclass."""

    @pytest.mark.unit
    def test_file_access_defaults(self):
        """FileAccess should have sensible defaults."""
        fa = FileAccess(path="test.py")

        assert fa.path == "test.py"
        assert fa.line_start is None
        assert fa.line_end is None
        assert fa.read_turn is None
        assert fa.write_turn is None

    @pytest.mark.unit
    def test_file_access_with_all_fields(self):
        """FileAccess should store all fields correctly."""
        fa = FileAccess(
            path="test.py",
            line_start=10,
            line_end=50,
            read_turn=1,
            write_turn=2,
        )

        assert fa.path == "test.py"
        assert fa.line_start == 10
        assert fa.line_end == 50
        assert fa.read_turn == 1
        assert fa.write_turn == 2


class TestToolContextHUD:
    """Tests for ToolContext HUD fields."""

    @pytest.mark.unit
    def test_tool_context_has_hud_fields(self, tmp_path):
        """ToolContext should have task_storage, working_set, turn fields."""
        ctx = ToolContext(project_root=tmp_path)

        # Fields should exist with defaults
        assert ctx.task_storage is None
        assert ctx.working_set is None
        assert ctx.turn == 0

    @pytest.mark.unit
    def test_tool_context_with_hud_components(self, tmp_path):
        """ToolContext should accept HUD components."""
        storage = InMemoryTaskStorage(initial_task="Test task")
        ws = WorkingSet()

        ctx = ToolContext(
            project_root=tmp_path,
            task_storage=storage,
            working_set=ws,
            turn=5,
        )

        assert ctx.task_storage is storage
        assert ctx.working_set is ws
        assert ctx.turn == 5

    @pytest.mark.unit
    def test_turn_can_be_incremented(self, tmp_path):
        """Turn should be mutable for loop increment."""
        ctx = ToolContext(project_root=tmp_path, turn=0)

        ctx.turn = 1
        assert ctx.turn == 1

        ctx.turn += 1
        assert ctx.turn == 2


class TestTaskToolWithContextStorage:
    """Tests for TaskTool using context.task_storage."""

    @pytest.mark.unit
    def test_task_tool_prefers_context_storage(self, tmp_path):
        """TaskTool should use context.task_storage when available."""
        from scrappy.agent_tools.tools.task_tools import TaskTool

        # Create context with in-memory storage
        storage = InMemoryTaskStorage()
        ctx = ToolContext(project_root=tmp_path, task_storage=storage)

        tool = TaskTool()
        result = tool.execute(ctx, command="add", description="Test task")

        assert result.success
        # Should be in the context storage, not a file
        assert len(storage.read_tasks()) == 1
        assert storage.read_tasks()[0].description == "Test task"

    @pytest.mark.unit
    def test_task_tool_uses_injected_over_context(self, tmp_path):
        """TaskTool injected storage takes priority over context."""
        from scrappy.agent_tools.tools.task_tools import TaskTool

        injected = InMemoryTaskStorage()
        context_storage = InMemoryTaskStorage()
        ctx = ToolContext(project_root=tmp_path, task_storage=context_storage)

        tool = TaskTool(storage=injected)
        tool.execute(ctx, command="add", description="Test")

        # Should use injected, not context
        assert len(injected.read_tasks()) == 1
        assert len(context_storage.read_tasks()) == 0
