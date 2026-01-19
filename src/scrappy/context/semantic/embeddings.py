"""
Legacy embedding function module.

This module provides backward compatibility with code that imports
EmbedFunction from this location. The actual implementation has
moved to the backends module.

For new code, use the registry:
    from scrappy.context.semantic import get_embedding_registry
    embedder = get_embedding_registry().create_best_available()
"""

# Re-export for backward compatibility
from scrappy.context.semantic.backends.bge_small import (
    BgeSmallEmbeddingFunction as EmbedFunction,
)

__all__ = ["EmbedFunction"]
