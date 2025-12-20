"""Provider recommendation based on rate limits."""
from __future__ import annotations
from typing import Any, Optional

from .protocols import UsageQueryProtocol, QuotaScorerProtocol


class RateLimitRecommender:
    """
    Recommends providers based on rate limits.

    Single responsibility: Provider selection logic.
    Depends only on UsageQueryProtocol, not full tracker.

    When a scorer is provided, uses score-based ranking for smarter selection.
    Otherwise falls back to simple is_rate_limited checks.
    """

    def __init__(
        self,
        usage_query: UsageQueryProtocol,
        scorer: Optional[QuotaScorerProtocol] = None,
    ):
        """
        Initialize recommender.

        Args:
            usage_query: Interface for querying usage data
            scorer: Optional scorer for score-based ranking
        """
        self._query = usage_query
        self._scorer = scorer

    def recommended(
        self,
        task_type: str,
        registry: Any,  # ProviderRegistry
        task_preferences: dict[str, list[str]],
    ) -> Optional[str]:
        """
        Recommend best available provider for task type.

        If a scorer is configured, ranks providers by quota score.
        Otherwise uses simple is_rate_limited checks.

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
        preferences = task_preferences.get(task_type, task_preferences.get("general", []))

        # If scorer available, use score-based selection
        if self._scorer is not None:
            return self._recommended_by_score(available, preferences, registry)

        # Otherwise use legacy is_rate_limited approach
        return self._recommended_by_availability(available, preferences, registry)

    def _recommended_by_score(
        self,
        available: list[str],
        preferences: list[str],
        registry: Any,
    ) -> Optional[str]:
        """
        Recommend provider using score-based ranking.

        Prioritizes preferred providers, but within each tier ranks by score.
        """
        # Rank all available providers by quota score
        ranked = self._scorer.rank_providers(available, registry)
        if not ranked:
            return available[0] if available else None

        # Build score lookup
        score_map = {s.provider: s for s in ranked}

        # First: try preferred providers in preference order, but skip exhausted ones
        for provider_name in preferences:
            if provider_name not in score_map:
                continue
            score = score_map[provider_name]
            if not score.is_rate_limited:
                return provider_name

        # Second: return highest-scoring non-exhausted provider
        for score in ranked:
            if not score.is_rate_limited:
                return score.provider

        # All exhausted - return highest scorer anyway (let enforcement handle it)
        return ranked[0].provider if ranked else None

    def _recommended_by_availability(
        self,
        available: list[str],
        preferences: list[str],
        registry: Any,
    ) -> Optional[str]:
        """
        Recommend provider using simple availability checks (legacy behavior).
        """
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
