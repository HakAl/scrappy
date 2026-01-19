"""
Jina Code embedding backend using sentence-transformers.

Optional backend, requires: pip install scrappy[jina]
Provides code-optimized embeddings with large context window.

Model: jinaai/jina-embeddings-v2-base-code (768 dimensions, 8192 context window)
"""
import logging
import threading
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Module-level cached model (singleton pattern)
_CACHED_MODEL: Optional["SentenceTransformer"] = None
_MODEL_LOCK = threading.Lock()

MODEL_NAME = "jinaai/jina-embeddings-v2-base-code"


def _get_or_create_model() -> "SentenceTransformer":
    """
    Get cached SentenceTransformer model or create if not exists.

    Thread-safe via double-checked locking pattern.

    Returns:
        Cached SentenceTransformer instance
    """
    global _CACHED_MODEL
    # Fast path: already initialized
    if _CACHED_MODEL is not None:
        return _CACHED_MODEL
    # Slow path: acquire lock and initialize
    with _MODEL_LOCK:
        # Double-check after acquiring lock
        if _CACHED_MODEL is None:
            from sentence_transformers import SentenceTransformer
            logger.debug(f"Initializing Jina Code model: {MODEL_NAME}")
            # trust_remote_code=True required for Jina models
            _CACHED_MODEL = SentenceTransformer(MODEL_NAME, trust_remote_code=True)
            logger.debug("Jina Code model initialized")
        return _CACHED_MODEL


class JinaEmbeddingFunction:
    """
    Jina Code embedding function using sentence-transformers.

    Implements EmbeddingFunctionProtocol for the registry.

    Model: jinaai/jina-embeddings-v2-base-code
    - 768 dimensions
    - 8192 token context window (largest among local options)
    - ~300MB model size
    - Runs locally (no API calls)
    - Optimized for code understanding

    Thread Safety:
        - Model is cached at module level (singleton)
        - Multiple instances share the same model
    """

    name: str = MODEL_NAME

    def __init__(self) -> None:
        """Initialize embedding function with lazy model loading."""
        self._model: Optional["SentenceTransformer"] = None

    def _ensure_model(self) -> "SentenceTransformer":
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
        # SentenceTransformer.encode() returns numpy array
        embeddings = model.encode(texts, convert_to_numpy=True)
        # Convert to list of lists for compatibility
        return [emb.tolist() for emb in embeddings]

    def ndims(self) -> int:
        """
        Return the dimensionality of the embeddings.

        Returns:
            768 (dimensions of jina-embeddings-v2-base-code)
        """
        return 768
