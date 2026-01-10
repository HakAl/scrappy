"""
Error recovery strategy protocols.

Following SOLID principles from CLAUDE.md:
- Protocols define contracts for error recovery behavior
- Implementations can be swapped for testing and different contexts
- Enables dependency injection and inversion of control
"""

from typing import Protocol, Callable, TypeVar, Any, Optional, runtime_checkable

# Re-export enums from exceptions.enums for backward compatibility
# (Enums moved to break circular dependency)
from ..exceptions.enums import (
    RecoveryAction,
    ErrorSeverity,
    ErrorCategory,
)

T = TypeVar('T')


@runtime_checkable
class RetryStrategyProtocol(Protocol):
    """Protocol for retry strategies.

    Implementations provide different backoff and retry logic.
    """

    def execute(
        self,
        func: Callable[..., T],
        *args: Any,
        max_retries: int = 3,
        retry_on: Optional[tuple[type[Exception], ...]] = None,
        **kwargs: Any
    ) -> T:
        """Execute function with retry logic.

        Args:
            func: Function to execute
            *args: Positional arguments for func
            max_retries: Maximum number of retry attempts
            retry_on: Tuple of exception types to retry on (None = retry all)
            **kwargs: Keyword arguments for func

        Returns:
            Result of successful function execution

        Raises:
            Last exception if all retries exhausted
        """
        ...

    async def execute_async(
        self,
        func: Callable[..., T],
        *args: Any,
        max_retries: int = 3,
        retry_on: Optional[tuple[type[Exception], ...]] = None,
        **kwargs: Any
    ) -> T:
        """Execute async function with retry logic.

        Args:
            func: Async function to execute
            *args: Positional arguments for func
            max_retries: Maximum number of retry attempts
            retry_on: Tuple of exception types to retry on (None = retry all)
            **kwargs: Keyword arguments for func

        Returns:
            Result of successful function execution

        Raises:
            Last exception if all retries exhausted
        """
        ...


@runtime_checkable
class CircuitBreakerProtocol(Protocol):
    """Protocol for circuit breaker pattern.

    Prevents cascading failures by stopping calls to failing services.
    """

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (blocking calls)."""
        ...

    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        ...

    @property
    def is_half_open(self) -> bool:
        """Check if circuit is half-open (testing recovery)."""
        ...

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Execute function through circuit breaker.

        Args:
            func: Function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Result of successful execution

        Raises:
            CircuitBreakerOpenError: If circuit is open
            Original exception: If function fails
        """
        ...

    async def call_async(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Execute async function through circuit breaker.

        Args:
            func: Async function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Result of successful execution

        Raises:
            CircuitBreakerOpenError: If circuit is open
            Original exception: If function fails
        """
        ...

    def record_success(self) -> None:
        """Record successful call."""
        ...

    def record_failure(self, exception: Exception) -> None:
        """Record failed call.

        Args:
            exception: The exception that occurred
        """
        ...

    def reset(self) -> None:
        """Manually reset circuit to closed state."""
        ...


@runtime_checkable
class FallbackStrategyProtocol(Protocol):
    """Protocol for fallback strategies.

    Provides alternative operations when primary fails.
    """

    def execute(
        self,
        primary: Callable[..., T],
        fallbacks: list[Callable[..., T]],
        *args: Any,
        **kwargs: Any
    ) -> T:
        """Execute primary operation with fallback chain.

        Args:
            primary: Primary operation to attempt first
            fallbacks: List of fallback operations (tried in order)
            *args: Positional arguments for operations
            **kwargs: Keyword arguments for operations

        Returns:
            Result from first successful operation

        Raises:
            Last exception if all operations fail
        """
        ...

    async def execute_async(
        self,
        primary: Callable[..., T],
        fallbacks: list[Callable[..., T]],
        *args: Any,
        **kwargs: Any
    ) -> T:
        """Execute async primary operation with fallback chain.

        Args:
            primary: Primary async operation to attempt first
            fallbacks: List of fallback async operations
            *args: Positional arguments for operations
            **kwargs: Keyword arguments for operations

        Returns:
            Result from first successful operation

        Raises:
            Last exception if all operations fail
        """
        ...


@runtime_checkable
class ErrorRecoveryProtocol(Protocol):
    """Composite protocol for complete error recovery.

    Combines retry, circuit breaker, and fallback strategies.
    """

    @property
    def retry_strategy(self) -> RetryStrategyProtocol:
        """Get retry strategy."""
        ...

    @property
    def circuit_breaker(self) -> Optional[CircuitBreakerProtocol]:
        """Get circuit breaker (if configured)."""
        ...

    @property
    def fallback_strategy(self) -> Optional[FallbackStrategyProtocol]:
        """Get fallback strategy (if configured)."""
        ...

    def execute_with_recovery(
        self,
        func: Callable[..., T],
        *args: Any,
        max_retries: int = 3,
        fallback: Optional[Callable[..., T]] = None,
        **kwargs: Any
    ) -> T:
        """Execute function with full recovery chain.

        Order of execution:
        1. Circuit breaker check (if configured)
        2. Retry strategy
        3. Fallback (if configured and retries exhausted)

        Args:
            func: Function to execute
            *args: Positional arguments
            max_retries: Maximum retry attempts
            fallback: Optional fallback function
            **kwargs: Keyword arguments

        Returns:
            Result of successful execution or fallback

        Raises:
            Exception if all recovery strategies exhausted
        """
        ...


@runtime_checkable
class ErrorContextProtocol(Protocol):
    """Protocol for error context managers.

    Provides structured error handling in with blocks.
    """

    @property
    def had_error(self) -> bool:
        """Check if error occurred in context."""
        ...

    @property
    def error(self) -> Optional[Exception]:
        """Get error that occurred (if any)."""
        ...

    @property
    def result(self) -> Any:
        """Get result from context execution."""
        ...

    def __enter__(self) -> "ErrorContextProtocol":
        """Enter context."""
        ...

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Exit context with error handling.

        Returns:
            True to suppress exception, False to propagate
        """
        ...
