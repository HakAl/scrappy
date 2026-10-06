"""Rate limit tracker facade."""
from __future__ import annotations
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from .protocols import (
    StorageProtocol,
    PolicyProtocol,
    CalculatorProtocol,
    RecommenderProtocol,
)
from scrappy.orchestrator.provider_types import ProviderLimits
from ..config import OrchestratorConfig

logger = logging.getLogger(__name__)


class RateLimitTracker:
    """
    Rate limit tracking facade.

    Coordinates between storage, policy, calculator, and recommender.
    All heavy lifting is delegated to specialized components.

    This class implements UsageQueryProtocol so it can be passed to recommender.
    """

    def __init__(
        self,
        storage: StorageProtocol,
        policy: PolicyProtocol,
        calculator: CalculatorProtocol,
        recommender: RecommenderProtocol,
        auto_load: bool = False,
        config: Optional[OrchestratorConfig] = None,
    ):
        """
        Initialize tracker.

        Args:
            storage: Persistence layer
            policy: Reset policy
            calculator: Usage calculations
            recommender: Provider recommendation
            auto_load: If True, load data from storage on init
            config: OrchestratorConfig instance (creates default if None)
        """
        self._storage = storage
        self._policy = policy
        self._calc = calculator
        self._recommender = recommender

        if config is None:
            config = OrchestratorConfig()
        self.config = config

        self._usage: Dict[str, Any] = {}
        self._initialise_empty()

        if auto_load:
            self.restore_from_disk()

    def restore_from_disk(self) -> RateLimitTracker:
        """Load usage data from storage, guarding against malformed persisted state."""
        blob = self._storage.load()
        self._adopt_if_restorable(blob)
        return self

    async def restore_from_disk_async(self) -> RateLimitTracker:
        """Load usage data from storage asynchronously, with the same guard."""
        blob = await self._storage.load_async()
        self._adopt_if_restorable(blob)
        return self

    def _adopt_if_restorable(self, blob: Any) -> None:
        """Shared startup gate for both restore paths.

        storage.load() returns {} for a missing file, a parse error, or an on-disk
        "{}" -- the existing missing/empty sentinel -- which stays a silent no-op.
        Any other value is validated against the accepted-document contract before
        adoption: a malformed document is rejected as a no-op that preserves the
        current in-memory counters and does NOT overwrite the stored file (no
        _check_and_reset runs, so no save fires). Only accepted data is adopted and
        passed to the existing reset logic.
        """
        if isinstance(blob, dict) and not blob:
            return  # {} sentinel: silent no-op, exactly as before

        if self._is_restorable(blob):
            self._usage = blob
            self._check_and_reset()
        else:
            # Pathless, content-free warning: does not read self._storage.path
            # (not promised by StorageProtocol) and does not echo file content.
            logger.warning(
                "Ignoring malformed persisted rate-limit state; retaining current "
                "in-memory counters and not overwriting stored state"
            )

    # --- Accepted-document contract (foreign/corrupt-schema rejection) ----------

    # The eight per-model counters the tracker writes and its consumers require.
    _REQUIRED_MODEL_COUNTERS = (
        "requests_today",
        "requests_this_month",
        "tokens_today",
        "tokens_this_month",
        "input_tokens_today",
        "output_tokens_today",
        "total_requests",
        "total_tokens",
    )

    # The numeric provider-header keys consumed by the quota/limit paths. The parser
    # emits the 16 generic/day/hour/minute keys; remaining_requests_month is an
    # additional CONSUMED key (tracker.py get-remaining -> calculator) not emitted by
    # the parser. Each permits an int (bool excluded) or null; signed/zero accepted.
    _NUMERIC_HEADER_KEYS = (
        "remaining_requests",
        "remaining_requests_day",
        "remaining_requests_hour",
        "remaining_requests_minute",
        "remaining_requests_month",
        "remaining_tokens",
        "remaining_tokens_day",
        "remaining_tokens_hour",
        "remaining_tokens_minute",
        "limit_requests",
        "limit_requests_day",
        "limit_requests_hour",
        "limit_requests_minute",
        "limit_tokens",
        "limit_tokens_day",
        "limit_tokens_hour",
        "limit_tokens_minute",
    )

    def _is_restorable(self, blob: Any) -> bool:
        """Accept or reject the WHOLE persisted document before any adoption.

        Validates exactly the fields the current tracker writes and its consumers
        require. Does NOT coerce, salvage, or migrate; unknown metadata is retained
        opaque. Returns a single accept/reject boolean and mutates nothing.
        """
        if not isinstance(blob, dict):
            return False

        # last_reset is REQUIRED: a mapping with canonical, real-calendar stamps.
        last_reset = blob.get("last_reset")
        if not isinstance(last_reset, dict):
            return False
        if not self._is_daily_stamp(last_reset.get("daily")):
            return False
        if not self._is_monthly_stamp(last_reset.get("monthly")):
            return False

        # providers MAY be absent; when present it must be a mapping of
        # provider -> (model -> model_entry).
        if "providers" in blob:
            providers = blob["providers"]
            if not isinstance(providers, dict):
                return False
            for model_map in providers.values():
                if not isinstance(model_map, dict):
                    return False
                for entry in model_map.values():
                    if not self._is_model_entry(entry):
                        return False

        # provider_headers is an optional persisted key.
        if "provider_headers" in blob:
            provider_headers = blob["provider_headers"]
            if not isinstance(provider_headers, dict):
                return False
            for header_map in provider_headers.values():
                if not isinstance(header_map, dict):
                    return False
                if not self._is_header_mapping(header_map):
                    return False

        return True

    @staticmethod
    def _is_int(value: Any) -> bool:
        """True for a real int, excluding bool (bool is an int subclass in Python)."""
        return isinstance(value, int) and not isinstance(value, bool)

    @classmethod
    def _is_model_entry(cls, entry: Any) -> bool:
        if not isinstance(entry, dict):
            return False
        for counter in cls._REQUIRED_MODEL_COUNTERS:
            value = entry.get(counter)
            # isinstance is inline rather than delegated to _is_int because a
            # bool-returning helper does not narrow Any | None, so the comparison
            # below would be unchecked. bool stays rejected: it is an int subclass.
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                return False
        if not isinstance(entry.get("errors"), list):
            return False
        if "last_request" in entry:
            last_request = entry["last_request"]
            if last_request is not None and not isinstance(last_request, str):
                return False
        return True

    @classmethod
    def _is_header_mapping(cls, header_map: dict[str, Any]) -> bool:
        for key in cls._NUMERIC_HEADER_KEYS:
            if key in header_map:
                value = header_map[key]
                if value is not None and not cls._is_int(value):
                    return False
        for timestamp_key in ("last_updated", "retry_at"):
            if timestamp_key in header_map:
                if not cls._is_naive_iso_datetime(header_map[timestamp_key]):
                    return False
        return True

    @staticmethod
    def _is_daily_stamp(value: Any) -> bool:
        """Exactly YYYY-MM-DD and a real calendar date (canonical roundtrip)."""
        if not isinstance(value, str):
            return False
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return False
        return parsed.isoformat() == value

    @staticmethod
    def _is_monthly_stamp(value: Any) -> bool:
        """Exactly YYYY-MM and a real calendar month (validated via a first-of-month)."""
        if not isinstance(value, str) or len(value) != 7 or value[4] != "-":
            return False
        try:
            parsed = date.fromisoformat(f"{value}-01")
        except ValueError:
            return False
        return parsed.strftime("%Y-%m") == value

    @staticmethod
    def _is_naive_iso_datetime(value: Any) -> bool:
        """None, or a NAIVE isoformat datetime string as the current writer emits."""
        if value is None:
            return True
        if not isinstance(value, str) or "T" not in value:
            return False
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return False
        if parsed.tzinfo is not None:
            return False
        return parsed.isoformat() == value

    def record_request(
        self,
        provider: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Record a request.

        Args:
            provider: Provider name
            model: Model name
            input_tokens: Input token count
            output_tokens: Output token count
            success: Whether request succeeded
            error_message: Optional error message
        """
        self._check_and_reset()
        self._ensure_provider_model(provider, model)
        self._update_counters(provider, model, input_tokens, output_tokens, success, error_message)
        self._storage.save(self._usage)

    async def record_request_async(
        self,
        provider: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> None:
        """Record a request asynchronously."""
        self._check_and_reset()
        self._ensure_provider_model(provider, model)
        self._update_counters(provider, model, input_tokens, output_tokens, success, error_message)
        await self._storage.save_async(self._usage)

    def get_usage(self, provider: str, model: Optional[str] = None) -> dict[str, Any]:
        """
        Get usage data for provider/model.

        Args:
            provider: Provider name
            model: Optional model name

        Returns:
            Usage dict for model, or all models if model not specified
        """
        self._check_and_reset()
        provider_data = self._usage.get("providers", {}).get(provider, {})
        if model:
            return provider_data.get(model, {})
        return provider_data

    def get_remaining_quota(
        self,
        provider: str,
        model: str,
        limits: ProviderLimits,
    ) -> dict[str, Any]:
        """
        Get remaining quota for provider/model.

        Prefers actual provider-reported values from HTTP headers when available
        and fresh. Falls back to calculated estimates from our usage tracking.

        Args:
            provider: Provider name
            model: Model name
            limits: Provider limits

        Returns:
            Dict with remaining counts
        """
        self._check_and_reset()
        self._ensure_provider_model(provider, model)

        # Try to use fresh header data first (actual provider-reported values)
        header_remaining = self._get_remaining_from_headers(provider, limits)
        if header_remaining is not None:
            return header_remaining

        # Fall back to calculated estimate
        usage = self._usage["providers"][provider][model]
        return self._calc.remaining(usage, limits)

    def _get_remaining_from_headers(
        self,
        provider: str,
        limits: ProviderLimits,
    ) -> Optional[Dict[str, Any]]:
        """
        Get remaining quota from cached HTTP headers if fresh.

        Args:
            provider: Provider name
            limits: Provider limits (used for fields we can't get from headers)

        Returns:
            Remaining quota dict or None if headers unavailable/stale
        """
        header_data = self.get_provider_headers(provider)
        if header_data is None:
            return None

        # Check freshness (default 5 minutes)
        freshness_seconds = self.config.header_freshness_seconds if hasattr(
            self.config, 'header_freshness_seconds'
        ) else 300

        last_updated = header_data.get("last_updated")
        if last_updated:
            try:
                updated_time = datetime.fromisoformat(last_updated)
                if datetime.now() - updated_time > timedelta(seconds=freshness_seconds):
                    return None  # Headers are stale
            except (ValueError, TypeError):
                return None  # Invalid timestamp

        # Build remaining dict from header data
        # Prefer day values, fall back to generic values
        requests_remaining = (
            header_data.get("remaining_requests_day")
            or header_data.get("remaining_requests")
        )
        tokens_remaining = (
            header_data.get("remaining_tokens_day")
            or header_data.get("remaining_tokens")
        )

        # If we don't have the key values, can't use header data
        if requests_remaining is None:
            return None

        # Get our tracked usage for fields headers don't provide
        usage = self._usage.get("providers", {}).get(provider, {})
        first_model: Dict[str, Any] = next(iter(usage.values()), {}) if usage else {}

        return {
            "requests_remaining_today": requests_remaining,
            "requests_remaining_month": (
                header_data.get("remaining_requests_month")
                or requests_remaining  # Approximate if not available
            ),
            "tokens_remaining_today": tokens_remaining or limits.tokens_per_day,
            "tokens_remaining_minute": (
                header_data.get("remaining_tokens_minute")
                or limits.tokens_per_minute
            ),
            # Include our tracked usage for reference
            "usage_today": first_model.get("requests_today", 0),
            "tokens_today": first_model.get("tokens_today", 0),
            "usage_this_month": first_model.get("requests_this_month", 0),
            # Mark that this came from headers
            "_source": "headers",
        }

    def is_rate_limited(self, provider_name: str, registry: Any) -> bool:
        """
        Check if provider is currently rate limited.

        Checks both quota-based limits and retry_at timestamp from error responses.

        Args:
            provider_name: Provider name
            registry: Provider registry

        Returns:
            True if rate limited
        """
        # Check if we have a retry_at timestamp that's still in the future
        # (from Gemini error responses or similar)
        header_data = self.get_provider_headers(provider_name)
        if header_data and "retry_at" in header_data:
            try:
                retry_at = datetime.fromisoformat(header_data["retry_at"])
                if retry_at > datetime.now():
                    return True  # Still waiting for retry window
            except (ValueError, TypeError):
                pass  # Invalid timestamp, ignore

        provider = registry.get(provider_name)
        if not provider:
            return False

        limits = provider.get_limits()
        if not limits:
            return False

        model = getattr(provider, "default_model", "default")
        remaining = self.get_remaining_quota(provider_name, model, limits)

        return (
            remaining.get("requests_remaining_today") == 0 or
            remaining.get("requests_remaining_month") == 0
        )

    def is_limit_approaching(
        self,
        provider: str,
        model: str,
        limits: ProviderLimits,
        threshold: float = 0.1,
    ) -> dict[str, Any]:
        """
        Check if approaching limits.

        Args:
            provider: Provider name
            model: Model name
            limits: Provider limits
            threshold: Warning threshold (0.1 = 10% remaining)

        Returns:
            Dict with warning flags and optional message
        """
        remaining = self.get_remaining_quota(provider, model, limits)
        return self._calc.warnings(remaining, limits, threshold)

    def get_all_usage_summary(self) -> dict[str, Any]:
        """
        Get summary of all usage.

        Returns:
            Nested dict with provider and model statistics
        """
        self._check_and_reset()
        return self._calc.summarise(self._usage)

    def clear(self) -> None:
        """Clear all usage data."""
        self._initialise_empty()
        self._storage.save(self._usage)

    def reset_provider(self, provider: str) -> None:
        """
        Reset usage for a specific provider.

        Args:
            provider: Provider name
        """
        self._usage.setdefault("providers", {}).pop(provider, None)
        self._storage.save(self._usage)

    def reset_rate_tracking(self, provider_name: Optional[str] = None) -> None:
        """
        Reset rate tracking.

        Args:
            provider_name: Optional provider to reset (None = reset all)
        """
        if provider_name:
            self.reset_provider(provider_name)
        else:
            self.clear()

    def get_recommended_provider(self, task_type: str, registry: Any) -> Optional[str]:
        """
        Get recommended provider for task type.

        Args:
            task_type: Type of task
            registry: Provider registry

        Returns:
            Provider name or None
        """
        return self._recommender.recommended(task_type, registry, self.config.task_preferences)

    def get_rate_limit_status_extended(self, registry: Any) -> dict[str, Any]:
        """
        Get extended rate limit status with limits and remaining quota.

        Args:
            registry: Provider registry

        Returns:
            Extended status dict
        """
        status = self.get_all_usage_summary()

        for provider_name in status.get("providers", {}):
            try:
                provider = registry.get(provider_name)
                if not provider:
                    continue

                limits = provider.get_limits()
                if not limits:
                    status["providers"][provider_name]["limits"] = {}
                    status["providers"][provider_name]["remaining"] = {}
                    continue

                remaining = self.get_remaining_quota(provider_name, provider.default_model, limits)

                status["providers"][provider_name]["limits"] = {
                    "requests_per_day": limits.requests_per_day,
                    "requests_per_month": limits.requests_per_month,
                    "tokens_per_day": limits.tokens_per_day,
                    "tokens_per_minute": limits.tokens_per_minute,
                }
                status["providers"][provider_name]["remaining"] = remaining

            except Exception:
                status["providers"][provider_name]["limits"] = {}
                status["providers"][provider_name]["remaining"] = {}

        return status

    def check_all_warnings(self, registry: Any) -> List[str]:
        """
        Check for warnings across all providers.

        Args:
            registry: Provider registry

        Returns:
            List of warning messages
        """
        warnings = []

        for provider_name in registry.list_available():
            try:
                provider = registry.get(provider_name)
                if not provider:
                    continue

                limits = provider.get_limits()
                if not limits:
                    continue

                for model in self.get_usage(provider_name).keys():
                    warning = self.is_limit_approaching(provider_name, model, limits)
                    if warning.get("message"):
                        # Prepend provider and model info to warning message
                        warnings.append(f"{provider_name}/{model}: {warning['message']}")

            except Exception:
                continue

        return warnings

    def get_remaining_quota_for_provider(
        self,
        provider_name: str,
        registry: Any,
        model: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Get remaining quota for a provider.

        Args:
            provider_name: Provider name
            registry: Provider registry
            model: Optional model name (defaults to provider default)

        Returns:
            Remaining quota dict

        Raises:
            ValueError: If provider not found
        """
        provider = registry.get(provider_name)
        if provider is None:
            raise ValueError(f"Provider '{provider_name}' not available")

        limits = provider.get_limits()
        if model is None:
            model = provider.default_model

        return self.get_remaining_quota(provider_name, model, limits)

    def _initialise_empty(self) -> None:
        """Initialize empty usage structure."""
        now = datetime.now()
        self._usage = {
            "providers": {},
            "last_reset": {
                "daily": now.date().isoformat(),
                "monthly": now.strftime("%Y-%m"),
            },
            "created_at": now.isoformat(),
        }

    def _check_and_reset(self) -> None:
        """Check if reset is needed and apply if so."""
        flags = self._policy.reset_needed(self._usage.get("last_reset", {}))

        if flags["daily"] or flags["monthly"]:
            self._policy.apply_reset(self._usage, flags)

            now = datetime.now()
            self._usage["last_reset"]["daily"] = now.date().isoformat()
            self._usage["last_reset"]["monthly"] = now.strftime("%Y-%m")

            self._storage.save(self._usage)

    def _ensure_provider_model(self, provider: str, model: str) -> None:
        """Ensure provider/model exists in usage dict."""
        providers = self._usage.setdefault("providers", {})
        provider_data = providers.setdefault(provider, {})

        if model not in provider_data:
            provider_data[model] = {
                "requests_today": 0,
                "requests_this_month": 0,
                "tokens_today": 0,
                "tokens_this_month": 0,
                "input_tokens_today": 0,
                "output_tokens_today": 0,
                "total_requests": 0,
                "total_tokens": 0,
                "last_request": None,
                "errors": [],
            }

    def _update_counters(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        success: bool,
        error_message: Optional[str],
    ) -> None:
        """Update usage counters.

        Only successful requests count against quota. Failed requests
        (rate limits, errors) were rejected by the API before consuming
        tokens, so they shouldn't inflate usage metrics. The response
        object is the source of truth for actual usage.
        """
        data = self._usage["providers"][provider][model]

        if success:
            total_tokens = input_tokens + output_tokens

            data["requests_today"] += 1
            data["requests_this_month"] += 1
            data["total_requests"] += 1

            data["tokens_today"] += total_tokens
            data["tokens_this_month"] += total_tokens
            data["total_tokens"] += total_tokens

            data["input_tokens_today"] += input_tokens
            data["output_tokens_today"] += output_tokens

            data["last_request"] = datetime.now().isoformat()

        if not success and error_message:
            data["errors"].append({
                "timestamp": datetime.now().isoformat(),
                "message": error_message[:200],
            })
            # Keep only last 10 errors
            data["errors"] = data["errors"][-10:]

    def update_from_headers(self, provider: str, headers: Dict[str, str]) -> None:
        """Update rate limits from HTTP response headers.

        Stores provider-reported remaining quotas for accurate routing decisions.
        Different providers use different header formats:
        - Groq: x-ratelimit-remaining-requests, x-ratelimit-limit-requests
        - Cerebras: x-ratelimit-remaining-requests-day/hour/minute
        - SambaNova: x-ratelimit-remaining-requests-day, x-ratelimit-limit-requests-day

        Args:
            provider: Provider name (groq, cerebras, sambanova, etc.)
            headers: Dict of rate limit headers (lowercase keys)
        """
        if not headers:
            return

        # Ensure provider_headers structure exists
        provider_headers = self._usage.setdefault("provider_headers", {})
        provider_data = provider_headers.setdefault(provider, {})

        # Store timestamp
        provider_data["last_updated"] = datetime.now().isoformat()

        # Parse headers based on provider format
        parsed = self._parse_rate_limit_headers(provider, headers)
        provider_data.update(parsed)

        # Save to storage
        self._storage.save(self._usage)

    def _parse_rate_limit_headers(
        self, provider: str, headers: Dict[str, str]
    ) -> Dict[str, Any]:
        """Parse rate limit headers into normalized format.

        Args:
            provider: Provider name
            headers: Raw headers dict

        Returns:
            Normalized dict with remaining/limit values
        """
        result: Dict[str, Any] = {"raw_headers": headers}

        # Common patterns across providers
        # Note: Check "reset" before "limit" because "ratelimit" contains "limit"
        for key, value in headers.items():
            key_lower = key.lower()

            # Try to parse numeric values
            try:
                numeric_value = int(value)
            except (ValueError, TypeError):
                # Keep as string for non-numeric (like reset times "6s")
                numeric_value = None

            # Reset times FIRST (stored as strings since format varies)
            # Must check before "limit" since "ratelimit" contains "limit"
            if "reset" in key_lower:
                if "request" in key_lower:
                    result["reset_requests"] = value
                elif "token" in key_lower:
                    result["reset_tokens"] = value

            # Remaining requests
            elif "remaining" in key_lower and "request" in key_lower:
                if "day" in key_lower:
                    result["remaining_requests_day"] = numeric_value
                elif "hour" in key_lower:
                    result["remaining_requests_hour"] = numeric_value
                elif "minute" in key_lower:
                    result["remaining_requests_minute"] = numeric_value
                else:
                    # Generic remaining requests (Groq format)
                    result["remaining_requests"] = numeric_value

            # Remaining tokens
            elif "remaining" in key_lower and "token" in key_lower:
                if "day" in key_lower:
                    result["remaining_tokens_day"] = numeric_value
                elif "hour" in key_lower:
                    result["remaining_tokens_hour"] = numeric_value
                elif "minute" in key_lower:
                    result["remaining_tokens_minute"] = numeric_value
                else:
                    result["remaining_tokens"] = numeric_value

            # Limit values (check "-limit-" to distinguish from "ratelimit")
            elif "-limit-" in key_lower and "request" in key_lower:
                if "day" in key_lower:
                    result["limit_requests_day"] = numeric_value
                elif "hour" in key_lower:
                    result["limit_requests_hour"] = numeric_value
                elif "minute" in key_lower:
                    result["limit_requests_minute"] = numeric_value
                else:
                    result["limit_requests"] = numeric_value

            elif "-limit-" in key_lower and "token" in key_lower:
                if "day" in key_lower:
                    result["limit_tokens_day"] = numeric_value
                elif "hour" in key_lower:
                    result["limit_tokens_hour"] = numeric_value
                elif "minute" in key_lower:
                    result["limit_tokens_minute"] = numeric_value
                else:
                    result["limit_tokens"] = numeric_value

        return result

    def get_provider_headers(self, provider: str) -> Optional[Dict[str, Any]]:
        """Get provider-reported rate limit info from headers.

        Args:
            provider: Provider name

        Returns:
            Dict with parsed header data or None if not available
        """
        return self._usage.get("provider_headers", {}).get(provider)

    def update_from_error(self, provider: str, error_data: Dict[str, Any]) -> None:
        """Update rate limits from error response data.

        Called for any provider whose exception carried server-reported retry
        info (headers, body, or message). Stores retry_after and computes the
        provider-scoped retry_at consumed by is_rate_limited.

        Args:
            provider: Provider name (e.g., "gemini", "groq")
            error_data: Parsed error data with keys like:
                - retry_after_seconds: Seconds until retry allowed
                - quota_type: Type of quota exceeded (e.g., "requests", "tokens")
                - message: Original error message
        """
        if not error_data:
            return

        # Store in same structure as header data for consistency
        provider_headers = self._usage.setdefault("provider_headers", {})
        provider_data = provider_headers.setdefault(provider, {})

        # Store timestamp
        provider_data["last_updated"] = datetime.now().isoformat()
        provider_data["from_error"] = True

        # Store retry_after if present
        if "retry_after_seconds" in error_data:
            retry_seconds = error_data["retry_after_seconds"]
            provider_data["retry_after_seconds"] = retry_seconds
            # Calculate when we can retry
            retry_at = datetime.now() + timedelta(seconds=retry_seconds)
            provider_data["retry_at"] = retry_at.isoformat()

        # Store any quota info
        if "quota_type" in error_data:
            provider_data["quota_exceeded"] = error_data["quota_type"]

        # Store original message for debugging
        if "message" in error_data:
            provider_data["error_message"] = error_data["message"][:200]

        # Save to storage
        self._storage.save(self._usage)
