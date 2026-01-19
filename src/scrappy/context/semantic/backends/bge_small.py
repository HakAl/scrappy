"""
BGE-small embedding backend using FastEmbed.

This is the default backend, always available in the base install.
Provides fast, lightweight local embeddings optimized for code search.

Model: BAAI/bge-small-en-v1.5 (384 dimensions, 512 context window)
"""
import logging
import threading
from typing import List, Optional, TYPE_CHECKING

from lancedb.embeddings import register, TextEmbeddingFunction
from fastembed import TextEmbedding

if TYPE_CHECKING:
    pass  # All types imported directly

logger = logging.getLogger(__name__)

# Module-level cached model (singleton pattern for expensive resource)
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
            # BAAI/bge-small-en-v1.5 automatically uses the quantized variant
            model_name = "BAAI/bge-small-en-v1.5"
            logger.debug(f"Initializing FastEmbed with model: {model_name}")
            _CACHED_MODEL = TextEmbedding(model_name=model_name)
            logger.debug("FastEmbed model initialized")
        return _CACHED_MODEL


@register("fastembed-embed")
class BgeSmallEmbeddingFunction(TextEmbeddingFunction):
    """
    BGE-small embedding function using FastEmbed.

    Implements EmbeddingFunctionProtocol for the registry.
    Also registered with LanceDB for backward compatibility.

    Model: BAAI/bge-small-en-v1.5
    - 384 dimensions
    - 512 token context window
    - ~33MB model size
    - Runs locally (no API calls)

    Thread Safety:
        - Model is cached at module level (singleton)
        - Multiple instances share the same model
        - ONNX Runtime is thread-safe by default
    """

    name: str = "BAAI/bge-small-en-v1.5"

    def __init__(self, **kwargs) -> None:
        """Initialize embedding function with lazy model loading."""
        super().__init__(**kwargs)
        self._model: Optional[TextEmbedding] = None

    def _ensure_model(self) -> TextEmbedding:
        """Ensure model is loaded (lazy initialization)."""
        if self._model is None:
            self._model = _get_or_create_model()
        return self._model

    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors (each vector is a list of floats)
        """
        model = self._ensure_model()
        # Larger batches = better CPU utilization
        embeddings = list(model.embed(texts, batch_size=256))
        # Convert numpy arrays to python lists for compatibility
        return [emb.tolist() for emb in embeddings]

    def ndims(self) -> int:
        """
        Return the dimensionality of the embeddings.

        Returns:
            384 (dimensions of BGE-small-en-v1.5)
        """
        return 384


# For backward compatibility with existing code that imports EmbedFunction
EmbedFunction = BgeSmallEmbeddingFunction
