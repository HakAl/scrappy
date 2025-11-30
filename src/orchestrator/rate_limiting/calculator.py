"""Rate limit calculations."""
from __future__ import annotations
from typing import Any, Dict, Optional

from src.providers.base import ProviderLimits


class RateLimitCalculator:
    """
    Pure calculations for rate limits.

    Single responsibility: Math operations on usage data.
    No I/O, no side effects, easily testable.
    """

    def remaining(
        self,
        usage: dict[str, Any],
        limits: ProviderLimits,
    ) -> Dict[str, Any]:
        """
        Calculate remaining quota.

        Args:
            usage: Usage data for a specific model
            limits: Provider limits

        Returns:
            Dict with remaining counts and current usage
        """
        return {
            "requests_remaining_today": self._sub(
                limits.requests_per_day,
                usage.get("requests_today", 0)
            ),
            "requests_remaining_month": self._sub(
                limits.requests_per_month,
                usage.get("requests_this_month", 0)
            ),
            "tokens_remaining_today": self._sub(
                limits.tokens_per_day,
                usage.get("tokens_today", 0)
            ),
            "tokens_remaining_minute": limits.tokens_per_minute,
            "usage_today": usage.get("requests_today", 0),
            "tokens_today": usage.get("tokens_today", 0),
            "usage_this_month": usage.get("requests_this_month", 0),
        }

    def warnings(
        self,
        remaining: Dict[str, Any],
        limits: ProviderLimits,
        threshold: float = 0.1,
    ) -> Dict[str, Any]:
        """
        Check if approaching limits.

        Args:
            remaining: Dict from remaining() method
            limits: Provider limits
            threshold: Warning threshold (0.1 = 10% remaining)

        Returns:
            Dict with warning flags and optional message
        """
        flags: Dict[str, Any] = {
            "approaching_daily_request_limit": False,
            "approaching_monthly_request_limit": False,
            "approaching_daily_token_limit": False,
            "message": None,
        }

        messages = []

        # Check daily request limit
        if limits.requests_per_day and remaining["requests_remaining_today"] is not None:
            if remaining["requests_remaining_today"] <= limits.requests_per_day * threshold:
                flags["approaching_daily_request_limit"] = True
                messages.append(
                    f"Only {remaining['requests_remaining_today']} requests remaining today"
                )

        # Check monthly request limit
        if limits.requests_per_month and remaining["requests_remaining_month"] is not None:
            if remaining["requests_remaining_month"] <= limits.requests_per_month * threshold:
                flags["approaching_monthly_request_limit"] = True
                messages.append(
                    f"Only {remaining['requests_remaining_month']} requests remaining this month"
                )

        # Check daily token limit
        if limits.tokens_per_day and remaining["tokens_remaining_today"] is not None:
            if remaining["tokens_remaining_today"] <= limits.tokens_per_day * threshold:
                flags["approaching_daily_token_limit"] = True
                messages.append(
                    f"Only {remaining['tokens_remaining_today']} tokens remaining today"
                )

        if messages:
            flags["message"] = ", ".join(messages)

        return flags

    def summarise(self, usage: dict[str, Any]) -> Dict[str, Any]:
        """
        Build summary of all provider usage.

        Args:
            usage: Full usage data structure

        Returns:
            Nested dict with provider and model statistics
        """
        providers = usage.get("providers", {})
        summary = {
            "last_reset": usage.get("last_reset", {}),
            "providers": {}
        }

        for provider_name, models in providers.items():
            summary["providers"][provider_name] = {
                "total_requests_today": sum(
                    m.get("requests_today", 0) for m in models.values()
                ),
                "total_tokens_today": sum(
                    m.get("tokens_today", 0) for m in models.values()
                ),
                "total_requests_month": sum(
                    m.get("requests_this_month", 0) for m in models.values()
                ),
                "models": list(models.keys()),
                "by_model": {
                    model_name: {
                        "requests_today": model_data.get("requests_today", 0),
                        "tokens_today": model_data.get("tokens_today", 0),
                        "last_request": model_data.get("last_request"),
                    }
                    for model_name, model_data in models.items()
                },
            }

        return summary

    @staticmethod
    def _sub(limit: Optional[int], used: int) -> Optional[int]:
        """Subtract usage from limit, returning None if no limit."""
        if limit is None:
            return None
        return max(0, limit - used)
