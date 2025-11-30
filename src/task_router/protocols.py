"""
Task router protocols.

Defines abstract interfaces for task classification, clarification,
routing, metrics collection, and intent classification.
"""

from typing import Protocol, Dict, Any, List, Optional, runtime_checkable
from enum import Enum
from datetime import datetime
from dataclasses import dataclass

from src.infrastructure.output_mode import OutputModeContext
from ..protocols.io import CLIIOProtocol


@runtime_checkable
class ClarificationConfigProtocol(Protocol):
    """
    Configuration for clarification behavior.

    Controls when user clarification is requested based on confidence levels.

    Implementations:
    - ClarificationConfig: Dataclass with yaml-loaded values
    - TestClarificationConfig: Test double with configurable thresholds

    Example:
        def check_clarification(config: ClarificationConfigProtocol, confidence: float) -> bool:
            if confidence < config.confidence_threshold:
                return True  # Low confidence, always clarify
            if confidence >= config.high_confidence_bypass:
                return False  # High confidence, trust classifier
            # Medium confidence, check for conflicting signals
            return has_conflicting_signals(...)
    """

    @property
    def confidence_threshold(self) -> float:
        """
        Confidence below this always needs clarification.

        Tasks with confidence below this value will always prompt
        for user clarification, regardless of other signals.

        Default: 0.7
        """
        ...

    @property
    def high_confidence_bypass(self) -> float:
        """
        Confidence at or above this bypasses conflicting signal checks.

        When the classifier is highly confident (>= this value),
        we trust it completely and skip the conflicting signals check.
        This prevents false positives like "how to make google?" triggering
        clarification even though it's clearly a research query.

        Default: 0.9
        """
        ...


@runtime_checkable
class TaskClassifierProtocol(Protocol):
    """
    Protocol for task classification.

    Abstracts task classification logic to enable testing with
    controlled classifications and support different strategies.

    Implementations:
    - TaskClassifier: LLM-based classification
    - RuleBasedClassifier: Rule-based classification for testing
    - FixedClassifier: Returns preset classification for testing

    Example:
        def classify_task(classifier: TaskClassifierProtocol, input: str) -> Dict[str, Any]:
            return classifier.classify(input)
    """

    def classify(self, user_input: str) -> Any:
        """
        Classify user input into task type.

        Args:
            user_input: User's task description

        Returns:
            ClassifiedTask object containing:
            - task_type: Type of task (RESEARCH, CODING, DIRECT, etc.)
            - confidence: Classification confidence (0.0 to 1.0)
            - reasoning: Explanation of classification
            - metadata: Additional classification metadata
        """
        ...

    def get_confidence(self, classification: Any) -> float:
        """
        Get classification confidence score.

        Args:
            classification: Classification result

        Returns:
            Confidence score (0.0 to 1.0)
        """
        ...

    def get_supported_types(self) -> List[str]:
        """
        Get list of supported task types.

        Returns:
            List of task type identifiers
        """
        ...


@runtime_checkable
class IntentClarifierProtocol(Protocol):
    """
    Protocol for intent clarification.

    Abstracts intent clarification to enable testing with controlled
    clarifications and support different clarification strategies.

    Implementations:
    - InteractiveClarifier: Interactive user prompts for clarification
    - AutoClarifier: Automatic clarification based on heuristics
    - NullClarifier: No clarification (returns task unchanged)

    Example:
        def clarify_intent(clarifier: IntentClarifierProtocol, task: Any) -> Any:
            return clarifier.clarify(task)
    """

    def clarify(self, classified_task: Any) -> Any:
        """
        Clarify task intent.

        Args:
            classified_task: Classified task to clarify

        Returns:
            Clarified task object (may be the same or modified)
        """
        ...


@runtime_checkable
class TaskRouterProtocol(Protocol):
    """
    Protocol for task routing.

    Abstracts task routing logic to enable testing with controlled
    routing and support different routing strategies.

    Implementations:
    - TaskRouter: Full routing with classification and strategy selection
    - DirectRouter: Direct execution without classification
    - TestRouter: Returns preset routing decisions

    Example:
        def route_task(router: TaskRouterProtocol, input: str) -> Any:
            return router.route(input)
    """

    def route(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Route task to appropriate execution strategy.

        Args:
            user_input: User's task description
            context: Optional context information

        Returns:
            ExecutionResult containing:
            - success: Whether execution succeeded
            - result: Execution result data
            - strategy: Strategy that was used
            - metadata: Additional execution metadata
        """
        ...

    def get_strategy(self, task_type: str) -> Any:
        """
        Get execution strategy for task type.

        Args:
            task_type: Type of task

        Returns:
            ExecutionStrategy instance

        Raises:
            ValueError: If no strategy for task type
        """
        ...

    def register_strategy(
        self,
        task_type: str,
        strategy: Any,
    ) -> None:
        """
        Register execution strategy for task type.

        Args:
            task_type: Task type identifier
            strategy: ExecutionStrategy instance
        """
        ...

    def list_strategies(self) -> Dict[str, str]:
        """
        List registered strategies.

        Returns:
            Dictionary mapping task types to strategy names
        """
        ...


@runtime_checkable
class MetricsCollectorProtocol(Protocol):
    """
    Protocol for metrics collection.

    Abstracts metrics collection to enable testing without actual
    metrics tracking and support different collection strategies.

    Implementations:
    - MetricsCollector: Full metrics collection and aggregation
    - InMemoryMetrics: In-memory metrics for testing
    - NullMetrics: No-op metrics collector

    Example:
        def track_task(metrics: MetricsCollectorProtocol, task_type: str, duration: float) -> None:
            metrics.record("task_executed", {
                "task_type": task_type,
                "duration": duration,
            })
    """

    def record(
        self,
        metric_name: str,
        value: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Record a metric.

        Args:
            metric_name: Name of metric to record
            value: Metric value (optional)
            metadata: Optional metadata about the metric
        """
        ...

    def get_metrics(
        self,
        metric_name: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Get collected metrics.

        Args:
            metric_name: Specific metric to retrieve (None for all)
            start_time: Filter metrics after this time
            end_time: Filter metrics before this time

        Returns:
            Dictionary containing:
            - metrics: List of metric records
            - summary: Aggregated statistics
            - count: Total number of records
        """
        ...

    def reset(self, metric_name: Optional[str] = None) -> None:
        """
        Reset metrics.

        Args:
            metric_name: Specific metric to reset (None for all)
        """
        ...

    def get_summary(self) -> Dict[str, Any]:
        """
        Get metrics summary.

        Returns:
            Dictionary containing aggregated metrics:
            - total_tasks: Total tasks executed
            - by_type: Breakdown by task type
            - avg_duration: Average execution duration
            - success_rate: Success rate percentage
        """
        ...

    def export(self, format: str = "json") -> str:
        """
        Export metrics in specified format.

        Args:
            format: Export format (json, csv, etc.)

        Returns:
            Formatted metrics string
        """
        ...

    def increment(
        self,
        counter_name: str,
        amount: int = 1,
    ) -> None:
        """
        Increment a counter metric.

        Args:
            counter_name: Name of counter to increment
            amount: Amount to increment by
        """
        ...

    def gauge(
        self,
        gauge_name: str,
        value: float,
    ) -> None:
        """
        Set a gauge metric value.

        Args:
            gauge_name: Name of gauge metric
            value: Current value
        """
        ...

    def histogram(
        self,
        histogram_name: str,
        value: float,
    ) -> None:
        """
        Record value in histogram.

        Args:
            histogram_name: Name of histogram
            value: Value to record
        """
        ...


# Intent Classification Protocols

class QueryIntent(Enum):
    """All possible intent classifications."""
    FILE_STRUCTURE = "file_structure"
    CODE_EXPLANATION = "code_explanation"
    GIT_HISTORY = "git_history"
    DEPENDENCY_INFO = "dependency_info"
    ARCHITECTURE = "architecture"
    BUG_INVESTIGATION = "bug_investigation"
    TESTING = "testing"
    PERFORMANCE = "performance"
    DOCUMENTATION = "documentation"
    REFACTORING = "refactoring"
    SECURITY = "security"
    CONFIGURATION = "configuration"
    GENERAL = "general"


@dataclass
class IntentResult:
    """Result of intent classification."""
    intent: QueryIntent
    confidence: float
    metadata: Dict[str, Any]


@dataclass
class Action:
    """Represents a concrete action to execute."""
    tool: str
    func: str
    args: Dict[str, Any]


@runtime_checkable
class IntentClassifierProtocol(Protocol):
    """
    Classifies user queries into intents.

    Abstracts intent classification logic to enable testing with
    controlled classifications and support different strategies
    (regex-based, LLM-based, embedding-based, hybrid).

    Implementations:
    - RegexIntentClassifier: Pattern-based classification
    - LLMClassifier: LLM-based classification
    - HybridClassifier: Combines multiple classifiers with fallback

    Example:
        def classify_query(classifier: IntentClassifierProtocol, query: str) -> IntentResult:
            result = classifier.classify(query)
            if result.confidence > 0.6:
                # High confidence, proceed
                return result
            # Low confidence, may need clarification
            return result
    """

    def classify(self, query: str) -> IntentResult:
        """
        Classifies a query into an intent with confidence score.

        Args:
            query: User's query string

        Returns:
            IntentResult containing:
            - intent: Classified intent enum
            - confidence: Confidence score (0.0 to 1.0)
            - metadata: Additional classification metadata (e.g., matched patterns)
        """
        ...


@runtime_checkable
class EntityExtractorProtocol(Protocol):
    """
    Extracts structured entities from queries.

    Abstracts entity extraction to enable testing with controlled
    extractions and support different extraction strategies.

    Implementations:
    - RegexEntityExtractor: Pattern-based entity extraction
    - NEREntityExtractor: Named Entity Recognition based extraction

    Example:
        def extract_info(extractor: EntityExtractorProtocol, query: str) -> Dict[str, List[str]]:
            entities = extractor.extract(query)
            if 'file_path' in entities:
                # Found file paths in query
                process_files(entities['file_path'])
            return entities
    """

    def extract(self, query: str) -> Dict[str, List[str]]:
        """
        Extracts entities like filenames, classes, functions, etc.

        Args:
            query: User's query string

        Returns:
            Dictionary mapping entity types to lists of extracted values:
            - file_path: File paths found in query
            - function_name: Function names found
            - class_name: Class names found
            - error_type: Error types mentioned
            - package_name: Package names mentioned
            - keyword: Domain keywords found
        """
        ...


@runtime_checkable
class ActionResolverProtocol(Protocol):
    """
    Maps intent + entities to executable actions.

    Abstracts action resolution to enable testing with controlled
    resolutions and support different resolution strategies.

    Implementations:
    - DefaultActionResolver: Standard intent-to-action mapping
    - ContextAwareResolver: Uses conversation context for resolution

    Example:
        def resolve_action(
            resolver: ActionResolverProtocol,
            result: IntentResult,
            entities: Dict[str, List[str]]
        ) -> Action:
            action = resolver.resolve(result, entities)
            # Execute the action
            execute_action(action)
            return action
    """

    def resolve(self, result: IntentResult, entities: Dict[str, List[str]]) -> Action:
        """
        Converts classification results into a concrete system action.

        Args:
            result: Intent classification result
            entities: Extracted entities from query

        Returns:
            Action object containing:
            - tool: Tool to invoke (e.g., 'FileSystem', 'CodeSearch')
            - func: Function to call on the tool
            - args: Arguments to pass to the function
        """
        ...


@runtime_checkable
class IntentServiceProtocol(Protocol):
    """
    Facade for end-to-end intent processing.

    Coordinates intent classification, entity extraction, and action
    resolution into a single pipeline. This is the main entry point
    for intent processing.

    Implementations:
    - IntentService: Standard implementation coordinating all components

    Example:
        def process_user_query(service: IntentServiceProtocol, query: str) -> Action:
            # Full pipeline: classify -> extract -> resolve
            action = service.process_query(query)
            # Action is ready to execute
            return action
    """

    def process_query(self, query: str) -> Action:
        """
        Full pipeline: classify intent -> extract entities -> resolve to action.

        This is the main entry point for processing user queries.

        Args:
            query: User's query string

        Returns:
            Action object ready to be executed
        """
        ...


@runtime_checkable
class TaskRouterInputProtocol(Protocol):
    """
    Protocol for user input in task router components.

    This protocol abstracts user input to enable:
    - Non-blocking input in Textual UI (via CLIIOProtocol adapters)
    - Testable code with mock input
    - CLI fallback via DefaultConsoleInput

    Implementations:
    - DefaultConsoleInput: Fallback using stdin (for CLI/non-Textual contexts)
    - CLIIOInputAdapter: Adapts CLIIOProtocol for Textual compatibility

    IMPORTANT: Direct input() calls in task router code will block forever
    in Textual worker threads. Always use this protocol instead.
    """

    def prompt(self, text: str, default: str = "") -> str:
        """
        Get text input from user.

        Args:
            text: Prompt text to display
            default: Default value if user provides no input

        Returns:
            User's input or default value
        """
        ...

    def confirm(self, text: str, default: bool = False) -> bool:
        """
        Get yes/no confirmation from user.

        Args:
            text: Confirmation prompt text
            default: Default value if user provides no input

        Returns:
            True if user confirms, False otherwise
        """
        ...

    def output(self, message: str) -> None:
        """
        Output a message to user.

        Args:
            message: Message to display
        """
        ...


class DefaultConsoleInput:
    """
    Fallback implementation using stdin.

    For CLI/non-Textual contexts where direct console input is safe.
    This is the shared default used by both IntentClarifier and TaskRouter
    when no IO protocol is injected.

    WARNING: CLI MODE ONLY. Do NOT use this in Textual worker threads - it will
    block forever because input() blocks the worker thread waiting for stdin
    that will never arrive (Textual handles input differently).

    For TUI mode, use IOBasedInput instead, or use the create_task_router_input()
    factory function which automatically selects the correct implementation.
    """

    def _check_tui_mode(self, operation: str) -> None:
        """Raise RuntimeError if called in TUI mode.

        Args:
            operation: Name of the operation being attempted

        Raises:
            RuntimeError: If called in TUI mode
        """
        if OutputModeContext.is_tui_mode():
            raise RuntimeError(
                f"DefaultConsoleInput.{operation}() called in TUI mode. "
                "Use IOBasedInput or create_task_router_input() factory instead."
            )

    def prompt(self, text: str, default: str = "") -> str:
        """Get text input from console.

        Raises:
            RuntimeError: If called in TUI mode
        """
        self._check_tui_mode("prompt")
        try:
            result = input(text)
            return result if result else default
        except (EOFError, KeyboardInterrupt):
            return default

    def confirm(self, text: str, default: bool = False) -> bool:
        """Get yes/no confirmation from console.

        Raises:
            RuntimeError: If called in TUI mode
        """
        self._check_tui_mode("confirm")
        try:
            result = input(text).strip().lower()
            return result in ('y', 'yes')
        except (EOFError, KeyboardInterrupt):
            return default

    def output(self, message: str) -> None:
        """Output message to console.

        Raises:
            RuntimeError: If called in TUI mode
        """
        self._check_tui_mode("output")
        print(message)


class IOBasedInput:
    """
    Input implementation that delegates to CLIIOProtocol.

    This adapter allows task router components to get user input
    through the IO abstraction, which correctly handles both CLI
    and TUI modes. In TUI mode, the IO interface routes prompts
    through Textual's modal system.

    Implements TaskRouterInputProtocol.
    """

    def __init__(self, io: CLIIOProtocol):
        """Initialize with CLIIOProtocol instance.

        Args:
            io: CLIIOProtocol instance for input/output operations
        """
        self._io = io

    def prompt(self, text: str, default: str = "") -> str:
        """Get text input via IO interface.

        Args:
            text: Prompt text to display
            default: Default value if user provides no input

        Returns:
            User's input or default value
        """
        return self._io.prompt(text, default=default)

    def confirm(self, text: str, default: bool = False) -> bool:
        """Get yes/no confirmation via IO interface.

        Args:
            text: Confirmation prompt text
            default: Default value if user provides no input

        Returns:
            True if user confirms, False otherwise
        """
        return self._io.confirm(text, default=default)

    def output(self, message: str) -> None:
        """Output message via IO interface.

        Args:
            message: Message to display
        """
        self._io.echo(message)


def create_task_router_input(io: Optional[CLIIOProtocol] = None) -> TaskRouterInputProtocol:
    """
    Factory function to create the appropriate input handler based on mode.

    This function selects the correct input implementation:
    - If io is None: Returns DefaultConsoleInput (for backward compatibility)
    - If io is provided: Returns IOBasedInput (routes through IO abstraction)

    Using IOBasedInput is preferred because it:
    - Works correctly in both CLI and TUI modes
    - Routes prompts through Textual's modal system in TUI mode
    - Avoids blocking worker threads with stdin reads

    Args:
        io: Optional CLIIOProtocol instance

    Returns:
        TaskRouterInputProtocol implementation appropriate for the context

    Example:
        # With IO interface (recommended)
        input_handler = create_task_router_input(io)

        # Without IO interface (fallback, CLI only)
        input_handler = create_task_router_input()
    """
    if io is None:
        return DefaultConsoleInput()
    return IOBasedInput(io)


@runtime_checkable
class OutputHandlerProtocol(Protocol):
    """
    Protocol for output handling in task router.

    Abstracts output handling to enable testing without actual I/O
    and support different output strategies (console, buffer, file, null).

    Implementations:
    - ConsoleOutputHandler: Outputs via CLIIOProtocol
    - BufferOutputHandler: Captures output in memory for testing
    - NullOutputHandler: No-op for silent mode
    - FileOutputHandler: Writes to file
    - CLIIOOutputHandler: Adapter wrapping CLIIOProtocol
    - RichOutputHandler: Rich-enhanced formatted output

    Example:
        def log_task(handler: OutputHandlerProtocol, task_type: str, conf: float) -> None:
            handler.log_classification(task_type, conf, 5, "determined by LLM")
            handler.log_execution_start("ResearchStrategy")
    """

    def log_classification(
        self,
        task_type: str,
        confidence: float,
        complexity: int,
        reasoning: str
    ) -> None:
        """
        Log task classification information.

        Args:
            task_type: Classified task type
            confidence: Classification confidence (0.0 to 1.0)
            complexity: Task complexity (0-10)
            reasoning: Classification reasoning
        """
        ...

    def log_provider_selection(
        self,
        provider: str,
        model: Optional[str],
        source: str
    ) -> None:
        """
        Log provider selection information.

        Args:
            provider: Selected provider name
            model: Selected model name (optional)
            source: Selection source (e.g., "classifier hint", "fallback")
        """
        ...

    def log_execution_start(self, strategy_name: str) -> None:
        """
        Log execution start with strategy name.

        Args:
            strategy_name: Name of execution strategy being used
        """
        ...

    def log_info(self, message: str) -> None:
        """
        Log general information message.

        Args:
            message: Information message to log
        """
        ...


@runtime_checkable
class ExecutionStrategyProtocol(Protocol):
    """
    Protocol for task execution strategies.

    Defines the contract for executing classified tasks. Each strategy
    handles a specific type of task (research, code generation, conversation, etc.).

    Implementations:
    - DirectExecutor: Simple pass-through execution
    - ResearchExecutor: Codebase exploration and research
    - AgentExecutor: Full agent-based code generation
    - ConversationExecutor: Conversational responses

    Example:
        def execute_task(strategy: ExecutionStrategyProtocol, task: ClassifiedTask) -> ExecutionResult:
            if strategy.can_handle(task):
                return strategy.execute(task)
            raise ValueError(f"Strategy {strategy.name} cannot handle task")
    """

    @property
    def name(self) -> str:
        """
        Strategy name for logging and identification.

        Returns:
            Human-readable strategy name
        """
        ...

    def execute(self, task: Any) -> Any:
        """
        Execute the classified task.

        Args:
            task: ClassifiedTask to execute

        Returns:
            ExecutionResult with output and metadata
        """
        ...

    def can_handle(self, task: Any) -> bool:
        """
        Check if this strategy can handle the given task.

        Args:
            task: ClassifiedTask to check

        Returns:
            True if strategy can handle task, False otherwise
        """
        ...
