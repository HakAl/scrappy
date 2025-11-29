"""
Fallback strategies for provider failures.

This module provides fallback mechanisms for trying alternative providers
or operations when the primary fails, including graceful degradation.
"""

import logging
from typing import Any, Callable, List, Optional

from ..exceptions import CLIError


def with_fallback(
    primary: Callable,
    fallbacks: List[Callable],
    logger: Optional[logging.Logger] = None
) -> Any:
    """
    Try primary operation, falling back to alternatives on failure.

    Args:
        primary: Primary operation to try
        fallbacks: List of fallback operations
        logger: Optional logger for logging fallbacks

    Returns:
        Result from first successful operation

    Raises:
        CLIError: If all operations fail
    """
    all_operations = [primary] + fallbacks
    last_exception = None

    for i, operation in enumerate(all_operations):
        try:
            return operation()
        except Exception as e:
            last_exception = e
            if logger:
                if i == 0:
                    logger.warning(f"Primary operation failed: {e}, trying fallback")
                else:
                    logger.warning(f"Fallback {i} failed: {e}")

    raise CLIError(
        f"All operations failed. Last error: {last_exception}",
        original=last_exception
    )


def fallback_providers(
    operation: Callable[[str], Any],
    primary: str,
    orchestrator: Any,
    logger: Optional[logging.Logger] = None
) -> Any:
    """
    Try operation with primary provider, falling back to alternatives.

    Args:
        operation: Operation that takes provider name
        primary: Primary provider name
        orchestrator: Orchestrator with list_available method
        logger: Optional logger

    Returns:
        Result from first successful provider
    """
    providers = orchestrator.list_available()

    # Ensure primary is first
    if primary in providers:
        providers = [primary] + [p for p in providers if p != primary]

    last_exception = None

    for provider in providers:
        try:
            return operation(provider)
        except Exception as e:
            last_exception = e
            if logger:
                logger.warning(f"Provider {provider} failed: {e}")

    raise CLIError(
        f"All providers failed. Last error: {last_exception}",
        original=last_exception
    )


def graceful_degrade(
    operation: Callable,
    on_error: Callable[[Exception], Any],
    io: Optional[Any] = None,
    degraded_message: Optional[str] = None
) -> Any:
    """
    Execute operation with graceful degradation on failure.

    Args:
        operation: Primary operation
        on_error: Handler that returns partial/degraded result
        io: Optional IO interface for user notification
        degraded_message: Message to display on degradation

    Returns:
        Full result or degraded result
    """
    try:
        return operation()
    except Exception as e:
        result = on_error(e)

        if io and degraded_message:
            io.secho(degraded_message, fg=io.theme.warning)
        elif io:
            io.secho("Operating in degraded mode due to error.", fg=io.theme.warning)

        return result
