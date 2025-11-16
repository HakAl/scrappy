"""
Task-type aware execution routing system.
Routes tasks to optimal execution strategies based on complexity and type.
"""

from .classifier import TaskType, TaskClassifier, ClassifiedTask
from .router import TaskRouter
from .strategies import (
    ExecutionStrategy,
    ExecutionResult,
    DirectExecutor,
    ResearchExecutor,
    AgentExecutor,
)

__all__ = [
    "TaskType",
    "TaskClassifier",
    "ClassifiedTask",
    "TaskRouter",
    "ExecutionStrategy",
    "ExecutionResult",
    "DirectExecutor",
    "ResearchExecutor",
    "AgentExecutor",
]
