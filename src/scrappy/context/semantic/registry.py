"""
Embedding model registry for pluggable backends.

Tracks available embedding backends, handles priority ordering,
and instantiates embedders on demand with lazy imports.
"""
import logging
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional

from scrappy.context.protocols import EmbeddingFunctionProtocol

logger = logging.getLogger(__name__)


class EmbeddingModelId(str, Enum):
    """Supported embedding model identifiers."""
    BGE_SMALL = "bge-small"
    NOMIC = "nomic"
    JINA = "jina"


@dataclass(frozen=True)
class EmbeddingModelInfo:
    """
    Metadata for an embedding model backend.

    Attributes:
        id: Unique identifier for the model
        display_name: Human-readable name
        dimensions: Output vector dimensions
        context_window: Maximum input tokens
        priority: Lower = higher quality (used for auto-selection)
        package_name: Package to check for availability
        install_extra: pip extra name (e.g., 'nomic' for pip install scrappy[nomic])
    """
    id: EmbeddingModelId
    display_name: str
    dimensions: int
    context_window: int
    priority: int  # Lower = better quality, used for auto-selection
    package_name: str  # Package to check for availability
    install_extra: Optional[str] = None  # pip extra name


# Model specifications from the plan
MODEL_INFO: Dict[EmbeddingModelId, EmbeddingModelInfo] = {
    EmbeddingModelId.NOMIC: EmbeddingModelInfo(
        id=EmbeddingModelId.NOMIC,
        display_name="Nomic Embed",
        dimensions=768,
        context_window=2048,
        priority=1,  # Highest quality
        package_name="gpt4all",
        install_extra="nomic",
    ),
    EmbeddingModelId.JINA: EmbeddingModelInfo(
        id=EmbeddingModelId.JINA,
        display_name="Jina Code",
        dimensions=768,
        context_window=8192,
        priority=2,
        package_name="sentence_transformers",
        install_extra="jina",
    ),
    EmbeddingModelId.BGE_SMALL: EmbeddingModelInfo(
        id=EmbeddingModelId.BGE_SMALL,
        display_name="BGE-small",
        dimensions=384,
        context_window=512,
        priority=3,  # Lowest quality, but always available
        package_name="fastembed",
        install_extra=None,  # Included in base install
    ),
}


def _check_package_available(package_name: str) -> bool:
    """Check if a package is available for import."""
    import importlib.util
    return importlib.util.find_spec(package_name) is not None


@dataclass
class EmbeddingRegistry:
    """
    Registry for embedding model backends.

    Tracks available backends, handles priority ordering,
    and creates embedding function instances on demand.

    Thread-safe singleton pattern via module-level instance.

    Example:
        registry = get_embedding_registry()
        if registry.is_available(EmbeddingModelId.NOMIC):
            embedder = registry.create(EmbeddingModelId.NOMIC)
        else:
            embedder = registry.create_best_available()
    """
    _backends: Dict[EmbeddingModelId, Callable[[], EmbeddingFunctionProtocol]] = field(
        default_factory=dict
    )
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def register_backend(
        self,
        model_id: EmbeddingModelId,
        factory: Callable[[], EmbeddingFunctionProtocol],
    ) -> None:
        """
        Register an embedding backend factory.

        Args:
            model_id: Model identifier
            factory: Callable that creates the embedding function (lazy import)
        """
        with self._lock:
            self._backends[model_id] = factory
            logger.debug(f"Registered embedding backend: {model_id.value}")

    def is_available(self, model_id: EmbeddingModelId) -> bool:
        """
        Check if a model's dependencies are installed.

        Args:
            model_id: Model identifier to check

        Returns:
            True if the model's package is available
        """
        if model_id not in MODEL_INFO:
            return False
        info = MODEL_INFO[model_id]
        return _check_package_available(info.package_name)

    def get_info(self, model_id: EmbeddingModelId) -> Optional[EmbeddingModelInfo]:
        """
        Get metadata for a model.

        Args:
            model_id: Model identifier

        Returns:
            EmbeddingModelInfo or None if not found
        """
        return MODEL_INFO.get(model_id)

    def get_available(self) -> List[EmbeddingModelInfo]:
        """
        Get list of available models sorted by priority.

        Returns:
            List of EmbeddingModelInfo for available models (best first)
        """
        available = [
            info for info in MODEL_INFO.values()
            if self.is_available(info.id)
        ]
        return sorted(available, key=lambda x: x.priority)

    def get_best_available(self) -> Optional[EmbeddingModelInfo]:
        """
        Get the highest quality available model.

        Returns:
            EmbeddingModelInfo for the best available model, or None if none available
        """
        available = self.get_available()
        return available[0] if available else None

    def create(self, model_id: EmbeddingModelId) -> EmbeddingFunctionProtocol:
        """
        Create an embedding function instance.

        Args:
            model_id: Model identifier to create

        Returns:
            EmbeddingFunctionProtocol instance

        Raises:
            ValueError: If model not available or not registered
        """
        if not self.is_available(model_id):
            info = MODEL_INFO.get(model_id)
            if info and info.install_extra:
                raise ValueError(
                    f"Embedding model '{model_id.value}' is not available. "
                    f"Install with: pip install scrappy[{info.install_extra}]"
                )
            raise ValueError(
                f"Embedding model '{model_id.value}' is not available. "
                f"Required package '{info.package_name if info else 'unknown'}' not installed."
            )

        with self._lock:
            if model_id not in self._backends:
                raise ValueError(
                    f"Embedding model '{model_id.value}' is available but not registered. "
                    f"This is a bug - backend module not imported."
                )
            factory = self._backends[model_id]

        logger.info(f"Creating embedding function: {model_id.value}")
        return factory()

    def create_best_available(self) -> EmbeddingFunctionProtocol:
        """
        Create the highest quality available embedding function.

        Returns:
            EmbeddingFunctionProtocol instance for the best available model

        Raises:
            RuntimeError: If no embedding backends are available
        """
        best = self.get_best_available()
        if best is None:
            raise RuntimeError(
                "No embedding backends available. This should not happen - "
                "BGE-small should always be available in base install."
            )
        return self.create(best.id)


# Module-level singleton
_registry: Optional[EmbeddingRegistry] = None
_registry_lock = threading.Lock()


def get_embedding_registry() -> EmbeddingRegistry:
    """
    Get the global embedding registry singleton.

    Thread-safe via double-checked locking.

    Returns:
        EmbeddingRegistry instance
    """
    global _registry
    if _registry is not None:
        return _registry

    with _registry_lock:
        if _registry is None:
            _registry = EmbeddingRegistry()
            _register_all_backends(_registry)
        return _registry


def _register_all_backends(registry: EmbeddingRegistry) -> None:
    """
    Register all available embedding backends.

    Uses lazy imports to avoid loading heavy dependencies until needed.
    """
    # BGE-small (always available in base install)
    def create_bge_small() -> EmbeddingFunctionProtocol:
        from scrappy.context.semantic.backends.bge_small import BgeSmallEmbeddingFunction
        return BgeSmallEmbeddingFunction()

    registry.register_backend(EmbeddingModelId.BGE_SMALL, create_bge_small)

    # Nomic (optional, requires gpt4all)
    def create_nomic() -> EmbeddingFunctionProtocol:
        from scrappy.context.semantic.backends.nomic import NomicEmbeddingFunction
        return NomicEmbeddingFunction()

    registry.register_backend(EmbeddingModelId.NOMIC, create_nomic)

    # Jina (optional, requires sentence-transformers)
    def create_jina() -> EmbeddingFunctionProtocol:
        from scrappy.context.semantic.backends.jina import JinaEmbeddingFunction
        return JinaEmbeddingFunction()

    registry.register_backend(EmbeddingModelId.JINA, create_jina)


def reset_registry() -> None:
    """
    Reset the registry singleton.

    For testing purposes only.
    """
    global _registry
    with _registry_lock:
        _registry = None
