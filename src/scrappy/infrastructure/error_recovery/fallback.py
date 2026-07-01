"""
Fallback strategy implementation.

Provides sequential fallback chain for when primary operations fail.
"""

from typing import Callable, TypeVar, Any, Optional
import logging
from ..exceptions import RetryExhaustedError

T = TypeVar('T')

logger = logging.getLogger(__name__)


class FallbackChain:
    """Fallback strategy that tries operations in sequence.

    Implements FallbackStrategyProtocol.
    """

    def __init__(
        self,
        logger_instance: Optional[logging.Logger] = None,
        suppress_errors: bool = False
    ):
        """Initialize fallback chain.

        Args:
            logger_instance: Logger for fallback events
            suppress_errors: If True, return None instead of raising on total failure
        """
        self.logger = logger_instance or logger
        self.suppress_errors = suppress_errors

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
            RetryExhaustedError: If all operations fail (unless suppress_errors=True)
        """
        operations = [primary] + fallbacks
        errors: list[Exception] = []

        for idx, operation in enumerate(operations):
            operation_name = getattr(operation, '__name__', f'<operation_{idx}>')
            is_primary = idx == 0

            try:
                if is_primary:
                    self.logger.debug(f"Trying primary operation: {operation_name}")
                else:
                    self.logger.info(
                        f"Primary failed, trying fallback {idx}/{len(fallbacks)}: {operation_name}"
                    )

                result = operation(*args, **kwargs)

                if not is_primary:
                    self.logger.info(
                        f"Fallback {idx} succeeded: {operation_name}",
                        extra={'fallback_index': idx, 'operation': operation_name}
                    )

                return result

            except Exception as e:
                errors.append(e)
                self.logger.warning(
                    f"{'Primary' if is_primary else f'Fallback {idx}'} operation failed: {e}",
                    extra={
                        'is_primary': is_primary,
                        'fallback_index': idx if not is_primary else None,
                        'operation': operation_name,
                        'error_type': type(e).__name__,
                    }
                )

        # All operations failed
        if self.suppress_errors:
            self.logger.error(
                f"All {len(operations)} operations failed (errors suppressed)",
                extra={'total_operations': len(operations)}
            )
            return None  # type: ignore

        last_error = errors[-1] if errors else None
        raise RetryExhaustedError(
            f"All {len(operations)} operations failed (primary + {len(fallbacks)} fallbacks)",
            attempted_providers=[getattr(op, '__name__', f'<operation_{i}>') for i, op in enumerate(operations)],
            last_error=last_error,
            total_attempts=len(operations)
        )

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
            RetryExhaustedError: If all operations fail (unless suppress_errors=True)
        """
        operations = [primary] + fallbacks
        errors: list[Exception] = []

        for idx, operation in enumerate(operations):
            operation_name = getattr(operation, '__name__', f'<operation_{idx}>')
            is_primary = idx == 0

            try:
                if is_primary:
                    self.logger.debug(f"Trying primary operation: {operation_name}")
                else:
                    self.logger.info(
                        f"Primary failed, trying fallback {idx}/{len(fallbacks)}: {operation_name}"
                    )

                result = await operation(*args, **kwargs)

                if not is_primary:
                    self.logger.info(
                        f"Fallback {idx} succeeded: {operation_name}",
                        extra={'fallback_index': idx, 'operation': operation_name}
                    )

                return result

            except Exception as e:
                errors.append(e)
                self.logger.warning(
                    f"{'Primary' if is_primary else f'Fallback {idx}'} operation failed: {e}",
                    extra={
                        'is_primary': is_primary,
                        'fallback_index': idx if not is_primary else None,
                        'operation': operation_name,
                        'error_type': type(e).__name__,
                    }
                )

        # All operations failed
        if self.suppress_errors:
            self.logger.error(
                f"All {len(operations)} operations failed (errors suppressed)",
                extra={'total_operations': len(operations)}
            )
            return None  # type: ignore

        last_error = errors[-1] if errors else None
        raise RetryExhaustedError(
            f"All {len(operations)} operations failed (primary + {len(fallbacks)} fallbacks)",
            attempted_providers=[getattr(op, '__name__', f'<operation_{i}>') for i, op in enumerate(operations)],
            last_error=last_error,
            total_attempts=len(operations)
        )


# Convenience functions for backward compatibility

def with_fallback(
    primary: Callable[..., T],
    fallbacks: list[Callable[..., T]],
    *args: Any,
    logger_instance: Optional[logging.Logger] = None,
    **kwargs: Any
) -> T:
    """Execute operation with fallback chain.

    Convenience function that uses FallbackChain internally.

    Args:
        primary: Primary operation
        fallbacks: List of fallback operations
        *args: Positional arguments
        logger_instance: Logger instance
        **kwargs: Keyword arguments

    Returns:
        Result from first successful operation
    """
    chain = FallbackChain(logger_instance=logger_instance)
    return chain.execute(primary, fallbacks, *args, **kwargs)


async def with_fallback_async(
    primary: Callable[..., T],
    fallbacks: list[Callable[..., T]],
    *args: Any,
    logger_instance: Optional[logging.Logger] = None,
    **kwargs: Any
) -> T:
    """Execute async operation with fallback chain.

    Convenience function that uses FallbackChain internally.

    Args:
        primary: Primary async operation
        fallbacks: List of fallback async operations
        *args: Positional arguments
        logger_instance: Logger instance
        **kwargs: Keyword arguments

    Returns:
        Result from first successful operation
    """
    chain = FallbackChain(logger_instance=logger_instance)
    return await chain.execute_async(primary, fallbacks, *args, **kwargs)


def graceful_degrade(
    operation: Callable[..., T],
    on_error: Callable[..., T],
    *args: Any,
    degraded_message: Optional[str] = None,
    logger_instance: Optional[logging.Logger] = None,
    **kwargs: Any
) -> T:
    """Execute operation with graceful degradation.

    Tries operation, falls back to on_error callback if it fails.

    Args:
        operation: Primary operation to try
        on_error: Callback to execute on error
        *args: Positional arguments for operation
        degraded_message: Message to log when degrading
        logger_instance: Logger instance
        **kwargs: Keyword arguments for operation

    Returns:
        Result from operation or on_error callback
    """
    log = logger_instance or logger

    try:
        return operation(*args, **kwargs)
    except Exception as e:
        if degraded_message:
            log.warning(degraded_message, extra={'error': str(e)})
        else:
            log.warning(f"Degrading after error: {e}")

        return on_error(*args, **kwargs)
