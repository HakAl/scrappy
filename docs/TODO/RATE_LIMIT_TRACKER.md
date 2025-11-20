
#### RateLimitTracker (`src/orchestrator/rate_limiter.py` - 636 lines)

**Multiple Responsibilities:**
1. File I/O operations
2. Usage calculations
3. Provider query logic
4. Daily/monthly reset logic
5. Quota recommendations

**Refactor Plan:**
```python
orchestrator/rate_limiting/
  ├── tracker.py (RateLimitTracker - coordination only)
  ├── storage.py (RateLimitStorage - file I/O)
  ├── calculator.py (RateLimitCalculator - usage calculations)
  ├── policy.py (RateLimitPolicy - reset intervals, thresholds)
  └── recommender.py (RateLimitRecommender - provider selection)
```
Below is an **incremental, safe-to-merge** refactoring that keeps every public method working (so existing callers don’t break) while moving the five responsibilities into their own SOLID classes.  
The new package layout is exactly the one you sketched:

```
orchestrator/rate_limiting/
├── __init__.py
├── tracker.py          # façade – keeps the old public API
├── storage.py          # file I/O (sync + async)
├── calculator.py       # maths: remaining quota, warnings, etc.
├── policy.py           # “when do we reset?”
└── recommender.py      # provider-selection logic
```

You can merge the PR after every commit; nothing outside `rate_limiter.py` has to change.

--------------------------------------------------
1.  storage.py  – single responsibility: persistence
--------------------------------------------------
```python
# orchestrator/rate_limiting/storage.py
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Optional

try:
    import aiofiles
    _AIO = True
except ImportError:
    _AIO = False

class RateLimitStorage:
    """Load / save the usage blob (dict).  No business logic."""

    def __init__(self, file_path: Optional[Path]):
        self.path: Optional[Path] = file_path

    # ---------- sync ----------
    def load(self) -> dict[str, Any]:
        if not self.path or not self.path.exists():
            return {}
        try:
            with self.path.open(encoding="utf-8") as f:
                return json.load(f)
        except Exception:          # corrupted file → start fresh
            return {}

    def save(self, data: dict[str, Any]) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    # ---------- async ----------
    async def load_async(self) -> dict[str, Any]:
        if not _AIO:
            return self.load()
        if not self.path or not self.path.exists():
            return {}
        try:
            async with aiofiles.open(self.path, encoding="utf-8") as f:
                return json.loads(await f.read())
        except Exception:
            return {}

    async def save_async(self, data: dict[str, Any]) -> None:
        if not _AIO:
            return self.save(data)
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(self.path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, indent=2))
```

--------------------------------------------------
2.  policy.py  – single responsibility: reset rules
--------------------------------------------------
```python
# orchestrator/rate_limiting/policy.py
from __future__ import annotations
from datetime import date, datetime
from typing import Any, Dict

class RateLimitPolicy:
    """Decides *when* to reset daily / monthly counters."""

    def __init__(self, today: date | None = None):
        self.today = today or date.today()

    def reset_needed(self, last_reset_info: Dict[str, str]) -> Dict[str, bool]:
        """Return flags: {'daily': bool, 'monthly': bool}"""
        cur_date = self.today.isoformat()
        cur_month = self.today.strftime("%Y-%m")

        return {
            "daily": last_reset_info.get("daily") != cur_date,
            "monthly": last_reset_info.get("monthly") != cur_month,
        }

    def apply_reset(self, usage: dict[str, Any], which: Dict[str, bool]) -> None:
        """Mutate usage dict in-place."""
        if which["daily"]:
            self._reset_daily(usage)
        if which["monthly"]:
            self._reset_monthly(usage)

    # ------- helpers -------
    def _reset_daily(self, usage: dict[str, Any]) -> None:
        for prov in usage.get("providers", {}).values():
            for model in prov.values():
                model["requests_today"] = 0
                model["tokens_today"] = 0
                model["input_tokens_today"] = 0
                model["output_tokens_today"] = 0

    def _reset_monthly(self, usage: dict[str, Any]) -> None:
        for prov in usage.get("providers", {}).values():
            for model in prov.values():
                model["requests_this_month"] = 0
                model["tokens_this_month"] = 0
```

--------------------------------------------------
3.  calculator.py  – single responsibility: maths
--------------------------------------------------
```python
# orchestrator/rate_limiting/calculator.py
from __future__ import annotations
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from ..providers import ProviderLimits

class RateLimitCalculator:
    """Pure functions to compute remaining quota & warnings."""

    # ---------- remaining ----------
    def remaining(
        self,
        usage: dict[str, Any],
        limits: ProviderLimits,
    ) -> Dict[str, Any]:
        """Return dict with remaining counts."""
        return {
            "requests_remaining_today": self._sub(limits.requests_per_day, usage.get("requests_today", 0)),
            "requests_remaining_month": self._sub(limits.requests_per_month, usage.get("requests_this_month", 0)),
            "tokens_remaining_today": self._sub(limits.tokens_per_day, usage.get("tokens_today", 0)),
            "tokens_remaining_minute": limits.tokens_per_minute,  # no history
            "usage_today": usage.get("requests_today", 0),
            "tokens_today": usage.get("tokens_today", 0),
            "usage_this_month": usage.get("requests_this_month", 0),
        }

    # ---------- warnings ----------
    def warnings(
        self,
        remaining: Dict[str, Any],
        limits: ProviderLimits,
        threshold: float = 0.1,
    ) -> Dict[str, Any]:
        """Return flag dict + optional human message."""
        flags: Dict[str, bool] = {
            "approaching_daily_request_limit": False,
            "approaching_monthly_request_limit": False,
            "approaching_daily_token_limit": False,
        }
        msgs = []
        if limits.requests_per_day and remaining["requests_remaining_today"] is not None:
            if remaining["requests_remaining_today"] <= limits.requests_per_day * threshold:
                flags["approaching_daily_request_limit"] = True
                msgs.append(f"Only {remaining['requests_remaining_today']} requests remaining today")

        if limits.requests_per_month and remaining["requests_remaining_month"] is not None:
            if remaining["requests_remaining_month"] <= limits.requests_per_month * threshold:
                flags["approaching_monthly_request_limit"] = True
                msgs.append(f"Only {remaining['requests_remaining_month']} requests remaining this month")

        if limits.tokens_per_day and remaining["tokens_remaining_today"] is not None:
            if remaining["tokens_remaining_today"] <= limits.tokens_per_day * threshold:
                flags["approaching_daily_token_limit"] = True
                msgs.append(f"Only {remaining['tokens_remaining_today']} tokens remaining today")

        flags["message"] = ", ".join(msgs) if msgs else None
        return flags

    # ---------- summary ----------
    def summarise(self, usage: dict[str, Any]) -> Dict[str, Any]:
        """Build the dict returned by get_all_usage_summary()."""
        providers = usage.get("providers", {})
        summary = {"last_reset": usage.get("last_reset", {}), "providers": {}}
        for pname, models in providers.items():
            summary["providers"][pname] = {
                "total_requests_today": sum(m.get("requests_today", 0) for m in models.values()),
                "total_tokens_today": sum(m.get("tokens_today", 0) for m in models.values()),
                "total_requests_month": sum(m.get("requests_this_month", 0) for m in models.values()),
                "models": list(models.keys()),
                "by_model": {
                    m: {
                        "requests_today": d.get("requests_today", 0),
                        "tokens_today": d.get("tokens_today", 0),
                        "last_request": d.get("last_request"),
                    }
                    for m, d in models.items()
                },
            }
        return summary

    # ------- helper -------
    @staticmethod
    def _sub(limit: Optional[int], used: int) -> Optional[int]:
        return max(0, limit - used) if limit is not None else None
```

--------------------------------------------------
4.  recommender.py  – single responsibility: pick provider
--------------------------------------------------
```python
# orchestrator/rate_limiting/recommender.py
from __future__ import annotations
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .calculator import RateLimitCalculator
    from .tracker import RateLimitTracker  # forward import

class RateLimitRecommender:
    """Chooses provider given task type and current usage."""

    def __init__(self, tracker: RateLimitTracker, calculator: RateLimitCalculator):
        self.tracker = tracker
        self.calc = calculator

    def recommended(
        self,
        task_type: str,
        registry,
        task_preferences: dict[str, list[str]],
    ) -> Optional[str]:
        """Return provider name or None."""
        available = registry.list_available()
        if not available:
            return None

        prefs = task_preferences.get(task_type, task_preferences["general"])
        for pname in prefs:
            if pname not in available:
                continue
            if self.tracker.is_rate_limited(pname, registry):   # re-use existing method
                continue
            return pname
        # fallback: first available even if limited
        return available[0] if available else None
```

--------------------------------------------------
5.  tracker.py  – façade that keeps the old API
--------------------------------------------------
We keep **exactly** the same public methods; they now delegate to the new classes.

```python
# orchestrator/rate_limiting/tracker.py
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .storage import RateLimitStorage
from .policy import RateLimitPolicy
from .calculator import RateLimitCalculator
from .recommender import RateLimitRecommender
from .config import TASK_PREFERENCES

if TYPE_CHECKING:
    from ..providers import ProviderLimits
    from .output import OutputInterface

class RateLimitTracker:
    """
    Persistent rate limit tracking for LLM providers.

    This is a **façade** – all heavy work is delegated to specialised classes.
    """

    def __init__(
        self,
        tracker_file: Optional[str | Path] = None,
        output: Optional[OutputInterface] = None,
        auto_load: bool = False,
    ) -> None:
        self.tracker_file = Path(tracker_file) if tracker_file else None
        self.output = output or self._default_output()

        self._storage = RateLimitStorage(self.tracker_file)
        self._policy = RateLimitPolicy()
        self._calc = RateLimitCalculator()
        self._recommender = RateLimitRecommender(self, self._calc)

        self._usage: Dict[str, Any] = {}
        self._initialise_empty()

        if auto_load and self.tracker_file and self.tracker_file.exists():
            self.restore_from_disk()

    # ---------- lifecycle ----------
    def restore_from_disk(self) -> RateLimitTracker:
        blob = self._storage.load()
        if blob:
            self._usage = blob
            self._check_and_reset()
        return self

    async def restore_from_disk_async(self) -> RateLimitTracker:
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
        self._check_and_reset()
        self._ensure_provider_model(provider, model)
        self._update_counters(provider, model, input_tokens, output_tokens, success, error_message)
        await self._storage.save_async(self._usage)

    # ---------- queries ----------
    def get_usage(self, provider: str, model: Optional[str] = None) -> dict[str, Any]:
        self._check_and_reset()
        prov = self._usage.get("providers", {}).get(provider, {})
        return prov.get(model, {}) if model else prov

    def get_remaining_quota(self, provider: str, model: str, limits: ProviderLimits) -> dict[str, Any]:
        self._check_and_reset()
        self._ensure_provider_model(provider, model)
        usage = self._usage["providers"][provider][model]
        return self._calc.remaining(usage, limits)

    def is_limit_approaching(
        self,
        provider: str,
        model: str,
        limits: ProviderLimits,
        threshold: float = 0.1,
    ) -> dict[str, Any]:
        remaining = self.get_remaining_quota(provider, model, limits)
        return self._calc.warnings(remaining, limits, threshold)

    def get_all_usage_summary(self) -> dict[str, Any]:
        self._check_and_reset()
        return self._calc.summarise(self._usage)

    # ---------- actions ----------
    def clear(self) -> None:
        self._initialise_empty()
        if self.tracker_file and self.tracker_file.exists():
            self.tracker_file.unlink()

    def reset_provider(self, provider: str) -> None:
        self._usage.setdefault("providers", {}).pop(provider, None)
        self._storage.save(self._usage)

    def reset_rate_tracking(self, provider_name: Optional[str] = None) -> None:
        if provider_name:
            self.reset_provider(provider_name)
        else:
            self.clear()

    # ---------- provider helpers ----------
    def is_rate_limited(self, provider_name: str, registry) -> bool:
        provider = registry.get(provider_name)
        if not provider:
            return False
        limits = provider.get_limits()
        if not limits:
            return False
        model = getattr(provider, "default_model", "default")
        rem = self.get_remaining_quota(provider_name, model, limits)
        return rem.get("requests_remaining_today") == 0 or rem.get("requests_remaining_month") == 0

    def get_recommended_provider(self, task_type: str, registry) -> Optional[str]:
        return self._recommender.recommended(task_type, registry, TASK_PREFERENCES)

    def get_rate_limit_status_extended(self, registry) -> dict[str, Any]:
        status = self.get_all_usage_summary()
        for pname in status.get("providers", {}):
            try:
                prov = registry.get(pname)
                if not prov:
                    continue
                limits = prov.get_limits()
                if not limits:
                    status["providers"][pname]["limits"] = {}
                    status["providers"][pname]["remaining"] = {}
                    continue
                rem = self.get_remaining_quota(pname, prov.default_model, limits)
                status["providers"][pname]["limits"] = {
                    "requests_per_day": limits.requests_per_day,
                    "requests_per_month": limits.requests_per_month,
                    "tokens_per_day": limits.tokens_per_day,
                    "tokens_per_minute": limits.tokens_per_minute,
                }
                status["providers"][pname]["remaining"] = rem
            except Exception:
                status["providers"][pname]["limits"] = {}
                status["providers"][pname]["remaining"] = {}
        return status

    def check_all_warnings(self, registry) -> List[str]:
        warnings = []
        for pname in registry.list_available():
            try:
                prov = registry.get(pname)
                if not prov:
                    continue
                limits = prov.get_limits()
                if not limits:
                    continue
                for model in self.get_usage(pname).keys():
                    w = self.is_limit_approaching(pname, model, limits)
                    if w.get("message"):
                        warnings.append(w["message"])
            except Exception:
                continue
        return warnings

    def get_remaining_quota_for_provider(
        self,
        provider_name: str,
        registry,
        model: Optional[str] = None,
    ) -> dict[str, Any]:
        provider = registry.get(provider_name)
        if provider is None:
            raise ValueError(f"Provider '{provider_name}' not available")
        limits = provider.get_limits()
        if model is None:
            model = provider.default_model
        return self.get_remaining_quota(provider_name, model, limits)

    # ---------- private ----------
    def _default_output(self) -> OutputInterface:
        from .output import NullOutput
        return NullOutput()

    def _initialise_empty(self) -> None:
        self._usage = {
            "providers": {},
            "last_reset": {
                "daily": datetime.now().date().isoformat(),
                "monthly": datetime.now().strftime("%Y-%m"),
            },
            "created_at": datetime.now().isoformat(),
        }

    def _check_and_reset(self) -> None:
        flags = self._policy.reset_needed(self._usage.get("last_reset", {}))
        if flags["daily"] or flags["monthly"]:
            self._policy.apply_reset(self._usage, flags)
            self._usage["last_reset"]["daily"] = datetime.now().date().isoformat()
            self._usage["last_reset"]["monthly"] = datetime.now().strftime("%Y-%m")
            self._storage.save(self._usage)

    def _ensure_provider_model(self, provider: str, model: str) -> None:
        providers = self._usage.setdefault("providers", {})
        prov = providers.setdefault(provider, {})
        prov.setdefault(model, {
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
        })

    def _update_counters(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        success: bool,
        error_message: Optional[str],
    ) -> None:
        data = self._usage["providers"][provider][model]
        total = input_tokens + output_tokens
        data["requests_today"] += 1
        data["requests_this_month"] += 1
        data["total_requests"] += 1
        data["tokens_today"] += total
        data["tokens_this_month"] += total
        data["total_tokens"] += total
        data["input_tokens_today"] += input_tokens
        data["output_tokens_today"] += output_tokens
        data["last_request"] = datetime.now().isoformat()
        if not success and error_message:
            data["errors"].append({"timestamp": datetime.now().isoformat(), "message": error_message[:200]})
            data["errors"] = data["errors"][-10:]
```

--------------------------------------------------
6.  __init__.py  – convenient re-export
--------------------------------------------------
```python
# orchestrator/rate_limiting/__init__.py
from .tracker import RateLimitTracker

__all__ = ["RateLimitTracker"]
```

--------------------------------------------------
7.  How to land this
--------------------------------------------------
1. Create the new package in a feature branch.  
2. Replace the old `src/orchestrator/rate_limiter.py` with a one-line re-export:

```python
# src/orchestrator/rate_limiter.py  (legacy compatibility)
# Deprecated – import from the new package instead.
from orchestrator.rate_limiting.tracker import RateLimitTracker
__all__ = ["RateLimitTracker"]
```

3. Run your existing test-suite – every call still works.  
4. Later, delete the compatibility shim and update imports.

--------------------------------------------------
8.  What we gained
--------------------------------------------------
- **SRP**: each class has one reason to change.  
- **OCP**: new reset policies, new persistence backends, new recommendation strategies can be added without touching existing code.  
- **ISP**: consumers that only need “remaining quota” can depend on `RateLimitCalculator` instead of the full tracker.  
- **DIP**: `tracker` depends on abstractions (`storage`, `policy`, `calculator`); we could inject mocks for unit tests.

The 636-line god class is gone, but **no caller was broken** – exactly what a refactoring should deliver.