"""
Code chunking for semantic search.

Implements CodeChunkerProtocol with semantic overlap strategy.
"""

from typing import List
from .protocols import CodeChunk, CodeChunkerProtocol


class SemanticCodeChunker:
    """
    Chunks code with overlapping lines for better context.

    Implements CodeChunkerProtocol.

    Design decisions:
    - Overlap prevents context loss at chunk boundaries
    - Line-based chunking (not token-based) for simplicity
    - Configurable chunk size for different use cases
    """

    def __init__(
        self,
        chunk_size: int = 250,
        overlap: int = 30
    ):
        """
        Initialize chunker (NO I/O, just configuration).

        Args:
            chunk_size: Lines per chunk
            overlap: Overlapping lines between chunks

        Raises:
            ValueError: If overlap >= chunk_size
        """
        if overlap >= chunk_size:
            raise ValueError(f"Overlap ({overlap}) must be less than chunk_size ({chunk_size})")

        self._chunk_size = chunk_size
        self._overlap = overlap

    def chunk(self, file_path: str, content: str) -> List[CodeChunk]:
        """
        Chunk content with overlap.

        Example with chunk_size=10, overlap=3:
        - Chunk 1: lines 1-10
        - Chunk 2: lines 8-17 (3 line overlap)
        - Chunk 3: lines 15-24 (3 line overlap)

        Args:
            file_path: Path to file (for reference, not used)
            content: File content to chunk

        Returns:
            List of CodeChunk objects with line ranges
        """
        if not content.strip():
            return []

        lines = content.splitlines()
        chunks: List[CodeChunk] = []

        i = 0
        while i < len(lines):
            chunk_start = i + 1  # 1-indexed for human readability
            chunk_end = min(i + self._chunk_size, len(lines))

            chunks.append(CodeChunk(
                start_line=chunk_start,
                end_line=chunk_end,
                file_path=file_path
            ))

            # Move forward by (chunk_size - overlap)
            step = self._chunk_size - self._overlap
            i += step

        return chunks
