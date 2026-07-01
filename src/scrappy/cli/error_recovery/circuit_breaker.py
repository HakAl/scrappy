"""
Circuit breaker pattern for preventing cascade failures.

This module provides a circuit breaker implementation that prevents
repeated calls to a failing service, allowing time for recovery.
"""

import logging
import time
from typing import Any, Callable, Optional

from ..exceptions import ProviderError


class CircuitBreaker:
    """
    Circuit breaker pattern for preventing cascade failures.

    The circuit opens after a threshold of failures, preventing further
    calls until a reset timeout expires.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: float = 60.0,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            reset_timeout: Seconds to wait before trying again
            logger: Optional logger
        """
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.logger = logger

        self._failures = 0
        self._state = "closed"  # closed, open, half-open
        self._last_failure_time = 0.0

    @property
    def is_open(self) -> bool:
        """Check if circuit breaker is in open state.

        When the circuit is open, calls will be blocked to prevent cascade
        failures. After the reset timeout expires, the circuit transitions
        to half-open state to allow a test call.

        Returns:
            True if circuit is open and blocking calls, False otherwise.

        Side Effects:
            - May transition circuit from "open" to "half-open" state if the
              reset timeout has elapsed since the last failure
        """
        if self._state == "open":
            # Check if reset timeout has passed
            if time.time() - self._last_failure_time >= self.reset_timeout:
                self._state = "half-open"
                return False
            return True
        return False

    def call(self, func: Callable) -> Any:
        """Execute function through circuit breaker.

        Attempts to execute the function if the circuit is not open. On success,
        resets the failure counter and closes the circuit. On failure, increments
        the failure counter and may open the circuit.

        Args:
            func: Zero-argument callable to execute.

        Returns:
            The return value of func() if successful.

        Raises:
            ProviderError: If circuit is open due to too many recent failures.
            Exception: Any exception raised by func() is re-raised after updating
                circuit state.

        Side Effects:
            - On success: Resets _failures to 0, sets _state to "closed"
            - On failure: Increments _failures, updates _last_failure_time,
              may set _state to "open" if threshold reached
            - Logs state changes if logger is configured
        """
        if self.is_open:
            raise ProviderError(
                "Circuit breaker is open - too many recent failures",
                provider="circuit_breaker"
            )

        try:
            result = func()

            # Success - reset failures
            if self._state == "half-open":
                if self.logger:
                    self.logger.info("Circuit breaker closed after successful call")
            self._state = "closed"
            self._failures = 0

            return result

        except Exception:
            self._failures += 1
            self._last_failure_time = time.time()

            if self._failures >= self.failure_threshold:
                self._state = "open"
                if self.logger:
                    self.logger.warning(
                        f"Circuit breaker opened after {self._failures} failures"
                    )

            raise
