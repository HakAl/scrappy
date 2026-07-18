"""Substring classification rules for LiteLLM provider errors.

Isolates the ordered predicate table from litellm_service so the
precedence contract is pinned and testable in isolation. Import-light:
this module must not import litellm or any other heavy dependency.
"""

from enum import Enum
from typing import Dict, Type

from scrappy.infrastructure.exceptions.failure_kinds import FailureKind
from scrappy.infrastructure.exceptions.provider_errors import (
    AuthenticationError,
    NetworkError,
    ProviderError,
    ProviderExecutionError,
    RateLimitError,
    TimeoutError,
)


class LiteLLMErrorRule(Enum):
    """Ordered classification rules for raw LiteLLM error text."""

    AUTH = "auth"
    PAYMENT = "payment"
    RATE_LIMIT = "rate_limit"
    CONNECTION = "connection"
    TIMEOUT = "timeout"
    CONTENT_FILTER = "content_filter"
    MODEL_NOT_FOUND = "model_not_found"
    SERVICE_UNAVAILABLE = "service_unavailable"
    BAD_REQUEST = "bad_request"
    SERVER_ERROR = "server_error"
    UNKNOWN = "unknown"


def classify_litellm_error(error: Exception) -> LiteLLMErrorRule:
    """Classify a raw LiteLLM exception by its text and type name.

    The predicates and their order are a pinned contract: earlier rules
    win over later ones.
    """
    error_msg = str(error).lower()
    error_type = type(error).__name__

    # Authentication errors
    if "auth" in error_type.lower() or "401" in str(error) or "unauthorized" in error_msg:
        return LiteLLMErrorRule.AUTH

    # Payment/account errors
    if (
        "402" in str(error)
        or "payment" in error_msg
        or "billing" in error_msg
        or "insufficient_quota" in error_msg
    ):
        return LiteLLMErrorRule.PAYMENT

    # Rate limiting
    if "rate" in error_type.lower() or "429" in str(error) or "rate limit" in error_msg or "quota" in error_msg:
        return LiteLLMErrorRule.RATE_LIMIT

    # Connection errors
    if "connection" in error_type.lower() or "connection" in error_msg or "unreachable" in error_msg:
        return LiteLLMErrorRule.CONNECTION

    # Timeout errors
    if "timeout" in error_type.lower() or "timeout" in error_msg or "timed out" in error_msg:
        return LiteLLMErrorRule.TIMEOUT

    # Content filtering / safety errors
    if "content" in error_msg and ("filter" in error_msg or "blocked" in error_msg or "safety" in error_msg):
        return LiteLLMErrorRule.CONTENT_FILTER

    # Model not found
    if (
        "deprecated" in error_msg
        or ("model" in error_msg and ("not found" in error_msg or "unknown" in error_msg or "invalid" in error_msg))
    ):
        return LiteLLMErrorRule.MODEL_NOT_FOUND

    # Service unavailable
    if "503" in str(error) or "service unavailable" in error_msg or "overloaded" in error_msg:
        return LiteLLMErrorRule.SERVICE_UNAVAILABLE

    # Bad request (400) - often malformed input
    if "400" in str(error) or "bad request" in error_msg:
        return LiteLLMErrorRule.BAD_REQUEST

    # Server errors (500)
    if "500" in str(error) or "internal server error" in error_msg:
        return LiteLLMErrorRule.SERVER_ERROR

    return LiteLLMErrorRule.UNKNOWN


RULE_TO_FAILURE_KIND: Dict[LiteLLMErrorRule, FailureKind] = {
    LiteLLMErrorRule.AUTH: FailureKind.AUTH,
    LiteLLMErrorRule.PAYMENT: FailureKind.PAYMENT_REQUIRED,
    LiteLLMErrorRule.RATE_LIMIT: FailureKind.RATE_LIMIT,
    LiteLLMErrorRule.CONNECTION: FailureKind.NETWORK,
    LiteLLMErrorRule.TIMEOUT: FailureKind.TIMEOUT,
    LiteLLMErrorRule.CONTENT_FILTER: FailureKind.CONTENT_REFUSED,
    LiteLLMErrorRule.MODEL_NOT_FOUND: FailureKind.DEPRECATED,
    LiteLLMErrorRule.SERVICE_UNAVAILABLE: FailureKind.SERVER_ERROR,
    LiteLLMErrorRule.BAD_REQUEST: FailureKind.UNKNOWN,
    LiteLLMErrorRule.SERVER_ERROR: FailureKind.SERVER_ERROR,
    LiteLLMErrorRule.UNKNOWN: FailureKind.UNKNOWN,
}

RULE_TO_EXCEPTION: Dict[LiteLLMErrorRule, Type[ProviderError]] = {
    LiteLLMErrorRule.AUTH: AuthenticationError,
    LiteLLMErrorRule.PAYMENT: ProviderExecutionError,
    LiteLLMErrorRule.RATE_LIMIT: RateLimitError,
    LiteLLMErrorRule.CONNECTION: NetworkError,
    LiteLLMErrorRule.TIMEOUT: TimeoutError,
    LiteLLMErrorRule.CONTENT_FILTER: ProviderExecutionError,
    LiteLLMErrorRule.MODEL_NOT_FOUND: ProviderExecutionError,
    LiteLLMErrorRule.SERVICE_UNAVAILABLE: ProviderExecutionError,
    LiteLLMErrorRule.BAD_REQUEST: ProviderExecutionError,
    LiteLLMErrorRule.SERVER_ERROR: ProviderExecutionError,
    LiteLLMErrorRule.UNKNOWN: ProviderExecutionError,
}
