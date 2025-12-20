"""
Protocols for rate limiting components.

Define ALL contracts BEFORE writing any implementation.
This enables testing, dependency injection, and SOLID principles.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol


# --- Enforcement Types ---

class EnforcementAction(Enum):
    """Actions the enforcement policy can recommend."""
    ALLOW = "allow"           # Proceed with request
    WARN = "warn"             # Allow but warn user
    QUEUE = "queue"           # Delay request (future)
    BLOCK = "block"           # Reject request, use fallback
    FAIL = "fail"             # Reject request, no fallback available


@dataclass
class EnforcementDecision:
    """Decision from enforcement policy."""
    action: EnforcementAction
    provider: str
    reason: str
    alternative_provider: Optional[str] = None
    wait_seconds: Optional[float] = None  # For QUEUE action
    remaining_quota: Optional[Dict[str, int]] = None


@dataclass
class QuotaScore:
    """Score representing provider availability."""
    provider: str
    score: float  # 0.0 (exhausted) to 1.0 (fully available)
    requests_remaining: int
    tokens_remaining: int
    is_rate_limited: bool
    warning_threshold_hit: bool


class NotificationLevel(Enum):
    """Notification severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class StorageProtocol(Protocol):
    """Contract for persisting rate limit data."""

    def load(self) -> dict[str, Any]:
        """Load usage data from storage. Returns empty dict if not found."""
        ...

    def save(self, data: dict[str, Any]) -> None:
        """Persist usage data to storage."""
        ...

    async def load_async(self) -> dict[str, Any]:
        """Load usage data asynchronously."""
        ...

    async def save_async(self, data: dict[str, Any]) -> None:
        """Persist usage data asynchronously."""
        ...


class PolicyProtocol(Protocol):
    """Contract for determining when to reset rate limit counters."""

    def reset_needed(self, last_reset_info: Dict[str, str]) -> Dict[str, bool]:
        """
        Check if daily or monthly reset is needed.

        Args:
            last_reset_info: Dict with 'daily' and 'monthly' ISO date strings

        Returns:
            Dict with 'daily' and 'monthly' boolean flags
        """
        ...

    def apply_reset(self, usage: dict[str, Any], which: Dict[str, bool]) -> None:
        """
        Reset counters in usage dict based on flags.

        Args:
            usage: Usage data dict (mutated in-place)
            which: Dict with 'daily' and 'monthly' boolean flags
        """
        ...


class CalculatorProtocol(Protocol):
    """Contract for computing rate limit calculations."""

    def remaining(
        self,
        usage: dict[str, Any],
        limits: Any,  # ProviderLimits - avoid circular import in protocol
    ) -> Dict[str, Any]:
        """
        Calculate remaining quota.

        Returns dict with:
        - requests_remaining_today
        - requests_remaining_month
        - tokens_remaining_today
        - tokens_remaining_minute
        - usage_today
        - tokens_today
        - usage_this_month
        """
        ...

    def warnings(
        self,
        remaining: Dict[str, Any],
        limits: Any,  # ProviderLimits
        threshold: float = 0.1,
    ) -> Dict[str, Any]:
        """
        Check if approaching limits.

        Returns dict with warning flags and optional message.
        """
        ...

    def summarise(self, usage: dict[str, Any]) -> Dict[str, Any]:
        """
        Build summary of all provider usage.

        Returns nested dict with provider and model statistics.
        """
        ...


class UsageQueryProtocol(Protocol):
    """
    Contract for querying rate limit usage.

    This breaks the circular dependency between tracker and recommender.
    Recommender only needs to QUERY usage, not the full tracker API.
    """

    def get_remaining_quota(
        self,
        provider: str,
        model: str,
        limits: Any,  # ProviderLimits
    ) -> dict[str, Any]:
        """Get remaining quota for provider/model."""
        ...

    def is_rate_limited(self, provider_name: str, registry: Any) -> bool:
        """Check if provider is currently rate limited."""
        ...


class RecommenderProtocol(Protocol):
    """Contract for recommending providers based on rate limits."""

    def recommended(
        self,
        task_type: str,
        registry: Any,  # ProviderRegistry
        task_preferences: dict[str, list[str]],
    ) -> Optional[str]:
        """
        Recommend best available provider for task type.

        Returns provider name or None if all are rate limited.
        """
        ...


class FileSystemProtocol(Protocol):
    """Contract for file system operations."""

    def exists(self, path: Path) -> bool:
        """Check if path exists."""
        ...

    def read_text(self, path: Path, encoding: str = "utf-8") -> str:
        """Read text file content."""
        ...

    def write_text(self, path: Path, content: str, encoding: str = "utf-8") -> None:
        """Write text to file."""
        ...

    def mkdir(self, path: Path, parents: bool = False, exist_ok: bool = False) -> None:
        """Create directory."""
        ...

    def unlink(self, path: Path) -> None:
        """Delete file."""
        ...


# --- Enforcement Protocols ---

class QuotaScorerProtocol(Protocol):
    """Contract for scoring providers by available quota."""

    def score_provider(
        self,
        provider: str,
        model: str,
        limits: Any,  # ProviderLimits
    ) -> QuotaScore:
        """
        Score a single provider's availability.

        Args:
            provider: Provider name
            model: Model name
            limits: Provider limits

        Returns:
            QuotaScore with availability metrics
        """
        ...

    def rank_providers(
        self,
        providers: List[str],
        registry: Any,  # ProviderRegistry
        task_type: str = "general",
    ) -> List[QuotaScore]:
        """
        Rank all providers by quota availability.

        Args:
            providers: List of provider names to rank
            registry: Provider registry for limit lookup
            task_type: Type of task for preference weighting

        Returns:
            List of QuotaScore sorted by score (highest first)
        """
        ...


class EnforcementPolicyProtocol(Protocol):
    """Contract for rate limit enforcement decisions."""

    def evaluate(
        self,
        provider: str,
        model: str,
        estimated_tokens: int,
        registry: Any,  # ProviderRegistry
    ) -> EnforcementDecision:
        """
        Evaluate whether a request should proceed.

        Args:
            provider: Target provider name
            model: Target model name
            estimated_tokens: Estimated token usage for request
            registry: Provider registry for fallback lookup

        Returns:
            EnforcementDecision with action and context
        """
        ...


class UserNotifierProtocol(Protocol):
    """Contract for user-facing rate limit notifications."""

    def notify_approaching_limit(
        self,
        provider: str,
        remaining_percent: float,
        remaining_requests: int,
    ) -> None:
        """
        Warn user that limits are approaching.

        Args:
            provider: Provider name
            remaining_percent: Percentage of quota remaining (0.0-1.0)
            remaining_requests: Absolute requests remaining
        """
        ...

    def notify_fallback(
        self,
        from_provider: str,
        to_provider: str,
        reason: str,
    ) -> None:
        """
        Inform user of automatic provider switch.

        Args:
            from_provider: Original provider
            to_provider: Fallback provider
            reason: Why fallback occurred
        """
        ...

    def notify_all_exhausted(
        self,
        attempted_providers: List[str],
    ) -> None:
        """
        Alert user that all providers are exhausted.

        Args:
            attempted_providers: List of providers that were tried
        """
        ...
