"""Rate limit tracker facade."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .protocols import (
    StorageProtocol,
    PolicyProtocol,
    CalculatorProtocol,
    RecommenderProtocol,
    UsageQueryProtocol,
)
from .recommender import TASK_PREFERENCES

if TYPE_CHECKING:
    from ..providers import ProviderLimits


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
    ):
        """
        Initialize tracker.

        Args:
            storage: Persistence layer
            policy: Reset policy
            calculator: Usage calculations
            recommender: Provider recommendation
            auto_load: If True, load data from storage on init
        """
        self._storage = storage
        self._policy = policy
        self._calc = calculator
        self._recommender = recommender

        self._usage: Dict[str, Any] = {}
        self._initialise_empty()

        if auto_load:
            self.restore_from_disk()

    def restore_from_disk(self) -> RateLimitTracker:
        """Load usage data from storage."""
        blob = self._storage.load()
        if blob:
            self._usage = blob
            self._check_and_reset()
        return self

    async def restore_from_disk_async(self) -> RateLimitTracker:
        """Load usage data from storage asynchronously."""
        blob = await self._storage.load_async()
        if blob:
            self._usage = blob
            self._check_and_reset()
        return self

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

        Args:
            provider: Provider name
            model: Model name
            limits: Provider limits

        Returns:
            Dict with remaining counts
        """
        self._check_and_reset()
        self._ensure_provider_model(provider, model)
        usage = self._usage["providers"][provider][model]
        return self._calc.remaining(usage, limits)

    def is_rate_limited(self, provider_name: str, registry: Any) -> bool:
        """
        Check if provider is currently rate limited.

        Args:
            provider_name: Provider name
            registry: Provider registry

        Returns:
            True if rate limited
        """
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
        return self._recommender.recommended(task_type, registry, TASK_PREFERENCES)

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
                        warnings.append(warning["message"])

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
        """Update usage counters."""
        data = self._usage["providers"][provider][model]
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
