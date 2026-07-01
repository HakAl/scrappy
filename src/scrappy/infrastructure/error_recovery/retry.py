"""
Unified retry strategy implementation.

Provides both synchronous and asynchronous retry with exponential backoff.
Consolidates the three different retry implementations that previously existed.
"""

from typing import Callable, TypeVar, Any, Optional
import time
import asyncio
import logging
from .config import RetryConfig, DEFAULT_RETRY_CONFIG
from ..exceptions import BaseError

T = TypeVar('T')

logger = logging.getLogger(__name__)


class ExponentialBackoffRetry:
    """Retry strategy with exponential backoff.

    Implements RetryStrategyProtocol with configurable backoff.
    Supports both sync and async execution.
    """

    def __init__(
        self,
        config: Optional[RetryConfig] = None,
        logger_instance: Optional[logging.Logger] = None
    ):
        """Initialize retry strategy.

        Args:
            config: Retry configuration (uses default if None)
            logger_instance: Logger for retry events
        """
        self.config = config or DEFAULT_RETRY_CONFIG
        self.logger = logger_instance or logger

    def execute(
        self,
        func: Callable[..., T],
        *args: Any,
        max_retries: Optional[int] = None,
        retry_on: Optional[tuple[type[Exception], ...]] = None,
        **kwargs: Any
    ) -> T:
        """Execute function with retry logic.

        Args:
            func: Function to execute
            *args: Positional arguments for func
            max_retries: Override config max_retries
            retry_on: Tuple of exception types to retry on (None = all)
            **kwargs: Keyword arguments for func

        Returns:
            Result of successful function execution

        Raises:
            Last exception if all retries exhausted
        """
        max_attempts = (max_retries if max_retries is not None
                       else self.config.max_retries)

        last_exception: Optional[Exception] = None

        for attempt in range(max_attempts + 1):
            try:
                result = func(*args, **kwargs)
                if attempt > 0:
                    self.logger.info(
                        f"Retry successful on attempt {attempt + 1}",
                        extra={'attempt': attempt + 1, 'function': getattr(func, '__name__', '<anonymous>')}
                    )
                return result

            except Exception as e:
                last_exception = e

                # Check if this exception should be retried
                if not self._should_retry(e, retry_on, attempt, max_attempts):
                    raise

                # Calculate delay and wait
                if attempt < max_attempts:
                    delay = self.config.calculate_delay(attempt)
                    self.logger.warning(
                        f"Attempt {attempt + 1} failed, retrying in {delay:.2f}s: {e}",
                        extra={
                            'attempt': attempt + 1,
                            'max_attempts': max_attempts + 1,
                            'delay': delay,
                            'error_type': type(e).__name__,
                            'function': getattr(func, '__name__', '<anonymous>'),
                        }
                    )
                    time.sleep(delay)

        # All retries exhausted
        assert last_exception is not None
        self.logger.error(
            f"All {max_attempts + 1} attempts failed",
            extra={
                'attempts': max_attempts + 1,
                'error_type': type(last_exception).__name__,
                'function': func.__name__,
            }
        )
        raise last_exception

    async def execute_async(
        self,
        func: Callable[..., T],
        *args: Any,
        max_retries: Optional[int] = None,
        retry_on: Optional[tuple[type[Exception], ...]] = None,
        **kwargs: Any
    ) -> T:
        """Execute async function with retry logic.

        Args:
            func: Async function to execute
            *args: Positional arguments for func
            max_retries: Override config max_retries
            retry_on: Tuple of exception types to retry on (None = all)
            **kwargs: Keyword arguments for func

        Returns:
            Result of successful function execution

        Raises:
            Last exception if all retries exhausted
        """
        max_attempts = (max_retries if max_retries is not None
                       else self.config.max_retries)

        last_exception: Optional[Exception] = None

        for attempt in range(max_attempts + 1):
            try:
                result = await func(*args, **kwargs)
                if attempt > 0:
                    self.logger.info(
                        f"Retry successful on attempt {attempt + 1}",
                        extra={'attempt': attempt + 1, 'function': getattr(func, '__name__', '<anonymous>')}
                    )
                return result

            except Exception as e:
                last_exception = e

                # Check if this exception should be retried
                if not self._should_retry(e, retry_on, attempt, max_attempts):
                    raise

                # Calculate delay and wait
                if attempt < max_attempts:
                    delay = self.config.calculate_delay(attempt)
                    self.logger.warning(
                        f"Attempt {attempt + 1} failed, retrying in {delay:.2f}s: {e}",
                        extra={
                            'attempt': attempt + 1,
                            'max_attempts': max_attempts + 1,
                            'delay': delay,
                            'error_type': type(e).__name__,
                            'function': getattr(func, '__name__', '<anonymous>'),
                        }
                    )
                    await asyncio.sleep(delay)

        # All retries exhausted
        assert last_exception is not None
        self.logger.error(
            f"All {max_attempts + 1} attempts failed",
            extra={
                'attempts': max_attempts + 1,
                'error_type': type(last_exception).__name__,
                'function': func.__name__,
            }
        )
        raise last_exception

    def _should_retry(
        self,
        exception: Exception,
        retry_on: Optional[tuple[type[Exception], ...]],
        attempt: int,
        max_attempts: int
    ) -> bool:
        """Determine if exception should be retried.

        Args:
            exception: Exception that occurred
            retry_on: Allowed exception types (None = all)
            attempt: Current attempt number
            max_attempts: Maximum attempts allowed

        Returns:
            True if should retry, False otherwise
        """
        # No more retries available
        if attempt >= max_attempts:
            return False

        # Check if exception type is in retry_on list
        if retry_on is not None:
            if not isinstance(exception, retry_on):
                self.logger.debug(
                    f"Exception {type(exception).__name__} not in retry_on list",
                    extra={'exception_type': type(exception).__name__}
                )
                return False

        # If exception is a BaseError, check is_retryable property
        if isinstance(exception, BaseError):
            if not exception.is_retryable:
                self.logger.debug(
                    f"{type(exception).__name__} is marked non-retryable",
                    extra={'exception_type': type(exception).__name__}
                )
                return False

        return True


# Convenience functions for backward compatibility

def retry_operation(
    func: Callable[..., T],
    *args: Any,
    max_retries: int = 3,
    backoff: bool = True,
    retry_on: Optional[tuple[type[Exception], ...]] = None,
    logger_instance: Optional[logging.Logger] = None,
    **kwargs: Any
) -> T:
    """Retry operation with exponential backoff.

    Convenience function that uses ExponentialBackoffRetry internally.

    Args:
        func: Function to execute
        *args: Positional arguments
        max_retries: Maximum retry attempts
        backoff: Use exponential backoff (always True for consistency)
        retry_on: Exception types to retry on
        logger_instance: Logger instance
        **kwargs: Keyword arguments

    Returns:
        Result of successful execution
    """
    config = RetryConfig(max_retries=max_retries) if backoff else RetryConfig(
        max_retries=max_retries,
        base_delay=0.0,
        multiplier=1.0
    )

    strategy = ExponentialBackoffRetry(config=config, logger_instance=logger_instance)
    return strategy.execute(func, *args, retry_on=retry_on, **kwargs)


async def retry_operation_async(
    func: Callable[..., T],
    *args: Any,
    max_retries: int = 3,
    backoff: bool = True,
    retry_on: Optional[tuple[type[Exception], ...]] = None,
    logger_instance: Optional[logging.Logger] = None,
    **kwargs: Any
) -> T:
    """Retry async operation with exponential backoff.

    Convenience function that uses ExponentialBackoffRetry internally.

    Args:
        func: Async function to execute
        *args: Positional arguments
        max_retries: Maximum retry attempts
        backoff: Use exponential backoff (always True for consistency)
        retry_on: Exception types to retry on
        logger_instance: Logger instance
        **kwargs: Keyword arguments

    Returns:
        Result of successful execution
    """
    config = RetryConfig(max_retries=max_retries) if backoff else RetryConfig(
        max_retries=max_retries,
        base_delay=0.0,
        multiplier=1.0
    )

    strategy = ExponentialBackoffRetry(config=config, logger_instance=logger_instance)
    return await strategy.execute_async(func, *args, retry_on=retry_on, **kwargs)
