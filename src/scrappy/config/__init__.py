"""
Configuration module for LLM delegation system.

Exports all delegation-related configuration constants and config loaders.
"""

from .delegation import (
    # Request Configuration
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    DEFAULT_PROVIDER,

    # Retry Configuration
    DEFAULT_MAX_RETRIES,
    EXPONENTIAL_BACKOFF_BASE,
    EXPONENTIAL_BACKOFF_MULTIPLIER,

    # Batch Configuration
    DEFAULT_MAX_CONCURRENT,

    # Rate Limit Configuration
    DEFAULT_QUOTA_THRESHOLD,

    # Timeout Configuration
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
)
from .loaders import (
    FileConfigLoader,
    ChainedConfigLoader,
)
from .protocols import (
    ConfigLoaderProtocol,
    ConfigLoadError,
)

__all__ = [
    # Request Configuration
    'DEFAULT_MAX_TOKENS',
    'DEFAULT_TEMPERATURE',
    'DEFAULT_PROVIDER',

    # Retry Configuration
    'DEFAULT_MAX_RETRIES',
    'EXPONENTIAL_BACKOFF_BASE',
    'EXPONENTIAL_BACKOFF_MULTIPLIER',

    # Batch Configuration
    'DEFAULT_MAX_CONCURRENT',

    # Rate Limit Configuration
    'DEFAULT_QUOTA_THRESHOLD',

    # Timeout Configuration
    'DEFAULT_REQUEST_TIMEOUT_SECONDS',

    # Config Loading
    'ConfigLoaderProtocol',
    'ConfigLoadError',
    'FileConfigLoader',
    'ChainedConfigLoader',
]
