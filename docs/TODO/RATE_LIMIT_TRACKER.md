# RateLimitTracker Refactoring Plan

## Current State

**File:** `src/orchestrator/rate_limiter.py` (636 lines)

**Multiple Responsibilities:**
1. File I/O operations
2. Usage calculations
3. Provider query logic
4. Daily/monthly reset logic
5. Quota recommendations

## Target Architecture

```
orchestrator/rate_limiting/
  ├── __init__.py
  ├── protocols.py         # ALL protocols defined FIRST
  ├── tracker.py           # Facade - coordination only
  ├── storage.py           # File I/O implementation
  ├── calculator.py        # Usage calculations implementation
  ├── policy.py            # Reset intervals implementation
  ├── recommender.py       # Provider selection implementation
  └── factory.py           # Factory for creating tracker with defaults
```

---

## Phase 1: Define Protocols (DO THIS FIRST)

**File:** `orchestrator/rate_limiting/protocols.py`

```python
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
```

---

## Phase 2: Implement Storage

**File:** `orchestrator/rate_limiting/storage.py`

```python
"""Rate limit data persistence."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Optional

try:
    import aiofiles
    _AIO = True
except ImportError:
    _AIO = False

from .protocols import StorageProtocol, FileSystemProtocol


class FileSystemAdapter:
    """Standard file system implementation."""

    def exists(self, path: Path) -> bool:
        return path.exists()

    def read_text(self, path: Path, encoding: str = "utf-8") -> str:
        return path.read_text(encoding=encoding)

    def write_text(self, path: Path, content: str, encoding: str = "utf-8") -> None:
        path.write_text(content, encoding=encoding)

    def mkdir(self, path: Path, parents: bool = False, exist_ok: bool = False) -> None:
        path.mkdir(parents=parents, exist_ok=exist_ok)

    def unlink(self, path: Path) -> None:
        path.unlink()


class RateLimitStorage:
    """
    Persistent storage for rate limit data.

    Single responsibility: Load and save usage data.
    No business logic, no calculations, no decisions.
    """

    def __init__(
        self,
        file_path: Optional[Path],
        file_system: FileSystemProtocol,
    ):
        """
        Initialize storage.

        Args:
            file_path: Path to storage file (None = no persistence)
            file_system: File system abstraction for I/O
        """
        self.path = file_path
        self._fs = file_system

    # ---------- sync ----------

    def load(self) -> dict[str, Any]:
        """Load usage data from disk."""
        if not self.path or not self._fs.exists(self.path):
            return {}

        try:
            content = self._fs.read_text(self.path)
            return json.loads(content)
        except Exception:
            # Corrupted file - start fresh
            return {}

    def save(self, data: dict[str, Any]) -> None:
        """Save usage data to disk."""
        if not self.path:
            return

        # Ensure parent directory exists
        if self.path.parent:
            self._fs.mkdir(self.path.parent, parents=True, exist_ok=True)

        content = json.dumps(data, indent=2)
        self._fs.write_text(self.path, content)

    # ---------- async ----------

    async def load_async(self) -> dict[str, Any]:
        """Load usage data asynchronously."""
        if not _AIO:
            return self.load()

        if not self.path or not self._fs.exists(self.path):
            return {}

        try:
            async with aiofiles.open(self.path, encoding="utf-8") as f:
                content = await f.read()
                return json.loads(content)
        except Exception:
            return {}

    async def save_async(self, data: dict[str, Any]) -> None:
        """Save usage data asynchronously."""
        if not _AIO:
            return self.save(data)

        if not self.path:
            return

        # Ensure parent directory exists (sync is fine here)
        if self.path.parent:
            self._fs.mkdir(self.path.parent, parents=True, exist_ok=True)

        content = json.dumps(data, indent=2)
        async with aiofiles.open(self.path, "w", encoding="utf-8") as f:
            await f.write(content)
```

---

## Phase 3: Implement Policy

**File:** `orchestrator/rate_limiting/policy.py`

```python
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

    # ------- private helpers -------

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
```

---

## Phase 4: Implement Calculator

**File:** `orchestrator/rate_limiting/calculator.py`

```python
"""Rate limit calculations."""
from __future__ import annotations
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from ..providers import ProviderLimits


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

    # ------- private helpers -------

    @staticmethod
    def _sub(limit: Optional[int], used: int) -> Optional[int]:
        """Subtract usage from limit, returning None if no limit."""
        if limit is None:
            return None
        return max(0, limit - used)
```

---

## Phase 5: Implement Recommender

**File:** `orchestrator/rate_limiting/recommender.py`

```python
"""Provider recommendation based on rate limits."""
from __future__ import annotations
from typing import Any, Optional

from .protocols import UsageQueryProtocol


# Task preferences - can be moved to config later
TASK_PREFERENCES = {
    "general": ["openai", "anthropic", "gemini"],
    "research": ["openai", "anthropic", "gemini"],
    "coding": ["anthropic", "openai", "gemini"],
    "analysis": ["anthropic", "openai", "gemini"],
}


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
```

---

## Phase 6: Implement Tracker Facade

**File:** `orchestrator/rate_limiting/tracker.py`

```python
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
    from .output import OutputInterface


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
        output: Optional[OutputInterface] = None,
        auto_load: bool = False,
    ):
        """
        Initialize tracker.

        Args:
            storage: Persistence layer
            policy: Reset policy
            calculator: Usage calculations
            recommender: Provider recommendation
            output: Optional output interface
            auto_load: If True, load data from storage on init
        """
        self._storage = storage
        self._policy = policy
        self._calc = calculator
        self._recommender = recommender
        self.output = output or self._default_output()

        self._usage: Dict[str, Any] = {}
        self._initialise_empty()

        if auto_load:
            self.restore_from_disk()

    # ---------- lifecycle ----------

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

    # ---------- recording ----------

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

    # ---------- queries (UsageQueryProtocol implementation) ----------

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

    # ---------- actions ----------

    def clear(self) -> None:
        """Clear all usage data and delete storage file."""
        self._initialise_empty()
        # Storage deletion handled via file system protocol
        # This is a bit awkward - might need to expose unlink on StorageProtocol

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

    # ---------- provider helpers ----------

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

    # ---------- private helpers ----------

    def _default_output(self) -> OutputInterface:
        """Create default output interface."""
        from .output import NullOutput
        return NullOutput()

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
```

---

## Phase 7: Factory Function

**File:** `orchestrator/rate_limiting/factory.py`

```python
"""Factory for creating rate limit tracker with default dependencies."""
from __future__ import annotations
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from .tracker import RateLimitTracker
from .storage import RateLimitStorage, FileSystemAdapter
from .policy import RateLimitPolicy
from .calculator import RateLimitCalculator
from .recommender import RateLimitRecommender

if TYPE_CHECKING:
    from .output import OutputInterface


def create_rate_limit_tracker(
    tracker_file: Optional[str | Path] = None,
    output: Optional[OutputInterface] = None,
    auto_load: bool = False,
) -> RateLimitTracker:
    """
    Create rate limit tracker with default dependencies.

    This is the primary way to create a tracker for production use.
    For testing, instantiate RateLimitTracker directly with test doubles.

    Args:
        tracker_file: Path to tracker file (None = no persistence)
        output: Optional output interface
        auto_load: If True, load data from storage on init

    Returns:
        Configured RateLimitTracker instance
    """
    # Convert to Path if string
    path = Path(tracker_file) if tracker_file else None

    # Create dependencies
    file_system = FileSystemAdapter()
    storage = RateLimitStorage(path, file_system)
    policy = RateLimitPolicy()
    calculator = RateLimitCalculator()

    # Create tracker first (needed by recommender)
    tracker = RateLimitTracker(
        storage=storage,
        policy=policy,
        calculator=calculator,
        recommender=None,  # type: ignore - will be set next
        output=output,
        auto_load=False,  # Load after recommender is set
    )

    # Create recommender with tracker as usage query
    recommender = RateLimitRecommender(tracker)

    # Inject recommender
    tracker._recommender = recommender

    # Now load if requested
    if auto_load:
        tracker.restore_from_disk()

    return tracker
```

---

## Phase 8: Package Exports

**File:** `orchestrator/rate_limiting/__init__.py`

```python
"""Rate limiting package."""
from .tracker import RateLimitTracker
from .factory import create_rate_limit_tracker
from .protocols import (
    StorageProtocol,
    PolicyProtocol,
    CalculatorProtocol,
    RecommenderProtocol,
    UsageQueryProtocol,
    FileSystemProtocol,
)

__all__ = [
    # Main API
    "RateLimitTracker",
    "create_rate_limit_tracker",

    # Protocols (for testing and custom implementations)
    "StorageProtocol",
    "PolicyProtocol",
    "CalculatorProtocol",
    "RecommenderProtocol",
    "UsageQueryProtocol",
    "FileSystemProtocol",
]
```

---

## Phase 9: Backward Compatibility Shim

**File:** `src/orchestrator/rate_limiter.py`

```python
"""
Legacy compatibility shim for RateLimitTracker.

DEPRECATED: Import from orchestrator.rate_limiting instead.
This file will be removed in a future version.
"""
from orchestrator.rate_limiting import RateLimitTracker, create_rate_limit_tracker

__all__ = ["RateLimitTracker", "create_rate_limit_tracker"]
```

---

## Phase 10: Testing Strategy

### Test Doubles

**File:** `tests/helpers.py` (add these)

```python
"""Test doubles for rate limiting components."""
from typing import Any, Dict, List, Optional
from pathlib import Path


class FakeFileSystem:
    """Test double for file system operations."""

    def __init__(self):
        self._files: Dict[Path, str] = {}
        self._dirs: set[Path] = set()

    def exists(self, path: Path) -> bool:
        return path in self._files or path in self._dirs

    def read_text(self, path: Path, encoding: str = "utf-8") -> str:
        if path not in self._files:
            raise FileNotFoundError(f"No such file: {path}")
        return self._files[path]

    def write_text(self, path: Path, content: str, encoding: str = "utf-8") -> None:
        self._files[path] = content

    def mkdir(self, path: Path, parents: bool = False, exist_ok: bool = False) -> None:
        if path in self._dirs and not exist_ok:
            raise FileExistsError(f"Directory exists: {path}")
        self._dirs.add(path)
        if parents:
            current = path.parent
            while current and current != current.parent:
                self._dirs.add(current)
                current = current.parent

    def unlink(self, path: Path) -> None:
        if path in self._files:
            del self._files[path]


class FakeStorage:
    """Test double for storage."""

    def __init__(self):
        self._data: Optional[dict[str, Any]] = None
        self.load_count = 0
        self.save_count = 0

    def load(self) -> dict[str, Any]:
        self.load_count += 1
        return self._data.copy() if self._data else {}

    def save(self, data: dict[str, Any]) -> None:
        self.save_count += 1
        self._data = data.copy()

    async def load_async(self) -> dict[str, Any]:
        return self.load()

    async def save_async(self, data: dict[str, Any]) -> None:
        return self.save(data)


class FakePolicy:
    """Test double for reset policy."""

    def __init__(self, reset_flags: Optional[Dict[str, bool]] = None):
        self.reset_flags = reset_flags or {"daily": False, "monthly": False}
        self.reset_calls: List[Dict[str, bool]] = []

    def reset_needed(self, last_reset_info: Dict[str, str]) -> Dict[str, bool]:
        return self.reset_flags

    def apply_reset(self, usage: dict[str, Any], which: Dict[str, bool]) -> None:
        self.reset_calls.append(which)


class FakeCalculator:
    """Test double for calculator."""

    def __init__(self):
        self.remaining_calls = []
        self.warnings_calls = []
        self.summarise_calls = []

    def remaining(self, usage: dict[str, Any], limits: Any) -> Dict[str, Any]:
        self.remaining_calls.append((usage, limits))
        return {
            "requests_remaining_today": 100,
            "requests_remaining_month": 1000,
            "tokens_remaining_today": 10000,
            "tokens_remaining_minute": 1000,
            "usage_today": 0,
            "tokens_today": 0,
            "usage_this_month": 0,
        }

    def warnings(
        self,
        remaining: Dict[str, Any],
        limits: Any,
        threshold: float = 0.1,
    ) -> Dict[str, Any]:
        self.warnings_calls.append((remaining, limits, threshold))
        return {
            "approaching_daily_request_limit": False,
            "approaching_monthly_request_limit": False,
            "approaching_daily_token_limit": False,
            "message": None,
        }

    def summarise(self, usage: dict[str, Any]) -> Dict[str, Any]:
        self.summarise_calls.append(usage)
        return {"last_reset": {}, "providers": {}}


class FakeRecommender:
    """Test double for recommender."""

    def __init__(self, provider_to_recommend: Optional[str] = "openai"):
        self.provider = provider_to_recommend
        self.calls = []

    def recommended(
        self,
        task_type: str,
        registry: Any,
        task_preferences: dict[str, list[str]],
    ) -> Optional[str]:
        self.calls.append((task_type, registry, task_preferences))
        return self.provider
```

### Test Structure

**File:** `tests/test_rate_limiting/` (new directory)

```
tests/test_rate_limiting/
  ├── test_storage.py
  ├── test_policy.py
  ├── test_calculator.py
  ├── test_recommender.py
  ├── test_tracker.py
  └── test_integration.py
```

### Example Test: Storage

**File:** `tests/test_rate_limiting/test_storage.py`

```python
"""Tests for rate limit storage."""
import json
from pathlib import Path
import pytest

from orchestrator.rate_limiting.storage import RateLimitStorage
from tests.helpers import FakeFileSystem


def test_load_returns_empty_dict_when_file_not_exists():
    """Should return empty dict when file doesn't exist."""
    fs = FakeFileSystem()
    storage = RateLimitStorage(Path("/data.json"), fs)

    result = storage.load()

    assert result == {}


def test_load_returns_data_when_file_exists():
    """Should return parsed JSON when file exists."""
    fs = FakeFileSystem()
    path = Path("/data.json")
    data = {"providers": {"openai": {}}}
    fs.write_text(path, json.dumps(data))

    storage = RateLimitStorage(path, fs)
    result = storage.load()

    assert result == data


def test_load_returns_empty_dict_when_file_corrupted():
    """Should return empty dict when JSON is invalid."""
    fs = FakeFileSystem()
    path = Path("/data.json")
    fs.write_text(path, "invalid json{")

    storage = RateLimitStorage(path, fs)
    result = storage.load()

    assert result == {}


def test_save_writes_json_to_file():
    """Should write formatted JSON to file."""
    fs = FakeFileSystem()
    path = Path("/data/usage.json")
    storage = RateLimitStorage(path, fs)

    data = {"providers": {"openai": {"gpt-4": {"requests_today": 5}}}}
    storage.save(data)

    saved_content = fs.read_text(path)
    assert json.loads(saved_content) == data


def test_save_creates_parent_directory():
    """Should create parent directories if they don't exist."""
    fs = FakeFileSystem()
    path = Path("/data/subdir/usage.json")
    storage = RateLimitStorage(path, fs)

    storage.save({"test": "data"})

    assert fs.exists(Path("/data"))
    assert fs.exists(Path("/data/subdir"))


def test_save_does_nothing_when_path_is_none():
    """Should not save when path is None."""
    fs = FakeFileSystem()
    storage = RateLimitStorage(None, fs)

    storage.save({"test": "data"})

    # Should not raise, should not write anything
    assert len(fs._files) == 0
```

### Example Test: Calculator Edge Cases

**File:** `tests/test_rate_limiting/test_calculator.py`

```python
"""Tests for rate limit calculator."""
import pytest

from orchestrator.rate_limiting.calculator import RateLimitCalculator


class FakeProviderLimits:
    """Test double for provider limits."""
    def __init__(
        self,
        requests_per_day=None,
        requests_per_month=None,
        tokens_per_day=None,
        tokens_per_minute=None,
    ):
        self.requests_per_day = requests_per_day
        self.requests_per_month = requests_per_month
        self.tokens_per_day = tokens_per_day
        self.tokens_per_minute = tokens_per_minute


def test_remaining_with_no_usage():
    """Should return full limits when no usage."""
    calc = RateLimitCalculator()
    usage = {
        "requests_today": 0,
        "requests_this_month": 0,
        "tokens_today": 0,
    }
    limits = FakeProviderLimits(
        requests_per_day=100,
        requests_per_month=1000,
        tokens_per_day=10000,
        tokens_per_minute=1000,
    )

    result = calc.remaining(usage, limits)

    assert result["requests_remaining_today"] == 100
    assert result["requests_remaining_month"] == 1000
    assert result["tokens_remaining_today"] == 10000
    assert result["tokens_remaining_minute"] == 1000


def test_remaining_with_partial_usage():
    """Should calculate remaining quota correctly."""
    calc = RateLimitCalculator()
    usage = {
        "requests_today": 30,
        "requests_this_month": 250,
        "tokens_today": 2500,
    }
    limits = FakeProviderLimits(
        requests_per_day=100,
        requests_per_month=1000,
        tokens_per_day=10000,
    )

    result = calc.remaining(usage, limits)

    assert result["requests_remaining_today"] == 70
    assert result["requests_remaining_month"] == 750
    assert result["tokens_remaining_today"] == 7500


def test_remaining_never_goes_negative():
    """Should return 0, not negative, when usage exceeds limit."""
    calc = RateLimitCalculator()
    usage = {
        "requests_today": 150,
        "tokens_today": 15000,
    }
    limits = FakeProviderLimits(
        requests_per_day=100,
        tokens_per_day=10000,
    )

    result = calc.remaining(usage, limits)

    assert result["requests_remaining_today"] == 0
    assert result["tokens_remaining_today"] == 0


def test_remaining_with_no_limits():
    """Should return None for unlimited quotas."""
    calc = RateLimitCalculator()
    usage = {"requests_today": 100}
    limits = FakeProviderLimits()  # All limits are None

    result = calc.remaining(usage, limits)

    assert result["requests_remaining_today"] is None
    assert result["requests_remaining_month"] is None
    assert result["tokens_remaining_today"] is None


def test_warnings_detects_approaching_daily_request_limit():
    """Should warn when approaching daily request limit."""
    calc = RateLimitCalculator()
    remaining = {
        "requests_remaining_today": 5,
        "requests_remaining_month": 500,
        "tokens_remaining_today": 5000,
    }
    limits = FakeProviderLimits(
        requests_per_day=100,
        requests_per_month=1000,
        tokens_per_day=10000,
    )

    result = calc.warnings(remaining, limits, threshold=0.1)

    assert result["approaching_daily_request_limit"] is True
    assert "5 requests remaining today" in result["message"]


def test_warnings_detects_approaching_token_limit():
    """Should warn when approaching daily token limit."""
    calc = RateLimitCalculator()
    remaining = {
        "requests_remaining_today": 50,
        "tokens_remaining_today": 500,
    }
    limits = FakeProviderLimits(
        requests_per_day=100,
        tokens_per_day=10000,
    )

    result = calc.warnings(remaining, limits, threshold=0.1)

    assert result["approaching_daily_token_limit"] is True
    assert "500 tokens remaining today" in result["message"]


def test_warnings_no_warning_when_plenty_remaining():
    """Should not warn when plenty of quota remaining."""
    calc = RateLimitCalculator()
    remaining = {
        "requests_remaining_today": 80,
        "tokens_remaining_today": 9000,
    }
    limits = FakeProviderLimits(
        requests_per_day=100,
        tokens_per_day=10000,
    )

    result = calc.warnings(remaining, limits, threshold=0.1)

    assert result["approaching_daily_request_limit"] is False
    assert result["approaching_daily_token_limit"] is False
    assert result["message"] is None
```

---

## Migration Guide

### Step 1: Create New Package (Merge Anytime)

```bash
mkdir -p orchestrator/rate_limiting
# Create all files in phases 1-9
python -m pytest tests/test_rate_limiting/ -v
```

### Step 2: Update Imports (Gradual)

```python
# Old
from orchestrator.rate_limiter import RateLimitTracker

# New (via factory)
from orchestrator.rate_limiting import create_rate_limit_tracker
tracker = create_rate_limit_tracker(tracker_file="usage.json", auto_load=True)

# New (for testing with doubles)
from orchestrator.rate_limiting import RateLimitTracker
from tests.helpers import FakeStorage, FakePolicy, FakeCalculator, FakeRecommender

tracker = RateLimitTracker(
    storage=FakeStorage(),
    policy=FakePolicy(),
    calculator=FakeCalculator(),
    recommender=FakeRecommender(),
)
```

### Step 3: Remove Old File (When Ready)

```bash
# Verify no more references
git grep "from orchestrator.rate_limiter import"

# Remove old file
rm src/orchestrator/rate_limiter.py
```

---

## Architecture Benefits

### SOLID Compliance

- **Single Responsibility**: Each class has one reason to change
  - `Storage`: Only changes if persistence format changes
  - `Policy`: Only changes if reset rules change
  - `Calculator`: Only changes if calculation logic changes
  - `Recommender`: Only changes if selection strategy changes

- **Open/Closed**: Add new behavior without modifying existing code
  - New storage backends (database, S3, Redis)
  - New reset policies (weekly, hourly, custom)
  - New recommendation strategies (ML-based, cost-based)

- **Liskov Substitution**: All implementations honor protocol contracts
  - Can swap `RateLimitStorage` for `RedisStorage`
  - Can swap `RateLimitPolicy` for `CustomPolicy`

- **Interface Segregation**: Recommender depends only on `UsageQueryProtocol`
  - Doesn't need full tracker API
  - Clear, minimal interface

- **Dependency Inversion**: All dependencies are protocols
  - Easy to test with fakes
  - Easy to swap implementations

### Testing Benefits

- **No file I/O in tests**: Use `FakeFileSystem`
- **No real dates in tests**: Inject `Policy(today=date(2024, 1, 1))`
- **Fast tests**: All pure Python, no I/O
- **Focused tests**: Test one component at a time
- **Edge cases easy**: Inject specific test doubles

### Maintainability Benefits

- **Clear responsibilities**: Know where to add features
- **No god class**: Each class < 200 lines
- **Easy to understand**: Each file has one job
- **Easy to extend**: Add new implementations without touching existing code

---

## What We Gained

From 636-line god class to focused components:
- 50 lines: `protocols.py` (contracts)
- 80 lines: `storage.py` (persistence)
- 50 lines: `policy.py` (reset rules)
- 80 lines: `calculator.py` (math)
- 60 lines: `recommender.py` (selection)
- 200 lines: `tracker.py` (facade)
- 30 lines: `factory.py` (construction)

**Total: ~550 lines across 7 focused files**

Each file:
- Has one responsibility
- Is easy to test
- Is easy to understand
- Is easy to extend
- Follows SOLID principles

**No breaking changes. Complete backward compatibility.**
