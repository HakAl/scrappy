"""
Semantic search components for codebase context.

This module provides vector-based semantic search capabilities using
LanceDB for vector storage and FastEmbed for embeddings.

Key Components:
    - JinaEmbedFunction: Custom FastEmbed embedding function for code
    - LanceDBSearchProvider: Vector + full-text hybrid search provider
    - SemanticCodeChunker: Intelligent code chunking for embeddings
    - SemanticSearchInitializer: Background initializer for heavy dependencies
    - NullInitializer: No-op initializer for testing

Usage:
    from context.semantic import LanceDBSearchProvider

    provider = LanceDBSearchProvider(project_path, chunker)
    provider.index_files(files)
    results = provider.search("authentication logic")
"""

from .embeddings import JinaEmbedFunction
from .provider import LanceDBSearchProvider
from .initializer import SemanticSearchInitializer, NullInitializer

__all__ = [
    "JinaEmbedFunction",
    "LanceDBSearchProvider",
    "SemanticSearchInitializer",
    "NullInitializer",
]
