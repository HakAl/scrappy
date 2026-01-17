"""Tests for ToolConfirmationHandler."""

import pytest
from pathlib import Path
from unittest.mock import Mock

from scrappy.cli.textual.tool_confirmation import ToolConfirmationHandler


class TestToolConfirmationHandlerInit:
    """Tests for handler initialization."""

    def test_creates_with_callbacks(self, tmp_path):
        """Creates handler with output and confirm callbacks."""
        handler = ToolConfirmationHandler(
            output_callback=Mock(),
            confirm_callback=Mock(),
            working_dir=str(tmp_path),
        )
        assert handler is not None

    def test_allow_all_initially_false(self, tmp_path):
        """Allow all is False on init."""
        handler = ToolConfirmationHandler(
            output_callback=Mock(),
            confirm_callback=Mock(),
            working_dir=str(tmp_path),
        )
        assert handler._allow_all is False


class TestConfirmTool:
    """Tests for confirm_tool method."""

    @pytest.fixture
    def handler(self, tmp_path):
        """Create handler with mocked callbacks."""
        output = Mock()
        confirm = Mock(return_value="y")
        return ToolConfirmationHandler(
            output_callback=output,
            confirm_callback=confirm,
            working_dir=str(tmp_path),
        )

    def test_returns_true_when_allow_all(self, handler):
        """Skips prompting when allow_all is set."""
        handler._allow_all = True

        result = handler.confirm_tool("write_file", "Write to test.py", {"path": "test.py"})

        assert result is True
        handler._confirm.assert_not_called()

    def test_returns_true_on_yes(self, handler):
        """Returns True when user responds 'y'."""
        handler._confirm.return_value = "y"

        result = handler.confirm_tool("write_file", "Write to test.py", {"path": "test.py"})

        assert result is True
        assert handler._allow_all is False

    def test_sets_allow_all_on_a(self, handler):
        """Sets allow_all when user responds 'a'."""
        handler._confirm.return_value = "a"

        result = handler.confirm_tool("write_file", "Write to test.py", {"path": "test.py"})

        assert result is True
        assert handler._allow_all is True

    def test_returns_false_on_no(self, handler):
        """Returns False when user responds 'n'."""
        handler._confirm.return_value = "n"

        result = handler.confirm_tool("write_file", "Write to test.py", {"path": "test.py"})

        assert result is False

    def test_outputs_tool_info(self, handler):
        """Outputs tool info before confirming."""
        handler._confirm.return_value = "y"

        handler.confirm_tool("write_file", "Write to test.py", {"path": "test.py"})

        # Should have called output at least once for tool info
        assert handler._output.call_count >= 1


class TestReset:
    """Tests for reset method."""

    def test_resets_allow_all(self, tmp_path):
        """Reset clears allow_all state."""
        handler = ToolConfirmationHandler(
            output_callback=Mock(),
            confirm_callback=Mock(),
            working_dir=str(tmp_path),
        )
        handler._allow_all = True

        handler.reset()

        assert handler._allow_all is False


class TestGenerateDiffPreview:
    """Tests for _generate_diff_preview method."""

    @pytest.fixture
    def handler(self, tmp_path):
        """Create handler with mocked callbacks."""
        return ToolConfirmationHandler(
            output_callback=Mock(),
            confirm_callback=Mock(),
            working_dir=str(tmp_path),
        )

    def test_returns_empty_for_new_file(self, handler, tmp_path):
        """Returns empty list for non-existent files."""
        args = {"path": "new_file.py", "content": "new content"}

        diff_lines = handler._generate_diff_preview(args)

        assert diff_lines == []

    def test_returns_empty_for_no_path(self, handler):
        """Returns empty list when path is missing."""
        args = {"content": "new content"}

        diff_lines = handler._generate_diff_preview(args)

        assert diff_lines == []

    def test_generates_diff_for_existing_file(self, handler, tmp_path):
        """Generates diff for existing files."""
        # Create existing file
        existing = tmp_path / "existing.py"
        existing.write_text("old content\n")

        args = {"path": "existing.py", "content": "new content\n"}

        diff_lines = handler._generate_diff_preview(args)

        assert len(diff_lines) > 0
        # Should contain diff markers
        diff_text = "\n".join(diff_lines)
        assert "-old content" in diff_text or "old content" in diff_text
        assert "+new content" in diff_text or "new content" in diff_text


class TestShowDiffPreview:
    """Tests for _show_diff_preview method."""

    @pytest.fixture
    def handler(self, tmp_path):
        """Create handler with mocked callbacks."""
        return ToolConfirmationHandler(
            output_callback=Mock(),
            confirm_callback=Mock(),
            working_dir=str(tmp_path),
        )

    def test_shows_new_file_indicator_for_empty_diff(self, handler):
        """Shows '(new file)' for empty diff lines."""
        handler._show_diff_preview("test.py", [])

        handler._output.assert_called()
        call_args = handler._output.call_args[0][0]
        assert "(new file)" in call_args

    def test_shows_colored_additions(self, handler):
        """Shows additions in green."""
        diff_lines = ["@@ -1 +1 @@", "+new line"]

        handler._show_diff_preview("test.py", diff_lines)

        # Check that green markup is used for additions
        calls = [call[0][0] for call in handler._output.call_args_list]
        addition_calls = [c for c in calls if "+new line" in c]
        assert len(addition_calls) > 0
        assert "[green]" in addition_calls[0]

    def test_shows_colored_deletions(self, handler):
        """Shows deletions in red."""
        diff_lines = ["@@ -1 +1 @@", "-old line"]

        handler._show_diff_preview("test.py", diff_lines)

        calls = [call[0][0] for call in handler._output.call_args_list]
        deletion_calls = [c for c in calls if "-old line" in c]
        assert len(deletion_calls) > 0
        assert "[red]" in deletion_calls[0]

    def test_truncates_long_diffs(self, handler):
        """Truncates diffs exceeding max_lines."""
        diff_lines = ["@@ -1 +1 @@"] + [f"+line {i}" for i in range(50)]

        handler._show_diff_preview("test.py", diff_lines, max_lines=10)

        calls = [call[0][0] for call in handler._output.call_args_list]
        truncation_calls = [c for c in calls if "more lines" in c]
        assert len(truncation_calls) > 0


class TestExtractKeyParam:
    """Tests for _extract_key_param method."""

    @pytest.fixture
    def handler(self, tmp_path):
        """Create handler."""
        return ToolConfirmationHandler(
            output_callback=Mock(),
            confirm_callback=Mock(),
            working_dir=str(tmp_path),
        )

    def test_extracts_path_for_write_file(self, handler):
        """Extracts path for write_file tool."""
        result = handler._extract_key_param("write_file", {"path": "test.py"})
        assert result == "test.py"

    def test_extracts_command_for_run_command(self, handler):
        """Extracts command for run_command tool."""
        result = handler._extract_key_param("run_command", {"command": "ls -la"})
        assert result == "ls -la"

    def test_truncates_long_values(self, handler):
        """Truncates values longer than 50 chars."""
        long_path = "a" * 60
        result = handler._extract_key_param("write_file", {"path": long_path})
        assert len(result) == 50
        assert result.endswith("...")

    def test_returns_empty_for_unknown_tool(self, handler):
        """Returns empty string for unknown tools."""
        result = handler._extract_key_param("unknown_tool", {"foo": "bar"})
        assert result == ""
