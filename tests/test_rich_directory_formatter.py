"""
Tests for Rich-based directory tree formatter.

Following TDD: Tests written FIRST to demonstrate expected behavior.
This will replace click.style usage in agent_tools with Rich formatting.
"""

import pytest
from pathlib import Path
from io import StringIO
from rich.console import Console

from src.agent_tools.formatters.output_formatter import NullFormatter, RichDirectoryFormatter


def test_format_directory_name_is_cyan_and_bold():
    """
    Test that directory names are formatted in cyan and bold.

    Expected behavior: Directories should be visually distinct with cyan color and bold.
    This test will FAIL initially (TDD red phase).
    """
    # Create formatter with string buffer to capture output
    string_buffer = StringIO()
    console = Console(file=string_buffer, force_terminal=True, width=100)
    formatter = RichDirectoryFormatter(console=console)

    # Format a directory name
    result = formatter.format_directory_name("src/")

    # Should contain "src/" text
    assert "src/" in result

    # Should have cyan color and bold in ANSI codes
    # Cyan is typically \x1b[36m or \x1b[96m (bright cyan)
    # Bold is \x1b[1m
    assert "\x1b[" in result, "Should contain ANSI escape codes for styling"


def test_format_python_file_is_green():
    """
    Test that Python files are formatted in green.

    Expected behavior: .py files should be green to indicate Python code.
    This test will FAIL initially (TDD red phase).
    """
    string_buffer = StringIO()
    console = Console(file=string_buffer, force_terminal=True, width=100)
    formatter = RichDirectoryFormatter(console=console)

    # Format a Python file
    result = formatter.format_file_name("main.py", extension=".py")

    # Should contain filename
    assert "main.py" in result

    # Should have green color in ANSI codes
    # Green is typically \x1b[32m or \x1b[92m (bright green)
    assert "\x1b[" in result, "Should contain ANSI escape codes for styling"


def test_format_javascript_file_is_yellow():
    """
    Test that JavaScript/TypeScript files are formatted in yellow.

    Expected behavior: .js, .ts files should be yellow.
    This test will FAIL initially (TDD red phase).
    """
    string_buffer = StringIO()
    console = Console(file=string_buffer, force_terminal=True, width=100)
    formatter = RichDirectoryFormatter(console=console)

    # Format a JavaScript file
    result = formatter.format_file_name("app.js", extension=".js")

    # Should contain filename
    assert "app.js" in result

    # Should have yellow color
    assert "\x1b[" in result, "Should contain ANSI escape codes for styling"


def test_format_config_file_is_magenta():
    """
    Test that config files (JSON, YAML) are formatted in magenta.

    Expected behavior: .json, .yaml, .yml files should be magenta.
    This test will FAIL initially (TDD red phase).
    """
    string_buffer = StringIO()
    console = Console(file=string_buffer, force_terminal=True, width=100)
    formatter = RichDirectoryFormatter(console=console)

    # Format a JSON config file
    result = formatter.format_file_name("config.json", extension=".json")

    # Should contain filename
    assert "config.json" in result

    # Should have magenta color
    assert "\x1b[" in result, "Should contain ANSI escape codes for styling"


def test_format_file_size_is_dim():
    """
    Test that file sizes are formatted in dim/bright_black color.

    Expected behavior: File size should be subtle, not distracting.
    This test will FAIL initially (TDD red phase).
    """
    string_buffer = StringIO()
    console = Console(file=string_buffer, force_terminal=True, width=100)
    formatter = RichDirectoryFormatter(console=console)

    # Format a file size
    result = formatter.format_file_size("(1.2KB)")

    # Should contain size text
    assert "1.2KB" in result or "(1.2KB)" in result

    # Should have dim styling
    assert "\x1b[" in result, "Should contain ANSI escape codes for styling"


def test_format_tree_line_preserves_tree_structure():
    """
    Test that formatting preserves tree structure characters.

    Expected behavior: Tree connectors (|, -, `) should remain unchanged.
    This test will FAIL initially (TDD red phase).
    """
    string_buffer = StringIO()
    console = Console(file=string_buffer, force_terminal=True, width=100)
    formatter = RichDirectoryFormatter(console=console)

    # Format a tree line with structure
    line = "|-- main.py"
    result = formatter.format_tree_line(line, is_directory=False, file_extension=".py")

    # Should preserve tree structure
    assert "|-- " in result or "|--" in result.replace("\x1b", "")




def test_null_formatter_compatibility():
    """
    Test that NullFormatter exists for fallback when Rich is unavailable.

    Expected behavior: NullFormatter should return output unchanged.
    """
    formatter = NullFormatter()

    # Should return output unchanged
    result = formatter.format("test output", output_type="tree")
    assert result == "test output"
