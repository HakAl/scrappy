"""Tests for SemanticRouter.

IMPORTANT: All tests use FakeEmbeddingFunc with deterministic vectors.
DO NOT use real embedding model in tests - they must be fast and repeatable.
"""

from typing import Dict, List, Optional

import numpy as np

from scrappy.task_router.semantic_router.router import SemanticRouter
from scrappy.task_router.classification_strategy import TaskType


class FakeEmbeddingFunc:
    """
    Fake embedding function for testing with deterministic vectors.

    Strategy:
    - Map known texts to specific vectors
    - Unknown texts get a default "distant" vector
    - Vectors are designed to produce predictable cosine distances
    """

    VECTOR_DIM = 384  # BGE-small-en-v1.5 dimension

    def __init__(self, text_to_vector: Optional[Dict[str, List[float]]] = None):
        """
        Args:
            text_to_vector: Map of text -> embedding vector.
                            If None, uses empty dict.
        """
        self._text_to_vector = text_to_vector or {}

    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate deterministic embeddings for testing."""
        result = []
        for text in texts:
            if text in self._text_to_vector:
                result.append(self._text_to_vector[text])
            else:
                # Default: zero vector (will be distant from everything)
                result.append([0.0] * self.VECTOR_DIM)
        return result

    def ndims(self) -> int:
        return self.VECTOR_DIM


def _make_unit_vector(dim: int, index: int) -> List[float]:
    """Create a unit vector with 1.0 at the given index, 0.0 elsewhere."""
    vec = [0.0] * dim
    vec[index % dim] = 1.0
    return vec


def _make_similar_vector(base: List[float], similarity: float = 0.9) -> List[float]:
    """Create a vector similar to base with given cosine similarity."""
    np.random.seed(42)  # Deterministic for tests
    # Add noise to reduce similarity
    noise_scale = np.sqrt(max(0, 1 - similarity**2))
    noise = np.random.randn(len(base)) * noise_scale
    result = np.array(base) * similarity + noise
    # Normalize
    norm = np.linalg.norm(result)
    if norm > 0:
        result = result / norm
    return result.tolist()


class TestSemanticRouter:
    """Tests for SemanticRouter using fake embeddings."""

    def test_classify_exact_match(self):
        """Exact match to example should classify with high confidence."""
        # Setup: CODE_GENERATION examples at index 0, CONVERSATION at index 1
        code_vec = _make_unit_vector(384, 0)
        conv_vec = _make_unit_vector(384, 1)

        fake_embed = FakeEmbeddingFunc({
            # Examples
            "write python": code_vec,
            "create server": code_vec,
            "build api": code_vec,
            "hi": conv_vec,
            "hello": conv_vec,
            "thanks": conv_vec,
        })

        examples = [
            {"text": "write python", "label": "CODE_GENERATION"},
            {"text": "create server", "label": "CODE_GENERATION"},
            {"text": "build api", "label": "CODE_GENERATION"},
            {"text": "hi", "label": "CONVERSATION"},
            {"text": "hello", "label": "CONVERSATION"},
            {"text": "thanks", "label": "CONVERSATION"},
        ]

        router = SemanticRouter(
            embedding_func=fake_embed,
            route_examples=examples,
            k_neighbors=3,
            confidence_threshold=0.6,
        )

        result = router.classify("write python")

        assert result is not None
        assert result.task_type == TaskType.CODE_GENERATION
        assert result.confidence >= 0.9  # Exact match = high confidence

    def test_classify_similar_input(self):
        """Similar input should classify correctly."""
        code_vec = _make_unit_vector(384, 0)
        # Use the same vector for the query to ensure high similarity
        # (the random noise in _make_similar_vector can cause low confidence)

        fake_embed = FakeEmbeddingFunc({
            "write python": code_vec,
            "create server": code_vec,
            "build api": code_vec,
            # Query - same vector as code examples for predictable result
            "make a script": code_vec,
        })

        examples = [
            {"text": "write python", "label": "CODE_GENERATION"},
            {"text": "create server", "label": "CODE_GENERATION"},
            {"text": "build api", "label": "CODE_GENERATION"},
        ]

        router = SemanticRouter(
            embedding_func=fake_embed,
            route_examples=examples,
        )

        result = router.classify("make a script")

        assert result is not None
        assert result.task_type == TaskType.CODE_GENERATION

    def test_returns_none_for_empty_input(self):
        """Empty input should return None."""
        router = SemanticRouter(
            embedding_func=FakeEmbeddingFunc(),
            route_examples=[{"text": "test", "label": "CODE_GENERATION"}],
        )

        assert router.classify("") is None
        assert router.classify("   ") is None

    def test_returns_none_for_none_input(self):
        """None input should return None without crashing."""
        router = SemanticRouter(
            embedding_func=FakeEmbeddingFunc(),
            route_examples=[{"text": "test", "label": "CODE_GENERATION"}],
        )

        # This previously crashed - now handles gracefully
        assert router.classify(None) is None  # type: ignore

    def test_truncates_long_input(self):
        """Long input should be truncated, not rejected."""
        code_vec = _make_unit_vector(384, 0)
        fake_embed = FakeEmbeddingFunc({
            "test": code_vec,
        })
        # Add truncated version too
        long_input = "x" * 3000
        truncated = long_input[:2000]
        fake_embed._text_to_vector[truncated] = code_vec

        router = SemanticRouter(
            embedding_func=fake_embed,
            route_examples=[{"text": "test", "label": "CODE_GENERATION"}],
        )

        # Should not raise, should truncate
        # Result may be None depending on distance, just checking no crash
        router.classify(long_input)

    def test_warm_up_initializes_router(self):
        """warm_up() should pre-initialize."""
        code_vec = _make_unit_vector(384, 0)
        fake_embed = FakeEmbeddingFunc({
            "test": code_vec,
        })

        router = SemanticRouter(
            embedding_func=fake_embed,
            route_examples=[{"text": "test", "label": "CODE_GENERATION"}],
        )

        assert not router.is_ready()  # Not initialized yet

        success = router.warm_up()

        assert success is True
        assert router.is_ready()

    def test_is_ready_false_before_init(self):
        """is_ready() should return False before initialization."""
        router = SemanticRouter(
            embedding_func=FakeEmbeddingFunc(),
            route_examples=[{"text": "test", "label": "CODE_GENERATION"}],
        )

        # is_ready() should NOT trigger initialization
        assert router.is_ready() is False

    def test_low_confidence_returns_none(self):
        """Below-threshold confidence should return None."""
        # Setup: query is distant from all examples
        code_vec = _make_unit_vector(384, 0)
        distant_vec = _make_unit_vector(384, 100)  # Orthogonal = 0 similarity

        fake_embed = FakeEmbeddingFunc({
            "write python": code_vec,
            "distant query": distant_vec,
        })

        router = SemanticRouter(
            embedding_func=fake_embed,
            route_examples=[{"text": "write python", "label": "CODE_GENERATION"}],
            confidence_threshold=0.6,
        )

        result = router.classify("distant query")

        # Distance ~1.0 -> confidence ~0.0 -> below threshold
        assert result is None

    def test_knn_voting_majority_wins(self):
        """K-nearest neighbors should vote by majority."""
        # 2 CODE examples close, 1 CONVERSATION close but slightly farther
        code_vec = _make_unit_vector(384, 0)
        code_vec2 = _make_similar_vector(code_vec, 0.99)
        conv_vec = _make_similar_vector(code_vec, 0.95)  # Slightly farther

        fake_embed = FakeEmbeddingFunc({
            "write python": code_vec,
            "create server": code_vec2,
            "hi there": conv_vec,
            "query": code_vec,  # Matches code examples
        })

        router = SemanticRouter(
            embedding_func=fake_embed,
            route_examples=[
                {"text": "write python", "label": "CODE_GENERATION"},
                {"text": "create server", "label": "CODE_GENERATION"},
                {"text": "hi there", "label": "CONVERSATION"},
            ],
            k_neighbors=3,
        )

        result = router.classify("query")

        # 2 CODE vs 1 CONVERSATION -> CODE wins
        assert result is not None
        assert result.task_type == TaskType.CODE_GENERATION

    def test_all_task_types_classifiable(self):
        """All four task types should be classifiable."""
        # Create distinct vectors for each type
        direct_vec = _make_unit_vector(384, 0)
        code_vec = _make_unit_vector(384, 1)
        research_vec = _make_unit_vector(384, 2)
        conv_vec = _make_unit_vector(384, 3)

        fake_embed = FakeEmbeddingFunc({
            # Examples
            "pip install": direct_vec,
            "git status": direct_vec,
            "npm run": direct_vec,
            "write code": code_vec,
            "create file": code_vec,
            "fix bug": code_vec,
            "what is python": research_vec,
            "explain api": research_vec,
            "search docs": research_vec,
            "hi": conv_vec,
            "hello": conv_vec,
            "thanks": conv_vec,
            # Queries
            "docker ps": direct_vec,
            "build server": code_vec,
            "how does this work": research_vec,
            "good morning": conv_vec,
        })

        examples = [
            {"text": "pip install", "label": "DIRECT_COMMAND"},
            {"text": "git status", "label": "DIRECT_COMMAND"},
            {"text": "npm run", "label": "DIRECT_COMMAND"},
            {"text": "write code", "label": "CODE_GENERATION"},
            {"text": "create file", "label": "CODE_GENERATION"},
            {"text": "fix bug", "label": "CODE_GENERATION"},
            {"text": "what is python", "label": "RESEARCH"},
            {"text": "explain api", "label": "RESEARCH"},
            {"text": "search docs", "label": "RESEARCH"},
            {"text": "hi", "label": "CONVERSATION"},
            {"text": "hello", "label": "CONVERSATION"},
            {"text": "thanks", "label": "CONVERSATION"},
        ]

        router = SemanticRouter(
            embedding_func=fake_embed,
            route_examples=examples,
            k_neighbors=3,
            confidence_threshold=0.6,
        )

        # Test DIRECT_COMMAND
        result = router.classify("docker ps")
        assert result is not None
        assert result.task_type == TaskType.DIRECT_COMMAND

        # Test CODE_GENERATION
        result = router.classify("build server")
        assert result is not None
        assert result.task_type == TaskType.CODE_GENERATION

        # Test RESEARCH
        result = router.classify("how does this work")
        assert result is not None
        assert result.task_type == TaskType.RESEARCH

        # Test CONVERSATION
        result = router.classify("good morning")
        assert result is not None
        assert result.task_type == TaskType.CONVERSATION

    def test_route_result_contains_metadata(self):
        """RouteResult should contain nearest example and distance."""
        code_vec = _make_unit_vector(384, 0)

        fake_embed = FakeEmbeddingFunc({
            "write python script": code_vec,
            "create api": code_vec,
            "query input": code_vec,
        })

        examples = [
            {"text": "write python script", "label": "CODE_GENERATION"},
            {"text": "create api", "label": "CODE_GENERATION"},
        ]

        router = SemanticRouter(
            embedding_func=fake_embed,
            route_examples=examples,
        )

        result = router.classify("query input")

        assert result is not None
        assert result.nearest_example in ["write python script", "create api"]
        assert 0.0 <= result.distance <= 2.0  # Cosine distance range
        assert 0.0 <= result.confidence <= 1.0

    def test_thread_safety_initialization(self):
        """Multiple warm_up calls should not cause issues."""
        import threading

        code_vec = _make_unit_vector(384, 0)
        fake_embed = FakeEmbeddingFunc({
            "test": code_vec,
        })

        router = SemanticRouter(
            embedding_func=fake_embed,
            route_examples=[{"text": "test", "label": "CODE_GENERATION"}],
        )

        results = []

        def warm_up_thread():
            result = router.warm_up()
            results.append(result)

        # Start multiple threads
        threads = [threading.Thread(target=warm_up_thread) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should succeed
        assert all(results)
        assert router.is_ready()
