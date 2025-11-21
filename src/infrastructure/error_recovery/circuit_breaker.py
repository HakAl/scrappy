"""
Circuit breaker implementation.

Enhanced version with persistence support and proper state management.
Prevents cascading failures by stopping calls to failing services.
"""

from typing import Callable, TypeVar, Any, Optional
import time
import asyncio
import logging
from enum import Enum
from dataclasses import dataclass, asdict
import json
from pathlib import Path

from infrastructure.error_recovery.protocols import CircuitBreakerProtocol
from infrastructure.error_recovery.config import (
    CircuitBreakerConfig,
    DEFAULT_CIRCUIT_BREAKER_CONFIG
)
from infrastructure.exceptions import CircuitBreakerOpenError, BaseError

T = TypeVar('T')

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Blocking calls
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitStats:
    """Circuit breaker statistics."""
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    total_calls: int = 0
    total_failures: int = 0
    total_successes: int = 0
    state: str = CircuitState.CLOSED.value
    opened_at: Optional[float] = None


class CircuitBreaker:
    """Circuit breaker with state management and persistence.

    Implements CircuitBreakerProtocol with enhanced features.
    """

    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
        persistence_path: Optional[Path] = None,
        logger_instance: Optional[logging.Logger] = None
    ):
        """Initialize circuit breaker.

        Args:
            name: Unique name for this circuit
            config: Circuit breaker configuration
            persistence_path: Path to persist circuit state
            logger_instance: Logger instance
        """
        self.name = name
        self.config = config or DEFAULT_CIRCUIT_BREAKER_CONFIG
        self.persistence_path = persistence_path
        self.logger = logger_instance or logger

        self._state = CircuitState.CLOSED
        self._stats = CircuitStats()
        self._half_open_calls = 0

        # Load persisted state if available
        if persistence_path:
            self._load_state()

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (blocking calls)."""
        self._update_state()
        return self._state == CircuitState.OPEN

    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        self._update_state()
        return self._state == CircuitState.CLOSED

    @property
    def is_half_open(self) -> bool:
        """Check if circuit is half-open (testing recovery)."""
        self._update_state()
        return self._state == CircuitState.HALF_OPEN

    @property
    def state(self) -> CircuitState:
        """Get current state."""
        self._update_state()
        return self._state

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
        self._update_state()

        if self._state == CircuitState.OPEN:
            self._raise_open_error()

        if self._state == CircuitState.HALF_OPEN:
            if self._half_open_calls >= self.config.half_open_max_calls:
                self._raise_open_error()
            self._half_open_calls += 1

        self._stats.total_calls += 1

        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except Exception as e:
            self.record_failure(e)
            raise

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
        self._update_state()

        if self._state == CircuitState.OPEN:
            self._raise_open_error()

        if self._state == CircuitState.HALF_OPEN:
            if self._half_open_calls >= self.config.half_open_max_calls:
                self._raise_open_error()
            self._half_open_calls += 1

        self._stats.total_calls += 1

        try:
            result = await func(*args, **kwargs)
            self.record_success()
            return result
        except Exception as e:
            self.record_failure(e)
            raise

    def record_success(self) -> None:
        """Record successful call."""
        self._stats.success_count += 1
        self._stats.total_successes += 1
        self._stats.last_success_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            self.logger.info(
                f"Circuit {self.name}: Success in half-open "
                f"({self._stats.success_count}/{self.config.success_threshold})"
            )
            if self._stats.success_count >= self.config.success_threshold:
                self._transition_to_closed()
        else:
            # In closed state, reset failure count on success
            self._stats.failure_count = 0

        self._persist_state()

    def record_failure(self, exception: Exception) -> None:
        """Record failed call.

        Args:
            exception: The exception that occurred
        """
        self._stats.failure_count += 1
        self._stats.total_failures += 1
        self._stats.last_failure_time = time.time()

        self.logger.warning(
            f"Circuit {self.name}: Failure recorded "
            f"({self._stats.failure_count}/{self.config.failure_threshold}) - {exception}"
        )

        if self._state == CircuitState.HALF_OPEN:
            # Any failure in half-open returns to open
            self._transition_to_open()
        elif self._state == CircuitState.CLOSED:
            if self._stats.failure_count >= self.config.failure_threshold:
                self._transition_to_open()

        self._persist_state()

    def reset(self) -> None:
        """Manually reset circuit to closed state."""
        self.logger.info(f"Circuit {self.name}: Manual reset to closed")
        self._stats.failure_count = 0
        self._stats.success_count = 0
        self._half_open_calls = 0
        self._transition_to_closed()
        self._persist_state()

    def _update_state(self) -> None:
        """Update state based on time and conditions."""
        if self._state == CircuitState.OPEN:
            if self._stats.opened_at is not None:
                elapsed = time.time() - self._stats.opened_at
                if elapsed >= self.config.reset_timeout:
                    self._transition_to_half_open()

    def _transition_to_open(self) -> None:
        """Transition to open state."""
        self._state = CircuitState.OPEN
        self._stats.state = CircuitState.OPEN.value
        self._stats.opened_at = time.time()
        self._half_open_calls = 0

        self.logger.warning(
            f"Circuit {self.name}: OPENED after {self._stats.failure_count} failures. "
            f"Will try half-open in {self.config.reset_timeout}s"
        )

    def _transition_to_half_open(self) -> None:
        """Transition to half-open state."""
        self._state = CircuitState.HALF_OPEN
        self._stats.state = CircuitState.HALF_OPEN.value
        self._stats.failure_count = 0
        self._stats.success_count = 0
        self._half_open_calls = 0

        self.logger.info(
            f"Circuit {self.name}: Entering HALF-OPEN state "
            f"(allowing {self.config.half_open_max_calls} test calls)"
        )

    def _transition_to_closed(self) -> None:
        """Transition to closed state."""
        self._state = CircuitState.CLOSED
        self._stats.state = CircuitState.CLOSED.value
        self._stats.failure_count = 0
        self._stats.success_count = 0
        self._stats.opened_at = None
        self._half_open_calls = 0

        self.logger.info(f"Circuit {self.name}: CLOSED - normal operation resumed")

    def _raise_open_error(self) -> None:
        """Raise circuit breaker open error."""
        wait_time = 0.0
        if self._stats.opened_at is not None:
            elapsed = time.time() - self._stats.opened_at
            wait_time = max(0, self.config.reset_timeout - elapsed)

        raise CircuitBreakerOpenError(
            f"Circuit breaker '{self.name}' is open",
            circuit_name=self.name,
            failure_count=self._stats.total_failures,
            reset_timeout=wait_time,
        )

    def _persist_state(self) -> None:
        """Persist circuit state to disk."""
        if not self.persistence_path:
            return

        try:
            self.persistence_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                'name': self.name,
                'stats': asdict(self._stats),
            }
            with open(self.persistence_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to persist circuit state: {e}")

    def _load_state(self) -> None:
        """Load circuit state from disk."""
        if not self.persistence_path or not self.persistence_path.exists():
            return

        try:
            with open(self.persistence_path, 'r') as f:
                data = json.load(f)

            stats_dict = data.get('stats', {})
            self._stats = CircuitStats(**stats_dict)

            # Restore state enum
            state_str = self._stats.state
            self._state = CircuitState(state_str)

            self.logger.info(
                f"Circuit {self.name}: Loaded state {self._state.value} "
                f"(failures: {self._stats.total_failures}, "
                f"successes: {self._stats.total_successes})"
            )

        except Exception as e:
            self.logger.warning(f"Failed to load circuit state, using defaults: {e}")

    def get_stats(self) -> dict:
        """Get circuit statistics.

        Returns:
            Dictionary of circuit statistics
        """
        self._update_state()
        return {
            'name': self.name,
            'state': self._state.value,
            'failure_count': self._stats.failure_count,
            'success_count': self._stats.success_count,
            'total_calls': self._stats.total_calls,
            'total_failures': self._stats.total_failures,
            'total_successes': self._stats.total_successes,
            'last_failure': self._stats.last_failure_time,
            'last_success': self._stats.last_success_time,
            'opened_at': self._stats.opened_at,
        }
