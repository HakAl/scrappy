"""
Unit tests for GraphContextFactory.

Tests:
- RAG context generation with semantic search
- Budget heuristics for adaptive token allocation
- Elbow filtering for quality results
- Search strategy section building
- NullContextFactory no-op behavior
"""

from dataclasses import dataclass
from typing import Any, Optional
from unittest.mock import Mock

from scrappy.graph.context_factory import (
    EXTENSION_LANGUAGE_MAP,
    GraphContextFactory,
    NullContextFactory,
    RAGConfig,
    _get_language_from_path,
)
from scrappy.graph.protocols import ContextFactoryProtocol


@dataclass
class SearchResult:
    """Mock SearchResult dataclass matching context.protocols.SearchResult."""
    chunks: list[dict[str, Any]]
    tokens_used: int
    limit_hit: Optional[str] = None


class MockSemanticManager:
    """
    Test double for SemanticSearchManagerProtocol.

    Provides controlled behavior for testing context factory without
    loading real FastEmbed models or LanceDB.
    """

    def __init__(self, is_ready: bool = True, search_results: list = None):
        """
        Initialize mock semantic manager.

        Args:
            is_ready: Whether semantic search reports as ready
            search_results: List of chunk dicts to return from search
        """
        self._is_ready = is_ready
        self._search_results = search_results or []
        self._search_calls: list[dict] = []

    def is_ready(self) -> bool:
        """Check if mock is ready."""
        return self._is_ready

    def search(self, query: str, max_tokens: int = 2000) -> SearchResult:
        """
        Mock search that returns preset results.

        Args:
            query: Search query
            max_tokens: Token budget

        Returns:
            SearchResult dataclass with chunks and metadata
        """
        self._search_calls.append({'query': query, 'max_tokens': max_tokens})
        chunks = self._search_results[:10]  # Simulate result limit
        return SearchResult(
            chunks=chunks,
            tokens_used=sum(len(r.get('content', '')) // 4 for r in chunks),
            limit_hit=None
        )

    def get_search_calls(self) -> list:
        """Get all search() calls for verification."""
        return self._search_calls


# =============================================================================
# Protocol Compliance Tests
# =============================================================================

class TestProtocolCompliance:
    """Test that implementations satisfy ContextFactoryProtocol."""

    def test_graph_context_factory_satisfies_protocol(self):
        """GraphContextFactory should implement ContextFactoryProtocol."""
        factory = GraphContextFactory(None)
        assert isinstance(factory, ContextFactoryProtocol)

    def test_null_context_factory_satisfies_protocol(self):
        """NullContextFactory should implement ContextFactoryProtocol."""
        factory = NullContextFactory()
        assert isinstance(factory, ContextFactoryProtocol)


# =============================================================================
# RAG Context Tests
# =============================================================================

class TestRAGContext:
    """Test RAG context generation."""

    def test_generates_rag_context_when_ready(self):
        """Should generate RAG context when semantic search is ready."""
        # Arrange
        search_results = [
            {
                'path': 'src/main.py',
                'lines': (10, 20),
                'content': 'def foo():\n    return 42',
                'score': 0.9
            },
            {
                'path': 'src/helper.py',
                'lines': (5, 15),
                'content': 'class Helper:\n    pass',
                'score': 0.85
            }
        ]
        semantic_manager = MockSemanticManager(is_ready=True, search_results=search_results)
        factory = GraphContextFactory(semantic_manager)

        # Act
        rag_context = factory.build_rag_context("How does foo work?")

        # Assert - new format with improved headers and patterns note
        assert rag_context is not None
        assert "Relevant Code from Your Project" in rag_context
        assert "### src/main.py" in rag_context
        assert "Lines 10-20:" in rag_context
        assert "```python" in rag_context  # Language detection
        assert "def foo()" in rag_context
        assert "### src/helper.py" in rag_context
        assert "existing patterns in your codebase" in rag_context  # Patterns note

    def test_no_rag_context_when_not_ready(self):
        """Should return None when semantic search not ready."""
        # Arrange
        semantic_manager = MockSemanticManager(is_ready=False)
        factory = GraphContextFactory(semantic_manager)

        # Act
        rag_context = factory.build_rag_context("Test task")

        # Assert
        assert rag_context is None

    def test_no_rag_context_when_no_semantic_manager(self):
        """Should return None when semantic_manager is None."""
        # Arrange
        factory = GraphContextFactory(None)

        # Act
        rag_context = factory.build_rag_context("Test task")

        # Assert
        assert rag_context is None

    def test_handles_empty_search_results(self):
        """Should return None when search returns no results."""
        # Arrange
        semantic_manager = MockSemanticManager(is_ready=True, search_results=[])
        factory = GraphContextFactory(semantic_manager)

        # Act
        rag_context = factory.build_rag_context("Test task")

        # Assert
        assert rag_context is None

    def test_handles_search_exception(self):
        """Should return None when search raises exception."""
        # Arrange
        semantic_manager = Mock()
        semantic_manager.is_ready.return_value = True
        semantic_manager.search.side_effect = Exception("Search failed")
        factory = GraphContextFactory(semantic_manager)

        # Act
        rag_context = factory.build_rag_context("Test task")

        # Assert - should not crash, should return None
        assert rag_context is None


# =============================================================================
# Elbow Filtering Tests
# =============================================================================

class TestElbowFiltering:
    """Test elbow-based quality filtering of RAG results."""

    def test_filters_out_low_score_results(self):
        """Should filter results below min_score floor."""
        # Arrange
        search_results = [
            {'path': 'good.py', 'lines': (1, 10), 'content': 'good', 'score': 0.5},
            {'path': 'bad.py', 'lines': (1, 10), 'content': 'bad', 'score': 0.2},  # Below floor
        ]
        config = RAGConfig(min_score=0.3)
        semantic_manager = MockSemanticManager(is_ready=True, search_results=search_results)
        factory = GraphContextFactory(semantic_manager, config)

        # Act
        rag_context = factory.build_rag_context("Test task")

        # Assert
        assert rag_context is not None
        assert "good.py" in rag_context
        assert "bad.py" not in rag_context

    def test_filters_at_large_score_gap(self):
        """Should stop at large score gap (elbow detection)."""
        # Arrange
        search_results = [
            {'path': 'best.py', 'lines': (1, 10), 'content': 'best', 'score': 0.9},
            {'path': 'good.py', 'lines': (1, 10), 'content': 'good', 'score': 0.85},
            {'path': 'far.py', 'lines': (1, 10), 'content': 'far', 'score': 0.5},  # Big gap from 0.85
        ]
        config = RAGConfig(min_score=0.3, max_gap=0.15)
        semantic_manager = MockSemanticManager(is_ready=True, search_results=search_results)
        factory = GraphContextFactory(semantic_manager, config)

        # Act
        rag_context = factory.build_rag_context("Test task")

        # Assert
        assert rag_context is not None
        assert "best.py" in rag_context
        assert "good.py" in rag_context
        assert "far.py" not in rag_context  # Filtered by elbow

    def test_returns_none_when_top_result_below_floor(self):
        """Should return None when even top result is below min_score."""
        # Arrange
        search_results = [
            {'path': 'weak.py', 'lines': (1, 10), 'content': 'weak', 'score': 0.2},
        ]
        config = RAGConfig(min_score=0.3)
        semantic_manager = MockSemanticManager(is_ready=True, search_results=search_results)
        factory = GraphContextFactory(semantic_manager, config)

        # Act
        rag_context = factory.build_rag_context("Test task")

        # Assert
        assert rag_context is None


# =============================================================================
# Budget Heuristics Tests
# =============================================================================

class TestBudgetHeuristics:
    """Test adaptive token budget computation."""

    def test_base_budget_without_heuristics(self):
        """Should use base budget when no heuristics triggered."""
        # Arrange
        semantic_manager = MockSemanticManager(is_ready=True, search_results=[
            {'path': 'test.py', 'lines': (1, 10), 'content': 'x' * 100, 'score': 0.9}
        ])
        config = RAGConfig(max_tokens=2000)
        factory = GraphContextFactory(semantic_manager, config)

        # Act
        factory.build_rag_context("simple query")

        # Assert - should call search with base budget
        search_calls = semantic_manager.get_search_calls()
        assert len(search_calls) == 1
        assert search_calls[0]['max_tokens'] == 2000  # Base budget, no boost

    def test_boosts_budget_for_file_references(self):
        """Should boost budget when task mentions file paths."""
        # Arrange
        semantic_manager = MockSemanticManager(is_ready=True, search_results=[
            {'path': 'test.py', 'lines': (1, 10), 'content': 'x' * 100, 'score': 0.9}
        ])
        config = RAGConfig(max_tokens=2000)
        factory = GraphContextFactory(semantic_manager, config)

        # Act
        factory.build_rag_context("Check src/main.py for errors")

        # Assert - should boost for file reference
        search_calls = semantic_manager.get_search_calls()
        assert len(search_calls) == 1
        assert search_calls[0]['max_tokens'] > 2000  # Boosted budget

    def test_boosts_budget_for_multiple_identifiers(self):
        """Should boost budget when task has many identifiers."""
        # Arrange
        semantic_manager = MockSemanticManager(is_ready=True, search_results=[
            {'path': 'test.py', 'lines': (1, 10), 'content': 'x' * 100, 'score': 0.9}
        ])
        config = RAGConfig(max_tokens=2000)
        factory = GraphContextFactory(semantic_manager, config)

        # Act - task with 4+ identifiers
        factory.build_rag_context("Update UserModel, ProductModel, OrderModel, and CartModel classes")

        # Assert - should boost for multiple identifiers
        search_calls = semantic_manager.get_search_calls()
        assert len(search_calls) == 1
        assert search_calls[0]['max_tokens'] > 2000  # Boosted budget

    def test_boosts_budget_for_exploration_queries(self):
        """Should boost budget for exploratory questions."""
        # Arrange
        semantic_manager = MockSemanticManager(is_ready=True, search_results=[
            {'path': 'test.py', 'lines': (1, 10), 'content': 'x' * 100, 'score': 0.9}
        ])
        config = RAGConfig(max_tokens=2000)
        factory = GraphContextFactory(semantic_manager, config)

        # Act
        factory.build_rag_context("How does the authentication system work?")

        # Assert - should boost for exploration words
        search_calls = semantic_manager.get_search_calls()
        assert len(search_calls) == 1
        assert search_calls[0]['max_tokens'] > 2000  # Boosted budget

    def test_caps_boost_at_2x_base_budget(self):
        """Should cap total boost at 2x base budget."""
        # Arrange
        semantic_manager = MockSemanticManager(is_ready=True, search_results=[
            {'path': 'test.py', 'lines': (1, 10), 'content': 'x' * 100, 'score': 0.9}
        ])
        config = RAGConfig(max_tokens=1000)
        factory = GraphContextFactory(semantic_manager, config)

        # Act - extreme case with all heuristics
        factory.build_rag_context(
            "Where are UserModel, ProductModel, OrderModel, CartModel, PaymentModel "
            "in src/models.py and how do they work?"
        )

        # Assert - should cap at 2x
        search_calls = semantic_manager.get_search_calls()
        assert len(search_calls) == 1
        assert search_calls[0]['max_tokens'] <= 2000  # 2x cap


# =============================================================================
# Search Strategy Section Tests
# =============================================================================

class TestSearchStrategySection:
    """Test search strategy guidance building."""

    def test_includes_semantic_search_guidance(self):
        """Should include semantic search guidance when available."""
        # Arrange
        factory = GraphContextFactory(None)

        # Act
        section = factory.build_search_strategy_section(["codebase_search", "read_file"])

        # Assert
        assert "Code Search Strategy" in section
        assert "codebase_search" in section
        assert "conceptual queries" in section

    def test_includes_exact_search_guidance(self):
        """Should include exact search guidance when available."""
        # Arrange
        factory = GraphContextFactory(None)

        # Act
        section = factory.build_search_strategy_section(["find_exact_text", "read_file"])

        # Assert
        assert "Code Search Strategy" in section
        assert "find_exact_text" in section
        assert "literal pattern matching" in section

    def test_includes_both_search_strategies(self):
        """Should include both strategies when both tools available."""
        # Arrange
        factory = GraphContextFactory(None)

        # Act
        section = factory.build_search_strategy_section(["codebase_search", "find_exact_text"])

        # Assert
        assert "Code Search Strategy" in section
        assert "codebase_search" in section
        assert "find_exact_text" in section
        assert "Prefer semantic search" in section

    def test_returns_empty_when_no_search_tools(self):
        """Should return empty string when no search tools available."""
        # Arrange
        factory = GraphContextFactory(None)

        # Act
        section = factory.build_search_strategy_section(["read_file", "write_file"])

        # Assert
        assert section == ""


# =============================================================================
# is_ready Tests
# =============================================================================

class TestIsReady:
    """Test is_ready method."""

    def test_ready_when_semantic_manager_ready(self):
        """Should return True when semantic manager is ready."""
        # Arrange
        semantic_manager = MockSemanticManager(is_ready=True)
        factory = GraphContextFactory(semantic_manager)

        # Assert
        assert factory.is_ready() is True

    def test_not_ready_when_semantic_manager_not_ready(self):
        """Should return False when semantic manager not ready."""
        # Arrange
        semantic_manager = MockSemanticManager(is_ready=False)
        factory = GraphContextFactory(semantic_manager)

        # Assert
        assert factory.is_ready() is False

    def test_not_ready_when_no_semantic_manager(self):
        """Should return False when no semantic manager."""
        # Arrange
        factory = GraphContextFactory(None)

        # Assert
        assert factory.is_ready() is False


# =============================================================================
# NullContextFactory Tests
# =============================================================================

class TestNullContextFactory:
    """Test NullContextFactory no-op behavior."""

    def test_build_rag_context_returns_none(self):
        """Should always return None for RAG context."""
        factory = NullContextFactory()
        assert factory.build_rag_context("any task") is None

    def test_build_search_strategy_returns_empty(self):
        """Should always return empty string for search strategy."""
        factory = NullContextFactory()
        assert factory.build_search_strategy_section(["any", "tools"]) == ""

    def test_is_ready_returns_false(self):
        """Should always return False for is_ready."""
        factory = NullContextFactory()
        assert factory.is_ready() is False


# =============================================================================
# Language Detection Tests
# =============================================================================

class TestLanguageDetection:
    """Test language detection from file paths."""

    def test_detects_python_files(self):
        """Should detect Python files."""
        assert _get_language_from_path("src/main.py") == "python"
        assert _get_language_from_path("tests/test_foo.py") == "python"

    def test_detects_javascript_files(self):
        """Should detect JavaScript/TypeScript files."""
        assert _get_language_from_path("src/index.js") == "javascript"
        assert _get_language_from_path("src/app.ts") == "typescript"
        assert _get_language_from_path("components/Button.tsx") == "tsx"
        assert _get_language_from_path("components/Modal.jsx") == "jsx"

    def test_detects_common_languages(self):
        """Should detect common programming languages."""
        assert _get_language_from_path("main.go") == "go"
        assert _get_language_from_path("lib.rs") == "rust"
        assert _get_language_from_path("App.java") == "java"
        assert _get_language_from_path("script.rb") == "ruby"
        assert _get_language_from_path("Program.cs") == "csharp"

    def test_detects_config_files(self):
        """Should detect config file languages."""
        assert _get_language_from_path("config.yaml") == "yaml"
        assert _get_language_from_path("settings.yml") == "yaml"
        assert _get_language_from_path("package.json") == "json"
        assert _get_language_from_path("pyproject.toml") == "toml"

    def test_returns_empty_for_unknown_extensions(self):
        """Should return empty string for unknown extensions."""
        assert _get_language_from_path("data.unknown") == ""
        assert _get_language_from_path("file.xyz") == ""
        assert _get_language_from_path("noextension") == ""

    def test_extension_language_map_has_common_languages(self):
        """Extension map should include common languages."""
        assert ".py" in EXTENSION_LANGUAGE_MAP
        assert ".js" in EXTENSION_LANGUAGE_MAP
        assert ".ts" in EXTENSION_LANGUAGE_MAP
        assert ".go" in EXTENSION_LANGUAGE_MAP
        assert ".rs" in EXTENSION_LANGUAGE_MAP


# =============================================================================
# RAG Formatting Tests
# =============================================================================

class TestRAGFormatting:
    """Test RAG context formatting with new structure."""

    def test_includes_language_hint_in_code_blocks(self):
        """Should include language hint in code blocks."""
        # Arrange
        search_results = [
            {
                'path': 'src/utils/helper.py',
                'lines': (1, 5),
                'content': 'def helper(): pass',
                'score': 0.9
            }
        ]
        semantic_manager = MockSemanticManager(is_ready=True, search_results=search_results)
        factory = GraphContextFactory(semantic_manager)

        # Act
        rag_context = factory.build_rag_context("test")

        # Assert
        assert "```python" in rag_context

    def test_includes_language_hint_for_typescript(self):
        """Should include typescript hint for .ts files."""
        # Arrange
        search_results = [
            {
                'path': 'src/components/App.tsx',
                'lines': (1, 5),
                'content': 'const App = () => <div />',
                'score': 0.9
            }
        ]
        semantic_manager = MockSemanticManager(is_ready=True, search_results=search_results)
        factory = GraphContextFactory(semantic_manager)

        # Act
        rag_context = factory.build_rag_context("test")

        # Assert
        assert "```tsx" in rag_context

    def test_handles_unknown_file_extension(self):
        """Should handle files with unknown extensions gracefully."""
        # Arrange
        search_results = [
            {
                'path': 'data/config.unknown',
                'lines': (1, 5),
                'content': 'some content',
                'score': 0.9
            }
        ]
        semantic_manager = MockSemanticManager(is_ready=True, search_results=search_results)
        factory = GraphContextFactory(semantic_manager)

        # Act
        rag_context = factory.build_rag_context("test")

        # Assert - should have code block without language hint
        assert "```\n" in rag_context or "```\r\n" in rag_context or rag_context.count("```") >= 2

    def test_includes_patterns_note_at_end(self):
        """Should include helpful note about patterns at the end."""
        # Arrange
        search_results = [
            {
                'path': 'src/main.py',
                'lines': (1, 5),
                'content': 'def main(): pass',
                'score': 0.9
            }
        ]
        semantic_manager = MockSemanticManager(is_ready=True, search_results=search_results)
        factory = GraphContextFactory(semantic_manager)

        # Act
        rag_context = factory.build_rag_context("test")

        # Assert
        assert "existing patterns in your codebase" in rag_context
        # Note should be at the end
        note_pos = rag_context.find("existing patterns")
        code_end = rag_context.rfind("```")
        assert note_pos > code_end

    def test_shows_lines_separately_from_path(self):
        """Should show line numbers on separate line from path."""
        # Arrange
        search_results = [
            {
                'path': 'src/utils.py',
                'lines': (42, 56),
                'content': 'def util(): pass',
                'score': 0.9
            }
        ]
        semantic_manager = MockSemanticManager(is_ready=True, search_results=search_results)
        factory = GraphContextFactory(semantic_manager)

        # Act
        rag_context = factory.build_rag_context("test")

        # Assert
        assert "### src/utils.py" in rag_context
        assert "Lines 42-56:" in rag_context
