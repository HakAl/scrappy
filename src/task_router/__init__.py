"""
Task-type aware execution routing system.
Routes tasks to optimal execution strategies based on complexity and type.
"""

from .classifier import TaskType, TaskClassifier, ClassifiedTask
from .config import ClarificationConfig
from .intent_clarifier import (
    InteractiveClarifier,
    AutoClarifier,
    NullClarifier,
)
from .output_handler import (
    ConsoleOutputHandler,
    BufferOutputHandler,
    NullOutputHandler,
    CLIIOOutputHandler,
)
from .router import TaskRouter
from .strategies import (
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
    TaskRouterInputProtocol,
    DefaultConsoleInput,
    OutputHandlerProtocol,
    ExecutionStrategyProtocol,
)

__all__ = [
    # Classification
    "TaskType",
    "TaskClassifier",
    "ClassifiedTask",
    # Configuration
    "ClarificationConfig",
    # Router
    "TaskRouter",
    # Intent Clarification
    "InteractiveClarifier",
    "AutoClarifier",
    "NullClarifier",
    # Output Handling
    "ConsoleOutputHandler",
    "BufferOutputHandler",
    "NullOutputHandler",
    "CLIIOOutputHandler",
    # Strategies
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
    "TaskRouterInputProtocol",
    "DefaultConsoleInput",
    "OutputHandlerProtocol",
    "ExecutionStrategyProtocol",
]
