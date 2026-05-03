"""Pilot test to verify confirmation UX shows tool info and diff before Y/N/A prompt.

Tests that when a destructive tool is about to execute:
1. Tool info is displayed (e.g., "> write_file: path/to/file.py")
2. Diff preview is shown for file modifications
3. Y/N/A prompt appears AFTER the above
"""

import pytest

from scrappy.cli.textual.tool_confirmation import ToolConfirmationHandler


class TestConfirmationUXFlow:
    """Test the confirmation UX flow shows info before prompt."""

    @pytest.fixture
    def tmp_file(self, tmp_path):
        """Create a temporary file with content."""
        f = tmp_path / "existing.py"
        f.write_text("old content\nline 2\n")
        return f

    def test_shows_tool_info_before_confirm(self, tmp_path):
        """Tool info is output before confirmation prompt."""
        outputs = []
        confirm_called = []

        def capture_output(content):
            outputs.append(content)

        def capture_confirm(question):
            confirm_called.append(question)
            # Record what was output BEFORE confirm was called
            confirm_called.append(f"outputs_before_confirm: {len(outputs)}")
            return "y"

        handler = ToolConfirmationHandler(
            output_callback=capture_output,
            confirm_callback=capture_confirm,
            working_dir=str(tmp_path),
        )

        handler.confirm_tool(
            "write_file",
            "Write to test.py",
            {"path": "test.py", "content": "new content"},
        )

        # Verify tool info was output
        assert len(outputs) > 0, "No output was generated"
        assert any("write_file" in o for o in outputs), "Tool name not in output"

        # Verify confirm was called AFTER outputs
        assert "outputs_before_confirm: " in confirm_called[1]
        output_count = int(confirm_called[1].split(": ")[1])
        assert output_count > 0, "Confirm was called before any output"

    def test_shows_diff_preview_for_existing_file(self, tmp_path, tmp_file):
        """Diff preview is shown when modifying existing file."""
        outputs = []

        def capture_output(content):
            outputs.append(content)

        handler = ToolConfirmationHandler(
            output_callback=capture_output,
            confirm_callback=lambda q: "y",
            working_dir=str(tmp_path),
        )

        handler.confirm_tool(
            "write_file",
            "Write to existing.py",
            {"path": "existing.py", "content": "new content\nline 2\n"},
        )

        # Check for diff markers in output
        all_output = "".join(outputs)
        assert "-old content" in all_output or "[red]" in all_output, \
            f"Deletion not shown in diff. Output: {all_output}"
        assert "+new content" in all_output or "[green]" in all_output, \
            f"Addition not shown in diff. Output: {all_output}"

    def test_shows_new_file_indicator(self, tmp_path):
        """Shows '(new file)' for files that don't exist."""
        outputs = []

        def capture_output(content):
            outputs.append(content)

        handler = ToolConfirmationHandler(
            output_callback=capture_output,
            confirm_callback=lambda q: "y",
            working_dir=str(tmp_path),
        )

        handler.confirm_tool(
            "write_file",
            "Write to new_file.py",
            {"path": "new_file.py", "content": "brand new content"},
        )

        all_output = "".join(outputs)
        assert "(new file)" in all_output, \
            f"New file indicator not shown. Output: {all_output}"

    def test_shows_command_for_run_command(self, tmp_path):
        """Shows command text for run_command tool."""
        outputs = []

        def capture_output(content):
            outputs.append(content)

        handler = ToolConfirmationHandler(
            output_callback=capture_output,
            confirm_callback=lambda q: "y",
            working_dir=str(tmp_path),
        )

        handler.confirm_tool(
            "run_command",
            "Run: npm install",
            {"command": "npm install"},
        )

        all_output = "".join(outputs)
        assert "npm install" in all_output, \
            f"Command not shown. Output: {all_output}"

    def test_write_files_shows_multiple_file_previews(self, tmp_path):
        """Batch writes should show per-file previews before confirmation."""
        outputs = []
        existing = tmp_path / "existing.py"
        existing.write_text("old content\n")

        def capture_output(content):
            outputs.append(content)

        handler = ToolConfirmationHandler(
            output_callback=capture_output,
            confirm_callback=lambda q: "y",
            working_dir=str(tmp_path),
        )

        handler.confirm_tool(
            "write_files",
            "Write multiple files",
            {
                "files": [
                    {"path": "existing.py", "content": "new content\n"},
                    {"path": "new.py", "content": "brand new\n"},
                ]
            },
        )

        all_output = "".join(outputs)
        assert "existing.py" in all_output, f"Existing file path not shown. Output: {all_output}"
        assert "new.py" in all_output, f"New file path not shown. Output: {all_output}"
        assert "(new file)" in all_output, f"New file indicator not shown. Output: {all_output}"
        assert "[green]" in all_output or "[red]" in all_output, f"Diff preview not shown. Output: {all_output}"

    def test_allow_all_skips_subsequent_prompts(self, tmp_path):
        """Pressing 'a' skips prompts for subsequent tools."""
        confirm_count = [0]

        def counting_confirm(question):
            confirm_count[0] += 1
            return "a"  # Allow all

        handler = ToolConfirmationHandler(
            output_callback=lambda c: None,
            confirm_callback=counting_confirm,
            working_dir=str(tmp_path),
        )

        # First call should prompt
        handler.confirm_tool("write_file", "Write 1", {"path": "a.py", "content": "a"})
        assert confirm_count[0] == 1

        # Second call should skip (allow_all)
        handler.confirm_tool("write_file", "Write 2", {"path": "b.py", "content": "b"})
        assert confirm_count[0] == 1, "Second call should not prompt"

        # Third call should also skip
        handler.confirm_tool("run_command", "Run cmd", {"command": "ls"})
        assert confirm_count[0] == 1, "Third call should not prompt"

    def test_denial_returns_false(self, tmp_path):
        """Pressing 'n' returns False and doesn't set allow_all."""
        handler = ToolConfirmationHandler(
            output_callback=lambda c: None,
            confirm_callback=lambda q: "n",
            working_dir=str(tmp_path),
        )

        result = handler.confirm_tool(
            "write_file", "Write test", {"path": "test.py", "content": "x"}
        )

        assert result is False
        assert handler._allow_all is False


class TestConfirmationUXOrder:
    """Verify the exact order of UX elements."""

    def test_order_tool_info_then_diff_then_prompt(self, tmp_path):
        """Verifies: tool info -> diff -> prompt (in that order)."""
        events = []

        def track_output(content):
            if "write_file" in content:
                events.append("tool_info")
            elif "[green]" in content or "[red]" in content or "(new file)" in content:
                events.append("diff")

        def track_confirm(question):
            events.append("prompt")
            return "y"

        # Create existing file for diff
        existing = tmp_path / "file.py"
        existing.write_text("old\n")

        handler = ToolConfirmationHandler(
            output_callback=track_output,
            confirm_callback=track_confirm,
            working_dir=str(tmp_path),
        )

        handler.confirm_tool(
            "write_file",
            "Write to file.py",
            {"path": "file.py", "content": "new\n"},
        )

        # Verify order
        assert events[0] == "tool_info", f"First should be tool_info, got {events}"
        assert "diff" in events, f"Diff should appear, got {events}"
        assert events[-1] == "prompt", f"Last should be prompt, got {events}"

        # Diff should come before prompt
        diff_idx = events.index("diff")
        prompt_idx = events.index("prompt")
        assert diff_idx < prompt_idx, "Diff should appear before prompt"
