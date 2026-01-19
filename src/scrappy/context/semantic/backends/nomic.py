"""
Nomic embedding backend using gpt4all.

Optional backend, requires: pip install scrappy[nomic]
Provides high-quality embeddings optimized for semantic search.

Model: nomic-embed-text-v1.5 (768 dimensions, 2048 context window)
"""
import logging
import threading
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from gpt4all import Embed4All

logger = logging.getLogger(__name__)

# Module-level cached model (singleton pattern)
_CACHED_MODEL: Optional["Embed4All"] = None
_MODEL_LOCK = threading.Lock()


def _get_or_create_model() -> "Embed4All":
    """
    Get cached Embed4All model or create if not exists.

    Thread-safe via double-checked locking pattern.

    Returns:
        Cached Embed4All instance
    """
    global _CACHED_MODEL
    # Fast path: already initialized
    if _CACHED_MODEL is not None:
        return _CACHED_MODEL
    # Slow path: acquire lock and initialize
    with _MODEL_LOCK:
        # Double-check after acquiring lock
        if _CACHED_MODEL is None:
            from gpt4all import Embed4All
            logger.debug("Initializing Nomic Embed model via gpt4all")
            _CACHED_MODEL = Embed4All()
            logger.debug("Nomic Embed model initialized")
        return _CACHED_MODEL


class NomicEmbeddingFunction:
    """
    Nomic embedding function using gpt4all.

    Implements EmbeddingFunctionProtocol for the registry.

    Model: nomic-embed-text-v1.5
    - 768 dimensions
    - 2048 token context window
    - ~274MB model size
    - Runs locally (no API calls)
    - Highest quality among local options

    Thread Safety:
        - Model is cached at module level (singleton)
        - Multiple instances share the same model
    """

    name: str = "nomic-embed-text-v1.5"

    def __init__(self) -> None:
        """Initialize embedding function with lazy model loading."""
        self._model: Optional["Embed4All"] = None

    def _ensure_model(self) -> "Embed4All":
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
        # gpt4all.Embed4All.embed() accepts a list and returns list of lists
        embeddings = model.embed(texts)
        return embeddings

    def ndims(self) -> int:
        """
        Return the dimensionality of the embeddings.

        Returns:
            768 (dimensions of nomic-embed-text-v1.5)
        """
        return 768
