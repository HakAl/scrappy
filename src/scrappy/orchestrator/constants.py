"""
Delegation Configuration - Centralized constants for LLM delegation.

This module contains all magic numbers extracted from delegation and orchestration
code, following the principle: "Never use magic numbers, always use named constants."

All constants are module-level for easy import and use across the codebase.
"""

# ===== Request Configuration =====

# Default maximum tokens in LLM responses
# Used when no explicit max_tokens is specified
DEFAULT_MAX_TOKENS = 1000

# Default sampling temperature (0.0 = deterministic, 1.0 = creative)
# Used when no explicit temperature is specified
DEFAULT_TEMPERATURE = 0.7

# Default provider to use when none specified
# groq is used as the default due to its speed and reliability
DEFAULT_PROVIDER = 'groq'


# ===== Retry Configuration =====

# Maximum number of retry attempts per provider before fallback
# Used in RetryOrchestrator for exponential backoff
DEFAULT_MAX_RETRIES = 3

# Base for exponential backoff calculation (2^attempt * multiplier)
# Used in RetryOrchestrator to calculate wait time between retries
EXPONENTIAL_BACKOFF_BASE = 2

# Multiplier for exponential backoff in seconds
# Actual wait time = (EXPONENTIAL_BACKOFF_BASE ^ attempt) * EXPONENTIAL_BACKOFF_MULTIPLIER
# Examples: attempt 0 = 0.5s, attempt 1 = 1.0s, attempt 2 = 2.0s
EXPONENTIAL_BACKOFF_MULTIPLIER = 0.5


# ===== Batch Configuration =====

# Maximum number of concurrent requests in batch/parallel execution
# Used in BatchScheduler and DelegationManager.batch_delegate_async
DEFAULT_MAX_CONCURRENT = 5


# ===== Rate Limit Configuration =====

# Default quota remaining threshold for proactive limit checking
# If remaining requests <= this value, provider is considered exhausted
DEFAULT_QUOTA_THRESHOLD = 100


# ===== Timeout Configuration =====

# Default timeout for LLM requests in seconds
# Note: Currently not enforced in the code, but available for future use
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0
