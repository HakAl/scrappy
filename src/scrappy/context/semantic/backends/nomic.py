"""
Nomic embedding backend using gpt4all.

Optional backend, requires: pip install scrappy[nomic]
Provides high-quality embeddings optimized for semantic search.

Model: nomic-embed-text-v1.5 (768 dimensions, 2048 context window)
"""
import contextlib
import logging
import os
import sys
import threading
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from gpt4all import Embed4All

logger = logging.getLogger(__name__)

# Module-level cached model (singleton pattern)
_CACHED_MODEL: Optional["Embed4All"] = None
_MODEL_LOCK = threading.Lock()


@contextlib.contextmanager
def _suppress_native_stderr():
    """
    Suppress stderr at the file descriptor level.

    This catches native C/C++ output that Python's sys.stderr redirect misses,
    like gpt4all's CUDA DLL loading warnings on Windows.
    """
    # Save the real stderr fd
    stderr_fd = sys.stderr.fileno()
    saved_stderr_fd = os.dup(stderr_fd)

    try:
        # Open devnull and redirect stderr fd to it
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, stderr_fd)
        os.close(devnull)
        yield
    finally:
        # Restore stderr fd
        os.dup2(saved_stderr_fd, stderr_fd)
        os.close(saved_stderr_fd)


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
            # Suppress native stderr during import/init to hide CUDA DLL warnings
            with _suppress_native_stderr():
                from gpt4all import Embed4All
                # Must explicitly specify the nomic model - default is all-MiniLM-L6-v2 (384 dims)
                # Full filename required: nomic-embed-text-v1.5.f16.gguf
                model_name = "nomic-embed-text-v1.5.f16.gguf"
                logger.debug(f"Initializing Nomic Embed model via gpt4all: {model_name}")
                _CACHED_MODEL = Embed4All(model_name=model_name, device="cpu")
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
        if not texts:
            return []

        model = self._ensure_model()

        # Handle empty strings by replacing with placeholder
        # (empty strings can cause dimension issues)
        processed_texts = [t if t.strip() else " " for t in texts]

        # gpt4all.Embed4All.embed() accepts a list and returns list of lists
        # Explicitly set dimensionality=768 to ensure consistent dimensions
        # and use truncate mode to avoid chunking that could affect dimensions
        embeddings = model.embed(
            processed_texts,
            dimensionality=768,
            long_text_mode="truncate",
        )

        # Validate dimensions - all embeddings must be exactly 768
        expected_dims = 768
        validated = []
        for i, emb in enumerate(embeddings):
            if len(emb) != expected_dims:
                logger.warning(
                    f"Embedding {i} has {len(emb)} dims, expected {expected_dims}. "
                    "Padding/truncating to match."
                )
                if len(emb) < expected_dims:
                    # Pad with zeros
                    emb = emb + [0.0] * (expected_dims - len(emb))
                else:
                    # Truncate
                    emb = emb[:expected_dims]
            validated.append(emb)

        return validated

    def ndims(self) -> int:
        """
        Return the dimensionality of the embeddings.

        Returns:
            768 (dimensions of nomic-embed-text-v1.5)
        """
        return 768
