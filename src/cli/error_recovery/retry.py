"""
Retry strategies for transient failures.

This module provides retry logic with exponential backoff for handling
transient errors like connection timeouts and temporary failures.
"""

import logging
import time
from typing import Any, Callable, Optional, Tuple, Type

from ..exceptions import ProviderError


def retry_operation(
    func: Callable,
    max_retries: int = 3,
    backoff: bool = False,
    retry_on: Optional[Tuple[Type[Exception], ...]] = None,
    logger: Optional[logging.Logger] = None
) -> Any:
    """
    Retry an operation with optional exponential backoff.

    Args:
        func: The function to execute
        max_retries: Maximum number of retry attempts
        backoff: Whether to use exponential backoff
        retry_on: Tuple of exception types to retry on (default: ConnectionError, TimeoutError)
        logger: Optional logger for logging retry attempts

    Returns:
        The result of the function

    Raises:
        ProviderError: If all retries are exhausted
    """
    if retry_on is None:
        retry_on = (ConnectionError, TimeoutError)

    last_exception = None
    attempts = 0

    for attempt in range(max_retries):
        try:
            return func()
        except ProviderError as e:
            # Don't retry non-retryable errors
            if not e.is_retryable:
                raise
            last_exception = e
            attempts += 1
        except retry_on as e:
            last_exception = e
            attempts += 1
        except Exception as e:
            # For other exceptions, don't retry
            raise ProviderError(
                f"Operation failed: {e}",
                provider="unknown",
                original=e
            )

        # Log retry attempt
        if logger:
            logger.warning(f"Retry attempt {attempt + 1}/{max_retries} after error: {last_exception}")

        # Apply backoff if enabled
        if backoff and attempt < max_retries - 1:
            delay = 2 ** attempt  # Exponential: 1, 2, 4...
            time.sleep(delay)

    # All retries exhausted
    raise ProviderError(
        f"Operation failed after {attempts} retries: {last_exception}",
        provider="unknown",
        original=last_exception
    )


def safe_operation_with_recovery(
    func: Callable,
    retry: bool = False,
    max_retries: int = 3,
    fallback_value: Any = None
) -> Tuple[bool, Any]:
    """
    Safely execute operation with recovery options.

    Args:
        func: Function to execute
        retry: Whether to retry on failure
        max_retries: Maximum retry attempts
        fallback_value: Value to return on failure

    Returns:
        Tuple of (success: bool, result: Any)
    """
    if retry:
        try:
            result = retry_operation(func, max_retries=max_retries)
            return True, result
        except Exception:
            return False, fallback_value
    else:
        try:
            result = func()
            return True, result
        except Exception:
            return False, fallback_value
