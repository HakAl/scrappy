"""Process-local provider fallback counters."""

from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderFallbackMetricsSnapshot:
    """Immutable snapshot of provider fallback counters."""

    provider_fallbacks_total: dict[tuple[str, str, str], int]
    provider_failure_unknown_total: dict[tuple[str, str], int]
    provider_selection_exhausted_total: dict[str, int]


class ProviderFallbackMetrics:
    """Thread-safe process-local counters for provider fallback behavior."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._fallbacks: dict[tuple[str, str, str], int] = {}
        self._unknown_failures: dict[tuple[str, str], int] = {}
        self._selection_exhausted: dict[str, int] = {}

    def record_fallback(
        self,
        *,
        from_provider: str,
        to_provider: str,
        failure_kind: str,
    ) -> None:
        """Increment successful fallback counter."""
        key = (from_provider, to_provider, failure_kind)
        with self._lock:
            self._fallbacks[key] = self._fallbacks.get(key, 0) + 1

    def record_unknown_failure(
        self,
        *,
        provider: str,
        error_type: str,
    ) -> None:
        """Increment UNKNOWN-classification counter."""
        key = (provider or "unknown", error_type or "unknown")
        with self._lock:
            self._unknown_failures[key] = self._unknown_failures.get(key, 0) + 1

    def record_selection_exhausted(self, *, selection_type: str) -> None:
        """Increment selection exhaustion counter."""
        key = selection_type or "unknown"
        with self._lock:
            self._selection_exhausted[key] = self._selection_exhausted.get(key, 0) + 1

    def snapshot(self) -> ProviderFallbackMetricsSnapshot:
        """Return a point-in-time copy of all counters."""
        with self._lock:
            return ProviderFallbackMetricsSnapshot(
                provider_fallbacks_total=dict(self._fallbacks),
                provider_failure_unknown_total=dict(self._unknown_failures),
                provider_selection_exhausted_total=dict(self._selection_exhausted),
            )

    def reset(self) -> None:
        """Clear all counters for tests and process-local resets."""
        with self._lock:
            self._fallbacks.clear()
            self._unknown_failures.clear()
            self._selection_exhausted.clear()


# This singleton is process-local. Tests that read counters must call reset()
# before assertions to avoid cross-test leakage. Do not assume cumulative values
# across pytest-xdist workers or process boundaries.
provider_fallback_metrics = ProviderFallbackMetrics()


def get_provider_fallback_metrics_snapshot() -> ProviderFallbackMetricsSnapshot:
    """Return process-local provider fallback metrics."""
    return provider_fallback_metrics.snapshot()
