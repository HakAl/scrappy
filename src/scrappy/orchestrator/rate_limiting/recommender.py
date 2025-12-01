"""Provider recommendation based on rate limits."""
from __future__ import annotations
from typing import Any, Optional

from .protocols import UsageQueryProtocol


class RateLimitRecommender:
    """
    Recommends providers based on rate limits.

    Single responsibility: Provider selection logic.
    Depends only on UsageQueryProtocol, not full tracker.
    """

    def __init__(self, usage_query: UsageQueryProtocol):
        """
        Initialize recommender.

        Args:
            usage_query: Interface for querying usage data
        """
        self._query = usage_query

    def recommended(
        self,
        task_type: str,
        registry: Any,  # ProviderRegistry
        task_preferences: dict[str, list[str]],
    ) -> Optional[str]:
        """
        Recommend best available provider for task type.

        Args:
            task_type: Type of task (e.g., 'coding', 'research')
            registry: Provider registry
            task_preferences: Mapping of task types to provider preferences

        Returns:
            Provider name or None if all are rate limited
        """
        available = registry.list_available()
        if not available:
            return None

        # Get preferences for this task type (fallback to general)
        preferences = task_preferences.get(task_type, task_preferences["general"])

        # Try each preferred provider in order
        for provider_name in preferences:
            if provider_name not in available:
                continue

            if self._query.is_rate_limited(provider_name, registry):
                continue

            return provider_name

        # No preferred provider available - return first non-limited
        for provider_name in available:
            if not self._query.is_rate_limited(provider_name, registry):
                return provider_name

        # All providers are rate limited - return first available anyway
        return available[0] if available else None
