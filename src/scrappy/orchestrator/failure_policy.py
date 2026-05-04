"""Provider failure policy for model health and fallback decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from scrappy.infrastructure.exceptions.failure_kinds import FailureKind
from scrappy.infrastructure.exceptions.provider_errors import ProviderError

if TYPE_CHECKING:
    from .model_selection import ModelHealthState


class HealthScope(Enum):
    """Scope applied when marking model health after a failure."""

    NONE = "none"
    PER_MODEL = "per_model"
    PER_PROVIDER = "per_provider"


@dataclass(frozen=True)
class FailurePolicy:
    """Policy for a failure kind."""

    should_retry: bool
    scope: HealthScope
    cooldown_seconds: float


@dataclass(frozen=True)
class FailureRecord:
    """Failure summary entry for selection exhaustion."""

    kind: FailureKind
    provider: str | None
    retry_after: float | None
    message: str

    @classmethod
    def from_error(cls, model: str, error: ProviderError) -> "FailureRecord":
        """Build a record from a provider exception."""
        provider = error.provider_name or _provider_from_model(model)
        return cls(
            kind=error.failure_kind,
            provider=provider,
            retry_after=error.retry_after,
            message=str(error),
        )

    @classmethod
    def from_health_state(cls, model: str, state: "ModelHealthState") -> "FailureRecord":
        """Build a record from tracker health state."""
        return cls(
            kind=state.failure_kind,
            provider=_provider_from_model(model),
            retry_after=state.retry_after,
            message=f"{model} unavailable due to {state.failure_kind.value}",
        )


FAILURE_POLICIES: dict[FailureKind, FailurePolicy] = {
    FailureKind.RATE_LIMIT: FailurePolicy(True, HealthScope.PER_MODEL, 60.0),
    FailureKind.AUTH: FailurePolicy(True, HealthScope.PER_PROVIDER, 3600.0),
    FailureKind.PAYMENT_REQUIRED: FailurePolicy(True, HealthScope.PER_PROVIDER, 3600.0),
    FailureKind.NETWORK: FailurePolicy(True, HealthScope.PER_PROVIDER, 120.0),
    FailureKind.TIMEOUT: FailurePolicy(True, HealthScope.PER_MODEL, 60.0),
    FailureKind.SERVER_ERROR: FailurePolicy(True, HealthScope.PER_MODEL, 300.0),
    FailureKind.DEPRECATED: FailurePolicy(True, HealthScope.PER_MODEL, 86400.0),
    FailureKind.CONTENT_REFUSED: FailurePolicy(False, HealthScope.NONE, 0.0),
    FailureKind.EXHAUSTED: FailurePolicy(False, HealthScope.NONE, 0.0),
    FailureKind.UNKNOWN: FailurePolicy(False, HealthScope.NONE, 0.0),
}


def _validate_failure_policies() -> None:
    """Validate failure policy coverage and retry semantics at import time."""
    configured = set(FAILURE_POLICIES)
    expected = set(FailureKind)
    if configured != expected:
        missing = expected - configured
        extra = configured - expected
        raise RuntimeError(
            f"FAILURE_POLICIES mismatch: missing={missing}, extra={extra}"
        )

    for kind, policy in FAILURE_POLICIES.items():
        if policy.should_retry and policy.scope == HealthScope.NONE:
            raise RuntimeError(
                f"Inconsistent policy for {kind}: should_retry=True but scope=NONE"
            )


_validate_failure_policies()

SHOULD_RETRY_KINDS = frozenset(
    kind for kind, policy in FAILURE_POLICIES.items() if policy.should_retry
)


def get_failure_policy(kind: FailureKind) -> FailurePolicy:
    """Return the policy for a failure kind."""
    return FAILURE_POLICIES[kind]


def _provider_from_model(model: str) -> str | None:
    """Extract provider prefix from provider/model strings."""
    if "/" not in model:
        return None
    return model.split("/", 1)[0]
