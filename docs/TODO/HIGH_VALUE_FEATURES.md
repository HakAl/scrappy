```
Priority Implementation List

  Based on the three documents, here's my recommended priority ordering:

  Tier 1: Immediate Value (Low Effort, High Impact)

  | Priority | Feature                   | Effort | Rationale

                                          |
  |----------|---------------------------|--------|-----------------------------------------------------------------
  ------------------------------------------------------------------------------------------------------------------
  ----------------------------------------|
  | 2        | XDG/platformdirs          | Low    | Cross-platform config paths with clear protocol design. Small
  scope, well-defined migration strategy. Improves user experience across OS platforms.
                                            |

  Tier 2: High Value (Medium Effort)

  | Priority | Feature                       | Effort | Rationale
                                                                                                               |
  |----------|-------------------------------|--------|-------------------------------------------------------------
  -------------------------------------------------------------------------------------------------------------|
  | 3        | Provider Performance Tracking | Medium | Natural extension of existing MetricsCollector. Enables
  intelligent routing decisions. Required foundation for proactive rate limiting.                                  |
  | 4        | Semantic Search Tool          | Medium | Core infrastructure already exists (LanceDBSearchProvider,
  SemanticSearchInitializer). Only needs thin tool wrapper and DI wiring. Unlocks significant agent capability. |

  Tier 3: Significant Investment (Higher Effort, High Impact)

  | Priority | Feature                | Effort | Rationale

                                                      |
  |----------|------------------------|--------|--------------------------------------------------------------------
  ------------------------------------------------------------------------------------------------------------------
  ----------------------------------------------------|
  | 5        | Rate Limit Enforcement | High   | Most complex - requires 3 new protocols, integration across
  RetryOrchestrator, RateLimitRecommender, and factory. However, depends on Provider Performance Tracking (#3) for
  score-based decisions. Should come after foundational work. |

  ---
  Recommended Implementation Order

  platformdirs (1-2 days)
      |
  Provider Perf Tracking (3-4 days)
      |
      +---> Semantic Search Tool (2-3 days)
      |
      +---> Rate Limit Enforcement (5-7 days)

  Key Dependencies:
  - Rate Limit Enforcement benefits from Provider Performance Tracking (uses scoring for intelligent routing)

``` 


## Feature Assessment

  Strong Recommendations

  1. Cache/Config Files (XDG/platformdirs) - HIGH VALUE
  - You already have src/context/cache.py and infrastructure for persistence
  - Using platformdirs is a low-effort, high-impact improvement
  - The migration strategy shown is practical and user-friendly
  - Aligns with your protocol-first architecture (could define ConfigPathProtocol)

  2. VCR.py / pytest-recording - HIGH VALUE
  - Directly addresses your CLAUDE.md mandate: "NEVER MAKE REAL API CALLS IN TESTS"
  - Your current architecture with protocols makes this easy to integrate
  - Cassettes give deterministic, free, fast tests
  - Already have MetricsCollector tracking execution - this complements it

  3. Provider Performance Tracking - HIGH VALUE
  - You already have MetricsCollector with success rates and execution times
  - Extending to track per-provider stats is a natural evolution
  - Supports "Automatic strategy tuning based on success rates" (next item)
  - Fits your existing protocol architecture


### Summary

  | Feature                | Effort | Value   | Recommendation |
  |------------------------|--------|---------|----------------|
  | XDG/platformdirs       | Low    | High    | Do it          |
  | VCR.py testing         | Low    | High    | Do it          |
  | Provider perf tracking | Medium | High    | Do it          |
---

## Implementation Plans (Priority Items)

### 1. Cross-Platform Config/Cache Paths (platformdirs)

**Goal:** Replace hardcoded paths with OS-appropriate locations using `platformdirs`.

**Protocol Design:**

```python
# src/infrastructure/protocols.py (extend existing)

class AppPathsProtocol(Protocol):
    """
    Protocol for resolving application directory paths.

    Abstracts platform-specific path resolution to enable:
    - Testing without touching real filesystem
    - Cross-platform compatibility (Windows, macOS, Linux)
    - XDG compliance on Linux
    """

    @property
    def config_dir(self) -> Path:
        """User config directory (~/.config/scrappy or platform equivalent)."""
        ...

    @property
    def cache_dir(self) -> Path:
        """Cache directory (~/.cache/scrappy or platform equivalent)."""
        ...

    @property
    def data_dir(self) -> Path:
        """Persistent data directory (history, sessions)."""
        ...

    @property
    def log_dir(self) -> Path:
        """Log file directory."""
        ...

    def ensure_dirs_exist(self) -> None:
        """Create all application directories if they don't exist."""
        ...
```

**Implementation:**

```python
# src/infrastructure/app_paths.py

from pathlib import Path
from platformdirs import user_config_dir, user_cache_dir, user_data_dir, user_log_dir

class PlatformAppPaths:
    """
    Cross-platform path resolution using platformdirs.

    Resolves to:
    - Linux: ~/.config/scrappy, ~/.cache/scrappy, ~/.local/share/scrappy
    - macOS: ~/Library/Application Support/scrappy, ~/Library/Caches/scrappy
    - Windows: C:/Users/<user>/AppData/Local/scrappy
    """

    APP_NAME = "scrappy"

    def __init__(self, file_system: FileSystemProtocol):
        self._fs = file_system

    @property
    def config_dir(self) -> Path:
        return Path(user_config_dir(self.APP_NAME))

    @property
    def cache_dir(self) -> Path:
        return Path(user_cache_dir(self.APP_NAME))

    @property
    def data_dir(self) -> Path:
        return Path(user_data_dir(self.APP_NAME))

    @property
    def log_dir(self) -> Path:
        return Path(user_log_dir(self.APP_NAME))

    def ensure_dirs_exist(self) -> None:
        for dir_path in [self.config_dir, self.cache_dir, self.data_dir, self.log_dir]:
            self._fs.mkdir(dir_path, parents=True, exist_ok=True)


class InMemoryAppPaths:
    """Test double for AppPathsProtocol - uses temp directories."""

    def __init__(self, base_dir: Path):
        self._base = base_dir

    @property
    def config_dir(self) -> Path:
        return self._base / "config"

    # ... etc
```

**Migration Strategy:**

```python
# src/infrastructure/migration.py

class LegacyMigration:
    """One-time migration from legacy .llm_agent_team directory."""

    LEGACY_DIR = Path.home() / ".llm_agent_team"

    def __init__(
        self,
        app_paths: AppPathsProtocol,
        file_system: FileSystemProtocol,
        output: OutputInterfaceProtocol,
    ):
        self._paths = app_paths
        self._fs = file_system
        self._output = output

    def migrate_if_needed(self) -> None:
        if not self._fs.exists(self.LEGACY_DIR):
            return
        if self._fs.exists(self._paths.data_dir):
            return  # Already migrated

        self._output.print_info("Migrating legacy data to new location...")
        self._fs.copy_tree(self.LEGACY_DIR, self._paths.data_dir)
        self._output.print_success(f"Migrated to {self._paths.data_dir}")
```

**Integration Points:**
- Update `ContextCache` to accept `AppPathsProtocol`
- Update `SessionManager` to use `app_paths.data_dir / "sessions"`
- Update logging config to use `app_paths.log_dir`

**Files to Modify:**
- `src/infrastructure/protocols.py` - Add AppPathsProtocol
- `src/infrastructure/app_paths.py` - New file, implementation
- `src/infrastructure/migration.py` - New file, legacy migration
- `src/context/cache.py` - Inject AppPathsProtocol
- `src/cli/__init__.py` - Call migration on startup

**Testing:**
- Unit tests with `InMemoryAppPaths`
- Integration test verifying correct paths per platform

---

### 2. VCR.py / pytest-recording for Deterministic API Tests

**Goal:** Record real API responses once, replay forever for fast/free/deterministic tests.

**Why This Fits Your Architecture:**
- You already have `LLMProviderProtocol` - VCR intercepts at HTTP level below this
- Works transparently with existing provider implementations
- No code changes to production code required

**Setup:**

```bash
pip install pytest-recording
```

**pytest Configuration:**

```python
# conftest.py

import pytest

@pytest.fixture(scope="module")
def vcr_config():
    """Configure VCR for API response recording."""
    return {
        "filter_headers": [
            "authorization",
            "x-api-key",
            "api-key",
        ],
        "filter_query_parameters": [
            "key",
            "api_key",
        ],
        "record_mode": "once",  # Record once, replay forever
        "match_on": ["method", "scheme", "host", "port", "path", "query", "body"],
        "cassette_library_dir": "tests/cassettes",
    }
```

**Example Test Pattern:**

```python
# tests/integration/test_providers_vcr.py

import pytest
from src.providers.groq import GroqProvider

@pytest.mark.vcr()
class TestGroqProviderVCR:
    """
    Integration tests using recorded API responses.

    First run: Makes real API call, saves to tests/cassettes/
    Subsequent runs: Replays saved response (fast, free, deterministic)
    """

    def test_chat_completion_basic(self, real_groq_provider):
        """Test basic chat completion with recorded response."""
        response = real_groq_provider.chat(
            messages=[{"role": "user", "content": "Say hello"}],
            model="llama-3.1-8b-instant",
        )

        assert response.content is not None
        assert len(response.content) > 0
        assert response.model == "llama-3.1-8b-instant"

    def test_handles_rate_limit_response(self):
        """Test rate limit handling with recorded 429 response."""
        # This cassette contains a recorded 429 response
        # Allows testing retry logic without hitting real rate limits
        ...

@pytest.fixture
def real_groq_provider():
    """
    Provider configured for VCR recording.
    Uses real API key from env for initial recording.
    """
    return GroqProvider(api_key=os.environ.get("GROQ_API_KEY", "test-key"))
```

**Directory Structure:**

```
tests/
  cassettes/                          # Recorded API responses
    test_groq_provider_vcr/
      test_chat_completion_basic.yaml
      test_handles_rate_limit_response.yaml
    test_gemini_provider_vcr/
      ...
  integration/
    test_providers_vcr.py             # VCR-enabled integration tests
  unit/
    ...                               # Existing unit tests (no VCR needed)
```

**Recording New Cassettes:**

```bash
# Record fresh cassettes (requires valid API keys)
GROQ_API_KEY=xxx pytest tests/integration/ --record-mode=rewrite

# Normal test run (uses recorded cassettes)
pytest tests/integration/
```

**Best Practices:**
1. Never commit API keys - filter_headers removes them from cassettes
2. Record cassettes in CI with secrets, commit the sanitized YAML
3. Use `--record-mode=none` in CI to fail if cassette missing
4. Separate cassette dirs per test module for organization

**Files to Create:**
- `tests/conftest.py` - VCR configuration
- `tests/integration/test_providers_vcr.py` - VCR-enabled tests
- `tests/cassettes/.gitkeep` - Cassette directory

**Integration with Existing Tests:**
- Keep existing unit tests unchanged (they use mocks/protocols)
- VCR tests are additive - they test real provider behavior
- Run VCR tests in separate CI job with longer timeout

---

### 3. Provider Performance Tracking

**Goal:** Track per-provider metrics (latency, success rate, cost) to enable intelligent routing.

**Protocol Design:**

```python
# src/orchestrator/protocols.py (extend existing)

@dataclass
class ProviderStats:
    """Statistics for a single provider."""
    provider_name: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_tokens: int = 0
    total_latency_ms: float = 0.0
    last_error: Optional[str] = None
    last_error_time: Optional[datetime] = None

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests

    @property
    def avg_latency_ms(self) -> float:
        if self.successful_requests == 0:
            return 0.0
        return self.total_latency_ms / self.successful_requests


class ProviderStatsProtocol(Protocol):
    """
    Protocol for tracking provider performance metrics.

    Enables:
    - Intelligent provider selection based on historical performance
    - Automatic deprioritization of failing providers
    - Cost tracking and optimization
    """

    def record_success(
        self,
        provider: str,
        latency_ms: float,
        tokens_used: int,
    ) -> None:
        """Record a successful provider request."""
        ...

    def record_failure(
        self,
        provider: str,
        error: str,
        latency_ms: float,
    ) -> None:
        """Record a failed provider request."""
        ...

    def get_stats(self, provider: str) -> Optional[ProviderStats]:
        """Get statistics for a specific provider."""
        ...

    def get_all_stats(self) -> Dict[str, ProviderStats]:
        """Get statistics for all providers."""
        ...

    def get_healthy_providers(self, min_success_rate: float = 0.5) -> List[str]:
        """Get providers meeting minimum success rate threshold."""
        ...

    def reset_stats(self, provider: Optional[str] = None) -> None:
        """Reset statistics for one or all providers."""
        ...
```

**Implementation:**

```python
# src/orchestrator/provider_stats.py

class ProviderStatsTracker:
    """
    Tracks per-provider performance metrics.

    Persists stats to disk for continuity across sessions.
    Thread-safe for concurrent access.
    """

    def __init__(
        self,
        persistence: PersistenceProtocol[Dict[str, Any]],
        clock: Optional[Callable[[], datetime]] = None,
    ):
        self._persistence = persistence
        self._clock = clock or datetime.now
        self._stats: Dict[str, ProviderStats] = {}
        self._lock = threading.Lock()
        self._load_stats()

    def record_success(
        self,
        provider: str,
        latency_ms: float,
        tokens_used: int,
    ) -> None:
        with self._lock:
            stats = self._get_or_create(provider)
            stats.total_requests += 1
            stats.successful_requests += 1
            stats.total_latency_ms += latency_ms
            stats.total_tokens += tokens_used
            self._persist()

    def record_failure(
        self,
        provider: str,
        error: str,
        latency_ms: float,
    ) -> None:
        with self._lock:
            stats = self._get_or_create(provider)
            stats.total_requests += 1
            stats.failed_requests += 1
            stats.last_error = error
            stats.last_error_time = self._clock()
            self._persist()

    def get_healthy_providers(self, min_success_rate: float = 0.5) -> List[str]:
        with self._lock:
            return [
                name for name, stats in self._stats.items()
                if stats.success_rate >= min_success_rate
            ]

    def _get_or_create(self, provider: str) -> ProviderStats:
        if provider not in self._stats:
            self._stats[provider] = ProviderStats(provider_name=provider)
        return self._stats[provider]

    def _persist(self) -> None:
        data = {
            name: asdict(stats)
            for name, stats in self._stats.items()
        }
        self._persistence.save(data)

    def _load_stats(self) -> None:
        data = self._persistence.load()
        if data:
            for name, stats_dict in data.items():
                self._stats[name] = ProviderStats(**stats_dict)


class InMemoryProviderStats:
    """Test double - no persistence, no threading."""

    def __init__(self):
        self._stats: Dict[str, ProviderStats] = {}

    # ... simplified implementation for tests
```

**Integration with ProviderSelector:**

```python
# src/orchestrator/provider_selector.py (modify existing)

class ProviderSelector:
    """
    Selects optimal provider based on task requirements and health.

    Now considers historical performance when selecting providers.
    """

    def __init__(
        self,
        registry: ProviderRegistryProtocol,
        stats_tracker: ProviderStatsProtocol,  # NEW dependency
        rate_tracker: RateLimitTrackerProtocol,
    ):
        self._registry = registry
        self._stats = stats_tracker
        self._rate_tracker = rate_tracker

    def select_provider(
        self,
        task_type: str,
        excluded: Set[str],
    ) -> Optional[str]:
        candidates = self._get_candidates(task_type, excluded)

        # Filter by health (success rate > 50%)
        healthy = [
            p for p in candidates
            if p in self._stats.get_healthy_providers(min_success_rate=0.5)
            or self._stats.get_stats(p) is None  # New providers get a chance
        ]

        if not healthy:
            # All providers unhealthy - try least-bad option
            healthy = candidates

        # Sort by success rate * inverse latency (fast + reliable first)
        def score(provider: str) -> float:
            stats = self._stats.get_stats(provider)
            if not stats or stats.total_requests < 5:
                return 0.5  # Neutral score for new providers
            # Higher success rate and lower latency = higher score
            latency_factor = 1000 / max(stats.avg_latency_ms, 100)
            return stats.success_rate * latency_factor

        healthy.sort(key=score, reverse=True)
        return healthy[0] if healthy else None
```

**Integration with RetryOrchestrator:**

```python
# Modify execute_with_retry to record stats

async def execute_with_retry(self, request: LLMRequest, ...) -> tuple:
    start_time = time.perf_counter()
    try:
        response = await self._execute(request)
        latency_ms = (time.perf_counter() - start_time) * 1000
        self._stats.record_success(
            provider=request.provider,
            latency_ms=latency_ms,
            tokens_used=response.usage.total_tokens,
        )
        return response, metadata
    except Exception as e:
        latency_ms = (time.perf_counter() - start_time) * 1000
        self._stats.record_failure(
            provider=request.provider,
            error=str(e),
            latency_ms=latency_ms,
        )
        raise
```

**CLI Integration (stats command):**

```python
# src/cli/commands/stats.py

def show_provider_stats(stats_tracker: ProviderStatsProtocol, output: OutputInterfaceProtocol):
    """Display provider performance statistics."""
    all_stats = stats_tracker.get_all_stats()

    if not all_stats:
        output.print_info("No provider statistics recorded yet.")
        return

    table_data = []
    for name, stats in sorted(all_stats.items()):
        table_data.append({
            "Provider": name,
            "Requests": stats.total_requests,
            "Success Rate": f"{stats.success_rate:.1%}",
            "Avg Latency": f"{stats.avg_latency_ms:.0f}ms",
            "Tokens": stats.total_tokens,
        })

    output.print_table(table_data, title="Provider Performance")
```

**Files to Create/Modify:**
- `src/orchestrator/protocols.py` - Add ProviderStatsProtocol, ProviderStats
- `src/orchestrator/provider_stats.py` - New file, implementation
- `src/orchestrator/provider_selector.py` - Inject and use stats
- `src/orchestrator/retry_orchestrator.py` - Record stats on success/failure
- `src/cli/commands/stats.py` - New CLI command
- `tests/unit/test_provider_stats.py` - Unit tests
- `tests/helpers.py` - Add InMemoryProviderStats test double

**Testing Strategy:**
- Unit tests with `InMemoryProviderStats` and injected clock
- Test scoring algorithm with various stat combinations
- Test persistence load/save cycle
- Test thread safety with concurrent record calls

---



