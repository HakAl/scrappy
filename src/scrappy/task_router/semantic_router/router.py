"""
Semantic router for task classification.

Uses vector similarity to classify user input against canonical examples.
Leverages existing lancedb + fastembed stack from context/semantic.

Features:
- Thread safety via Lock in _ensure_initialized
- numpy for cosine distance (vectorized)
- Input validation (empty, truncation)
- warm_up() method for app startup
- Store vectors as np.ndarray
"""

import logging
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from ..classification_strategy import TaskType
from ...context.protocols import EmbeddingFunctionProtocol

logger = logging.getLogger(__name__)

# Input constraints
MAX_INPUT_LENGTH = 2000  # Truncate long inputs


@dataclass
class RouteResult:
    """Result from semantic routing."""
    task_type: TaskType
    confidence: float
    nearest_example: str
    distance: float


class SemanticRouter:
    """
    Semantic router using K-nearest neighbors in vector space.

    Architecture:
    - Pre-embeds canonical examples on first use (or via warm_up)
    - In-memory storage (examples are small)
    - Queries using numpy-vectorized cosine similarity
    - Returns majority vote of K nearest neighbors

    Design Decisions:
    - Uses same EmbeddingFunctionProtocol as semantic search
    - Lazy initialization (no I/O in constructor)
    - Thread-safe initialization via Lock
    - Fallback to None if not ready (caller uses regex)

    Thread Safety:
    - _ensure_initialized uses a Lock to prevent race conditions
    - Multiple threads can call classify() safely after init
    """

    def __init__(
        self,
        embedding_func: Optional[EmbeddingFunctionProtocol] = None,
        route_examples: Optional[List[Dict[str, str]]] = None,
        k_neighbors: int = 3,
        confidence_threshold: float = 0.6,
    ):
        """
        Initialize semantic router.

        Args:
            embedding_func: Embedding function (lazy-loaded if None)
            route_examples: Canonical examples (uses defaults if None)
            k_neighbors: Number of neighbors for voting
            confidence_threshold: Minimum confidence to return result
        """
        self._embedding_func = embedding_func
        self._k = k_neighbors
        self._threshold = confidence_threshold

        # Lazy state
        self._examples = route_examples
        # Store as numpy array for vectorized operations
        self._example_vectors: Optional[np.ndarray] = None
        self._is_initialized = False

        # Thread safety
        self._init_lock = threading.Lock()

    def _ensure_initialized(self) -> bool:
        """
        Lazy initialization of embedding function and example vectors.

        Thread-safe via Lock to prevent race conditions during
        concurrent first-access.

        Returns:
            True if initialized successfully, False otherwise
        """
        # Fast path: already initialized
        if self._is_initialized:
            return True

        # Slow path: acquire lock and initialize
        with self._init_lock:
            # Double-check after acquiring lock
            if self._is_initialized:
                return True

            try:
                # Load examples if not provided
                if self._examples is None:
                    from .route_data import ROUTE_EXAMPLES
                    self._examples = ROUTE_EXAMPLES

                # Load embedding function if not provided
                if self._embedding_func is None:
                    from ...context.semantic.embeddings import EmbedFunction
                    self._embedding_func = EmbedFunction()

                # Pre-embed all examples, store as numpy array
                texts = [ex["text"] for ex in self._examples]
                embeddings = self._embedding_func.generate_embeddings(texts)
                self._example_vectors = np.array(embeddings)

                self._is_initialized = True
                logger.debug(f"SemanticRouter initialized with {len(texts)} examples")
                return True

            except Exception as e:
                logger.warning(f"SemanticRouter initialization failed: {e}")
                return False

    def warm_up(self) -> bool:
        """
        Pre-initialize the router during application startup.

        Call this during app init, NOT on first user request.
        This avoids cold-start latency for the first user.

        Returns:
            True if warm-up succeeded, False otherwise
        """
        return self._ensure_initialized()

    def is_ready(self) -> bool:
        """Check if router is ready."""
        return self._is_initialized

    def _validate_input(self, user_input: str) -> Optional[str]:
        """
        Validate and normalize user input.

        Args:
            user_input: Raw user input (may be None)

        Returns:
            Validated input or None if invalid
        """
        # Handle None and empty input
        if not user_input:  # Handles None and empty string
            logger.debug("Empty/None input, returning None")
            return None

        cleaned = user_input.strip()

        # Handle whitespace-only input
        if not cleaned:
            logger.debug("Whitespace-only input, returning None")
            return None

        # Truncate long input
        if len(cleaned) > MAX_INPUT_LENGTH:
            logger.debug(f"Truncating input from {len(cleaned)} to {MAX_INPUT_LENGTH} chars")
            cleaned = cleaned[:MAX_INPUT_LENGTH]

        return cleaned

    def classify(self, user_input: str) -> Optional[RouteResult]:
        """
        Classify user input using K-nearest neighbors.

        Args:
            user_input: Raw user input

        Returns:
            RouteResult or None if not ready/uncertain/invalid
        """
        # Input validation
        validated_input = self._validate_input(user_input)
        if validated_input is None:
            return None

        if not self._ensure_initialized():
            return None

        # These are guaranteed to be set after _ensure_initialized succeeds
        assert self._embedding_func is not None
        assert self._example_vectors is not None
        assert self._examples is not None

        # Embed user input
        try:
            user_embedding = self._embedding_func.generate_embeddings([validated_input])[0]
            user_vector = np.array(user_embedding)
        except Exception as e:
            logger.warning(f"Failed to embed user input: {e}")
            return None

        # Calculate distances using numpy (vectorized)
        distances = self._cosine_distances_vectorized(user_vector, self._example_vectors)

        # Find K nearest neighbors
        k_indices = np.argsort(distances)[:self._k]
        k_distances = distances[k_indices]

        # Strong match shortcut: if nearest neighbor is very close, trust it
        # This prevents K-NN voting from overriding near-exact matches
        STRONG_MATCH_THRESHOLD = 0.15  # ~85% cosine similarity
        nearest_idx = int(k_indices[0])
        nearest_dist = float(k_distances[0])

        if nearest_dist < STRONG_MATCH_THRESHOLD:
            winner = self._examples[nearest_idx]["label"]
            confidence = 1.0 - nearest_dist
        else:
            # Vote on task type (weighted by inverse distance)
            votes: Dict[str, float] = {}
            for idx, dist in zip(k_indices, k_distances):
                label = self._examples[idx]["label"]
                # Weight: closer = higher weight (avoid div by zero)
                weight = 1.0 / (dist + 0.01)
                votes[label] = votes.get(label, 0.0) + weight

            # Find winner by total weighted votes
            winner = max(votes.keys(), key=lambda k: votes[k])

            # Calculate confidence from nearest neighbor distance
            confidence = 1.0 - min(nearest_dist, 1.0)

        # Return None if below threshold
        if confidence < self._threshold:
            logger.debug(f"Low confidence {confidence:.2f} for '{validated_input[:50]}...', returning None")
            return None

        # Map label to TaskType
        task_type_map = {
            "CODE_GENERATION": TaskType.CODE_GENERATION,
            "CONVERSATION": TaskType.CONVERSATION,
            "RESEARCH": TaskType.RESEARCH,
            "DIRECT_COMMAND": TaskType.DIRECT_COMMAND,
        }
        task_type = task_type_map.get(winner)
        if task_type is None:
            return None

        return RouteResult(
            task_type=task_type,
            confidence=confidence,
            nearest_example=self._examples[nearest_idx]["text"],
            distance=nearest_dist,
        )

    @staticmethod
    def _cosine_distances_vectorized(
        query: np.ndarray,
        examples: np.ndarray
    ) -> np.ndarray:
        """
        Calculate cosine distances using numpy vectorized operations.

        Args:
            query: Query vector (1D array, 384 dims for BGE-small)
            examples: Example vectors (2D array, N x 384)

        Returns:
            Array of cosine distances (N,)
        """
        # Normalize query
        query_norm = np.linalg.norm(query)
        if query_norm == 0:
            return np.ones(len(examples))
        query_normalized = query / query_norm

        # Normalize examples (row-wise)
        example_norms = np.linalg.norm(examples, axis=1, keepdims=True)
        # Avoid division by zero
        example_norms = np.where(example_norms == 0, 1, example_norms)
        examples_normalized = examples / example_norms

        # Cosine similarity via dot product of normalized vectors
        similarities = examples_normalized @ query_normalized

        # Convert to distance
        return 1.0 - similarities
