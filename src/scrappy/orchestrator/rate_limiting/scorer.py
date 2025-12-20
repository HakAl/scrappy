"""
QuotaScorer - Scores providers by remaining quota capacity.

Implements QuotaScorerProtocol following SOLID:
- Single Responsibility: Only scores providers by quota
- Open/Closed: Speed bonuses configurable without code changes
- Dependency Inversion: Depends on UsageQueryProtocol, not tracker
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

from .protocols import QuotaScore, UsageQueryProtocol


# Default speed bonuses for fast providers
DEFAULT_SPEED_BONUSES: Dict[str, float] = {
    "cerebras": 0.1,
    "groq": 0.05,
}


class QuotaScorer:
    """
    Scores providers by remaining quota capacity.

    Score calculation:
    - Base score = min(requests_ratio, tokens_ratio) where ratio = remaining / limit
    - Penalties: None currently (can be extended)
    - Bonuses: Fast provider bonus (configurable)

    A score of 1.0 means fully available, 0.0 means exhausted.
    """

    def __init__(
        self,
        usage_query: UsageQueryProtocol,
        *,
        speed_bonus: Optional[Dict[str, float]] = None,
        warn_threshold: float = 0.1,
    ):
        """
        Initialize scorer.

        Args:
            usage_query: Interface for querying usage data
            speed_bonus: Provider -> bonus mapping (added to score)
            warn_threshold: Threshold below which warning flag is set
        """
        self._usage_query = usage_query
        self._speed_bonus = speed_bonus if speed_bonus is not None else DEFAULT_SPEED_BONUSES
        self._warn_threshold = warn_threshold

    def score_provider(
        self,
        provider: str,
        model: str,
        limits: Any,
    ) -> QuotaScore:
        """
        Score a single provider's availability.

        Args:
            provider: Provider name
            model: Model name
            limits: ProviderLimits object

        Returns:
            QuotaScore with availability metrics
        """
        # Get remaining quota from usage query
        remaining = self._usage_query.get_remaining_quota(provider, model, limits)

        # Extract values with safe defaults
        requests_remaining = remaining.get("requests_remaining_today", 0)
        tokens_remaining = remaining.get("tokens_remaining_today", 0)

        # Calculate ratios (handle None/0 limits gracefully)
        requests_limit = getattr(limits, "requests_per_day", None) or 0
        tokens_limit = getattr(limits, "tokens_per_day", None) or 0

        if requests_limit > 0:
            requests_ratio = requests_remaining / requests_limit
        else:
            requests_ratio = 1.0  # No limit = fully available

        if tokens_limit > 0:
            tokens_ratio = tokens_remaining / tokens_limit
        else:
            tokens_ratio = 1.0  # No limit = fully available

        # Base score is minimum of the two ratios
        base_score = min(requests_ratio, tokens_ratio)

        # Apply speed bonus (capped at 1.0)
        bonus = self._speed_bonus.get(provider, 0.0)
        final_score = min(base_score + bonus, 1.0)

        # Determine flags
        is_rate_limited = requests_remaining <= 0 or (
            remaining.get("requests_remaining_month", 1) <= 0
        )
        warning_threshold_hit = base_score <= self._warn_threshold and not is_rate_limited

        return QuotaScore(
            provider=provider,
            score=final_score,
            requests_remaining=requests_remaining,
            tokens_remaining=tokens_remaining,
            is_rate_limited=is_rate_limited,
            warning_threshold_hit=warning_threshold_hit,
        )

    def rank_providers(
        self,
        providers: List[str],
        registry: Any,
        task_type: str = "general",
    ) -> List[QuotaScore]:
        """
        Rank all providers by quota availability.

        Args:
            providers: List of provider names to rank
            registry: Provider registry for limit lookup
            task_type: Type of task (currently unused, for future weighting)

        Returns:
            List of QuotaScore sorted by score (highest first)
        """
        scores = []

        for provider_name in providers:
            try:
                provider = registry.get(provider_name)
                if provider is None:
                    continue

                limits = provider.get_limits()
                if limits is None:
                    # No limits = fully available
                    scores.append(QuotaScore(
                        provider=provider_name,
                        score=1.0 + self._speed_bonus.get(provider_name, 0.0),
                        requests_remaining=999999,
                        tokens_remaining=999999,
                        is_rate_limited=False,
                        warning_threshold_hit=False,
                    ))
                    continue

                model = getattr(provider, "default_model", "default")
                score = self.score_provider(provider_name, model, limits)
                scores.append(score)

            except Exception:
                # Skip providers that fail to score
                continue

        # Sort by score descending
        scores.sort(key=lambda s: s.score, reverse=True)
        return scores
