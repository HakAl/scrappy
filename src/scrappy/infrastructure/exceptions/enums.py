"""
Error classification enums.

These enums are used throughout the error handling infrastructure
to classify and describe errors without creating circular dependencies.
"""

from enum import Enum


class RecoveryAction(Enum):
    """Actions that can be taken when an error occurs."""
    RETRY = "retry"
    FALLBACK = "fallback"
    ABORT = "abort"
    SKIP = "skip"
    ASK_USER = "ask_user"


class ErrorSeverity(Enum):
    """Severity levels for errors."""
    INFO = 1
    WARNING = 2
    ERROR = 3
    CRITICAL = 4


class ErrorCategory(Enum):
    """Categories of errors for classification."""
    VALIDATION = "validation"
    API = "api"
    FILE = "file"
    SYSTEM = "system"
    PARSE = "parse"
    TASK = "task"
    USER_INPUT = "user_input"
    NETWORK = "network"
    RATE_LIMIT = "rate_limit"
    AUTHENTICATION = "authentication"
    CANCELLATION = "cancellation"
