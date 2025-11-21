"""
Custom FastEmbed embedding function for LanceDB.

Provides Jina AI embeddings optimized for code understanding.
Uses FastEmbed for fast, local embedding generation.
"""

import logging
from typing import List

from lancedb.embeddings import register, TextEmbeddingFunction
from fastembed import TextEmbedding

logger = logging.getLogger(__name__)


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
        - TextEmbedding model is created in __init__ (lazy, called by .create())
        - Follows SOLID: Single responsibility, dependency inversion ready
    """

    name: str = "jinaai/jina-embeddings-v2-base-code"

    def __init__(self, **kwargs):
        """
        Initialize the embedding function.

        This is called lazily when registry.get("fastembed-jina").create() is invoked.
        The TextEmbedding model is loaded here (10-30s on first use for model download).

        Args:
            **kwargs: Additional arguments passed to parent TextEmbeddingFunction
        """
        super().__init__(**kwargs)
        logger.debug(f"Initializing FastEmbed with model: {self.name}")
        self._model = TextEmbedding(model_name=self.name)
        logger.debug("FastEmbed model initialized")

    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors (each vector is a list of floats)

        Note:
            FastEmbed returns a generator, so we convert to list for LanceDB compatibility.
        """
        return list(self._model.embed(texts))

    def ndims(self) -> int:
        """
        Return the dimensionality of the embeddings.

        Returns:
            768 (dimensions of Jina v2 base code model)

        Note:
            Hardcoded since we control the model choice. More efficient than
            running a dummy embedding to detect dimensions.
        """
        return 768
