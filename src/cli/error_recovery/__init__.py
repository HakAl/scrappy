"""
Error recovery strategies for CLI operations.

This module provides CLI-specific error recovery with backward compatibility.
For new code, consider using infrastructure.error_recovery directly.
"""

# Import from local CLI implementations (maintain backward compatibility)
from .retry import retry_operation, safe_operation_with_recovery
from .fallback import with_fallback, fallback_providers, graceful_degrade
from .circuit_breaker import CircuitBreaker
from .context import error_recovery_context, ErrorRecoveryContext


__all__ = [
    # Retry strategies
    'retry_operation',
    'safe_operation_with_recovery',
    # Fallback strategies
    'with_fallback',
    'fallback_providers',
    'graceful_degrade',
    # Circuit breaker
    'CircuitBreaker',
    # Context managers
    'error_recovery_context',
    'ErrorRecoveryContext',
]
