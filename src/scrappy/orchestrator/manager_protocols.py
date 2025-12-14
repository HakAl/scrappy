"""
Manager protocols for orchestrator module.

Defines abstract interfaces for orchestrator manager components that handle
specific concerns like delegation, task execution, background tasks, and reporting.
"""

from typing import Protocol, Dict, Any, List, Optional, Callable, Coroutine, runtime_checkable
from datetime import datetime
from pathlib import Path

from ..providers.base import LLMResponse, LLMProviderBase

try:
    from ..context import CodebaseContextProtocol
except ImportError:
    from context import CodebaseContextProtocol


@runtime_checkable
class DelegationManagerProtocol(Protocol):
    """
    Protocol for delegation management.

    Abstracts LLM delegation logic including retry, fallback, and caching
    to enable testing with controlled responses.

    Implementations:
    - DelegationManager: Full delegation with retry/fallback logic
    - MockDelegator: Returns preset responses for testing
    - RecordingDelegator: Records delegation calls for verification

    Example:
        def query_llm(delegator: DelegationManagerProtocol, prompt: str) -> LLMResponse:
            return delegator.delegate(prompt=prompt)
    """

    def delegate(
        self,
        provider_name: Optional[str] = None,
        prompt: str = "",
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Delegate task to LLM provider with retry/fallback.

        Args:
            provider_name: Target provider (None for auto-selection)
            prompt: The prompt to send
            model: Specific model to use
            system_prompt: System prompt for context
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            **kwargs: Additional provider-specific parameters

        Returns:
            LLMResponse with provider's response

        Raises:
            AllProvidersRateLimitedError: If all providers are rate limited
        """
        ...

    async def delegate_async(
        self,
        provider_name: str,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Asynchronously delegate task to LLM provider.

        Args:
            provider_name: Target provider
            prompt: The prompt to send
            model: Specific model to use
            system_prompt: System prompt for context
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            **kwargs: Additional provider-specific parameters

        Returns:
            LLMResponse with provider's response
        """
        ...

    def delegate_with_retry(
        self,
        prompt: str,
        max_retries: int = 3,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Delegate with automatic retry on failure.

        Args:
            prompt: The prompt to send
            max_retries: Maximum retry attempts
            **kwargs: Additional delegation parameters

        Returns:
            LLMResponse with provider's response

        Raises:
            Exception: If all retries exhausted
        """
        ...


@runtime_checkable
class TaskExecutorProtocol(Protocol):
    """
    Protocol for task execution.

    Abstracts task execution logic to enable testing with controlled
    execution and support different execution strategies.

    Implementations:
    - TaskExecutor: Standard task execution
    - SyncTaskExecutor: Synchronous execution for testing
    - MockTaskExecutor: Returns preset results

    Example:
        def run_task(executor: TaskExecutorProtocol, task: Dict[str, Any]) -> Any:
            return executor.execute(task)
    """

    def execute(self, task: Dict[str, Any]) -> Any:
        """
        Execute a task.

        Args:
            task: Task specification dictionary

        Returns:
            Task execution result
        """
        ...

    def execute_parallel(self, tasks: List[Dict[str, Any]]) -> List[Any]:
        """
        Execute multiple tasks in parallel.

        Args:
            tasks: List of task specifications

        Returns:
            List of task results in same order
        """
        ...

    def execute_sequential(self, tasks: List[Dict[str, Any]]) -> List[Any]:
        """
        Execute multiple tasks sequentially.

        Args:
            tasks: List of task specifications

        Returns:
            List of task results in same order
        """
        ...


@runtime_checkable
class BackgroundTaskManagerProtocol(Protocol):
    """
    Protocol for background task management.

    Abstracts background task execution to enable testing without
    actual concurrency and support different execution models.

    Implementations:
    - BackgroundTaskManager: Async background tasks with error tracking
    - SyncBackgroundManager: Synchronous execution for testing
    - NullBackgroundManager: No-op for testing

    Example:
        async def cleanup():
            await asyncio.sleep(0.1)

        manager = BackgroundTaskManager()
        task_id = manager.submit_background_task(cleanup())
        await manager.wait_for_background_tasks()
    """

    def submit_background_task(self, coro: Coroutine[Any, Any, Any]) -> str:
        """
        Schedule a coroutine as a background task (fire-and-forget).

        The task runs without blocking the caller. Errors are captured
        but don't affect the main flow.

        Args:
            coro: Coroutine to execute in background

        Returns:
            str: Unique task ID for tracking/cancellation
        """
        ...

    def get_task_status(self) -> Dict[str, Any]:
        """
        Get status of background task processing.

        Returns:
            Dictionary containing:
            - pending_tasks: Number of pending tasks
            - recent_errors: List of recent errors (last 10)
            - total_errors: Total number of errors captured
        """
        ...

    async def wait_for_background_tasks(self, timeout: float = 5.0) -> Dict[str, Any]:
        """
        Wait for all pending background tasks to complete.

        Useful for testing or graceful shutdown.

        Args:
            timeout: Maximum seconds to wait

        Returns:
            Dictionary containing:
            - status: 'no_pending' | 'completed' | 'timeout' | 'error'
            - completed: Number of completed tasks
            - pending: Number of still-pending tasks (if timeout)
            - errors: Number of errors captured
        """
        ...

    def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a pending background task.

        Args:
            task_id: ID returned from submit_background_task

        Returns:
            True if task was found and cancelled, False otherwise
        """
        ...

    def clear_background_errors(self) -> None:
        """
        Clear the background error log.
        """
        ...


@runtime_checkable
class UsageReporterProtocol(Protocol):
    """
    Protocol for usage reporting.

    Abstracts usage tracking and reporting to enable testing without
    actual tracking and support different reporting strategies.

    Implementations:
    - UsageReporter: Full usage tracking and reporting
    - NullReporter: No-op reporter for testing
    - InMemoryReporter: In-memory tracking for testing

    Example:
        def get_stats(reporter: UsageReporterProtocol) -> Dict[str, Any]:
            return reporter.get_report()
    """

    def record(
        self,
        provider: str,
        tokens_used: int,
        cached: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Record usage event.

        Args:
            provider: Provider name
            tokens_used: Number of tokens used
            cached: Whether response was cached
            metadata: Optional additional metadata
        """
        ...

    def get_report(self) -> Dict[str, Any]:
        """
        Get usage report.

        Returns:
            Dictionary containing:
            - total_tasks: Total tasks executed
            - by_provider: Per-provider breakdown
            - cache_stats: Cache hit/miss statistics
            - token_usage: Total tokens used
        """
        ...

    def reset(self) -> None:
        """
        Reset usage statistics.
        """
        ...

    def export(self, format: str = "json") -> str:
        """
        Export usage report in specified format.

        Args:
            format: Export format (json, csv, etc.)

        Returns:
            Formatted report string
        """
        ...


@runtime_checkable
class StatusReporterProtocol(Protocol):
    """
    Protocol for status reporting.

    Abstracts status reporting to enable testing without output
    and support different reporting strategies.

    Implementations:
    - ProviderStatusReporter: Full status reporting
    - NullStatusReporter: No-op reporter for testing
    - LoggingStatusReporter: Logs status instead of printing

    Example:
        def show_status(reporter: StatusReporterProtocol) -> None:
            reporter.print_status()
    """

    def get_status(self) -> Dict[str, Any]:
        """
        Get current status information.

        Returns:
            Dictionary containing system status
        """
        ...

    def print_status(self) -> None:
        """
        Print status to output.
        """
        ...

    def update_quality_mode(self, quality_mode: bool) -> None:
        """
        Update the quality mode setting.

        Args:
            quality_mode: Whether quality mode is enabled
        """
        ...

    def get_health(self) -> Dict[str, bool]:
        """
        Get health check results.

        Returns:
            Dictionary mapping component names to health status
        """
        ...


@runtime_checkable
class ContextManagerProtocol(Protocol):
    """
    Protocol for orchestrator-level context management coordination.

    Adds orchestration concerns (logging, task executor integration,
    lifecycle policies) on top of CodebaseContext. Does NOT duplicate
    CodebaseContext functionality - instead coordinates context operations
    with other orchestrator components.

    Implementations:
    - ContextManager: Full coordination with logging and task integration
    - MockContextManager: Returns preset context for testing
    - NullContextManager: No-op context manager

    Example:
        def setup_context(manager: ContextManagerProtocol) -> None:
            manager.auto_explore()
            prompt = manager.context.augment_prompt("explain this code")
    """

    @property
    def context(self) -> CodebaseContextProtocol:
        """
        Access underlying codebase context.

        Direct context operations should use this property:
        - context.augment_prompt(prompt)
        - context.get_file_count()
        - context.add_files(files)
        - context.is_explored()
        - context.get_status()

        Returns:
            The underlying CodebaseContext instance
        """
        ...

    def auto_explore(self) -> Dict[str, Any]:
        """
        Orchestrator-level auto-exploration on startup.

        Coordinates:
        - Check if context is cached (via context.is_explored())
        - Log status via OutputInterface
        - Trigger exploration if needed (via context.explore())
        - Generate summary via TaskExecutor if exploration occurred
        - Log results

        Returns:
            Dictionary containing:
            - status: 'cached' | 'explored' | 'skipped'
            - total_files: Number of files found (if explored)
            - cache_used: Whether cached data was used
        """
        ...

    def explore_project(self, force: bool = False) -> Dict[str, Any]:
        """
        Orchestrator-level manual exploration trigger.

        Coordinates:
        - Clear cache if force=True (via context.clear_cache())
        - Trigger exploration (via context.explore())
        - Generate summary via TaskExecutor if exploration occurred
        - Log results via OutputInterface

        Args:
            force: Force re-exploration even if cached

        Returns:
            Dictionary containing:
            - status: 'explored' | 'cached' | 'failed'
            - total_files: Number of files found
            - error: Error message if status is 'failed'
        """
        ...
