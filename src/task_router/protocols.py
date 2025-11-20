"""
Task router protocols.

Defines abstract interfaces for task classification, clarification,
routing, and metrics collection.
"""

from typing import Protocol, Dict, Any, List, Optional, runtime_checkable
from enum import Enum
from datetime import datetime


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
    - NoOpClarifier: No clarification (uses original input)

    Example:
        def clarify_intent(clarifier: IntentClarifierProtocol, task: Any) -> Any:
            if clarifier.needs_clarification(task):
                return clarifier.clarify(task)
            return task
    """

    def needs_clarification(self, classified_task: Any) -> bool:
        """
        Check if task needs clarification.

        Args:
            classified_task: Classified task object

        Returns:
            True if clarification needed, False otherwise
        """
        ...

    def clarify(
        self,
        classified_task: Any,
        options: Optional[List[str]] = None,
    ) -> Any:
        """
        Clarify task intent.

        Args:
            classified_task: Classified task to clarify
            options: Optional list of clarification options

        Returns:
            Clarified task object
        """
        ...

    def get_clarification_options(
        self,
        classified_task: Any,
    ) -> List[Dict[str, str]]:
        """
        Get clarification options for task.

        Args:
            classified_task: Classified task

        Returns:
            List of option dictionaries with 'value' and 'description'
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
