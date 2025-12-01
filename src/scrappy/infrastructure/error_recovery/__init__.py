"""
Unified error recovery infrastructure.

This package consolidates the three separate error recovery systems
that previously existed in the codebase:
1. CLI error recovery (cli/error_recovery/)
2. Orchestrator retry (orchestrator/retry_orchestrator.py)
3. Agent tool retry (agent_tools/tools/command_tool.py)

All implementations now use shared protocols, strategies, and configuration.

Example usage:

    from infrastructure.error_recovery import (
        ExponentialBackoffRetry,
        CircuitBreaker,
        FallbackChain,
        RetryConfig,
    )

    # Configure retry
    config = RetryConfig(max_retries=5, base_delay=0.5)
    retry = ExponentialBackoffRetry(config=config)

    # Use retry
    result = retry.execute(make_api_call, provider="groq")

    # Use circuit breaker
    circuit = CircuitBreaker(name="groq_api")
    result = circuit.call(make_api_call)

    # Use fallback chain
    fallback = FallbackChain()
    result = fallback.execute(
        primary=call_groq,
        fallbacks=[call_openai, call_claude],
    )

Backward compatibility:

    # Old-style convenience functions still work
    from infrastructure.error_recovery import retry_operation, with_fallback

    result = retry_operation(func, max_retries=3, backoff=True)
    result = with_fallback(primary, [fallback1, fallback2])
"""

# Protocols
from .protocols import (
    RetryStrategyProtocol,
    CircuitBreakerProtocol,
    FallbackStrategyProtocol,
    ErrorRecoveryProtocol,
    ErrorContextProtocol,
    RecoveryAction,
    ErrorSeverity,
    ErrorCategory,
)

# Configuration
from .config import (
    RetryConfig,
    CircuitBreakerConfig,
    ErrorRecoveryConfig,
    DEFAULT_RETRY_CONFIG,
    AGGRESSIVE_RETRY_CONFIG,
    CONSERVATIVE_RETRY_CONFIG,
    DEFAULT_CIRCUIT_BREAKER_CONFIG,
    LENIENT_CIRCUIT_BREAKER_CONFIG,
    STRICT_CIRCUIT_BREAKER_CONFIG,
)

# Strategies
from .retry import (
    ExponentialBackoffRetry,
    retry_operation,
    retry_operation_async,
)

from .circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitStats,
)

from .fallback import (
    FallbackChain,
    with_fallback,
    with_fallback_async,
    graceful_degrade,
)

__all__ = [
    # Protocols
    'RetryStrategyProtocol',
    'CircuitBreakerProtocol',
    'FallbackStrategyProtocol',
    'ErrorRecoveryProtocol',
    'ErrorContextProtocol',
    'RecoveryAction',
    'ErrorSeverity',
    'ErrorCategory',

    # Configuration
    'RetryConfig',
    'CircuitBreakerConfig',
    'ErrorRecoveryConfig',
    'DEFAULT_RETRY_CONFIG',
    'AGGRESSIVE_RETRY_CONFIG',
    'CONSERVATIVE_RETRY_CONFIG',
    'DEFAULT_CIRCUIT_BREAKER_CONFIG',
    'LENIENT_CIRCUIT_BREAKER_CONFIG',
    'STRICT_CIRCUIT_BREAKER_CONFIG',

    # Retry strategies
    'ExponentialBackoffRetry',
    'retry_operation',
    'retry_operation_async',

    # Circuit breaker
    'CircuitBreaker',
    'CircuitState',
    'CircuitStats',

    # Fallback strategies
    'FallbackChain',
    'with_fallback',
    'with_fallback_async',
    'graceful_degrade',
]
