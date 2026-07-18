"""
Error recovery strategies for CLI operations.

This module provides CLI-specific error recovery with backward compatibility.
For new code, consider using infrastructure.error_recovery directly.
"""

from .fallback import with_fallback, fallback_providers, graceful_degrade
from .context import error_recovery_context, ErrorRecoveryContext


__all__ = [
    # Fallback strategies
    'with_fallback',
    'fallback_providers',
    'graceful_degrade',
    # Context managers
    'error_recovery_context',
    'ErrorRecoveryContext',
]
