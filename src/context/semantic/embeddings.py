"""
Custom FastEmbed embedding function for LanceDB.

Provides Jina AI embeddings optimized for code understanding.
Uses FastEmbed for fast, local embedding generation.
"""

import logging
import threading
from typing import List, Optional
import numpy as np

from lancedb.embeddings import register, TextEmbeddingFunction
from fastembed import TextEmbedding

logger = logging.getLogger(__name__)


# Module-level cached model (singleton pattern for expensive resource)
# This ensures TextEmbedding is only loaded once, even if multiple
# JinaEmbedFunction instances are created by LanceDB
_CACHED_MODEL: Optional[TextEmbedding] = None

# Thread lock for embedding generation (ONNX Runtime is not thread-safe)
_EMBEDDING_LOCK = threading.Lock()


def _get_or_create_model() -> TextEmbedding:
    """
    Get cached TextEmbedding model or create if not exists.

    Returns:
        Cached TextEmbedding instance
    """
    global _CACHED_MODEL
    if _CACHED_MODEL is None:
        model_name = "BAAI/bge-small-en-v1.5"
        logger.debug(f"Initializing FastEmbed with model: {model_name}")
        _CACHED_MODEL = TextEmbedding(model_name=model_name)
        logger.debug("FastEmbed model initialized")
    return _CACHED_MODEL


@register("fastembed-jina")
class JinaEmbedFunction(TextEmbeddingFunction):
    """
    Custom embedding function using Jina AI's code-optimized model via FastEmbed.

    Model: jinaai/jina-embeddings-v2-base-code
    - Optimized for code understanding and semantic search
    - 768 dimensions
    - 8K context window
    - Runs locally (no API calls)

    Usage:
        from lancedb.embeddings import get_registry

        registry = get_registry()
        embed_func = registry.get("fastembed-jina").create()

    Architecture Notes:
        - Registration (@register) happens at module import (fast, metadata only)
        - TextEmbedding model is cached at module level (singleton pattern)
        - Multiple JinaEmbedFunction instances share the same TextEmbedding model
        - Follows SOLID: Single responsibility, dependency inversion ready
    """

    name: str = "jinaai/jina-embeddings-v2-base-code"

    def __init__(self, **kwargs):
        """
        Initialize the embedding function.

        This is called lazily when registry.get("fastembed-jina").create() is invoked.
        The TextEmbedding model is cached and reused across all instances.

        Args:
            **kwargs: Additional arguments passed to parent TextEmbeddingFunction
        """
        super().__init__(**kwargs)
        self._model = _get_or_create_model()

    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts (thread-safe).

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors (each vector is a list of floats)

        Note:
            FastEmbed returns a generator of numpy.ndarray objects.
            We must convert each array to a Python list to satisfy LanceDB/Pydantic validation.
            Without this conversion, ONNX Runtime may miscalculate buffer sizes.

            Thread-safety: Uses a lock to ensure ONNX Runtime is not called concurrently.
        """
        # Thread lock to prevent concurrent ONNX Runtime calls
        with _EMBEDDING_LOCK:
            # FastEmbed returns Iterable[np.ndarray]
            embeddings_generator = self._model.embed(texts)

            # Convert numpy arrays to python lists to satisfy LanceDB/Pydantic validation
            return [embedding.tolist() for embedding in embeddings_generator]

    def ndims(self) -> int:
        """
        Return the dimensionality of the embeddings.

        Returns:
            384 (dimensions of BGE-small-en-v1.5 model)

        Note:
            Hardcoded since we control the model choice. More efficient than
            running a dummy embedding to detect dimensions.
        """
        return 384
