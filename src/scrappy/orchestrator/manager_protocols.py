"""
Manager protocols for orchestrator module.

Defines abstract interfaces for orchestrator manager components that handle
specific concerns like delegation, task execution, background tasks, and reporting.
"""

from typing import AsyncIterator, Protocol, Dict, Any, List, Optional, Coroutine, runtime_checkable

from .constants import (
    DEFAULT_MAX_CONCURRENT,
    DEFAULT_MAX_TOKENS,
    DEFAULT_PROVIDER,
    DEFAULT_TEMPERATURE,
)
from .provider_types import LLMResponse
from .types import StreamChunk
from ..context import CodebaseContextProtocol


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
        messages: Optional[list[dict]] = None,
        **kwargs: Any,
    ) -> tuple[LLMResponse, dict[str, Any]]:
        """
        Delegate task to LLM provider with retry/fallback.

        Args:
            provider_name: Target provider (None for auto-selection)
            prompt: The prompt to send
            model: Specific model to use
            system_prompt: System prompt for context
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            messages: Pre-built messages array (bypasses prompt/system_prompt)
            **kwargs: Additional provider-specific parameters

        Returns:
            Tuple of LLMResponse and task metadata

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
    ) -> tuple[LLMResponse, dict[str, Any]]:
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
            Tuple of LLMResponse and task metadata
        """
        ...

    def stream_delegate(
        self,
        provider_name: Optional[str] = None,
        prompt: str = "",
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream a delegated task through an async iterator.

        Args:
            provider_name: Target provider or group hint
            prompt: The prompt to send
            model: Specific model to use
            system_prompt: System prompt for context
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            **kwargs: Additional provider-specific parameters

        Yields:
            StreamChunk objects as they arrive
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

    def delegate_structured_sync(
        self,
        provider_name: str,
        prompt: str,
        response_model: type[Any],
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        min_context: int = 0,
        **kwargs: Any,
    ) -> Any:
        """
        Delegate with structured output validation using a synchronous call path.

        Args:
            provider_name: Target provider or model group
            prompt: The prompt to send
            response_model: Pydantic-compatible response model
            system_prompt: Optional system prompt
            model: Specific concrete model to use
            min_context: Minimum required context window
            **kwargs: Additional delegation parameters

        Returns:
            Validated response model instance
        """
        ...

    def delegate_batch(
        self,
        tasks: list[dict],
        provider_name: str = DEFAULT_PROVIDER,
        **kwargs: Any,
    ) -> list[LLMResponse]:
        """
        Process multiple tasks with same provider (synchronous).

        Args:
            tasks: List of task dicts with 'prompt' and optional 'system_prompt', 'kwargs'
            provider_name: Provider to use for all tasks
            **kwargs: Additional arguments passed to delegate

        Returns:
            List of LLMResponse objects in the same order as input tasks
        """
        ...

    async def batch_delegate_async(
        self,
        tasks: list[dict],
        provider_name: str = DEFAULT_PROVIDER,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        **kwargs: Any,
    ) -> list[LLMResponse]:
        """
        Process multiple tasks in parallel using async.

        Args:
            tasks: List of task dicts with 'prompt' and optional 'system_prompt', 'kwargs'
            provider_name: Provider to use for all tasks
            max_concurrent: Maximum number of concurrent requests
            **kwargs: Additional arguments passed to all tasks

        Returns:
            List of LLMResponse objects in the same order as input tasks
        """
        ...

    async def multi_provider_query_async(
        self,
        prompt: str,
        providers: list[str],
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        **kwargs: Any,
    ) -> dict[str, tuple]:
        """
        Query multiple providers in parallel for the same prompt.

        Args:
            prompt: The prompt to send to all providers
            providers: List of provider names to query
            model: Specific model (optional)
            system_prompt: System prompt (optional)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            **kwargs: Additional arguments passed to requests

        Returns:
            Dict mapping provider name to (LLMResponse, task_record) tuple.
            Failed providers are excluded from results.

        Raises:
            ValueError: If providers list is empty
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

    def plan(
        self,
        task: str,
        context: Optional[str] = None,
        max_steps: int = 10,
        complexity_score: Optional[int] = None,
    ) -> list[dict]:
        """
        Break down a complex task into steps.

        Args:
            task: The complex task to plan
            context: Optional context about the codebase/project
            max_steps: Maximum number of steps to generate
            complexity_score: Optional complexity score (1-10). If <= 3, planning is skipped.

        Returns:
            List of step dicts with 'step', 'description', 'provider_type' keys
        """
        ...

    def reason(
        self,
        question: str,
        context: Optional[str] = None,
        evidence: Optional[list[str]] = None,
    ) -> dict:
        """
        Perform complex reasoning on a question or problem.

        Args:
            question: The question or problem to reason about
            context: Optional context information
            evidence: Optional list of evidence/facts to consider

        Returns:
            Dict with 'question', 'analysis', 'conclusion', 'confidence' keys
        """
        ...

    def synthesize(
        self,
        results: list[LLMResponse],
        synthesis_prompt: str = "Synthesize these results into a coherent summary:",
    ) -> str:
        """
        Synthesize multiple agent results into a coherent summary.

        Args:
            results: List of LLMResponse objects from various agents
            synthesis_prompt: Prompt for how to synthesize

        Returns:
            Synthesized summary string
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

    def cancel_all_tasks(self) -> int:
        """
        Cancel all pending background tasks.

        Called during shutdown to prevent tasks from blocking exit.

        Returns:
            Number of tasks that were cancelled
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

    def get_usage_report(self) -> Dict[str, Any]:
        """
        Get usage report across all providers.

        Returns:
            Dictionary with per-provider usage statistics
        """
        ...

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache hit/miss statistics
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

    def get_selection_info(self) -> dict:
        """
        Get model selection information.

        Returns:
            Dictionary describing current model selection state
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
