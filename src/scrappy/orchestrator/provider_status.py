"""
Provider status tracking for health monitoring and key validation.

Provides:
- ProviderStatusTracker: Tracks provider health from callbacks and health checks
- ProviderStatus: Status data for a single provider with rolling window metrics
- validate_api_key: Validate API key via LiteLLM (for wizard)
- run_health_check: Run health check for a model (for /status)

Used by:
- RateTrackingCallback: Records success/failure events
- SetupWizard: Validates API keys before saving
- /status command: Displays provider health
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any, Deque
import asyncio
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Rolling window size for metrics
DEFAULT_WINDOW_SIZE = 50


@dataclass
class RequestRecord:
    """Single request record for rolling window."""
    timestamp: datetime
    success: bool
    latency_ms: float
    tokens: int = 0
    error: Optional[str] = None


@dataclass
class ProviderStatus:
    """Status data for a single provider with rolling window metrics."""

    healthy: bool = True
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    last_error: Optional[str] = None
    last_latency_ms: Optional[float] = None
    request_count: int = 0
    error_count: int = 0
    total_tokens: int = 0

    # Rolling window of recent requests (not serialized directly)
    _recent_requests: Deque[RequestRecord] = field(
        default_factory=lambda: deque(maxlen=DEFAULT_WINDOW_SIZE)
    )

    @property
    def success_rate(self) -> float:
        """Calculate success rate from rolling window."""
        if not self._recent_requests:
            return 1.0 if self.healthy else 0.0
        successes = sum(1 for r in self._recent_requests if r.success)
        return successes / len(self._recent_requests)

    @property
    def avg_latency_ms(self) -> float:
        """Calculate average latency from successful requests in window."""
        successful = [r for r in self._recent_requests if r.success]
        if not successful:
            return self.last_latency_ms or 0.0
        return sum(r.latency_ms for r in successful) / len(successful)

    @property
    def window_tokens(self) -> int:
        """Total tokens in rolling window."""
        return sum(r.tokens for r in self._recent_requests)

    @property
    def window_size(self) -> int:
        """Number of requests in rolling window."""
        return len(self._recent_requests)

    def add_request(self, record: RequestRecord) -> None:
        """Add a request to the rolling window."""
        self._recent_requests.append(record)


@dataclass
class HealthCheckResult:
    """Result of a health check."""

    model: str
    healthy: bool
    latency_ms: Optional[float] = None
    error: Optional[str] = None


class ProviderStatusTracker:
    """
    Tracks provider health from callbacks and health checks.

    Real-time status is updated by RateTrackingCallback on each request.
    On-demand health checks can be run for the /status command.

    Features:
    - Rolling window metrics (last N requests per provider)
    - Persistence to user-level ~/.scrappy/provider_stats.json
    - Success rate and average latency calculations
    - Token tracking

    Thread-safe for use in async contexts.
    """

    def __init__(self, persist_path: Optional[Path] = None):
        """
        Initialize provider status tracker.

        Args:
            persist_path: Path for persistence file. If None, uses
                         ~/.scrappy/provider_stats.json
        """
        self._status: dict[str, ProviderStatus] = {}
        self._lock = asyncio.Lock()
        self._persist_path = persist_path or self._default_persist_path()
        self._load()

    def _default_persist_path(self) -> Path:
        """Get default persistence path (~/.scrappy/provider_stats.json)."""
        return Path.home() / ".scrappy" / "provider_stats.json"

    def on_success(
        self,
        provider: str,
        model: str,
        latency_ms: float,
        tokens: int = 0,
    ) -> None:
        """
        Record a successful request.

        Called by RateTrackingCallback after successful completion.

        Args:
            provider: Provider name (e.g., "groq")
            model: Full model ID (e.g., "groq/llama-3.1-8b-instant")
            latency_ms: Request latency in milliseconds
            tokens: Total tokens used (input + output)
        """
        if provider not in self._status:
            self._status[provider] = ProviderStatus()

        status = self._status[provider]
        status.healthy = True
        status.last_success = datetime.now()
        status.last_latency_ms = latency_ms
        status.request_count += 1
        status.total_tokens += tokens
        status.last_error = None

        # Add to rolling window
        status.add_request(RequestRecord(
            timestamp=datetime.now(),
            success=True,
            latency_ms=latency_ms,
            tokens=tokens,
        ))

        self._persist()

    def on_failure(
        self,
        provider: str,
        error: str,
        latency_ms: float = 0.0,
    ) -> None:
        """
        Record a failed request.

        Called by RateTrackingCallback after failed completion.

        Args:
            provider: Provider name (e.g., "groq")
            error: Error message
            latency_ms: Request latency in milliseconds
        """
        if provider not in self._status:
            self._status[provider] = ProviderStatus()

        status = self._status[provider]
        status.healthy = False
        status.last_failure = datetime.now()
        status.last_error = error
        status.error_count += 1

        # Add to rolling window
        status.add_request(RequestRecord(
            timestamp=datetime.now(),
            success=False,
            latency_ms=latency_ms,
            error=error,
        ))

        self._persist()

    def get_healthy_providers(self, min_success_rate: float = 0.5) -> list[str]:
        """
        Get providers meeting minimum success rate threshold.

        Args:
            min_success_rate: Minimum success rate (0.0 to 1.0)

        Returns:
            List of provider names with success rate >= threshold
        """
        return [
            name for name, status in self._status.items()
            if status.success_rate >= min_success_rate
        ]

    def get_status(self, provider: str) -> Optional[ProviderStatus]:
        """
        Get status for a provider.

        Args:
            provider: Provider name

        Returns:
            ProviderStatus or None if no data
        """
        return self._status.get(provider)

    def get_all_status(self) -> dict[str, ProviderStatus]:
        """
        Get status for all tracked providers.

        Returns:
            Dictionary mapping provider names to status
        """
        return dict(self._status)

    def is_healthy(self, provider: str) -> bool:
        """
        Check if provider is healthy.

        Args:
            provider: Provider name

        Returns:
            True if healthy or unknown (no data)
        """
        status = self._status.get(provider)
        return status.healthy if status else True

    async def run_health_checks(
        self,
        models: list[dict[str, Any]],
        timeout: float = 15.0,
    ) -> list[HealthCheckResult]:
        """
        Run health checks for configured models.

        Args:
            models: List of model configs from Router (with litellm_params)
            timeout: Timeout per check in seconds

        Returns:
            List of HealthCheckResult for each model
        """
        import litellm

        results = []
        for model_config in models:
            model_id = model_config["litellm_params"]["model"]
            api_key = model_config["litellm_params"].get("api_key")

            try:
                start = datetime.now()

                # LiteLLM ahealth_check expects model_params dict
                model_params = {
                    "model": model_id,
                    "api_key": api_key,
                    "timeout": timeout,
                }

                response = await litellm.ahealth_check(
                    model_params=model_params,
                    mode="chat",
                )
                elapsed = (datetime.now() - start).total_seconds() * 1000

                # Response has 'healthy_endpoints' and 'unhealthy_endpoints'
                healthy_endpoints = response.get("healthy_endpoints", [])
                unhealthy_endpoints = response.get("unhealthy_endpoints", [])

                healthy = len(healthy_endpoints) > 0
                error = None
                if unhealthy_endpoints:
                    endpoint = unhealthy_endpoints[0]
                    error = endpoint.get("error", "") if isinstance(endpoint, dict) else str(endpoint)

                results.append(HealthCheckResult(
                    model=model_id,
                    healthy=healthy,
                    latency_ms=elapsed if healthy else None,
                    error=error,
                ))

                # Update status tracker
                provider = model_id.split("/")[0] if "/" in model_id else "unknown"
                if healthy:
                    self.on_success(provider, model_id, elapsed)
                else:
                    self.on_failure(provider, error or "Health check failed")

            except Exception as e:
                results.append(HealthCheckResult(
                    model=model_id,
                    healthy=False,
                    error=str(e),
                ))

        return results

    def _load(self) -> None:
        """Load persisted stats from disk."""
        if not self._persist_path.exists():
            return

        try:
            data = json.loads(self._persist_path.read_text())
            for provider, stats_data in data.items():
                status = ProviderStatus(
                    healthy=stats_data.get("healthy", True),
                    last_success=datetime.fromisoformat(stats_data["last_success"])
                    if stats_data.get("last_success") else None,
                    last_failure=datetime.fromisoformat(stats_data["last_failure"])
                    if stats_data.get("last_failure") else None,
                    last_error=stats_data.get("last_error"),
                    last_latency_ms=stats_data.get("last_latency_ms"),
                    request_count=stats_data.get("request_count", 0),
                    error_count=stats_data.get("error_count", 0),
                    total_tokens=stats_data.get("total_tokens", 0),
                )
                # Restore rolling window
                for record_data in stats_data.get("recent_requests", []):
                    status.add_request(RequestRecord(
                        timestamp=datetime.fromisoformat(record_data["timestamp"]),
                        success=record_data["success"],
                        latency_ms=record_data["latency_ms"],
                        tokens=record_data.get("tokens", 0),
                        error=record_data.get("error"),
                    ))
                self._status[provider] = status
            logger.debug(f"Loaded provider stats for {len(self._status)} providers")
        except Exception as e:
            logger.warning(f"Failed to load provider stats: {e}")

    def _persist(self) -> None:
        """Persist stats to disk."""
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)

            data = {}
            for provider, status in self._status.items():
                data[provider] = {
                    "healthy": status.healthy,
                    "last_success": status.last_success.isoformat()
                    if status.last_success else None,
                    "last_failure": status.last_failure.isoformat()
                    if status.last_failure else None,
                    "last_error": status.last_error,
                    "last_latency_ms": status.last_latency_ms,
                    "request_count": status.request_count,
                    "error_count": status.error_count,
                    "total_tokens": status.total_tokens,
                    "recent_requests": [
                        {
                            "timestamp": r.timestamp.isoformat(),
                            "success": r.success,
                            "latency_ms": r.latency_ms,
                            "tokens": r.tokens,
                            "error": r.error,
                        }
                        for r in status._recent_requests
                    ],
                }

            self._persist_path.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.warning(f"Failed to persist provider stats: {e}")

    def reset_stats(self, provider: Optional[str] = None) -> None:
        """
        Reset statistics for one or all providers.

        Args:
            provider: Provider name to reset, or None to reset all
        """
        if provider:
            if provider in self._status:
                del self._status[provider]
        else:
            self._status.clear()
        self._persist()
