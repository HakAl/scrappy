"""Tests for task management tools."""

import tempfile
from pathlib import Path

import pytest

from scrappy.agent_tools.tools.base import ToolContext
from scrappy.agent_tools.tools.task_tools import (
    MarkdownTaskStorage,
    TaskTool,
    TASK_PATTERN,
)
from scrappy.agent_config import AgentConfig
from scrappy.protocols.tasks import (
    Task,
    TaskStatus,
    TaskPriority,
    InMemoryTaskStorage,
)


class TestTaskDataclass:
    """Test Task dataclass behavior."""

    def test_create_simple_task(self):
        """Can create task with just description and status."""
        task = Task(description="Do something", status=TaskStatus.PENDING)
        assert task.description == "Do something"
        assert task.status == TaskStatus.PENDING
        assert task.priority is None

    def test_create_task_with_priority(self):
        """Can create task with priority."""
        task = Task(
            description="Urgent task",
            status=TaskStatus.PENDING,
            priority=TaskPriority.HIGH,
        )
        assert task.priority == TaskPriority.HIGH




class TestTaskPattern:
    """Test the regex pattern for parsing task lines."""

    def test_matches_pending_task(self):
        """Pattern matches pending task."""
        match = TASK_PATTERN.match("- [ ] Do something")
        assert match is not None
        assert match.group(1) == " "
        assert match.group(3) == "Do something"

    def test_matches_done_task(self):
        """Pattern matches completed task."""
        match = TASK_PATTERN.match("- [x] Done task")
        assert match is not None
        assert match.group(1) == "x"

    def test_matches_in_progress_task(self):
        """Pattern matches in-progress task."""
        match = TASK_PATTERN.match("- [>] Working on it")
        assert match is not None
        assert match.group(1) == ">"

    def test_matches_task_with_priority(self):
        """Pattern matches task with priority."""
        match = TASK_PATTERN.match("- [ ] [HIGH] Important task")
        assert match is not None
        assert match.group(2) == "HIGH"
        assert match.group(3) == "Important task"

    def test_matches_asterisk_bullet(self):
        """Pattern matches asterisk bullet."""
        match = TASK_PATTERN.match("* [ ] Task with asterisk")
        assert match is not None

    def test_ignores_header_lines(self):
        """Pattern does not match header lines."""
        match = TASK_PATTERN.match("# Agent Tasks")
        assert match is None

    def test_ignores_plain_text(self):
        """Pattern does not match plain text."""
        match = TASK_PATTERN.match("Some random text")
        assert match is None


class TestMarkdownTaskStorage:
    """Test MarkdownTaskStorage file operations."""

    def test_read_empty_returns_empty_list(self):
        """Reading non-existent file returns empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / ".scrappy" / ".todo.md"
            storage = MarkdownTaskStorage(path)

            tasks = storage.read_tasks()

            assert tasks == []

    def test_exists_returns_false_when_no_file(self):
        """exists() returns False when file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / ".scrappy" / ".todo.md"
            storage = MarkdownTaskStorage(path)

            assert storage.exists() is False

    def test_write_creates_directory_and_file(self):
        """write_tasks creates parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / ".scrappy" / ".todo.md"
            storage = MarkdownTaskStorage(path)

            storage.write_tasks([
                Task(description="Test task", status=TaskStatus.PENDING)
            ])

            assert path.exists()
            assert storage.exists() is True

    def test_write_and_read_roundtrip(self):
        """Tasks survive write/read roundtrip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / ".scrappy" / ".todo.md"
            storage = MarkdownTaskStorage(path)

            original = [
                Task("First task", TaskStatus.DONE),
                Task("Second task", TaskStatus.IN_PROGRESS, TaskPriority.HIGH),
                Task("Third task", TaskStatus.PENDING, TaskPriority.LOW),
            ]
            storage.write_tasks(original)
            loaded = storage.read_tasks()

            assert len(loaded) == 3
            assert loaded[0].description == "First task"
            assert loaded[0].status == TaskStatus.DONE
            assert loaded[1].status == TaskStatus.IN_PROGRESS
            assert loaded[1].priority == TaskPriority.HIGH
            assert loaded[2].priority == TaskPriority.LOW

    def test_clear_removes_file(self):
        """clear() removes the task file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / ".scrappy" / ".todo.md"
            storage = MarkdownTaskStorage(path)

            storage.write_tasks([Task("Test", TaskStatus.PENDING)])
            assert path.exists()

            storage.clear()
            assert not path.exists()
  # Should not raise

    def test_preserves_header_format(self):
        """Written file has proper markdown header."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / ".scrappy" / ".todo.md"
            storage = MarkdownTaskStorage(path)

            storage.write_tasks([Task("Test", TaskStatus.PENDING)])
            content = path.read_text()

            assert content.startswith("# Agent Tasks")


class TestInMemoryTaskStorage:
    """Test InMemoryTaskStorage for testing."""

    def test_starts_empty(self):
        """Empty storage starts with no tasks."""
        storage = InMemoryTaskStorage()
        assert storage.read_tasks() == []
        assert storage.exists() is False

    def test_starts_with_initial_tasks(self):
        """Can initialize with tasks."""
        initial = [Task("Test", TaskStatus.PENDING)]
        storage = InMemoryTaskStorage(initial)

        assert len(storage.read_tasks()) == 1
        assert storage.exists() is True

    def test_write_makes_exists_true(self):
        """Writing tasks sets exists to True."""
        storage = InMemoryTaskStorage()
        storage.write_tasks([Task("Test", TaskStatus.PENDING)])

        assert storage.exists() is True

    def test_clear_resets_storage(self):
        """clear() empties storage and resets exists."""
        storage = InMemoryTaskStorage([Task("Test", TaskStatus.PENDING)])
        storage.clear()

        assert storage.read_tasks() == []
        assert storage.exists() is False


class TestTaskToolProperties:
    """Test TaskTool properties."""

    def test_name(self):
        """Tool has correct name."""
        tool = TaskTool()
        assert tool.name == "task"

    def test_description(self):
        """Tool has description."""
        tool = TaskTool()
        assert tool.description
        assert "task" in tool.description.lower()

    def test_parameters(self):
        """Tool has expected parameters."""
        tool = TaskTool()
        param_names = [p.name for p in tool.parameters]

        assert "command" in param_names
        assert "description" in param_names
        assert "task_id" in param_names
        assert "status" in param_names
        assert "priority" in param_names
        assert "filter" in param_names


class TestTaskToolAdd:
    """Test task add command."""

    def test_adds_task_to_empty_list(self):
        """Can add task to empty storage."""
        storage = InMemoryTaskStorage()
        tool = TaskTool(storage=storage)
        context = ToolContext(project_root=Path("."), config=AgentConfig())

        result = tool.execute(context, command="add", description="Do thing")

        assert result.success
        assert "Added task #1" in result.output
        assert len(storage.read_tasks()) == 1

    def test_adds_task_with_priority(self):
        """Can add task with priority."""
        storage = InMemoryTaskStorage()
        tool = TaskTool(storage=storage)
        context = ToolContext(project_root=Path("."), config=AgentConfig())

        result = tool.execute(
            context, command="add", description="Urgent", priority="high"
        )

        assert result.success
        assert "[HIGH]" in result.output
        tasks = storage.read_tasks()
        assert tasks[0].priority == TaskPriority.HIGH

    def test_rejects_empty_description(self):
        """Empty description returns error."""
        storage = InMemoryTaskStorage()
        tool = TaskTool(storage=storage)
        context = ToolContext(project_root=Path("."), config=AgentConfig())

        result = tool.execute(context, command="add", description="")

        assert not result.success
        assert "cannot be empty" in result.error

    def test_rejects_invalid_priority(self):
        """Invalid priority returns error."""
        storage = InMemoryTaskStorage()
        tool = TaskTool(storage=storage)
        context = ToolContext(project_root=Path("."), config=AgentConfig())

        result = tool.execute(
            context, command="add", description="Test", priority="urgent"
        )

        assert not result.success
        assert "Invalid priority" in result.error

    def test_sets_tasks_changed_metadata(self):
        """Add sets tasks_changed metadata."""
        storage = InMemoryTaskStorage()
        tool = TaskTool(storage=storage)
        context = ToolContext(project_root=Path("."), config=AgentConfig())

        result = tool.execute(context, command="add", description="Test")

        assert result.metadata.get("tasks_changed") is True
        assert "tasks" in result.metadata


class TestTaskToolList:
    """Test task list command."""

    def test_list_empty_storage(self):
        """List on empty storage returns helpful message."""
        storage = InMemoryTaskStorage()
        tool = TaskTool(storage=storage)
        context = ToolContext(project_root=Path("."), config=AgentConfig())

        result = tool.execute(context, command="list")

        assert result.success
        assert "No tasks found" in result.output

    def test_list_shows_all_tasks(self):
        """List shows all tasks with indices."""
        storage = InMemoryTaskStorage([
            Task("First", TaskStatus.DONE),
            Task("Second", TaskStatus.PENDING),
        ])
        tool = TaskTool(storage=storage)
        context = ToolContext(project_root=Path("."), config=AgentConfig())

        result = tool.execute(context, command="list")

        assert result.success
        assert "1." in result.output
        assert "2." in result.output
        assert "First" in result.output
        assert "Second" in result.output

    def test_list_filter_pending(self):
        """Can filter to pending tasks only."""
        storage = InMemoryTaskStorage([
            Task("Done task", TaskStatus.DONE),
            Task("Pending task", TaskStatus.PENDING),
        ])
        tool = TaskTool(storage=storage)
        context = ToolContext(project_root=Path("."), config=AgentConfig())

        result = tool.execute(context, command="list", filter="pending")

        assert result.success
        assert "Pending task" in result.output
        assert "Done task" not in result.output

    def test_list_shows_in_progress_marker(self):
        """In-progress tasks show <-- marker."""
        storage = InMemoryTaskStorage([
            Task("Working", TaskStatus.IN_PROGRESS),
        ])
        tool = TaskTool(storage=storage)
        context = ToolContext(project_root=Path("."), config=AgentConfig())

        result = tool.execute(context, command="list")

        assert "<--" in result.output

    def test_list_shows_checkboxes(self):
        """List shows appropriate checkboxes."""
        storage = InMemoryTaskStorage([
            Task("Done", TaskStatus.DONE),
            Task("Progress", TaskStatus.IN_PROGRESS),
            Task("Pending", TaskStatus.PENDING),
        ])
        tool = TaskTool(storage=storage)
        context = ToolContext(project_root=Path("."), config=AgentConfig())

        result = tool.execute(context, command="list")

        assert "[x]" in result.output
        assert "[>]" in result.output
        assert "[ ]" in result.output


class TestTaskToolUpdate:
    """Test task update command."""

    def test_update_to_done(self):
        """Can mark task as done."""
        storage = InMemoryTaskStorage([
            Task("Test task", TaskStatus.PENDING),
        ])
        tool = TaskTool(storage=storage)
        context = ToolContext(project_root=Path("."), config=AgentConfig())

        result = tool.execute(context, command="update", task_id=1, status="done")

        assert result.success
        assert "Completed" in result.output
        assert storage.read_tasks()[0].status == TaskStatus.DONE

    def test_update_to_in_progress(self):
        """Can mark task as in-progress."""
        storage = InMemoryTaskStorage([
            Task("Test task", TaskStatus.PENDING),
        ])
        tool = TaskTool(storage=storage)
        context = ToolContext(project_root=Path("."), config=AgentConfig())

        result = tool.execute(
            context, command="update", task_id=1, status="in_progress"
        )

        assert result.success
        assert "Started" in result.output
        assert storage.read_tasks()[0].status == TaskStatus.IN_PROGRESS

    def test_update_invalid_id(self):
        """Invalid task_id returns error."""
        storage = InMemoryTaskStorage([
            Task("Test task", TaskStatus.PENDING),
        ])
        tool = TaskTool(storage=storage)
        context = ToolContext(project_root=Path("."), config=AgentConfig())

        result = tool.execute(context, command="update", task_id=5, status="done")

        assert not result.success
        assert "not found" in result.error

    def test_update_requires_task_id(self):
        """Update without task_id returns error."""
        storage = InMemoryTaskStorage([Task("Test", TaskStatus.PENDING)])
        tool = TaskTool(storage=storage)
        context = ToolContext(project_root=Path("."), config=AgentConfig())

        result = tool.execute(context, command="update", status="done")

        assert not result.success
        assert "task_id is required" in result.error

    def test_update_requires_status(self):
        """Update without status returns error."""
        storage = InMemoryTaskStorage([Task("Test", TaskStatus.PENDING)])
        tool = TaskTool(storage=storage)
        context = ToolContext(project_root=Path("."), config=AgentConfig())

        result = tool.execute(context, command="update", task_id=1)

        assert not result.success
        assert "status is required" in result.error

    def test_update_sets_tasks_changed_metadata(self):
        """Update sets tasks_changed metadata."""
        storage = InMemoryTaskStorage([Task("Test", TaskStatus.PENDING)])
        tool = TaskTool(storage=storage)
        context = ToolContext(project_root=Path("."), config=AgentConfig())

        result = tool.execute(context, command="update", task_id=1, status="done")

        assert result.metadata.get("tasks_changed") is True


class TestTaskToolDelete:
    """Test task delete command."""

    def test_delete_task(self):
        """Can delete a task."""
        storage = InMemoryTaskStorage([
            Task("First", TaskStatus.PENDING),
            Task("Second", TaskStatus.PENDING),
        ])
        tool = TaskTool(storage=storage)
        context = ToolContext(project_root=Path("."), config=AgentConfig())

        result = tool.execute(context, command="delete", task_id=1)

        assert result.success
        assert "Deleted" in result.output
        assert len(storage.read_tasks()) == 1
        assert storage.read_tasks()[0].description == "Second"

    def test_delete_invalid_id(self):
        """Invalid task_id returns error."""
        storage = InMemoryTaskStorage([Task("Test", TaskStatus.PENDING)])
        tool = TaskTool(storage=storage)
        context = ToolContext(project_root=Path("."), config=AgentConfig())

        result = tool.execute(context, command="delete", task_id=5)

        assert not result.success
        assert "not found" in result.error

    def test_delete_requires_task_id(self):
        """Delete without task_id returns error."""
        storage = InMemoryTaskStorage([Task("Test", TaskStatus.PENDING)])
        tool = TaskTool(storage=storage)
        context = ToolContext(project_root=Path("."), config=AgentConfig())

        result = tool.execute(context, command="delete")

        assert not result.success
        assert "task_id is required" in result.error


class TestTaskToolClear:
    """Test task clear command."""

    def test_clear_removes_all_tasks(self):
        """Clear removes all tasks."""
        storage = InMemoryTaskStorage([
            Task("First", TaskStatus.PENDING),
            Task("Second", TaskStatus.DONE),
        ])
        tool = TaskTool(storage=storage)
        context = ToolContext(project_root=Path("."), config=AgentConfig())

        result = tool.execute(context, command="clear")

        assert result.success
        assert "Cleared 2 tasks" in result.output
        assert not storage.exists()

    def test_clear_empty_storage(self):
        """Clear on empty storage returns message."""
        storage = InMemoryTaskStorage()
        tool = TaskTool(storage=storage)
        context = ToolContext(project_root=Path("."), config=AgentConfig())

        result = tool.execute(context, command="clear")

        assert result.success
        assert "No tasks to clear" in result.output


class TestTaskToolUnknownCommand:
    """Test unknown command handling."""

    def test_unknown_command_returns_error(self):
        """Unknown command returns helpful error."""
        storage = InMemoryTaskStorage()
        tool = TaskTool(storage=storage)
        context = ToolContext(project_root=Path("."), config=AgentConfig())

        result = tool.execute(context, command="foo")

        assert not result.success
        assert "Unknown command" in result.error
        assert "add, list, update, delete, clear" in result.error


class TestTaskToolIntegration:
    """Integration tests with real file storage."""

    def test_full_workflow_with_file_storage(self):
        """Test complete add/list/update/delete workflow with files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            tool = TaskTool()
            context = ToolContext(project_root=project_root, config=AgentConfig())

            # Add tasks
            result = tool.execute(
                context, command="add", description="First task", priority="high"
            )
            assert result.success

            result = tool.execute(
                context, command="add", description="Second task"
            )
            assert result.success

            # List tasks
            result = tool.execute(context, command="list")
            assert "First task" in result.output
            assert "Second task" in result.output

            # Update task
            result = tool.execute(
                context, command="update", task_id=1, status="done"
            )
            assert result.success

            # Verify file persisted
            todo_file = project_root / ".scrappy" / ".todo.md"
            assert todo_file.exists()
            content = todo_file.read_text()
            assert "[x]" in content
            assert "First task" in content

            # Delete task
            result = tool.execute(context, command="delete", task_id=2)
            assert result.success

            # Clear remaining
            result = tool.execute(context, command="clear")
            assert result.success
            assert not todo_file.exists()
