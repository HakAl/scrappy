"""
RateLimitEnforcementPolicy - Decides whether requests should proceed.

Implements EnforcementPolicyProtocol following SOLID:
- Single Responsibility: Only makes enforcement decisions
- Open/Closed: Thresholds configurable without code changes
- Dependency Inversion: Depends on protocols, not concrete implementations
"""
from __future__ import annotations
from typing import Any, Optional

from .protocols import (
    EnforcementAction,
    EnforcementDecision,
    QuotaScorerProtocol,
    UsageQueryProtocol,
)


class RateLimitEnforcementPolicy:
    """
    Decides whether requests should proceed based on quota.

    Decision logic:
    1. Score requested provider
    2. If score > warn_threshold: ALLOW
    3. If score > block_threshold: WARN + suggest alternative
    4. If score <= block_threshold:
       a. Rank all providers
       b. If alternative exists with score > warn_threshold: BLOCK + alternative
       c. If alternative exists with score > 0: BLOCK + alternative (with warning)
       d. If no alternatives: FAIL
    """

    def __init__(
        self,
        usage_query: UsageQueryProtocol,
        scorer: QuotaScorerProtocol,
        *,
        warn_threshold: float = 0.1,
        block_threshold: float = 0.0,
    ):
        """
        Initialize enforcement policy.

        Args:
            usage_query: Interface for querying usage data
            scorer: Interface for scoring providers
            warn_threshold: Score below which to warn (default 10%)
            block_threshold: Score at or below which to block (default 0%)
        """
        self._usage_query = usage_query
        self._scorer = scorer
        self._warn_threshold = warn_threshold
        self._block_threshold = block_threshold

    def evaluate(
        self,
        provider: str,
        model: str,
        estimated_tokens: int,
        registry: Any,
    ) -> EnforcementDecision:
        """
        Evaluate whether a request should proceed.

        Args:
            provider: Target provider name
            model: Target model name
            estimated_tokens: Estimated token usage (for future use)
            registry: Provider registry for fallback lookup

        Returns:
            EnforcementDecision with action and context
        """
        # Get provider and limits
        provider_obj = registry.get(provider)
        if provider_obj is None:
            return EnforcementDecision(
                action=EnforcementAction.FAIL,
                provider=provider,
                reason=f"Provider '{provider}' not available",
            )

        limits = provider_obj.get_limits()
        if limits is None:
            # No limits configured = always allow
            return EnforcementDecision(
                action=EnforcementAction.ALLOW,
                provider=provider,
                reason="No rate limits configured",
            )

        # Score the requested provider
        score = self._scorer.score_provider(provider, model, limits)

        # Case 1: Plenty of quota - allow
        if score.score > self._warn_threshold:
            return EnforcementDecision(
                action=EnforcementAction.ALLOW,
                provider=provider,
                reason="Sufficient quota available",
                remaining_quota={
                    "requests": score.requests_remaining,
                    "tokens": score.tokens_remaining,
                },
            )

        # Case 2: Approaching limit but not exhausted - warn
        if score.score > self._block_threshold:
            alternative = self._find_alternative(provider, registry)
            return EnforcementDecision(
                action=EnforcementAction.WARN,
                provider=provider,
                reason=f"Approaching rate limit ({int(score.score * 100)}% remaining)",
                alternative_provider=alternative,
                remaining_quota={
                    "requests": score.requests_remaining,
                    "tokens": score.tokens_remaining,
                },
            )

        # Case 3: Exhausted - try to find alternative
        alternative = self._find_alternative(provider, registry)

        if alternative:
            return EnforcementDecision(
                action=EnforcementAction.BLOCK,
                provider=provider,
                reason=f"Rate limit exhausted, switching to {alternative}",
                alternative_provider=alternative,
                remaining_quota={
                    "requests": score.requests_remaining,
                    "tokens": score.tokens_remaining,
                },
            )

        # Case 4: No alternatives available
        return EnforcementDecision(
            action=EnforcementAction.FAIL,
            provider=provider,
            reason="All providers exhausted",
            remaining_quota={
                "requests": score.requests_remaining,
                "tokens": score.tokens_remaining,
            },
        )

    def _find_alternative(
        self,
        exclude_provider: str,
        registry: Any,
    ) -> Optional[str]:
        """
        Find best alternative provider.

        Args:
            exclude_provider: Provider to exclude from consideration
            registry: Provider registry

        Returns:
            Alternative provider name or None
        """
        available = registry.list_available()
        candidates = [p for p in available if p != exclude_provider]

        if not candidates:
            return None

        # Rank candidates by quota
        ranked = self._scorer.rank_providers(candidates, registry)

        # Return first non-exhausted provider
        for score in ranked:
            if not score.is_rate_limited and score.score > self._block_threshold:
                return score.provider

        return None
