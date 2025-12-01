"""Tests for text search backends."""

import pytest
from pathlib import Path
from unittest.mock import Mock

from scrappy.agent_tools.protocols import ExecutionResult, SearchMetadata
from scrappy.agent_tools.components.text_search import RipgrepSearch, GrepSearch, FindstrSearch


class TestRipgrepSearch:
    """Tests for RipgrepSearch backend."""

    def test_search_returns_matches(self):
        """Should parse ripgrep output and return matches."""
        mock_runner = Mock()
        mock_runner.execute_list.return_value = ExecutionResult(
            stdout="test.py:1:match\ntest.py:5:another",
            stderr="",
            exit_code=0,
            execution_time=0.1
        )
        mock_platform = Mock()
        mock_platform.has_tool.return_value = True
        mock_platform.is_windows.return_value = False
        mock_parser = Mock()
        mock_parser.parse_line.side_effect = [
            ("test.py", 1, "match", True),
            ("test.py", 5, "another", True),
        ]

        search = RipgrepSearch(mock_runner, mock_parser, mock_platform)
        matches, metadata = search.search(pattern="test", path=Path("."))

        assert len(matches) == 2
        assert matches[0].file_path == "test.py"
        assert matches[0].line_number == 1
        assert matches[1].line_number == 5
        assert metadata.error is None

    def test_search_error_populates_metadata(self):
        """Should populate error metadata when ripgrep fails."""
        mock_runner = Mock()
        mock_runner.execute_list.return_value = ExecutionResult(
            stdout="", stderr="error message", exit_code=2, execution_time=0.1
        )
        mock_platform = Mock()
        mock_platform.has_tool.return_value = True
        mock_parser = Mock()

        search = RipgrepSearch(mock_runner, mock_parser, mock_platform)
        matches, metadata = search.search(pattern="test", path=Path("."))

        assert matches == []
        assert metadata.error is not None
        assert "code 2" in metadata.error

    def test_is_available_checks_platform(self):
        """Should check platform for rg tool availability."""
        mock_runner = Mock()
        mock_parser = Mock()
        mock_platform = Mock()
        mock_platform.has_tool.return_value = True

        search = RipgrepSearch(mock_runner, mock_parser, mock_platform)

        assert search.is_available()
        mock_platform.has_tool.assert_called_with("rg")

    def test_name_property(self):
        """Should return backend name."""
        mock_runner = Mock()
        mock_parser = Mock()
        mock_platform = Mock()

        search = RipgrepSearch(mock_runner, mock_parser, mock_platform)

        assert search.name == "ripgrep"

    def test_no_matches_returns_empty_list(self):
        """Should return empty list when no matches found."""
        mock_runner = Mock()
        mock_runner.execute_list.return_value = ExecutionResult(
            stdout="",
            stderr="",
            exit_code=1,  # Exit code 1 = no matches
            execution_time=0.1
        )
        mock_platform = Mock()
        mock_platform.has_tool.return_value = True
        mock_platform.is_windows.return_value = False
        mock_parser = Mock()
        mock_parser.parse_line.return_value = None  # No lines to parse

        search = RipgrepSearch(mock_runner, mock_parser, mock_platform)
        matches, metadata = search.search(pattern="test", path=Path("."))

        assert matches == []
        assert metadata.error is None


class TestGrepSearch:
    """Tests for GrepSearch backend."""

    def test_search_returns_matches(self):
        """Should parse grep output and return matches."""
        mock_runner = Mock()
        mock_runner.execute_list.return_value = ExecutionResult(
            stdout="file.py:10:found\nfile.py:20:another",
            stderr="",
            exit_code=0,
            execution_time=0.1
        )
        mock_platform = Mock()
        mock_platform.has_tool.return_value = True
        mock_platform.is_windows.return_value = False
        mock_parser = Mock()
        mock_parser.parse_line.side_effect = [
            ("file.py", 10, "found", True),
            ("file.py", 20, "another", True),
        ]

        search = GrepSearch(mock_runner, mock_parser, mock_platform)
        matches, metadata = search.search(pattern="test", path=Path("."))

        assert len(matches) == 2
        assert metadata.error is None

    def test_search_error_populates_metadata(self):
        """Should populate error metadata when grep fails."""
        mock_runner = Mock()
        mock_runner.execute_list.return_value = ExecutionResult(
            stdout="", stderr="grep: error", exit_code=2, execution_time=0.1
        )
        mock_platform = Mock()
        mock_platform.has_tool.return_value = True
        mock_parser = Mock()

        search = GrepSearch(mock_runner, mock_parser, mock_platform)
        matches, metadata = search.search(pattern="test", path=Path("."))

        assert matches == []
        assert metadata.error is not None
        assert "code 2" in metadata.error

    def test_name_property(self):
        """Should return backend name."""
        mock_runner = Mock()
        mock_parser = Mock()
        mock_platform = Mock()

        search = GrepSearch(mock_runner, mock_parser, mock_platform)

        assert search.name == "grep"


class TestFindstrSearch:
    """Tests for FindstrSearch backend."""

    def test_search_returns_matches(self):
        """Should parse findstr output and return matches."""
        mock_runner = Mock()
        mock_runner.execute_list.return_value = ExecutionResult(
            stdout="test.py:1:match", stderr="", exit_code=0, execution_time=0.1
        )
        mock_platform = Mock()
        mock_platform.has_tool.return_value = True
        mock_platform.is_windows.return_value = True
        mock_parser = Mock()
        mock_parser.parse_line.return_value = ("test.py", 1, "match", True)

        search = FindstrSearch(mock_runner, mock_parser, mock_platform)
        matches, metadata = search.search(pattern="test", path=Path("."))

        assert len(matches) == 1
        assert matches[0].file_path == "test.py"

    def test_context_lines_warning(self):
        """Should warn when context_lines requested (not supported)."""
        mock_runner = Mock()
        mock_runner.execute_list.return_value = ExecutionResult(
            stdout="test.py:1:match", stderr="", exit_code=0, execution_time=0.1
        )
        mock_platform = Mock()
        mock_platform.has_tool.return_value = True
        mock_platform.is_windows.return_value = True
        mock_parser = Mock()
        mock_parser.parse_line.return_value = ("test.py", 1, "match", True)

        search = FindstrSearch(mock_runner, mock_parser, mock_platform)
        matches, metadata = search.search(pattern="test", path=Path("."), context_lines=2)

        assert metadata.context_lines_supported is False
        assert metadata.warning is not None
        assert "does not support context lines" in metadata.warning

    def test_no_matches_exit_code_1(self):
        """Should handle exit code 1 (no matches) gracefully."""
        mock_runner = Mock()
        mock_runner.execute_list.return_value = ExecutionResult(
            stdout="", stderr="", exit_code=1, execution_time=0.1
        )
        mock_platform = Mock()
        mock_platform.has_tool.return_value = True
        mock_parser = Mock()

        search = FindstrSearch(mock_runner, mock_parser, mock_platform)
        matches, metadata = search.search(pattern="test", path=Path("."))

        assert matches == []
        assert metadata.error is None  # Exit code 1 is not an error

    def test_error_exit_code_2(self):
        """Should populate error metadata for exit code 2."""
        mock_runner = Mock()
        mock_runner.execute_list.return_value = ExecutionResult(
            stdout="", stderr="findstr: error", exit_code=2, execution_time=0.1
        )
        mock_platform = Mock()
        mock_platform.has_tool.return_value = True
        mock_parser = Mock()

        search = FindstrSearch(mock_runner, mock_parser, mock_platform)
        matches, metadata = search.search(pattern="test", path=Path("."))

        assert matches == []
        assert metadata.error is not None

    def test_name_property(self):
        """Should return backend name."""
        mock_runner = Mock()
        mock_parser = Mock()
        mock_platform = Mock()

        search = FindstrSearch(mock_runner, mock_parser, mock_platform)

        assert search.name == "findstr"
