"""Tests for search output parser."""

import pytest
from unittest.mock import Mock

from scrappy.agent_tools.components.search_output_parser import SearchOutputParser


class TestSearchOutputParser:
    """Tests for SearchOutputParser."""

    def test_parse_unix_path(self):
        """Should parse Unix-style paths correctly."""
        mock_platform = Mock()
        mock_platform.is_windows.return_value = False

        parser = SearchOutputParser(mock_platform)
        result = parser.parse_line("src/main.py:42:def hello():")

        assert result == ("src/main.py", 42, "def hello():", True)

    def test_parse_windows_path(self):
        """Should parse Windows-style paths with drive letters."""
        mock_platform = Mock()
        mock_platform.is_windows.return_value = True

        parser = SearchOutputParser(mock_platform)
        result = parser.parse_line("C:\\src\\main.py:42:def hello():")

        assert result == ("C:/src/main.py", 42, "def hello():", True)

    def test_parse_context_line(self):
        """Should identify context lines (marked with -)."""
        mock_platform = Mock()
        mock_platform.is_windows.return_value = False

        parser = SearchOutputParser(mock_platform)
        result = parser.parse_line("src/main.py-43-    pass")

        assert result == ("src/main.py", 43, "    pass", False)

    def test_parse_separator_returns_none(self):
        """Should return None for separator lines."""
        mock_platform = Mock()
        mock_platform.is_windows.return_value = False

        parser = SearchOutputParser(mock_platform)
        result = parser.parse_line("--")

        assert result is None

    def test_parse_empty_line_returns_none(self):
        """Should return None for empty lines."""
        mock_platform = Mock()
        mock_platform.is_windows.return_value = False

        parser = SearchOutputParser(mock_platform)
        result = parser.parse_line("")

        assert result is None

    def test_normalize_path_converts_backslashes(self):
        """Should normalize Windows backslashes to forward slashes."""
        mock_platform = Mock()

        parser = SearchOutputParser(mock_platform)
        result = parser.normalize_path("C:\\Users\\test\\file.py")

        assert result == "C:/Users/test/file.py"

    def test_parse_windows_path_with_multiple_colons(self):
        """Should handle Windows paths with colons in content."""
        mock_platform = Mock()
        mock_platform.is_windows.return_value = True

        parser = SearchOutputParser(mock_platform)
        result = parser.parse_line("D:\\code\\test.py:10:time: 12:30:45")

        assert result == ("D:/code/test.py", 10, "time: 12:30:45", True)

    def test_parse_unix_path_with_colons_in_content(self):
        """Should handle Unix paths with colons in content."""
        mock_platform = Mock()
        mock_platform.is_windows.return_value = False

        parser = SearchOutputParser(mock_platform)
        result = parser.parse_line("/home/user/test.py:10:time: 12:30:45")

        assert result == ("/home/user/test.py", 10, "time: 12:30:45", True)

    def test_parse_invalid_format_returns_none(self):
        """Should return None for lines that don't match expected format."""
        mock_platform = Mock()
        mock_platform.is_windows.return_value = False

        parser = SearchOutputParser(mock_platform)
        result = parser.parse_line("just some random text")

        assert result is None
