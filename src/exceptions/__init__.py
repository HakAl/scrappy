"""Domain exceptions for the orchestration framework.

This package contains domain-specific exception hierarchies for different
components of the system. Using domain exceptions instead of generic
Exception provides better error semantics and type-safe exception handling.
"""

from .delegation import (
    DelegationError,
    RetryExhaustedError,
    CacheError,
    ProviderNotFoundError,
    RateLimitExceededError,
    InvalidRequestError,
    PromptAugmentationError,
    BatchSchedulingError,
    ProviderExecutionError,
)

__all__ = [
    "DelegationError",
    "RetryExhaustedError",
    "CacheError",
    "ProviderNotFoundError",
    "RateLimitExceededError",
    "InvalidRequestError",
    "PromptAugmentationError",
    "BatchSchedulingError",
    "ProviderExecutionError",
]
