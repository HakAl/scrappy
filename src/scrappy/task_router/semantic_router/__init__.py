"""Semantic router for task classification.

Uses vector embeddings to classify user input by finding
nearest neighbors among canonical examples.

Example usage:
    from scrappy.task_router.semantic_router import SemanticRouter, RouteResult

    router = SemanticRouter()
    router.warm_up()  # Call during app startup

    result = router.classify("add a node.js server")
    if result:
        print(f"Task type: {result.task_type}, confidence: {result.confidence}")
"""

from .router import SemanticRouter, RouteResult
from .route_data import ROUTE_EXAMPLES

__all__ = ["SemanticRouter", "RouteResult", "ROUTE_EXAMPLES"]
