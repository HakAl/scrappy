"""
Manager protocols for orchestrator module.

Defines abstract interfaces for orchestrator manager components that handle
specific concerns like delegation, task execution, background tasks, and reporting.
"""

from typing import Protocol, Dict, Any, List, Optional, Callable, Coroutine, runtime_checkable
from datetime import datetime

from ..providers.base import LLMResponse, LLMProvider


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
    - BackgroundTaskManager: Async background tasks
    - SyncBackgroundManager: Synchronous execution for testing
    - NullBackgroundManager: No-op for testing

    Example:
        def schedule_cleanup(manager: BackgroundTaskManagerProtocol) -> None:
            manager.submit(cleanup_function)
    """

    def submit(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        Submit function for background execution.

        Args:
            func: Function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Task handle or future
        """
        ...

    def submit_async(
        self,
        coro: Coroutine[Any, Any, Any],
    ) -> Any:
        """
        Submit coroutine for background execution.

        Args:
            coro: Coroutine to execute

        Returns:
            Task handle or future
        """
        ...

    def wait_all(self, timeout: Optional[float] = None) -> None:
        """
        Wait for all background tasks to complete.

        Args:
            timeout: Maximum time to wait in seconds

        Raises:
            TimeoutError: If timeout exceeded
        """
        ...

    def cancel_all(self) -> int:
        """
        Cancel all pending background tasks.

        Returns:
            Number of tasks cancelled
        """
        ...

    def get_status(self) -> Dict[str, Any]:
        """
        Get background task status.

        Returns:
            Dictionary containing:
            - pending: Number of pending tasks
            - running: Number of running tasks
            - completed: Number of completed tasks
            - failed: Number of failed tasks
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

    def get_health(self) -> Dict[str, bool]:
        """
        Get health check results.

        Returns:
            Dictionary mapping component names to health status
        """
        ...


@runtime_checkable
class ProviderRegistrarProtocol(Protocol):
    """
    Protocol for provider registration.

    Abstracts provider registration logic to enable testing with
    controlled provider sets and support different registration strategies.

    Implementations:
    - ProviderRegistrar: Auto-discovery and registration
    - ManualRegistrar: Manual registration only
    - TestRegistrar: Registers test providers

    Example:
        def setup_providers(registrar: ProviderRegistrarProtocol) -> None:
            registrar.auto_register()
    """

    def auto_register(self, provider_names: Optional[List[str]] = None) -> int:
        """
        Automatically register available providers.

        Args:
            provider_names: Specific providers to register (None for all)

        Returns:
            Number of providers registered
        """
        ...

    def register_provider(
        self,
        provider: LLMProvider,
        force: bool = False,
    ) -> bool:
        """
        Register a specific provider.

        Args:
            provider: Provider instance to register
            force: Force registration even if already registered

        Returns:
            True if registered, False if already exists and not forced
        """
        ...

    def discover_providers(self) -> List[str]:
        """
        Discover available providers without registering.

        Returns:
            List of available provider names
        """
        ...

    def get_registered_count(self) -> int:
        """
        Get number of registered providers.

        Returns:
            Number of providers currently registered
        """
        ...
