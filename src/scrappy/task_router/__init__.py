"""
Task-type aware execution routing system.
Routes tasks to optimal execution strategies based on complexity and type.
"""

from .classifier import TaskType, TaskClassifier, ClassifiedTask
from .classification_strategy import (
    ClassificationStrategyBase,
    ClassificationStrategyProtocol,
    PatternBasedStrategy,
    StrategyResult,
)
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
    SemanticRouterProtocol,
)
from .semantic_router import SemanticRouter, RouteResult, ROUTE_EXAMPLES
from .factory import create_task_classifier, create_test_classifier

__all__ = [
    # Classification
    "TaskType",
    "TaskClassifier",
    "ClassifiedTask",
    # Classification Strategies
    "ClassificationStrategyProtocol",
    "ClassificationStrategyBase",
    "PatternBasedStrategy",
    "StrategyResult",
    # Configuration
    "ClarificationConfig",
    # Router
    "TaskRouter",
    # Semantic Router
    "SemanticRouter",
    "RouteResult",
    "ROUTE_EXAMPLES",
    "SemanticRouterProtocol",
    # Factories
    "create_task_classifier",
    "create_test_classifier",
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
