"""Tests for SemanticSearchTool."""

import pytest
from unittest.mock import Mock

from scrappy.agent_tools.tools.semantic_search_tool import SemanticSearchTool
from scrappy.agent_tools.tools.base import ToolContext
from scrappy.context.protocols import SearchResult


@pytest.fixture
def mock_context(tmp_path):
    """Create a mock tool context."""
    context = Mock(spec=ToolContext)
    context.project_root = tmp_path
    context.remember_search = Mock()
    context.config = Mock()
    return context


@pytest.fixture
def mock_search_provider():
    """Create a mock semantic search provider."""
    provider = Mock()
    provider.is_indexed.return_value = True
    provider.search.return_value = SearchResult(
        chunks=[
            {
                "path": "src/main.py",
                "lines": (10, 25),
                "content": "def handle_error():\n    pass",
                "score": 0.85
            }
        ],
        tokens_used=150,
        limit_hit=None
    )
    return provider


class TestSemanticSearchToolProperties:
    """Tests for SemanticSearchTool properties."""

    def test_tool_name(self):
        """Should have correct name."""
        tool = SemanticSearchTool()
        assert tool.name == "codebase_search"

    def test_tool_description_mentions_semantic(self):
        """Description should mention semantic search."""
        tool = SemanticSearchTool()
        assert "semantic" in tool.description.lower()

    def test_tool_description_mentions_conceptual(self):
        """Description should mention conceptual queries."""
        tool = SemanticSearchTool()
        assert "conceptual" in tool.description.lower()

    def test_has_query_parameter(self):
        """Should have required query parameter."""
        tool = SemanticSearchTool()
        param_names = [p.name for p in tool.parameters]
        assert "query" in param_names

        query_param = next(p for p in tool.parameters if p.name == "query")
        assert query_param.required is True

    def test_has_max_tokens_parameter(self):
        """Should have optional max_tokens parameter."""
        tool = SemanticSearchTool()
        param_names = [p.name for p in tool.parameters]
        assert "max_tokens" in param_names

        max_tokens_param = next(p for p in tool.parameters if p.name == "max_tokens")
        assert max_tokens_param.required is False
        assert max_tokens_param.default == 4000


class TestSemanticSearchToolUnavailable:
    """Tests for when semantic search is unavailable."""

    def test_returns_success_when_provider_none(self, mock_context):
        """Should return success=True with helpful message when provider is None."""
        tool = SemanticSearchTool(semantic_search=None)
        result = tool.execute(mock_context, query="error handling")

        assert result.success is True
        assert "not available" in result.output.lower()
        assert result.metadata.get("available") is False

    def test_suggests_find_exact_text_when_unavailable(self, mock_context):
        """Should suggest find_exact_text as alternative."""
        tool = SemanticSearchTool(semantic_search=None)
        result = tool.execute(mock_context, query="error handling")

        assert "find_exact_text" in result.output

    def test_mentions_indexing_when_unavailable(self, mock_context):
        """Should mention indexing may be in progress."""
        tool = SemanticSearchTool(semantic_search=None)
        result = tool.execute(mock_context, query="error handling")

        assert "indexing" in result.output.lower()


class TestSemanticSearchToolIndexNotReady:
    """Tests for when index is not ready."""

    def test_returns_success_when_not_indexed(self, mock_context, mock_search_provider):
        """Should return success=True with message when not indexed."""
        mock_search_provider.is_indexed.return_value = False

        tool = SemanticSearchTool(semantic_search=mock_search_provider)
        result = tool.execute(mock_context, query="error handling")

        assert result.success is True
        assert "not ready" in result.output.lower()
        assert result.metadata.get("indexed") is False

    def test_suggests_find_exact_text_when_not_indexed(self, mock_context, mock_search_provider):
        """Should suggest find_exact_text when index not ready."""
        mock_search_provider.is_indexed.return_value = False

        tool = SemanticSearchTool(semantic_search=mock_search_provider)
        result = tool.execute(mock_context, query="error handling")

        assert "find_exact_text" in result.output

    def test_does_not_call_search_when_not_indexed(self, mock_context, mock_search_provider):
        """Should not call search() when index is not ready."""
        mock_search_provider.is_indexed.return_value = False

        tool = SemanticSearchTool(semantic_search=mock_search_provider)
        tool.execute(mock_context, query="error handling")

        mock_search_provider.search.assert_not_called()


class TestSemanticSearchToolSuccess:
    """Tests for successful search operations."""

    def test_returns_success_with_results(self, mock_context, mock_search_provider):
        """Should return success=True with formatted results."""
        tool = SemanticSearchTool(semantic_search=mock_search_provider)
        result = tool.execute(mock_context, query="error handling")

        assert result.success is True
        assert "src/main.py" in result.output
        assert result.metadata["matches"] == 1

    def test_formats_file_path_and_lines(self, mock_context, mock_search_provider):
        """Should format output with file path and line range."""
        tool = SemanticSearchTool(semantic_search=mock_search_provider)
        result = tool.execute(mock_context, query="error handling")

        assert "src/main.py:10-25" in result.output

    def test_includes_score_in_output(self, mock_context, mock_search_provider):
        """Should include relevance score in output."""
        tool = SemanticSearchTool(semantic_search=mock_search_provider)
        result = tool.execute(mock_context, query="error handling")

        assert "0.85" in result.output or "score" in result.output.lower()

    def test_includes_content_with_line_numbers(self, mock_context, mock_search_provider):
        """Should include code content with line numbers."""
        tool = SemanticSearchTool(semantic_search=mock_search_provider)
        result = tool.execute(mock_context, query="error handling")

        assert "def handle_error" in result.output
        # Line numbers should be present
        assert "10" in result.output

    def test_passes_query_to_provider(self, mock_context, mock_search_provider):
        """Should pass query to search provider."""
        tool = SemanticSearchTool(semantic_search=mock_search_provider)
        tool.execute(mock_context, query="authentication flow")

        mock_search_provider.search.assert_called_once()
        call_kwargs = mock_search_provider.search.call_args[1]
        assert call_kwargs["query"] == "authentication flow"

    def test_passes_max_tokens_to_provider(self, mock_context, mock_search_provider):
        """Should pass max_tokens to search provider."""
        tool = SemanticSearchTool(semantic_search=mock_search_provider)
        tool.execute(mock_context, query="error handling", max_tokens=2000)

        call_kwargs = mock_search_provider.search.call_args[1]
        assert call_kwargs["max_tokens"] == 2000

    def test_uses_default_max_tokens(self, mock_context, mock_search_provider):
        """Should use default max_tokens (4000) when not specified."""
        tool = SemanticSearchTool(semantic_search=mock_search_provider)
        tool.execute(mock_context, query="error handling")

        call_kwargs = mock_search_provider.search.call_args[1]
        assert call_kwargs["max_tokens"] == 4000

    def test_remembers_search_in_context(self, mock_context, mock_search_provider):
        """Should remember search results in context."""
        tool = SemanticSearchTool(semantic_search=mock_search_provider)
        tool.execute(mock_context, query="error handling")

        mock_context.remember_search.assert_called_once()
        call_args = mock_context.remember_search.call_args[0]
        assert call_args[0] == "error handling"  # query
        assert "src/main.py" in call_args[1]  # file paths

    def test_metadata_includes_tokens_used(self, mock_context, mock_search_provider):
        """Should include tokens_used in metadata."""
        tool = SemanticSearchTool(semantic_search=mock_search_provider)
        result = tool.execute(mock_context, query="error handling")

        assert result.metadata["tokens_used"] == 150

    def test_metadata_includes_query(self, mock_context, mock_search_provider):
        """Should include original query in metadata."""
        tool = SemanticSearchTool(semantic_search=mock_search_provider)
        result = tool.execute(mock_context, query="error handling")

        assert result.metadata["query"] == "error handling"


class TestSemanticSearchToolEmptyResults:
    """Tests for empty search results."""

    def test_returns_success_with_no_results_message(self, mock_context, mock_search_provider):
        """Should return success=True with message when no results found."""
        mock_search_provider.search.return_value = SearchResult(
            chunks=[],
            tokens_used=0,
            limit_hit=None
        )

        tool = SemanticSearchTool(semantic_search=mock_search_provider)
        result = tool.execute(mock_context, query="nonexistent feature")

        assert result.success is True
        assert "no relevant code found" in result.output.lower()
        assert result.metadata["matches"] == 0

    def test_includes_query_in_no_results_message(self, mock_context, mock_search_provider):
        """Should include the query in the no results message."""
        mock_search_provider.search.return_value = SearchResult(
            chunks=[],
            tokens_used=0,
            limit_hit=None
        )

        tool = SemanticSearchTool(semantic_search=mock_search_provider)
        result = tool.execute(mock_context, query="nonexistent feature")

        assert "nonexistent feature" in result.output


class TestSemanticSearchToolTokenLimit:
    """Tests for token limit handling."""

    def test_shows_truncation_note_when_token_limit_hit(self, mock_context, mock_search_provider):
        """Should show note when results truncated due to token limit."""
        mock_search_provider.search.return_value = SearchResult(
            chunks=[
                {
                    "path": "src/main.py",
                    "lines": (10, 25),
                    "content": "def handle_error():\n    pass",
                    "score": 0.85
                }
            ],
            tokens_used=4000,
            limit_hit="token_limit"
        )

        tool = SemanticSearchTool(semantic_search=mock_search_provider)
        result = tool.execute(mock_context, query="error handling")

        assert result.success is True
        assert "truncated" in result.output.lower() or "token_limit" in result.output.lower()

    def test_metadata_includes_limit_hit(self, mock_context, mock_search_provider):
        """Should include limit_hit in metadata."""
        mock_search_provider.search.return_value = SearchResult(
            chunks=[
                {
                    "path": "src/main.py",
                    "lines": (10, 25),
                    "content": "code",
                    "score": 0.85
                }
            ],
            tokens_used=4000,
            limit_hit="token_limit"
        )

        tool = SemanticSearchTool(semantic_search=mock_search_provider)
        result = tool.execute(mock_context, query="error handling")

        assert result.metadata["limit_hit"] == "token_limit"

    def test_metadata_limit_hit_none_when_not_truncated(self, mock_context, mock_search_provider):
        """Should have limit_hit=None in metadata when not truncated."""
        tool = SemanticSearchTool(semantic_search=mock_search_provider)
        result = tool.execute(mock_context, query="error handling")

        assert result.metadata.get("limit_hit") is None


class TestSemanticSearchToolErrors:
    """Tests for error handling."""

    def test_returns_failure_on_search_exception(self, mock_context, mock_search_provider):
        """Should return failure when search raises exception."""
        mock_search_provider.search.side_effect = Exception("Connection timeout")

        tool = SemanticSearchTool(semantic_search=mock_search_provider)
        result = tool.execute(mock_context, query="error handling")

        assert result.success is False
        assert "error" in result.error.lower()
        assert "Connection timeout" in result.error

    def test_does_not_remember_search_on_error(self, mock_context, mock_search_provider):
        """Should not call remember_search when search fails."""
        mock_search_provider.search.side_effect = Exception("Search failed")

        tool = SemanticSearchTool(semantic_search=mock_search_provider)
        tool.execute(mock_context, query="error handling")

        mock_context.remember_search.assert_not_called()


class TestSemanticSearchToolMultipleResults:
    """Tests for multiple search results."""

    def test_formats_multiple_results(self, mock_context, mock_search_provider):
        """Should format multiple results correctly."""
        mock_search_provider.search.return_value = SearchResult(
            chunks=[
                {
                    "path": "src/auth.py",
                    "lines": (10, 20),
                    "content": "def authenticate():\n    pass",
                    "score": 0.92
                },
                {
                    "path": "src/handlers.py",
                    "lines": (50, 65),
                    "content": "def handle_auth_error():\n    pass",
                    "score": 0.78
                },
                {
                    "path": "tests/test_auth.py",
                    "lines": (5, 15),
                    "content": "def test_auth():\n    pass",
                    "score": 0.65
                }
            ],
            tokens_used=500,
            limit_hit=None
        )

        tool = SemanticSearchTool(semantic_search=mock_search_provider)
        result = tool.execute(mock_context, query="authentication")

        assert result.success is True
        assert "src/auth.py" in result.output
        assert "src/handlers.py" in result.output
        assert "tests/test_auth.py" in result.output
        assert result.metadata["matches"] == 3

    def test_remembers_all_file_paths(self, mock_context, mock_search_provider):
        """Should remember all file paths from results."""
        mock_search_provider.search.return_value = SearchResult(
            chunks=[
                {"path": "src/a.py", "lines": (1, 10), "content": "a", "score": 0.9},
                {"path": "src/b.py", "lines": (1, 10), "content": "b", "score": 0.8},
            ],
            tokens_used=100,
            limit_hit=None
        )

        tool = SemanticSearchTool(semantic_search=mock_search_provider)
        tool.execute(mock_context, query="test")

        call_args = mock_context.remember_search.call_args[0]
        file_paths = call_args[1]
        assert "src/a.py" in file_paths
        assert "src/b.py" in file_paths
