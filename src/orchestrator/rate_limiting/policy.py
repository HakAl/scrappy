"""Rate limit reset policy."""
from __future__ import annotations
from datetime import date
from typing import Any, Dict


class RateLimitPolicy:
    """
    Determines when to reset rate limit counters.

    Single responsibility: Decide when resets happen and apply them.
    """

    def __init__(self, today: date | None = None):
        """
        Initialize policy.

        Args:
            today: Current date (for testing, defaults to today)
        """
        self._today = today or date.today()

    def reset_needed(self, last_reset_info: Dict[str, str]) -> Dict[str, bool]:
        """
        Check if daily or monthly reset is needed.

        Args:
            last_reset_info: Dict with 'daily' and 'monthly' ISO date strings

        Returns:
            Dict with 'daily' and 'monthly' boolean flags
        """
        current_date = self._today.isoformat()
        current_month = self._today.strftime("%Y-%m")

        return {
            "daily": last_reset_info.get("daily") != current_date,
            "monthly": last_reset_info.get("monthly") != current_month,
        }

    def apply_reset(self, usage: dict[str, Any], which: Dict[str, bool]) -> None:
        """
        Reset counters in usage dict based on flags.

        Args:
            usage: Usage data dict (mutated in-place)
            which: Dict with 'daily' and 'monthly' boolean flags
        """
        if which["daily"]:
            self._reset_daily(usage)

        if which["monthly"]:
            self._reset_monthly(usage)

    def _reset_daily(self, usage: dict[str, Any]) -> None:
        """Reset all daily counters to zero."""
        for provider_models in usage.get("providers", {}).values():
            for model_data in provider_models.values():
                model_data["requests_today"] = 0
                model_data["tokens_today"] = 0
                model_data["input_tokens_today"] = 0
                model_data["output_tokens_today"] = 0

    def _reset_monthly(self, usage: dict[str, Any]) -> None:
        """Reset all monthly counters to zero."""
        for provider_models in usage.get("providers", {}).values():
            for model_data in provider_models.values():
                model_data["requests_this_month"] = 0
                model_data["tokens_this_month"] = 0
