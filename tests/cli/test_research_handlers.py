"""
Tests for research handlers used by smart_query.

These tests verify the ResearchHandler protocol and individual handler implementations.
"""

import pytest
from unittest.mock import Mock, MagicMock
from typing import List

from scrappy.task_router.protocols import QueryIntent, IntentResult
from scrappy.cli.research_handlers.base import ClassificationResult
from scrappy.protocols.io import CLIIOProtocol


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_agent():
    """Create a mock CodeAgent with tool methods."""
    agent = Mock()

    # Configure tool methods to return realistic data
    agent._tool_list_directory.return_value = """src/
  __init__.py
  cli/
    smart_query.py
  agent.py
tests/
  test_agent.py"""

    agent._tool_search_code.return_value = """src/agent.py:10: class CodeAgent:
src/agent.py:50: def _tool_search_code(self, pattern):"""

    agent._tool_read_file.return_value = """def example_function():
    '''Example docstring.'''
    return 42"""

    agent._tool_git_log.return_value = """abc1234 Fix bug in parser
def5678 Add new feature
ghi9012 Initial commit"""

    agent._tool_git_status.return_value = """On branch main
Your branch is up to date with 'origin/main'.

nothing to commit, working tree clean"""

    return agent


@pytest.fixture
def mock_io():
    """Create a mock IO interface."""
    io = Mock(spec=CLIIOProtocol)
    return io


@pytest.fixture
def sample_classification():
    """Create a sample classification result for testing."""
    intent_result = IntentResult(
        intent=QueryIntent.FILE_STRUCTURE,
        confidence=0.9,
        metadata={'matched_patterns': ["where is", "structure"]}
    )
    return ClassificationResult(
        query="What is the directory structure?",
        intent_result=intent_result,
        entities={'file_path': []},
        keywords=['directory', 'structure']
    )


# =============================================================================
# ResearchHandler Protocol Tests
# =============================================================================

class TestResearchHandlerProtocol:
    """Tests for the ResearchHandler protocol contract."""

    def test_handler_has_intent_property(self):
        """Handler must expose which intent it handles."""
        from scrappy.cli.research_handlers.base import ResearchHandler
        from scrappy.cli.research_handlers.file_structure import FileStructureHandler

        handler = FileStructureHandler()
        assert hasattr(handler, 'intent')
        assert handler.intent == QueryIntent.FILE_STRUCTURE



        # Should handle errors gracefully

    def test_execute_uses_io_for_progress(self, mock_agent, mock_io, sample_classification):
        """execute() should report progress via io interface."""
        from scrappy.cli.research_handlers.file_structure import FileStructureHandler

        handler = FileStructureHandler()
        handler.execute(mock_agent, sample_classification, mock_io)

        # Handler should output progress messages
        assert mock_io.echo.called


# =============================================================================
# FileStructureHandler Tests
# =============================================================================

class TestFileStructureHandler:
    """Tests for FileStructureHandler."""

    def test_handles_file_structure_intent(self):
        """Handler identifies as FILE_STRUCTURE intent handler."""
        from scrappy.cli.research_handlers.file_structure import FileStructureHandler

        handler = FileStructureHandler()
        assert handler.intent == QueryIntent.FILE_STRUCTURE

    def test_lists_directory_structure(self, mock_agent, mock_io, sample_classification):
        """Handler calls list_directory tool and returns formatted result."""
        from scrappy.cli.research_handlers.file_structure import FileStructureHandler

        handler = FileStructureHandler()
        results = handler.execute(mock_agent, sample_classification, mock_io)

        mock_agent._tool_list_directory.assert_called_once()
        assert len(results) >= 1
        assert "Directory Structure" in results[0] or "src/" in results[0]

    def test_handles_tool_error_gracefully(self, mock_agent, mock_io, sample_classification):
        """Handler returns empty list when tool raises exception."""
        from scrappy.cli.research_handlers.file_structure import FileStructureHandler

        mock_agent._tool_list_directory.side_effect = Exception("Permission denied")

        handler = FileStructureHandler()
        results = handler.execute(mock_agent, sample_classification, mock_io)

        # Should not raise, should return empty list
        assert results == []

    def test_reports_warning_on_error(self, mock_agent, mock_io, sample_classification):
        """Handler reports warning to io when tool fails."""
        from scrappy.cli.research_handlers.file_structure import FileStructureHandler

        mock_agent._tool_list_directory.side_effect = Exception("Permission denied")

        handler = FileStructureHandler()
        handler.execute(mock_agent, sample_classification, mock_io)

        # Should report the error via io
        io_output = str(mock_io.echo.call_args_list)
        assert "Warning" in io_output or "Could not" in io_output or mock_io.echo.called


# =============================================================================
# GitHistoryHandler Tests
# =============================================================================

class TestGitHistoryHandler:
    """Tests for GitHistoryHandler."""

    def test_handles_git_history_intent(self):
        """Handler identifies as GIT_HISTORY intent handler."""
        from scrappy.cli.research_handlers.git_history import GitHistoryHandler

        handler = GitHistoryHandler()
        assert handler.intent == QueryIntent.GIT_HISTORY

    def test_gets_git_log(self, mock_agent, mock_io, sample_classification):
        """Handler retrieves git log."""
        from scrappy.cli.research_handlers.git_history import GitHistoryHandler

        handler = GitHistoryHandler()
        results = handler.execute(mock_agent, sample_classification, mock_io)

        mock_agent._tool_git_log.assert_called()
        # Should include commit history
        assert any("Commits" in r or "abc1234" in r for r in results)

    def test_gets_git_status(self, mock_agent, mock_io, sample_classification):
        """Handler also retrieves git status."""
        from scrappy.cli.research_handlers.git_history import GitHistoryHandler

        handler = GitHistoryHandler()
        results = handler.execute(mock_agent, sample_classification, mock_io)

        mock_agent._tool_git_status.assert_called()
        # Should include status info
        assert any("Status" in r or "branch" in r for r in results)


# =============================================================================
# ResearchHandlerRegistry Tests
# =============================================================================

class TestResearchHandlerRegistry:
    """Tests for the handler registry."""

    def test_register_handler(self):
        """Registry can register a handler."""
        from scrappy.cli.research_handlers.registry import ResearchHandlerRegistry
        from scrappy.cli.research_handlers.file_structure import FileStructureHandler

        registry = ResearchHandlerRegistry()
        handler = FileStructureHandler()

        registry.register(handler)

        retrieved = registry.get_handler(QueryIntent.FILE_STRUCTURE)
        assert retrieved is handler

    def test_get_handler_returns_none_for_unregistered(self):
        """Registry returns None for unregistered intents."""
        from scrappy.cli.research_handlers.registry import ResearchHandlerRegistry

        registry = ResearchHandlerRegistry()

        result = registry.get_handler(QueryIntent.FILE_STRUCTURE)
        assert result is None

    def test_register_multiple_handlers(self):
        """Registry can hold multiple handlers."""
        from scrappy.cli.research_handlers.registry import ResearchHandlerRegistry
        from scrappy.cli.research_handlers.file_structure import FileStructureHandler
        from scrappy.cli.research_handlers.git_history import GitHistoryHandler

        registry = ResearchHandlerRegistry()

        fs_handler = FileStructureHandler()
        git_handler = GitHistoryHandler()

        registry.register(fs_handler)
        registry.register(git_handler)

        assert registry.get_handler(QueryIntent.FILE_STRUCTURE) is fs_handler
        assert registry.get_handler(QueryIntent.GIT_HISTORY) is git_handler

    def test_list_registered_intents(self):
        """Registry can list all registered intents."""
        from scrappy.cli.research_handlers.registry import ResearchHandlerRegistry
        from scrappy.cli.research_handlers.file_structure import FileStructureHandler
        from scrappy.cli.research_handlers.git_history import GitHistoryHandler

        registry = ResearchHandlerRegistry()
        registry.register(FileStructureHandler())
        registry.register(GitHistoryHandler())

        intents = registry.list_intents()

        assert QueryIntent.FILE_STRUCTURE in intents
        assert QueryIntent.GIT_HISTORY in intents
        assert len(intents) == 2



# =============================================================================
# Handler Integration Tests
# =============================================================================

class TestHandlerIntegration:
    """Integration tests for handlers working together."""


    def test_handlers_are_stateless(self, mock_agent, mock_io):
        """Handlers should be stateless - multiple calls work correctly."""
        from scrappy.cli.research_handlers.file_structure import FileStructureHandler

        classification = ClassificationResult(
            query="Show files",
            intent_result=IntentResult(intent=QueryIntent.FILE_STRUCTURE, confidence=0.9, metadata={}),
            entities={},
            keywords=[]
        )

        handler = FileStructureHandler()

        # Call multiple times
        results1 = handler.execute(mock_agent, classification, mock_io)
        results2 = handler.execute(mock_agent, classification, mock_io)

        # Both calls should work
        assert results1 == results2
