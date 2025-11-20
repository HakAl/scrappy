"""
Task-type aware execution routing system.
Routes tasks to optimal execution strategies based on complexity and type.
"""

from .classifier import TaskType, TaskClassifier, ClassifiedTask
from .intent_clarifier import (
    IntentClarifierInterface,
    InteractiveClarifier,
    AutoClarifier,
    NullClarifier,
)
from .output_handler import (
    OutputHandlerInterface,
    ConsoleOutputHandler,
    BufferOutputHandler,
    NullOutputHandler,
)
from .router import TaskRouter
from .strategies import (
    ExecutionStrategy,
    ExecutionResult,
    DirectExecutor,
    ResearchExecutor,
    AgentExecutor,
)
from .validator import InputValidator, ValidationError
from .protocols import (
    TaskClassifierProtocol,
    IntentClarifierProtocol,
    TaskRouterProtocol,
    MetricsCollectorProtocol,
)

__all__ = [
    # Classification
    "TaskType",
    "TaskClassifier",
    "ClassifiedTask",
    # Router
    "TaskRouter",
    # Intent Clarification
    "IntentClarifierInterface",
    "InteractiveClarifier",
    "AutoClarifier",
    "NullClarifier",
    # Output Handling
    "OutputHandlerInterface",
    "ConsoleOutputHandler",
    "BufferOutputHandler",
    "NullOutputHandler",
    # Strategies
    "ExecutionStrategy",
    "ExecutionResult",
    "DirectExecutor",
    "ResearchExecutor",
    "AgentExecutor",
    # Validation
    "InputValidator",
    "ValidationError",
    # Protocols
    "TaskClassifierProtocol",
    "IntentClarifierProtocol",
    "TaskRouterProtocol",
    "MetricsCollectorProtocol",
]
