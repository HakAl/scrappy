"""
Integration tests for semantic search with CodebaseContext.

Tests end-to-end behavior across multiple components.

Note: These tests work both with and without LanceDB dependencies.
      They verify graceful degradation when dependencies are unavailable.
"""

import pytest
from pathlib import Path
from src.context import CodebaseContext


def test_semantic_context_retrieval_end_to_end(tmp_path):
    """End-to-end: explore codebase, semantic search works automatically."""
    # Create test files
    (tmp_path / "auth.py").write_text(
        "def authenticate_user(username, password):\n"
        "    '''Authenticate a user with credentials.'''\n"
        "    return validate_credentials(username, password)\n"
    )
    (tmp_path / "email.py").write_text(
        "def validate_email(email):\n"
        "    '''Check if email is valid.'''\n"
        "    return '@' in email\n"
    )

    # Create context (semantic search auto-created if available)
    context = CodebaseContext(str(tmp_path))

    # Explore codebase (should auto-index)
    result = context.explore()

    # If semantic search is available, should be indicated
    # (gracefully handles if LanceDB not installed)
    if result.get('semantic_search_enabled'):
        # Get context for authentication query
        context_str = context.get_relevant_context("user authentication")

        # Should find relevant content
        assert "authenticate_user" in context_str or "auth.py" in context_str
        assert len(context_str) > 0
    else:
        # Semantic search not available (LanceDB not installed)
        # Should fall back to keyword matching
        context_str = context.get_relevant_context("authentication")
        # Keyword matching may or may not find it - that's OK
        assert isinstance(context_str, str)


def test_graceful_degradation_without_lancedb(tmp_path, monkeypatch):
    """Context works without LanceDB (graceful degradation)."""
    # Simulate LanceDB not available
    import sys
    if 'lancedb' in sys.modules:
        monkeypatch.setitem(sys.modules, 'lancedb', None)

    # Create context - should not crash
    context = CodebaseContext(str(tmp_path))

    # Explore should work
    (tmp_path / "test.py").write_text("def test(): pass")
    result = context.explore()
    assert result['status'] == 'explored'

    # get_relevant_context should fall back to keyword
    context_str = context.get_relevant_context("test")
    assert isinstance(context_str, str)  # Should return something, not crash


def test_context_status_includes_semantic_search_info(tmp_path):
    """get_status() includes semantic search availability."""
    (tmp_path / "test.py").write_text("def test(): pass")

    context = CodebaseContext(str(tmp_path))
    result = context.explore()

    # Status should include semantic search indicator
    assert 'semantic_search_enabled' in result
    assert isinstance(result['semantic_search_enabled'], bool)


def test_explore_returns_consistent_data_with_or_without_semantic(tmp_path):
    """explore() returns consistent structure regardless of semantic search availability."""
    (tmp_path / "main.py").write_text("print('hello')")

    context = CodebaseContext(str(tmp_path))
    result = context.explore()

    # Core fields should always be present
    assert 'status' in result
    assert 'explored_at' in result
    assert 'total_files' in result
    assert 'semantic_search_enabled' in result

    # Should be explored successfully
    assert result['status'] == 'explored'
    assert result['total_files'] > 0
