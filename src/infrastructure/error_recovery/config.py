"""
Configuration for error recovery strategies.

Centralizes all retry, circuit breaker, and fallback configuration
to ensure consistency across the application.
"""

from typing import Optional
from dataclasses import dataclass, field


@dataclass
class RetryConfig:
    """Configuration for retry strategy.

    Attributes:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay for exponential backoff (seconds)
        multiplier: Multiplier for exponential backoff
        max_delay: Maximum delay between retries (seconds)
        jitter: Add random jitter to delays (prevents thundering herd)
    """

    max_retries: int = 3
    base_delay: float = 0.5
    multiplier: float = 2.0
    max_delay: float = 60.0
    jitter: bool = True

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number.

        Formula: min(base_delay * (multiplier ** attempt), max_delay)
        With optional jitter: delay * random(0.5, 1.5)

        Args:
            attempt: Attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        import random

        delay = min(
            self.base_delay * (self.multiplier ** attempt),
            self.max_delay
        )

        if self.jitter:
            # Add +/- 50% jitter
            delay *= random.uniform(0.5, 1.5)

        return delay


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker.

    Attributes:
        failure_threshold: Number of failures before opening circuit
        success_threshold: Number of successes in half-open before closing
        reset_timeout: Seconds to wait before trying half-open
        half_open_max_calls: Max calls allowed in half-open state
    """

    failure_threshold: int = 5
    success_threshold: int = 2
    reset_timeout: float = 60.0
    half_open_max_calls: int = 1


@dataclass
class ErrorRecoveryConfig:
    """Complete error recovery configuration.

    Combines retry, circuit breaker, and fallback settings.
    """

    retry: RetryConfig = field(default_factory=RetryConfig)
    circuit_breaker: Optional[CircuitBreakerConfig] = field(
        default_factory=CircuitBreakerConfig
    )
    enable_fallback: bool = True
    timeout_seconds: Optional[float] = 30.0


# Default configurations for different contexts

DEFAULT_RETRY_CONFIG = RetryConfig(
    max_retries=3,
    base_delay=0.5,
    multiplier=2.0,
    max_delay=60.0,
    jitter=True,
)

AGGRESSIVE_RETRY_CONFIG = RetryConfig(
    max_retries=5,
    base_delay=0.1,
    multiplier=1.5,
    max_delay=10.0,
    jitter=True,
)

CONSERVATIVE_RETRY_CONFIG = RetryConfig(
    max_retries=2,
    base_delay=1.0,
    multiplier=3.0,
    max_delay=30.0,
    jitter=False,
)

DEFAULT_CIRCUIT_BREAKER_CONFIG = CircuitBreakerConfig(
    failure_threshold=5,
    success_threshold=2,
    reset_timeout=60.0,
    half_open_max_calls=1,
)

LENIENT_CIRCUIT_BREAKER_CONFIG = CircuitBreakerConfig(
    failure_threshold=10,
    success_threshold=3,
    reset_timeout=30.0,
    half_open_max_calls=3,
)

STRICT_CIRCUIT_BREAKER_CONFIG = CircuitBreakerConfig(
    failure_threshold=3,
    success_threshold=1,
    reset_timeout=120.0,
    half_open_max_calls=1,
)
