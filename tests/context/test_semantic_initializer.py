"""
Tests for semantic search background initializer.

Tests verify that:
- Background initialization works without blocking
- Progress can be tracked
- Results are available after completion
- Errors are handled gracefully
- Timeout works correctly
"""

import time
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from src.context.semantic.initializer import SemanticSearchInitializer, NullInitializer


def test_null_initializer_always_complete():
    """NullInitializer should always be complete and return None."""
    initializer = NullInitializer()

    assert initializer.is_complete()
    assert not initializer.is_running()
    assert initializer.get_result() is None
    assert initializer.get_error() is None
    assert initializer.get_status() == "Not available"


def test_null_initializer_wait_returns_false():
    """NullInitializer wait should return False (no result)."""
    initializer = NullInitializer()
    assert not initializer.wait_for_completion(timeout=0.1)


def test_semantic_initializer_starts_non_blocking():
    """Semantic initializer should start without blocking."""
    initializer = SemanticSearchInitializer(Path("."))

    start_time = time.time()
    initializer.start()
    duration = time.time() - start_time

    # Should return almost immediately (< 100ms)
    assert duration < 0.1
    assert initializer.is_running() or initializer.is_complete()


def test_semantic_initializer_completes_eventually():
    """Semantic initializer should eventually complete."""
    initializer = SemanticSearchInitializer(Path("."))

    initializer.start()

    # Wait for completion with reasonable timeout
    success = initializer.wait_for_completion(timeout=60.0)

    # Should complete (either success or graceful failure)
    assert initializer.is_complete()
    assert not initializer.is_running()


def test_semantic_initializer_status_updates():
    """Status should change from initial to complete."""
    initializer = SemanticSearchInitializer(Path("."))

    initial_status = initializer.get_status()
    assert initial_status == "Not started"

    initializer.start()

    # Status should change while running
    time.sleep(0.1)
    running_status = initializer.get_status()
    assert running_status != "Not started"

    # Wait for completion
    initializer.wait_for_completion(timeout=60.0)

    # Status should indicate completion
    final_status = initializer.get_status()
    assert final_status in ["Complete", "Failed: Missing dependencies (No module named 'fastembed')", "Failed: No module named 'fastembed'"] or final_status.startswith("Failed:")


def test_semantic_initializer_cannot_start_twice():
    """Starting twice should be a no-op."""
    initializer = SemanticSearchInitializer(Path("."))

    initializer.start()
    thread1 = initializer._thread

    # Try starting again
    initializer.start()
    thread2 = initializer._thread

    # Should be the same thread
    assert thread1 is thread2


def test_semantic_initializer_result_available_after_completion():
    """Result should be available after successful completion."""
    initializer = SemanticSearchInitializer(Path("."))

    initializer.start()
    success = initializer.wait_for_completion(timeout=60.0)

    if success:
        result = initializer.get_result()
        # If successful, result should be a semantic search provider
        assert result is not None
        assert hasattr(result, 'index_files')
        assert hasattr(result, 'search')
    else:
        # If failed, error should be set
        error = initializer.get_error()
        assert error is not None


def test_semantic_initializer_handles_import_error():
    """Should handle missing dependencies gracefully."""
    initializer = SemanticSearchInitializer(Path("."))

    # Mock module import to fail (patch at import location inside thread function)
    with patch('src.context.code_chunker.SemanticCodeChunker', side_effect=ImportError("No module named 'fastembed'")):
        initializer.start()
        initializer.wait_for_completion(timeout=5.0)

        # Should complete with error
        assert initializer.is_complete()
        assert initializer.get_result() is None
        error = initializer.get_error()
        assert isinstance(error, ImportError)
        assert "fastembed" in str(error)


def test_semantic_initializer_handles_generic_error():
    """Should handle unexpected errors gracefully."""
    initializer = SemanticSearchInitializer(Path("."))

    # Mock to raise unexpected error
    with patch('src.context.code_chunker.SemanticCodeChunker', side_effect=RuntimeError("Unexpected error")):
        initializer.start()
        initializer.wait_for_completion(timeout=5.0)

        # Should complete with error
        assert initializer.is_complete()
        assert initializer.get_result() is None
        error = initializer.get_error()
        assert isinstance(error, RuntimeError)


def test_semantic_initializer_timeout_behavior():
    """Wait with timeout should return False if not complete."""
    initializer = SemanticSearchInitializer(Path("."))

    # Don't start initialization
    result = initializer.wait_for_completion(timeout=0.1)

    # Should timeout/fail since not started
    assert not result


def test_semantic_initializer_thread_safety():
    """Accessing status from multiple locations should be thread-safe."""
    initializer = SemanticSearchInitializer(Path("."))

    initializer.start()

    # Poll status multiple times while initializing
    statuses = []
    for _ in range(10):
        statuses.append(initializer.get_status())
        statuses.append(initializer.is_complete())
        statuses.append(initializer.is_running())
        time.sleep(0.01)

    # Should not crash or raise exceptions
    initializer.wait_for_completion(timeout=60.0)
    assert initializer.is_complete()
