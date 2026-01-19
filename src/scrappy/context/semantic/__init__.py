"""
Semantic search components for codebase context.

This module provides vector-based semantic search capabilities using
LanceDB for vector storage and pluggable embedding backends.

Key Components:
    - EmbeddingRegistry: Registry for pluggable embedding backends
    - EmbeddingModelId: Supported embedding model identifiers
    - LanceDBSearchProvider: Vector + full-text hybrid search provider
    - SemanticCodeChunker: Intelligent code chunking for embeddings
    - SemanticSearchInitializer: Background initializer for heavy dependencies
    - NullInitializer: No-op initializer for testing
    - SemanticFileCollector: File collection with size limits
    - IndexFilterConfig: Configuration for file filtering

Embedding Backends:
    - BGE-small (default): Fast, lightweight (384 dims, 512 context)
    - Nomic: High quality (768 dims, 2048 context) - pip install scrappy[nomic]
    - Jina Code: Code-optimized (768 dims, 8192 context) - pip install scrappy[jina]

Usage:
    from context.semantic import LanceDBSearchProvider, SemanticFileCollector
    from context.semantic import get_embedding_registry, EmbeddingModelId

    # Auto-detect best available embedding model
    registry = get_embedding_registry()
    embedder = registry.create_best_available()

    collector = SemanticFileCollector(project_path)
    files = collector.collect_files()

    provider = LanceDBSearchProvider(project_path, chunker, embedding_function=embedder)
    provider.index_files(files)
    results = provider.search("authentication logic")
"""

from .embeddings import EmbedFunction
from .provider import LanceDBSearchProvider
from .initializer import SemanticSearchInitializer, NullInitializer
from .file_collector import SemanticFileCollector, IndexFilterConfig
from .file_prioritizer import DefaultFilePrioritizer, FilePriorityConfig
from .ranker import DefaultResultRanker, PassthroughRanker
from .registry import (
    EmbeddingRegistry,
    EmbeddingModelId,
    EmbeddingModelInfo,
    get_embedding_registry,
)

__all__ = [
    # Registry
    "EmbeddingRegistry",
    "EmbeddingModelId",
    "EmbeddingModelInfo",
    "get_embedding_registry",
    # Legacy
    "EmbedFunction",
    # Provider
    "LanceDBSearchProvider",
    "SemanticSearchInitializer",
    "NullInitializer",
    "SemanticFileCollector",
    "IndexFilterConfig",
    "DefaultFilePrioritizer",
    "FilePriorityConfig",
    "DefaultResultRanker",
    "PassthroughRanker",
]
