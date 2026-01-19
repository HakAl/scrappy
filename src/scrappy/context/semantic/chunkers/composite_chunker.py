"""
Composite code chunker that routes to language-specific strategies.

Provides a unified interface for chunking code across multiple languages,
with automatic fallback to line-based chunking for unsupported languages.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set

from ...protocols import CodeChunk, ChunkingStrategyProtocol
from ...code_chunker import SemanticCodeChunker
from .python_chunker import PythonASTChunker

logger = logging.getLogger(__name__)


class CompositeCodeChunker:
    """
    Routes files to language-specific chunkers.

    Falls back to line-based chunking for unsupported languages.
    Implements CodeChunkerProtocol for compatibility with existing code.

    Strategy pattern: each language has its own chunking strategy,
    and this class routes based on file extension.

    Example:
        chunker = CompositeCodeChunker()
        chunks = chunker.chunk("example.py", python_code)  # Uses AST
        chunks = chunker.chunk("example.js", js_code)      # Uses fallback
    """

    def __init__(
        self,
        strategies: Optional[Dict[str, ChunkingStrategyProtocol]] = None,
        fallback_chunk_size: int = 60,
        fallback_overlap: int = 15,
    ):
        """
        Initialize composite chunker.

        Args:
            strategies: Dict mapping language names to chunking strategies.
                       If None, uses default strategies.
            fallback_chunk_size: Lines per chunk for fallback chunker
            fallback_overlap: Overlap lines for fallback chunker
        """
        self._strategies = strategies or self._default_strategies()
        self._fallback = SemanticCodeChunker(
            chunk_size=fallback_chunk_size,
            overlap=fallback_overlap,
        )

        # Build extension -> strategy mapping
        self._ext_map: Dict[str, ChunkingStrategyProtocol] = {}
        for strategy in self._strategies.values():
            for ext in strategy.supported_extensions:
                self._ext_map[ext.lower()] = strategy

    def _default_strategies(self) -> Dict[str, ChunkingStrategyProtocol]:
        """
        Create default language strategies.

        Returns:
            Dict mapping language names to chunking strategies
        """
        return {
            "python": PythonASTChunker(),
            # Future: "javascript": JavaScriptChunker(),
            # Future: "typescript": TypeScriptChunker(),
            # Future: "go": GoChunker(),
        }

    def chunk(self, file_path: str, content: str) -> List[CodeChunk]:
        """
        Chunk code content using appropriate strategy.

        Implements CodeChunkerProtocol.

        Args:
            file_path: Path to the file being chunked
            content: File content to chunk

        Returns:
            List of CodeChunk objects with line ranges
        """
        if not content.strip():
            return []

        ext = Path(file_path).suffix.lower()

        if ext in self._ext_map:
            strategy = self._ext_map[ext]
            logger.debug(f"Using {type(strategy).__name__} for {file_path}")
            # Note: ChunkingStrategyProtocol has (content, file_path) order
            return strategy.chunk(content, file_path)

        # Fallback to line-based chunking
        logger.debug(f"Using fallback chunker for {file_path} (ext: {ext})")
        chunks = self._fallback.chunk(file_path, content)

        # Add metadata to fallback chunks
        for chunk in chunks:
            if chunk.chunk_type is None:
                chunk.chunk_type = "block"

        return chunks

    def supports_language(self, file_extension: str) -> bool:
        """
        Check if chunker has language-specific support for this extension.

        Args:
            file_extension: File extension (e.g., ".py", ".js")

        Returns:
            True if AST-aware chunking is available
        """
        return file_extension.lower() in self._ext_map

    def get_supported_extensions(self) -> Set[str]:
        """
        Get all extensions with AST-aware chunking support.

        Returns:
            Set of supported extensions
        """
        return set(self._ext_map.keys())

    def add_strategy(
        self,
        language_name: str,
        strategy: ChunkingStrategyProtocol,
    ) -> None:
        """
        Add or replace a language strategy.

        Args:
            language_name: Name of the language (e.g., "python")
            strategy: Chunking strategy for the language
        """
        self._strategies[language_name] = strategy

        # Update extension map
        for ext in strategy.supported_extensions:
            self._ext_map[ext.lower()] = strategy
