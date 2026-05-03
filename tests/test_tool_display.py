"""Tests for shared tool display helpers."""

from scrappy.tool_display import (
    extract_file_path,
    extract_tool_key_param,
    format_confirmation_prompt,
)


def test_extract_tool_key_param_summarizes_write_files():
    """Batch writes should summarize the first path and remaining count."""
    result = extract_tool_key_param(
        "write_files",
        {"files": [{"path": "a.py"}, {"path": "b.py"}]},
    )

    assert result == "a.py (+1 more)"


def test_extract_tool_key_param_truncates_long_values():
    """Long display values should be truncated consistently."""
    result = extract_tool_key_param("write_file", {"path": "a" * 60})

    assert len(result) == 50
    assert result.endswith("...")


def test_extract_file_path_checks_common_argument_names():
    """File path extraction should support the common tool argument variants."""
    assert extract_file_path({"path": "a.py"}) == "a.py"
    assert extract_file_path({"file_path": "b.py"}) == "b.py"
    assert extract_file_path({"filepath": "c.py"}) == "c.py"
    assert extract_file_path({"file": "d.py"}) == "d.py"


def test_format_confirmation_prompt_summarizes_batch_writes():
    """Destructive confirmation prompts should describe batch writes clearly."""
    result = format_confirmation_prompt(
        "write_files",
        {"files": [{"path": "a.py"}, {"path": "b.py"}]},
    )

    assert result == "Write 2 files (a.py +1 more)"


def test_format_confirmation_prompt_truncates_long_commands():
    """Long command confirmations should stay readable."""
    result = format_confirmation_prompt("run_command", {"command": "a" * 80})

    assert result.startswith("Run: ")
    assert len(result) == 65
    assert result.endswith("...")
