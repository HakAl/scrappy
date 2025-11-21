"""
Tests for code chunking.

Following TDD: Test behavior, not implementation.
"""

import pytest
from src.context.code_chunker import SemanticCodeChunker


def test_chunks_empty_content():
    """Chunker handles empty content gracefully."""
    chunker = SemanticCodeChunker(chunk_size=10, overlap=2)
    chunks = chunker.chunk("test.py", "")
    assert chunks == []


def test_chunks_whitespace_only():
    """Chunker handles whitespace-only content."""
    chunker = SemanticCodeChunker(chunk_size=10, overlap=2)
    chunks = chunker.chunk("test.py", "   \n\n   \n")
    assert chunks == []


def test_chunks_single_small_file():
    """Chunker creates single chunk for small files."""
    chunker = SemanticCodeChunker(chunk_size=100, overlap=3)
    content = "\n".join([f"line {i}" for i in range(10)])

    chunks = chunker.chunk("test.py", content)

    assert len(chunks) == 1
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 10


def test_chunks_with_overlap():
    """Chunker creates overlapping chunks for context."""
    chunker = SemanticCodeChunker(chunk_size=10, overlap=3)
    content = "\n".join([f"line {i}" for i in range(30)])

    chunks = chunker.chunk("test.py", content)

    # Should have multiple chunks
    assert len(chunks) >= 3

    # Verify overlap exists between most consecutive chunks
    # At least the first two chunks should have proper overlap
    for i in range(min(2, len(chunks) - 1)):
        # Next chunk should start before current ends (creating overlap)
        next_starts_before_current_ends = chunks[i + 1].start_line <= chunks[i].end_line
        assert next_starts_before_current_ends




def test_chunk_boundaries():
    """Chunker respects exact boundaries."""
    chunker = SemanticCodeChunker(chunk_size=5, overlap=1)
    content = "\n".join([f"line {i}" for i in range(1, 11)])  # 10 lines

    chunks = chunker.chunk("test.py", content)

    # First chunk should be lines 1-5
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 5

    # Second chunk should be lines 5-9 (1 line overlap)
    assert chunks[1].start_line == 5
    assert chunks[1].end_line == 9
