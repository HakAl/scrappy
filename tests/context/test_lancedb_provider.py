"""
Tests for LanceDB semantic search.

Tests BEHAVIOR (indexing, search, updates), not implementation details.

Note: These tests require semantic dependencies:
    pip install -e ".[semantic]"
"""

import pytest
import shutil
from pathlib import Path

# Skip all tests if LanceDB not available
pytest.importorskip("lancedb", reason="LanceDB not installed. Run: pip install -e '.[semantic]'")

from src.context.lancedb_search_provider import LanceDBSearchProvider
from src.context.code_chunker import SemanticCodeChunker


@pytest.fixture
def provider(tmp_path):
    """Create search provider with temp directory."""
    chunker = SemanticCodeChunker(chunk_size=100, overlap=3)
    provider = LanceDBSearchProvider(tmp_path, chunker)

    yield provider

    # Cleanup
    db_path = tmp_path / ".lancedb"
    if db_path.exists():
        shutil.rmtree(db_path)


def test_empty_search_returns_empty(provider):
    """Search on empty index returns no results."""
    result = provider.search("test query")

    assert result.chunks == []
    assert result.tokens_used == 0
    assert result.limit_hit is None


def test_is_indexed_returns_false_when_empty(provider):
    """is_indexed() returns False before indexing."""
    assert provider.is_indexed() is False


def test_indexes_and_retrieves_content(provider):
    """End-to-end: index files and retrieve via search."""
    files = {
        "main.py": "def hello():\n    print('Hello world')\n",
        "utils.py": "def add(a, b):\n    return a + b\n"
    }

    provider.index_files(files)

    assert provider.is_indexed() is True

    result = provider.search("hello")

    assert len(result.chunks) > 0
    assert result.tokens_used > 0

    # Should find main.py content
    found_hello = any("hello" in c['content'].lower() for c in result.chunks)
    assert found_hello


def test_incremental_update_removes_old_version(provider):
    """Incremental update replaces old file version."""
    # Index v1
    files = {"test.py": "def old_function():\n    pass\n"}
    provider.index_files(files)

    result = provider.search("old_function")
    assert len(result.chunks) > 0

    # Update to v2
    files["test.py"] = "def new_function():\n    pass\n"
    provider.index_files(files)

    # Search should find new, not old
    result = provider.search("new_function")
    assert len(result.chunks) > 0

    result_old = provider.search("old_function")
    assert len(result_old.chunks) == 0


def test_handles_file_deletion(provider):
    """Index update removes deleted files."""
    # Index two files
    files = {
        "keep.py": "def keep_this():\n    pass\n",
        "delete.py": "def delete_this():\n    pass\n"
    }
    provider.index_files(files)

    # Search finds both
    result = provider.search("keep_this")
    assert len(result.chunks) > 0
    result = provider.search("delete_this")
    assert len(result.chunks) > 0

    # Update index without delete.py
    files_updated = {"keep.py": "def keep_this():\n    pass\n"}
    provider.index_files(files_updated)

    # Should still find keep.py
    result = provider.search("keep_this")
    assert len(result.chunks) > 0

    # Should NOT find delete.py
    result = provider.search("delete_this")
    assert len(result.chunks) == 0


def test_handles_nasty_filenames(provider):
    """Handles special characters in filenames."""
    nasty_files = {
        "space in name.py": "print('space')",
        "dir/with/forward.py": "print('forward')",
        "weird'quote.py": "print('quote')",
    }

    # Should index without crashing
    provider.index_files(nasty_files)

    # Should retrieve file with spaces
    result = provider.search("space", max_tokens=1000)
    assert len(result.chunks) > 0


def test_security_prevents_path_traversal(provider, tmp_path):
    """Prevents indexing files outside project root."""
    # Create file outside project root
    outside_file = tmp_path.parent / "secret.txt"
    outside_file.write_text("secret data")

    # Attempt path traversal
    nasty_input = {"../secret.txt": "secret content"}

    # Should not crash, should skip file
    provider.index_files(nasty_input)

    # Should not find secret content
    result = provider.search("secret")
    assert len(result.chunks) == 0


def test_respects_token_limit(provider):
    """Search respects max_tokens parameter."""
    # Create large file
    large_content = "\n".join([f"line {i} with some content here" for i in range(1000)])
    files = {"large.py": large_content}

    provider.index_files(files)

    # Search with small token limit
    result = provider.search("line", max_tokens=100)

    # Should respect token limit
    assert result.tokens_used <= 100
    # Should hit limit
    assert result.limit_hit == 'token_limit'


def test_clear_index_removes_all_data(provider):
    """clear_index() removes all indexed data."""
    files = {"test.py": "def foo():\n    pass\n"}
    provider.index_files(files)

    assert provider.is_indexed() is True

    provider.clear_index()

    assert provider.is_indexed() is False

    result = provider.search("foo")
    assert len(result.chunks) == 0
