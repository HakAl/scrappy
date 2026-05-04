"""Provider failure classifications used for fallback policy."""

from enum import Enum


class FailureKind(Enum):
    """Semantic classification for provider and model failures."""

    RATE_LIMIT = "rate_limit"
    AUTH = "auth"
    PAYMENT_REQUIRED = "payment_required"
    DEPRECATED = "deprecated"
    SERVER_ERROR = "server_error"
    NETWORK = "network"
    TIMEOUT = "timeout"
    CONTENT_REFUSED = "content_refused"
    EXHAUSTED = "exhausted"
    UNKNOWN = "unknown"
