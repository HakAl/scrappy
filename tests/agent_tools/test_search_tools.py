"""Tests for FindExactTextTool."""

import pytest
from unittest.mock import Mock

from scrappy.agent_tools.tools.search_tools import FindExactTextTool
from scrappy.agent_tools.tools.base import ToolContext
from scrappy.agent_tools.protocols import SearchMatch, SearchMetadata, NoSearchToolError


@pytest.fixture
def mock_context(tmp_path):
    """Create a mock tool context."""
    context = Mock(spec=ToolContext)
    context.project_root = tmp_path
    context.remember_search = Mock()
    context.config = Mock()
    context.config.max_search_results = 100
    return context


class TestFindExactTextTool:
    """Tests for FindExactTextTool."""

    def test_tool_properties(self):
        """Should have correct name and description."""
        tool = FindExactTextTool()

        assert tool.name == "find_exact_text"
        assert "exact" in tool.description.lower()
        assert any(p.name == "pattern" for p in tool.parameters)

    def test_uses_injected_backend(self, mock_context):
        """Should use pre-configured search backend."""
        mock_search = Mock()
        mock_search.search.return_value = (
            [SearchMatch("test.py", 10, "hello", True)],
            SearchMetadata()
        )
        mock_search.name = "mock"

        tool = FindExactTextTool(text_search=mock_search)
        result = tool.execute(mock_context, pattern="hello")

        assert result.success
        assert "test.py:10" in result.output
        mock_search.search.assert_called_once()

    def test_no_tool_returns_error(self, mock_context):
        """Should return error when no search tool available."""
        mock_factory = Mock()
        mock_factory.create_backend.side_effect = NoSearchToolError("No tool")

        tool = FindExactTextTool(backend_factory=mock_factory)
        result = tool.execute(mock_context, pattern="hello")

        assert not result.success
        assert "No tool" in result.error

    def test_search_error_returns_failure(self, mock_context):
        """Should return failure when search encounters error."""
        mock_search = Mock()
        mock_search.search.return_value = (
            [],
            SearchMetadata(error="grep failed", stderr="permission denied")
        )
        mock_search.name = "grep"

        tool = FindExactTextTool(text_search=mock_search)
        result = tool.execute(mock_context, pattern="hello")

        assert not result.success
        assert "grep failed" in result.error
        assert result.metadata["stderr"] == "permission denied"

    def test_no_matches_returns_success(self, mock_context):
        """Should return success with message when no matches found."""
        mock_search = Mock()
        mock_search.search.return_value = ([], SearchMetadata())
        mock_search.name = "rg"

        tool = FindExactTextTool(text_search=mock_search)
        result = tool.execute(mock_context, pattern="nomatch")

        assert result.success
        assert "No matches found" in result.output
        assert result.metadata["matches"] == 0

    def test_formats_matches_correctly(self, mock_context):
        """Should format matches with file:line:content."""
        mock_search = Mock()
        mock_search.search.return_value = (
            [
                SearchMatch("src/main.py", 42, "def hello():", True),
                SearchMatch("src/test.py", 10, "import hello", True),
            ],
            SearchMetadata()
        )
        mock_search.name = "rg"

        tool = FindExactTextTool(text_search=mock_search)
        result = tool.execute(mock_context, pattern="hello")

        assert result.success
        assert "src/main.py:42:> def hello():" in result.output
        assert "src/test.py:10:> import hello" in result.output

    def test_context_lines_formatting(self, mock_context):
        """Should format context lines with proper markers."""
        mock_search = Mock()
        mock_search.search.return_value = (
            [
                SearchMatch("test.py", 1, "before", False),  # Context
                SearchMatch("test.py", 2, "match", True),    # Match
                SearchMatch("test.py", 3, "after", False),   # Context
            ],
            SearchMetadata()
        )
        mock_search.name = "rg"

        tool = FindExactTextTool(text_search=mock_search)
        result = tool.execute(mock_context, pattern="match", context_lines=1)

        assert result.success
        assert "test.py:1:  before" in result.output  # Space marker for context
        assert "test.py:2:> match" in result.output   # > marker for match
        assert "test.py:3:  after" in result.output   # Space marker for context

    def test_adds_separator_between_files(self, mock_context):
        """Should add separator between different files when using context."""
        mock_search = Mock()
        mock_search.search.return_value = (
            [
                SearchMatch("file1.py", 10, "match1", True),
                SearchMatch("file2.py", 20, "match2", True),
            ],
            SearchMetadata()
        )
        mock_search.name = "rg"

        tool = FindExactTextTool(text_search=mock_search)
        result = tool.execute(mock_context, pattern="match", context_lines=1)

        assert result.success
        assert "---" in result.output

    def test_truncation_message(self, mock_context):
        """Should show truncation message when max results reached."""
        mock_context.config.max_search_results = 5

        mock_search = Mock()
        # Return exactly max_results matches
        mock_search.search.return_value = (
            [SearchMatch(f"file{i}.py", i, f"match{i}", True) for i in range(5)],
            SearchMetadata()
        )
        mock_search.name = "rg"

        tool = FindExactTextTool(text_search=mock_search)
        result = tool.execute(mock_context, pattern="match")

        assert result.success
        assert "truncated to 5 matches" in result.output
        assert result.metadata["truncated"] is True

    def test_findstr_warning_shown(self, mock_context):
        """Should display warning when backend has limitations."""
        mock_search = Mock()
        mock_search.search.return_value = (
            [SearchMatch("test.py", 10, "hello", True)],
            SearchMetadata(
                warning="findstr does not support context lines",
                context_lines_supported=False
            )
        )
        mock_search.name = "findstr"

        tool = FindExactTextTool(text_search=mock_search)
        result = tool.execute(mock_context, pattern="hello", context_lines=2)

        assert result.success
        assert "[Warning:" in result.output
        assert "findstr does not support context lines" in result.output

    def test_remembers_search_in_context(self, mock_context):
        """Should remember search in context."""
        mock_search = Mock()
        mock_search.search.return_value = (
            [SearchMatch("test.py", 10, "hello", True)],
            SearchMetadata()
        )
        mock_search.name = "rg"

        tool = FindExactTextTool(text_search=mock_search)
        tool.execute(mock_context, pattern="hello", file_pattern="*.py")

        mock_context.remember_search.assert_called_once()
        call_args = mock_context.remember_search.call_args[0]
        assert "hello" in call_args[0]
        assert "*.py" in call_args[0]
        assert "test.py" in call_args[1]

    def test_passes_all_parameters_to_backend(self, mock_context):
        """Should pass all parameters to search backend."""
        mock_search = Mock()
        mock_search.search.return_value = ([], SearchMetadata())
        mock_search.name = "rg"

        tool = FindExactTextTool(text_search=mock_search)
        tool.execute(
            mock_context,
            pattern="test",
            file_pattern="*.js",
            use_regex=True,
            case_sensitive=True,
            context_lines=3
        )

        call_kwargs = mock_search.search.call_args[1]
        assert call_kwargs["pattern"] == "test"
        assert call_kwargs["file_glob"] == "*.js"
        assert call_kwargs["use_regex"] is True
        assert call_kwargs["case_sensitive"] is True
        assert call_kwargs["context_lines"] == 3

    def test_backend_name_in_metadata(self, mock_context):
        """Should include backend name in result metadata."""
        mock_search = Mock()
        mock_search.search.return_value = (
            [SearchMatch("test.py", 10, "hello", True)],
            SearchMetadata()
        )
        mock_search.name = "ripgrep"

        tool = FindExactTextTool(text_search=mock_search)
        result = tool.execute(mock_context, pattern="hello")

        assert result.metadata["backend"] == "ripgrep"

    def test_exception_handling(self, mock_context):
        """Should handle unexpected exceptions gracefully."""
        mock_search = Mock()
        mock_search.search.side_effect = Exception("Unexpected error")
        mock_search.name = "rg"

        tool = FindExactTextTool(text_search=mock_search)
        result = tool.execute(mock_context, pattern="hello")

        assert not result.success
        assert "Search error" in result.error
