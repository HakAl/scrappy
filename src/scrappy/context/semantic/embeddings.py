"""
Custom FastEmbed embedding function for LanceDB.

Provides embeddings optimized for code understanding.
Uses FastEmbed for fast, local embedding generation.
"""
import logging
import threading
from typing import List, Optional

from lancedb.embeddings import register, TextEmbeddingFunction
from fastembed import TextEmbedding

logger = logging.getLogger(__name__)

# Module-level cached model (singleton pattern for expensive resource)
# This ensures TextEmbedding is only loaded once, even if multiple
# EmbedFunction instances are created by LanceDB
_CACHED_MODEL: Optional[TextEmbedding] = None
_MODEL_LOCK = threading.Lock()


def _get_or_create_model() -> TextEmbedding:
    """
    Get cached TextEmbedding model or create if not exists.

    Thread-safe via double-checked locking pattern.

    Returns:
        Cached TextEmbedding instance
    """
    global _CACHED_MODEL
    # Fast path: already initialized
    if _CACHED_MODEL is not None:
        return _CACHED_MODEL
    # Slow path: acquire lock and initialize
    with _MODEL_LOCK:
        # Double-check after acquiring lock
        if _CACHED_MODEL is None:
            # BAAI/bge-small-en-v1.5 automatically uses the quantized variant (qdrant/bge-small-en-v1.5-onnx-q)
            # This gives us 2-3x speedup with 99% quality retention
            model_name = "BAAI/bge-small-en-v1.5"
            logger.debug(f"Initializing FastEmbed with model: {model_name}")
            _CACHED_MODEL = TextEmbedding(
                model_name=model_name,
            )
            logger.debug("FastEmbed model initialized")
        return _CACHED_MODEL


@register("fastembed-embed")
class EmbedFunction(TextEmbeddingFunction):
    """
    Custom embedding function using model via FastEmbed.

    Model: BAAI/bge-small-en-v1.5
    - Optimized for code understanding and semantic search
    - 384 dimensions
    - 8K context window
    - Runs locally (no API calls)

    Usage:
        from lancedb.embeddings import get_registry

        registry = get_registry()
        embed_func = registry.get("fastembed-embed").create()

    Architecture Notes:
        - Registration (@register) happens at module import (fast, metadata only)
        - TextEmbedding model is cached at module level (singleton pattern)
        - Multiple EmbedFunction instances share the same TextEmbedding model
        - Follows SOLID: Single responsibility, dependency inversion ready
    """

    name: str = "BAAI/bge-small-en-v1.5"

    def __init__(self, **kwargs):
        """
        Initialize the embedding function.

        This is called lazily when registry.get("fastembed-embed").create() is invoked.
        The TextEmbedding model is cached and reused across all instances.

        Args:
            **kwargs: Additional arguments passed to parent TextEmbeddingFunction
        """
        super().__init__(**kwargs)
        self._model = _get_or_create_model()

    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts with optimized batching.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors (each vector is a list of floats)

        Note:
            FastEmbed returns numpy arrays which must be converted to lists
            for LanceDB/Pydantic validation.

            ONNX Runtime is thread-safe by default, no lock needed.
        """
        # Materialize embeddings with explicit batch size for better throughput
        embeddings = list(self._model.embed(
            texts,
            batch_size=256,  # Larger batches = better CPU utilization
        ))

        # Convert numpy arrays to python lists for LanceDB compatibility
        return [emb.tolist() for emb in embeddings]

    def ndims(self) -> int:
        """
        Return the dimensionality of the embeddings.

        Returns:
            384 (dimensions of BGE-small-en-v1.5 and quantized variants)

        Note:
            Hardcoded since we control the model choice. More efficient than
            running a dummy embedding to detect dimensions.
        """
        return 384
