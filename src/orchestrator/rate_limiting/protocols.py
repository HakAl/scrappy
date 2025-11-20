"""
Protocols for rate limiting components.

Define ALL contracts BEFORE writing any implementation.
This enables testing, dependency injection, and SOLID principles.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol


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
