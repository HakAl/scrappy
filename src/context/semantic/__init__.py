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
    - SemanticFileCollector: Git-aware file collection with size limits
    - IndexFilterConfig: Configuration for file filtering

Usage:
    from context.semantic import LanceDBSearchProvider, SemanticFileCollector

    collector = SemanticFileCollector(project_path)
    files = collector.collect_files()

    provider = LanceDBSearchProvider(project_path, chunker)
    provider.index_files(files)
    results = provider.search("authentication logic")
"""

from .embeddings import JinaEmbedFunction
from .provider import LanceDBSearchProvider
from .initializer import SemanticSearchInitializer, NullInitializer
from .file_collector import SemanticFileCollector, IndexFilterConfig

__all__ = [
    "JinaEmbedFunction",
    "LanceDBSearchProvider",
    "SemanticSearchInitializer",
    "NullInitializer",
    "SemanticFileCollector",
    "IndexFilterConfig",
]
