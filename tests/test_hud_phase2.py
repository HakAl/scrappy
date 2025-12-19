"""
Tests for HUD Phase 2: Working Set Integration with File Tools.

Tests that ReadFileTool and WriteFileTool properly record file access
in the WorkingSet for HUD display.
"""
import pytest
from pathlib import Path

from scrappy.agent_tools.tools.file_tools import ReadFileTool, WriteFileTool
from scrappy.agent_tools.tools.base import ToolContext, WorkingSet
from scrappy.agent_config import AgentConfig


class TestReadFileToolWorkingSet:
    """Tests for ReadFileTool working set integration."""

    @pytest.mark.unit
    def test_read_records_in_working_set(self, tmp_path):
        """ReadFileTool should record successful reads in working_set."""
        # Setup: Create a file to read
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        # Create context with working set
        ws = WorkingSet()
        ctx = ToolContext(
            project_root=tmp_path,
            config=AgentConfig(),
            working_set=ws,
            turn=3,
        )

        tool = ReadFileTool()
        result = tool.execute(ctx, path="test.py")

        assert result.success
        recent = ws.get_recent()
        assert len(recent) == 1
        assert recent[0].path == "test.py"
        assert recent[0].read_turn == 3
        assert recent[0].write_turn is None

    @pytest.mark.unit
    def test_read_without_working_set_still_works(self, tmp_path):
        """ReadFileTool should work when working_set is None."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        # Context without working set (default)
        ctx = ToolContext(project_root=tmp_path, config=AgentConfig())
        assert ctx.working_set is None

        tool = ReadFileTool()
        result = tool.execute(ctx, path="test.py")

        assert result.success
        assert "print('hello')" in result.output

    @pytest.mark.unit
    def test_read_failure_does_not_record(self, tmp_path):
        """Failed reads should not record in working_set."""
        ws = WorkingSet()
        ctx = ToolContext(
            project_root=tmp_path,
            config=AgentConfig(),
            working_set=ws,
            turn=1,
        )

        tool = ReadFileTool()
        result = tool.execute(ctx, path="nonexistent.py")

        assert not result.success
        assert ws.get_recent() == []

    @pytest.mark.unit
    def test_multiple_reads_tracked_with_turns(self, tmp_path):
        """Multiple file reads should track correct turns."""
        # Create test files
        (tmp_path / "a.py").write_text("a")
        (tmp_path / "b.py").write_text("b")
        (tmp_path / "c.py").write_text("c")

        ws = WorkingSet()
        ctx = ToolContext(
            project_root=tmp_path,
            config=AgentConfig(),
            working_set=ws,
            turn=1,
        )

        tool = ReadFileTool()

        # Read files at different turns
        tool.execute(ctx, path="a.py")
        ctx.turn = 2
        tool.execute(ctx, path="b.py")
        ctx.turn = 3
        tool.execute(ctx, path="c.py")

        recent = ws.get_recent()
        assert len(recent) == 3
        # Most recent first
        assert recent[0].path == "c.py"
        assert recent[0].read_turn == 3
        assert recent[1].path == "b.py"
        assert recent[1].read_turn == 2
        assert recent[2].path == "a.py"
        assert recent[2].read_turn == 1


class TestWriteFileToolWorkingSet:
    """Tests for WriteFileTool working set integration."""

    @pytest.mark.unit
    def test_write_records_in_working_set(self, tmp_path):
        """WriteFileTool should record successful writes in working_set."""
        ws = WorkingSet()
        ctx = ToolContext(
            project_root=tmp_path,
            config=AgentConfig(),
            working_set=ws,
            turn=5,
        )

        tool = WriteFileTool()
        result = tool.execute(ctx, path="new_file.py", content="print('created')")

        assert result.success
        recent = ws.get_recent()
        assert len(recent) == 1
        assert recent[0].path == "new_file.py"
        assert recent[0].write_turn == 5
        assert recent[0].read_turn is None

    @pytest.mark.unit
    def test_write_without_working_set_still_works(self, tmp_path):
        """WriteFileTool should work when working_set is None."""
        ctx = ToolContext(project_root=tmp_path, config=AgentConfig())
        assert ctx.working_set is None

        tool = WriteFileTool()
        result = tool.execute(ctx, path="test.py", content="print('hello')")

        assert result.success
        assert (tmp_path / "test.py").read_text() == "print('hello')"

    @pytest.mark.unit
    def test_write_failure_does_not_record(self, tmp_path):
        """Failed writes should not record in working_set."""
        ws = WorkingSet()
        ctx = ToolContext(
            project_root=tmp_path,
            config=AgentConfig(),
            working_set=ws,
            turn=1,
        )

        tool = WriteFileTool()
        # Empty content causes validation failure
        result = tool.execute(ctx, path="test.py", content="")

        assert not result.success
        assert ws.get_recent() == []

    @pytest.mark.unit
    def test_dry_run_does_not_record(self, tmp_path):
        """Dry run writes should not record in working_set."""
        ws = WorkingSet()
        ctx = ToolContext(
            project_root=tmp_path,
            config=AgentConfig(),
            working_set=ws,
            turn=1,
            dry_run=True,
        )

        tool = WriteFileTool()
        result = tool.execute(ctx, path="test.py", content="print('hello')")

        assert result.success
        assert "DRY RUN" in result.output
        assert ws.get_recent() == []


class TestReadThenWriteWorkingSet:
    """Tests for combined read/write tracking."""

    @pytest.mark.unit
    def test_read_then_write_same_file(self, tmp_path):
        """Reading then writing same file should track both turns."""
        test_file = tmp_path / "file.py"
        test_file.write_text("original")

        ws = WorkingSet()
        ctx = ToolContext(
            project_root=tmp_path,
            config=AgentConfig(),
            working_set=ws,
            turn=1,
        )

        read_tool = ReadFileTool()
        write_tool = WriteFileTool()

        # Read at turn 1
        read_tool.execute(ctx, path="file.py")

        # Write at turn 2
        ctx.turn = 2
        write_tool.execute(ctx, path="file.py", content="modified content here")

        recent = ws.get_recent()
        assert len(recent) == 1  # Same file, not duplicated
        assert recent[0].path == "file.py"
        assert recent[0].read_turn == 1
        assert recent[0].write_turn == 2

    @pytest.mark.unit
    def test_write_then_read_same_file(self, tmp_path):
        """Writing then reading same file should track both turns."""
        ws = WorkingSet()
        ctx = ToolContext(
            project_root=tmp_path,
            config=AgentConfig(),
            working_set=ws,
            turn=1,
        )

        read_tool = ReadFileTool()
        write_tool = WriteFileTool()

        # Write at turn 1
        write_tool.execute(ctx, path="new.py", content="print('new')")

        # Read at turn 2
        ctx.turn = 2
        read_tool.execute(ctx, path="new.py")

        recent = ws.get_recent()
        assert len(recent) == 1
        assert recent[0].path == "new.py"
        assert recent[0].write_turn == 1
        assert recent[0].read_turn == 2

    @pytest.mark.unit
    def test_interleaved_operations_multiple_files(self, tmp_path):
        """Interleaved operations on multiple files should track correctly."""
        (tmp_path / "a.py").write_text("a")
        (tmp_path / "b.py").write_text("b")

        ws = WorkingSet()
        ctx = ToolContext(
            project_root=tmp_path,
            config=AgentConfig(),
            working_set=ws,
            turn=1,
        )

        read_tool = ReadFileTool()
        write_tool = WriteFileTool()

        # Turn 1: read a.py
        read_tool.execute(ctx, path="a.py")

        # Turn 2: read b.py
        ctx.turn = 2
        read_tool.execute(ctx, path="b.py")

        # Turn 3: write a.py (update existing)
        ctx.turn = 3
        write_tool.execute(ctx, path="a.py", content="modified a")

        # Turn 4: write c.py (new file)
        ctx.turn = 4
        write_tool.execute(ctx, path="c.py", content="new c file")

        recent = ws.get_recent()
        assert len(recent) == 3

        # Most recent first (c.py, a.py, b.py)
        paths = [f.path for f in recent]
        assert paths == ["c.py", "a.py", "b.py"]

        # Check a.py has both read and write
        a_file = next(f for f in recent if f.path == "a.py")
        assert a_file.read_turn == 1
        assert a_file.write_turn == 3

        # Check b.py has only read
        b_file = next(f for f in recent if f.path == "b.py")
        assert b_file.read_turn == 2
        assert b_file.write_turn is None

        # Check c.py has only write
        c_file = next(f for f in recent if f.path == "c.py")
        assert c_file.read_turn is None
        assert c_file.write_turn == 4


class TestWorkingSetMaxFilesWithTools:
    """Tests for working set max_files limit with file tools."""

    @pytest.mark.unit
    def test_max_files_enforced_across_reads(self, tmp_path):
        """Working set should respect max_files across multiple reads."""
        # Create many test files
        for i in range(10):
            (tmp_path / f"file{i}.py").write_text(f"content {i}")

        ws = WorkingSet(max_files=3)
        ctx = ToolContext(
            project_root=tmp_path,
            config=AgentConfig(),
            working_set=ws,
            turn=0,
        )

        read_tool = ReadFileTool()

        # Read more files than max
        for i in range(10):
            ctx.turn = i
            read_tool.execute(ctx, path=f"file{i}.py")

        recent = ws.get_recent()
        assert len(recent) == 3

        # Should have most recent files
        paths = [f.path for f in recent]
        assert "file9.py" in paths
        assert "file8.py" in paths
        assert "file7.py" in paths
        assert "file0.py" not in paths  # Dropped as oldest
