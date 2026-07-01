"""
Test that semantic search fixtures work correctly.

This ensures that tests don't load real FastEmbed models or LanceDB databases.
"""

from helpers import MockSemanticSearch, MockSemanticInitializer


def test_mock_semantic_search_basic():
    """Test basic MockSemanticSearch operations."""
    search = MockSemanticSearch()

    assert not search.is_indexed()

    search.index_files({'test.py': 'def foo(): pass'})

    assert search.is_indexed()
    assert len(search.get_index_calls()) == 1

    search.set_search_results([
        {'path': 'test.py', 'lines': (1, 1), 'content': 'def foo():', 'score': 0.9}
    ])

    result = search.search("find foo")

    assert len(result['chunks']) == 1
    assert result['chunks'][0]['path'] == 'test.py'
    assert len(search.get_search_calls()) == 1


def test_mock_semantic_search_max_results():
    """Test MockSemanticSearch respects max_results."""
    search = MockSemanticSearch()

    search.set_search_results([
        {'path': 'a.py', 'content': 'test', 'score': 0.9},
        {'path': 'b.py', 'content': 'test', 'score': 0.8},
        {'path': 'c.py', 'content': 'test', 'score': 0.7},
    ])

    result = search.search("test", max_results=2)

    assert len(result['chunks']) == 2
    assert result['chunks'][0]['path'] == 'a.py'
    assert result['chunks'][1]['path'] == 'b.py'


def test_mock_semantic_search_clear():
    """Test MockSemanticSearch clear_index."""
    search = MockSemanticSearch()

    search.index_files({'test.py': 'content'})
    assert search.is_indexed()

    search.clear_index()
    assert not search.is_indexed()
    assert len(search.get_index_calls()) == 0


def test_mock_semantic_initializer_auto_complete():
    """Test MockSemanticInitializer with auto_complete=True."""
    initializer = MockSemanticInitializer(auto_complete=True)

    assert initializer.is_complete()
    assert not initializer.is_running()

    initializer.start()

    assert initializer.is_complete()
    assert not initializer.is_running()
    assert initializer.wait_for_completion()


def test_mock_semantic_initializer_with_result():
    """Test MockSemanticInitializer returns preset result."""
    mock_search = MockSemanticSearch()
    initializer = MockSemanticInitializer(result=mock_search)

    initializer.start()

    result = initializer.get_result()
    assert result is mock_search


def test_mock_semantic_initializer_manual_complete():
    """Test MockSemanticInitializer with manual completion."""
    initializer = MockSemanticInitializer(auto_complete=False)

    assert not initializer.is_complete()
    assert not initializer.is_running()

    initializer.start()

    assert not initializer.is_complete()
    assert initializer.is_running()

    initializer.set_complete(True)

    assert initializer.is_complete()
    assert not initializer.is_running()


def test_mock_semantic_initializer_with_error():
    """Test MockSemanticInitializer with error."""
    error = ImportError("FastEmbed not available")
    initializer = MockSemanticInitializer(error=error)

    assert initializer.get_error() is error
    assert not initializer.wait_for_completion()


def test_mock_semantic_initializer_status():
    """Test MockSemanticInitializer status messages."""
    initializer = MockSemanticInitializer(auto_complete=False)

    initializer.set_status("Loading model...")
    assert initializer.get_status() == "Loading model..."

    initializer.set_complete()
    assert initializer.get_status() == "Complete"




def test_fixture_mock_semantic_initializer(mock_semantic_initializer):
    """Test pytest fixture for semantic initializer."""
    assert mock_semantic_initializer is not None
    assert mock_semantic_initializer.is_complete() is True
    assert mock_semantic_initializer.get_status() == "Complete"
