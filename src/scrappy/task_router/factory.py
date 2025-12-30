"""
Factory functions for task routing components.

This module provides composition root functions for creating
fully-wired TaskClassifier and TaskRouter instances with
proper dependency injection.

Usage:
    # In app startup
    classifier = create_task_classifier(warm_up=True)

    # For testing (disable real embedding model)
    classifier = create_task_classifier(enable_semantic_router=False)

    # Or use test factory with fake embeddings
    classifier = create_test_classifier(fake_embedding_func=FakeEmbeddingFunc())
"""

import logging
from typing import Any, List, Dict, Optional

from .classifier import TaskClassifier
from .semantic_router.router import SemanticRouter

logger = logging.getLogger(__name__)


def create_task_classifier(
    enable_semantic_router: bool = True,
    warm_up: bool = True,
    confidence_threshold: float = 0.6,
    k_neighbors: int = 3,
) -> TaskClassifier:
    """
    Factory function to create a fully-wired TaskClassifier.

    This is the ONLY place where SemanticRouter is instantiated
    and injected into TaskClassifier. DI principle: construct
    dependencies at composition root.

    Args:
        enable_semantic_router: Whether to use semantic routing (default True)
        warm_up: Whether to pre-initialize the router (default True)
        confidence_threshold: Minimum confidence for semantic routing (default 0.6)
        k_neighbors: Number of neighbors for KNN voting (default 3)

    Returns:
        Configured TaskClassifier instance
    """
    semantic_router: Optional[SemanticRouter] = None

    if enable_semantic_router:
        semantic_router = SemanticRouter(
            # Let it lazy-load the real embedding function
            embedding_func=None,
            route_examples=None,  # Use default examples
            k_neighbors=k_neighbors,
            confidence_threshold=confidence_threshold,
        )

        if warm_up:
            # Pre-initialize during app startup, NOT on first request
            success = semantic_router.warm_up()
            if not success:
                # Log warning but continue - will fall back to regex
                logger.warning(
                    "SemanticRouter warm-up failed, will use regex fallback"
                )

    return TaskClassifier(
        semantic_router=semantic_router,
        enable_semantic_routing=enable_semantic_router,
    )


def create_test_classifier(
    fake_embedding_func: Optional[Any] = None,
    route_examples: Optional[List[Dict[str, str]]] = None,
    enable_semantic_routing: bool = True,
    confidence_threshold: float = 0.6,
    k_neighbors: int = 3,
) -> TaskClassifier:
    """
    Factory for tests - uses fake/controlled dependencies.

    Args:
        fake_embedding_func: Fake embedding function for deterministic tests.
                            If None and enable_semantic_routing=True,
                            creates router without embedding (will fail gracefully).
        route_examples: Custom route examples for testing
        enable_semantic_routing: Whether to enable semantic routing
        confidence_threshold: Minimum confidence threshold
        k_neighbors: Number of neighbors for KNN voting

    Returns:
        TaskClassifier with test-friendly configuration

    Example:
        # Create classifier with fake embeddings
        from tests.task_router.test_semantic_router import FakeEmbeddingFunc

        fake_embed = FakeEmbeddingFunc({
            "pip install": [1.0] + [0.0] * 383,
            "write code": [0.0, 1.0] + [0.0] * 382,
        })

        classifier = create_test_classifier(
            fake_embedding_func=fake_embed,
            route_examples=[
                {"text": "pip install", "label": "DIRECT_COMMAND"},
                {"text": "write code", "label": "CODE_GENERATION"},
            ]
        )
    """
    semantic_router = None

    if enable_semantic_routing and fake_embedding_func is not None:
        semantic_router = SemanticRouter(
            embedding_func=fake_embedding_func,
            route_examples=route_examples or [],
            k_neighbors=k_neighbors,
            confidence_threshold=confidence_threshold,
        )
        # Warm up the test router
        semantic_router.warm_up()

    return TaskClassifier(
        semantic_router=semantic_router,
        enable_semantic_routing=enable_semantic_routing,
    )
