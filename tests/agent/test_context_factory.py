"""
Unit tests for AgentContextFactory.

Tests:
- Tool filtering when semantic search index is not ready
- Passive RAG context generation
- Budget heuristics for adaptive token allocation
- System prompt construction with search strategy
"""

import pytest
from unittest.mock import Mock
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from scrappy.agent.context_factory import AgentContextFactory
from scrappy.agent.types import AgentContext
from scrappy.agent_config import AgentConfig
from scrappy.agent_tools.tools import ToolRegistry


@dataclass
class SearchResult:
    """Mock SearchResult dataclass matching context.protocols.SearchResult."""
    chunks: List[Dict[str, Any]]
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
        self._search_calls = []

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


class MockToolRegistry:
    """
    Test double for ToolRegistry.

    Provides a minimal registry for testing tool filtering.
    """

    def __init__(self, tool_names: list = None):
        """
        Initialize mock tool registry.

        Args:
            tool_names: List of tool names to include
        """
        self._tool_names = tool_names or ["read_file", "write_file", "codebase_search"]

    def list_all(self) -> list:
        """Return list of mock tools."""
        tools = []
        for name in self._tool_names:
            tool = Mock()
            tool.name = name  # Set name as attribute, not as Mock argument
            tools.append(tool)
        return tools


# =============================================================================
# Tool Filtering Tests
# =============================================================================

class TestToolFiltering:
    """Test tool filtering based on semantic search availability."""

    def test_includes_all_tools_when_semantic_search_ready(self):
        """All tools should be active when semantic search is ready."""
        # Arrange
        semantic_manager = MockSemanticManager(is_ready=True)
        config = AgentConfig()
        tool_registry = MockToolRegistry(["read_file", "write_file", "codebase_search"])
        factory = AgentContextFactory(semantic_manager, config, tool_registry)

        # Act
        context = factory.build_context(
            task="Test task",
            base_system_prompt="Base prompt"
        )

        # Assert
        assert "codebase_search" in context.active_tools
        assert "read_file" in context.active_tools
        assert "write_file" in context.active_tools
        assert len(context.active_tools) == 3

    def test_filters_out_codebase_search_when_not_ready(self):
        """codebase_search should be filtered when semantic search not ready."""
        # Arrange
        semantic_manager = MockSemanticManager(is_ready=False)
        config = AgentConfig()
        tool_registry = MockToolRegistry(["read_file", "write_file", "codebase_search"])
        factory = AgentContextFactory(semantic_manager, config, tool_registry)

        # Act
        context = factory.build_context(
            task="Test task",
            base_system_prompt="Base prompt"
        )

        # Assert
        assert "codebase_search" not in context.active_tools
        assert "read_file" in context.active_tools
        assert "write_file" in context.active_tools
        assert len(context.active_tools) == 2

    def test_filters_out_codebase_search_when_no_semantic_manager(self):
        """codebase_search should be filtered when semantic_manager is None."""
        # Arrange
        config = AgentConfig()
        tool_registry = MockToolRegistry(["read_file", "write_file", "codebase_search"])
        factory = AgentContextFactory(None, config, tool_registry)

        # Act
        context = factory.build_context(
            task="Test task",
            base_system_prompt="Base prompt"
        )

        # Assert
        assert "codebase_search" not in context.active_tools
        assert "read_file" in context.active_tools
        assert "write_file" in context.active_tools

    def test_preserves_other_tools_when_no_codebase_search(self):
        """Other tools should work normally when codebase_search not in registry."""
        # Arrange
        semantic_manager = MockSemanticManager(is_ready=False)
        config = AgentConfig()
        tool_registry = MockToolRegistry(["read_file", "write_file", "run_command"])
        factory = AgentContextFactory(semantic_manager, config, tool_registry)

        # Act
        context = factory.build_context(
            task="Test task",
            base_system_prompt="Base prompt"
        )

        # Assert
        assert "read_file" in context.active_tools
        assert "write_file" in context.active_tools
        assert "run_command" in context.active_tools
        assert len(context.active_tools) == 3


# =============================================================================
# Passive RAG Context Tests
# =============================================================================

class TestPassiveRAGContext:
    """Test passive RAG context generation."""

    def test_generates_rag_context_when_enabled_and_ready(self):
        """Should generate RAG context when enabled and semantic search ready."""
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
        config = AgentConfig()
        config.passive_rag_enabled = True
        tool_registry = MockToolRegistry()
        factory = AgentContextFactory(semantic_manager, config, tool_registry)

        # Act
        context = factory.build_context(
            task="How does foo work?",
            base_system_prompt="Base prompt"
        )

        # Assert
        assert context.passive_rag_context is not None
        assert "Relevant Codebase Context" in context.passive_rag_context
        assert "src/main.py:10-20" in context.passive_rag_context
        assert "def foo()" in context.passive_rag_context
        assert "src/helper.py:5-15" in context.passive_rag_context

    def test_no_rag_context_when_disabled(self):
        """Should not generate RAG context when disabled in config."""
        # Arrange
        search_results = [
            {'path': 'test.py', 'lines': (1, 10), 'content': 'code', 'score': 0.9}
        ]
        semantic_manager = MockSemanticManager(is_ready=True, search_results=search_results)
        config = AgentConfig()
        config.passive_rag_enabled = False
        tool_registry = MockToolRegistry()
        factory = AgentContextFactory(semantic_manager, config, tool_registry)

        # Act
        context = factory.build_context(
            task="Test task",
            base_system_prompt="Base prompt"
        )

        # Assert
        assert context.passive_rag_context is None

    def test_no_rag_context_when_not_ready(self):
        """Should not generate RAG context when semantic search not ready."""
        # Arrange
        semantic_manager = MockSemanticManager(is_ready=False)
        config = AgentConfig()
        config.passive_rag_enabled = True
        tool_registry = MockToolRegistry()
        factory = AgentContextFactory(semantic_manager, config, tool_registry)

        # Act
        context = factory.build_context(
            task="Test task",
            base_system_prompt="Base prompt"
        )

        # Assert
        assert context.passive_rag_context is None

    def test_no_rag_context_when_no_semantic_manager(self):
        """Should not generate RAG context when semantic_manager is None."""
        # Arrange
        config = AgentConfig()
        config.passive_rag_enabled = True
        tool_registry = MockToolRegistry()
        factory = AgentContextFactory(None, config, tool_registry)

        # Act
        context = factory.build_context(
            task="Test task",
            base_system_prompt="Base prompt"
        )

        # Assert
        assert context.passive_rag_context is None

    def test_handles_empty_search_results_gracefully(self):
        """Should return None when search returns no results."""
        # Arrange
        semantic_manager = MockSemanticManager(is_ready=True, search_results=[])
        config = AgentConfig()
        config.passive_rag_enabled = True
        tool_registry = MockToolRegistry()
        factory = AgentContextFactory(semantic_manager, config, tool_registry)

        # Act
        context = factory.build_context(
            task="Test task",
            base_system_prompt="Base prompt"
        )

        # Assert
        assert context.passive_rag_context is None

    def test_handles_search_exception_gracefully(self):
        """Should return None when search raises exception."""
        # Arrange
        semantic_manager = Mock()
        semantic_manager.is_ready.return_value = True
        semantic_manager.search.side_effect = Exception("Search failed")
        config = AgentConfig()
        config.passive_rag_enabled = True
        tool_registry = MockToolRegistry()
        factory = AgentContextFactory(semantic_manager, config, tool_registry)

        # Act
        context = factory.build_context(
            task="Test task",
            base_system_prompt="Base prompt"
        )

        # Assert - should not crash, should return None for RAG context
        assert context.passive_rag_context is None


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
        config = AgentConfig()
        config.passive_rag_enabled = True
        config.passive_rag_max_tokens = 2000
        tool_registry = MockToolRegistry()
        factory = AgentContextFactory(semantic_manager, config, tool_registry)

        # Act
        context = factory.build_context(
            task="simple query",
            base_system_prompt="Base prompt"
        )

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
        config = AgentConfig()
        config.passive_rag_enabled = True
        config.passive_rag_max_tokens = 2000
        tool_registry = MockToolRegistry()
        factory = AgentContextFactory(semantic_manager, config, tool_registry)

        # Act
        context = factory.build_context(
            task="Check src/main.py for errors",
            base_system_prompt="Base prompt"
        )

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
        config = AgentConfig()
        config.passive_rag_enabled = True
        config.passive_rag_max_tokens = 2000
        tool_registry = MockToolRegistry()
        factory = AgentContextFactory(semantic_manager, config, tool_registry)

        # Act - task with 4+ identifiers
        context = factory.build_context(
            task="Update UserModel, ProductModel, OrderModel, and CartModel classes",
            base_system_prompt="Base prompt"
        )

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
        config = AgentConfig()
        config.passive_rag_enabled = True
        config.passive_rag_max_tokens = 2000
        tool_registry = MockToolRegistry()
        factory = AgentContextFactory(semantic_manager, config, tool_registry)

        # Act
        context = factory.build_context(
            task="How does the authentication system work?",
            base_system_prompt="Base prompt"
        )

        # Assert - should boost for exploration words
        search_calls = semantic_manager.get_search_calls()
        assert len(search_calls) == 1
        assert search_calls[0]['max_tokens'] > 2000  # Boosted budget

    def test_combines_multiple_boosts(self):
        """Should combine boosts from multiple heuristics."""
        # Arrange
        semantic_manager = MockSemanticManager(is_ready=True, search_results=[
            {'path': 'test.py', 'lines': (1, 10), 'content': 'x' * 100, 'score': 0.9}
        ])
        config = AgentConfig()
        config.passive_rag_enabled = True
        config.passive_rag_max_tokens = 1000
        tool_registry = MockToolRegistry()
        factory = AgentContextFactory(semantic_manager, config, tool_registry)

        # Act - multiple heuristics: file ref + exploration + identifiers
        context = factory.build_context(
            task="Where is the UserManager class in src/auth.py and how does it work?",
            base_system_prompt="Base prompt"
        )

        # Assert - should apply multiple boosts
        search_calls = semantic_manager.get_search_calls()
        assert len(search_calls) == 1
        # With file (1.3x) + exploration (1.5x) = 1.5x total, capped at 2x
        # 1000 * 1.5 = 1500
        assert search_calls[0]['max_tokens'] >= 1500

    def test_caps_boost_at_2x_base_budget(self):
        """Should cap total boost at 2x base budget."""
        # Arrange
        semantic_manager = MockSemanticManager(is_ready=True, search_results=[
            {'path': 'test.py', 'lines': (1, 10), 'content': 'x' * 100, 'score': 0.9}
        ])
        config = AgentConfig()
        config.passive_rag_enabled = True
        config.passive_rag_max_tokens = 1000
        tool_registry = MockToolRegistry()
        factory = AgentContextFactory(semantic_manager, config, tool_registry)

        # Act - extreme case with all heuristics
        context = factory.build_context(
            task="Where are UserModel, ProductModel, OrderModel, CartModel, PaymentModel in src/models.py and how do they work?",
            base_system_prompt="Base prompt"
        )

        # Assert - should cap at 2x
        search_calls = semantic_manager.get_search_calls()
        assert len(search_calls) == 1
        assert search_calls[0]['max_tokens'] <= 2000  # 2x cap


# =============================================================================
# System Prompt Construction Tests
# =============================================================================

class TestSystemPromptConstruction:
    """Test system prompt building with search strategy."""

    def test_includes_base_prompt(self):
        """System prompt should include base prompt."""
        # Arrange
        semantic_manager = MockSemanticManager(is_ready=False)
        config = AgentConfig()
        tool_registry = MockToolRegistry(["read_file"])
        factory = AgentContextFactory(semantic_manager, config, tool_registry)

        # Act
        context = factory.build_context(
            task="Test task",
            base_system_prompt="You are a helpful assistant"
        )

        # Assert
        assert "You are a helpful assistant" in context.system_prompt

    def test_includes_search_strategy_for_semantic_search(self):
        """Should include semantic search guidance when available."""
        # Arrange
        semantic_manager = MockSemanticManager(is_ready=True)
        config = AgentConfig()
        tool_registry = MockToolRegistry(["codebase_search", "read_file"])
        factory = AgentContextFactory(semantic_manager, config, tool_registry)

        # Act
        context = factory.build_context(
            task="Test task",
            base_system_prompt="Base prompt"
        )

        # Assert
        assert "Code Search Strategy" in context.system_prompt
        assert "codebase_search" in context.system_prompt
        assert "conceptual queries" in context.system_prompt

    def test_includes_search_strategy_for_exact_search(self):
        """Should include exact search guidance when available."""
        # Arrange
        semantic_manager = MockSemanticManager(is_ready=False)
        config = AgentConfig()
        tool_registry = MockToolRegistry(["find_exact_text", "read_file"])
        factory = AgentContextFactory(semantic_manager, config, tool_registry)

        # Act
        context = factory.build_context(
            task="Test task",
            base_system_prompt="Base prompt"
        )

        # Assert
        assert "Code Search Strategy" in context.system_prompt
        assert "find_exact_text" in context.system_prompt
        assert "literal pattern matching" in context.system_prompt

    def test_includes_both_search_strategies(self):
        """Should include both search strategies when both available."""
        # Arrange
        semantic_manager = MockSemanticManager(is_ready=True)
        config = AgentConfig()
        tool_registry = MockToolRegistry(["codebase_search", "find_exact_text"])
        factory = AgentContextFactory(semantic_manager, config, tool_registry)

        # Act
        context = factory.build_context(
            task="Test task",
            base_system_prompt="Base prompt"
        )

        # Assert
        assert "Code Search Strategy" in context.system_prompt
        assert "codebase_search" in context.system_prompt
        assert "find_exact_text" in context.system_prompt
        assert "Prefer semantic search" in context.system_prompt

    def test_no_search_strategy_when_no_search_tools(self):
        """Should not include search strategy when no search tools available."""
        # Arrange
        semantic_manager = MockSemanticManager(is_ready=False)
        config = AgentConfig()
        tool_registry = MockToolRegistry(["read_file", "write_file"])
        factory = AgentContextFactory(semantic_manager, config, tool_registry)

        # Act
        context = factory.build_context(
            task="Test task",
            base_system_prompt="Base prompt"
        )

        # Assert
        assert "Code Search Strategy" not in context.system_prompt

    def test_includes_rag_context_in_prompt(self):
        """Should append RAG context to system prompt when available."""
        # Arrange
        search_results = [
            {
                'path': 'src/main.py',
                'lines': (10, 20),
                'content': 'def foo():\n    return 42',
                'score': 0.9
            }
        ]
        semantic_manager = MockSemanticManager(is_ready=True, search_results=search_results)
        config = AgentConfig()
        config.passive_rag_enabled = True
        tool_registry = MockToolRegistry()
        factory = AgentContextFactory(semantic_manager, config, tool_registry)

        # Act
        context = factory.build_context(
            task="How does foo work?",
            base_system_prompt="Base prompt"
        )

        # Assert
        assert "Base prompt" in context.system_prompt
        assert "Relevant Codebase Context" in context.system_prompt
        assert "src/main.py:10-20" in context.system_prompt
        assert "def foo()" in context.system_prompt

    def test_prompt_structure_with_all_sections(self):
        """Should have proper structure with all sections."""
        # Arrange
        search_results = [
            {'path': 'test.py', 'lines': (1, 10), 'content': 'code', 'score': 0.9}
        ]
        semantic_manager = MockSemanticManager(is_ready=True, search_results=search_results)
        config = AgentConfig()
        config.passive_rag_enabled = True
        tool_registry = MockToolRegistry(["codebase_search", "find_exact_text"])
        factory = AgentContextFactory(semantic_manager, config, tool_registry)

        # Act
        context = factory.build_context(
            task="Test task",
            base_system_prompt="You are a helpful assistant"
        )

        # Assert - verify order and structure
        prompt = context.system_prompt
        base_pos = prompt.find("You are a helpful assistant")
        search_strategy_pos = prompt.find("Code Search Strategy")
        rag_pos = prompt.find("Relevant Codebase Context")

        assert base_pos < search_strategy_pos < rag_pos
        assert base_pos != -1
        assert search_strategy_pos != -1
        assert rag_pos != -1


# =============================================================================
# AgentContext Output Tests
# =============================================================================

class TestAgentContextOutput:
    """Test AgentContext dataclass structure."""

    def test_returns_agent_context_dataclass(self):
        """Should return AgentContext with all required fields."""
        # Arrange
        semantic_manager = MockSemanticManager(is_ready=False)
        config = AgentConfig()
        tool_registry = MockToolRegistry()
        factory = AgentContextFactory(semantic_manager, config, tool_registry)

        # Act
        context = factory.build_context(
            task="Test task",
            base_system_prompt="Base prompt"
        )

        # Assert
        assert isinstance(context, AgentContext)
        assert hasattr(context, 'system_prompt')
        assert hasattr(context, 'active_tools')
        assert hasattr(context, 'passive_rag_context')

    def test_system_prompt_is_string(self):
        """system_prompt should be a string."""
        # Arrange
        semantic_manager = MockSemanticManager(is_ready=False)
        config = AgentConfig()
        tool_registry = MockToolRegistry()
        factory = AgentContextFactory(semantic_manager, config, tool_registry)

        # Act
        context = factory.build_context(
            task="Test task",
            base_system_prompt="Base prompt"
        )

        # Assert
        assert isinstance(context.system_prompt, str)
        assert len(context.system_prompt) > 0

    def test_active_tools_is_list_of_strings(self):
        """active_tools should be a list of tool name strings."""
        # Arrange
        semantic_manager = MockSemanticManager(is_ready=False)
        config = AgentConfig()
        tool_registry = MockToolRegistry(["read_file", "write_file"])
        factory = AgentContextFactory(semantic_manager, config, tool_registry)

        # Act
        context = factory.build_context(
            task="Test task",
            base_system_prompt="Base prompt"
        )

        # Assert
        assert isinstance(context.active_tools, list)
        assert all(isinstance(tool, str) for tool in context.active_tools)
        assert len(context.active_tools) > 0

    def test_passive_rag_context_is_optional_string(self):
        """passive_rag_context should be None or string."""
        # Arrange - with RAG
        search_results = [
            {'path': 'test.py', 'lines': (1, 10), 'content': 'code', 'score': 0.9}
        ]
        semantic_manager_with = MockSemanticManager(is_ready=True, search_results=search_results)
        config_with = AgentConfig()
        config_with.passive_rag_enabled = True
        tool_registry_with = MockToolRegistry()
        factory_with = AgentContextFactory(semantic_manager_with, config_with, tool_registry_with)

        # Arrange - without RAG
        semantic_manager_without = MockSemanticManager(is_ready=False)
        config_without = AgentConfig()
        tool_registry_without = MockToolRegistry()
        factory_without = AgentContextFactory(semantic_manager_without, config_without, tool_registry_without)

        # Act
        context_with_rag = factory_with.build_context("Test", "Base")
        context_without_rag = factory_without.build_context("Test", "Base")

        # Assert
        assert isinstance(context_with_rag.passive_rag_context, str)
        assert context_without_rag.passive_rag_context is None
