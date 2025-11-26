# Rate Limiting Implementation Plan

## Problem Statement

The current rate limiting system **tracks** usage but does not **enforce** limits. Rate limiting is reactive (triggered on API error) rather than proactive (prevented before API call). This leads to:

1. Unnecessary API calls that fail due to rate limits
2. Wasted time on retries and fallback cascades
3. Users not warned until limits are already hit
4. No intelligent routing based on remaining quota

## Current Architecture Analysis

### What Exists

| Component | Location | Purpose |
|-----------|----------|---------|
| `RateLimitTracker` | `src/orchestrator/rate_limiting/tracker.py` | Facade coordinating usage tracking |
| `RateLimitStorage` | `src/orchestrator/rate_limiting/storage.py` | JSON persistence |
| `RateLimitPolicy` | `src/orchestrator/rate_limiting/policy.py` | Daily/monthly reset logic |
| `RateLimitCalculator` | `src/orchestrator/rate_limiting/calculator.py` | Remaining quota math |
| `RateLimitRecommender` | `src/orchestrator/rate_limiting/recommender.py` | Provider selection |
| `RetryOrchestrator` | `src/orchestrator/retry_orchestrator.py` | Retry with fallback |

### Gap Analysis

| Issue | Current Behavior | Desired Behavior |
|-------|------------------|------------------|
| Pre-request blocking | None - requests always attempted | Block if quota exhausted |
| Proactive warnings | Advisory only in `is_limit_approaching()` | User notification before hitting limits |
| Request queuing | None | Queue requests when approaching limits |
| Intelligent routing | Basic preference-based | Score-based using remaining quota |
| Fallback timing | After RateLimitError | Before API call when quota is low |

---

## Implementation Plan

### Phase 1: Protocol-First Design (New Abstractions)

**Principle: Define contracts BEFORE any implementation.**

#### 1.1 EnforcementPolicy Protocol

```python
# src/orchestrator/rate_limiting/protocols.py

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

class EnforcementPolicyProtocol(Protocol):
    """Contract for rate limit enforcement decisions."""

    def evaluate(
        self,
        provider: str,
        model: str,
        estimated_tokens: int,
        registry: ProviderRegistryProtocol,
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
```

**Rationale:** Separates the decision logic from the enforcement mechanism. Enables testing decisions without real API calls.

#### 1.2 QuotaScorer Protocol

```python
class QuotaScore:
    """Score representing provider availability."""
    provider: str
    score: float  # 0.0 (exhausted) to 1.0 (fully available)
    requests_remaining: int
    tokens_remaining: int
    is_rate_limited: bool
    warning_threshold_hit: bool

class QuotaScorerProtocol(Protocol):
    """Contract for scoring providers by available quota."""

    def score_provider(
        self,
        provider: str,
        model: str,
        limits: ProviderLimits,
    ) -> QuotaScore:
        """Score a single provider's availability."""
        ...

    def rank_providers(
        self,
        providers: List[str],
        registry: ProviderRegistryProtocol,
        task_type: str = "general",
    ) -> List[QuotaScore]:
        """Rank all providers by quota availability."""
        ...
```

**Rationale:** Provides quantitative comparison between providers for intelligent routing.

#### 1.3 UserNotifier Protocol

```python
class NotificationLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

class UserNotifierProtocol(Protocol):
    """Contract for user-facing notifications."""

    def notify_approaching_limit(
        self,
        provider: str,
        remaining_percent: float,
        remaining_requests: int,
    ) -> None:
        """Warn user that limits are approaching."""
        ...

    def notify_fallback(
        self,
        from_provider: str,
        to_provider: str,
        reason: str,
    ) -> None:
        """Inform user of automatic provider switch."""
        ...

    def notify_all_exhausted(
        self,
        attempted_providers: List[str],
    ) -> None:
        """Alert user that all providers are exhausted."""
        ...
```

**Rationale:** Decouples notification delivery from enforcement logic. Enables different UI implementations (CLI, TUI, silent mode).

---

### Phase 2: Core Implementation

#### 2.1 EnforcementPolicy Implementation

**File:** `src/orchestrator/rate_limiting/enforcement.py`

```python
class RateLimitEnforcementPolicy:
    """
    Decides whether requests should proceed based on quota.

    Implements EnforcementPolicyProtocol following SOLID:
    - Single Responsibility: Only makes enforcement decisions
    - Open/Closed: Thresholds configurable without code changes
    - Dependency Inversion: Depends on UsageQueryProtocol, not tracker
    """

    def __init__(
        self,
        usage_query: UsageQueryProtocol,
        scorer: QuotaScorerProtocol,
        *,
        warn_threshold: float = 0.1,   # 10% remaining
        block_threshold: float = 0.0,   # 0% remaining
    ):
        self._usage_query = usage_query
        self._scorer = scorer
        self._warn_threshold = warn_threshold
        self._block_threshold = block_threshold
```

**Decision Logic:**

```
1. Score requested provider
2. If score > warn_threshold: ALLOW
3. If score > block_threshold: WARN + suggest alternative
4. If score <= block_threshold:
   a. Rank all providers
   b. If alternative exists with score > warn_threshold: BLOCK + alternative
   c. If alternative exists with score > 0: BLOCK + alternative (with warning)
   d. If no alternatives: FAIL
```

#### 2.2 QuotaScorer Implementation

**File:** `src/orchestrator/rate_limiting/scorer.py`

```python
class QuotaScorer:
    """
    Scores providers by remaining quota capacity.

    Score calculation:
    - Base score = min(requests_remaining / requests_limit, tokens_remaining / tokens_limit)
    - Penalties: Recent errors (-0.1), approaching reset time (-0.05)
    - Bonuses: Fast provider (+0.1 for cerebras/groq)
    """

    def __init__(
        self,
        usage_query: UsageQueryProtocol,
        *,
        speed_bonus: Dict[str, float] = None,
    ):
        self._usage_query = usage_query
        self._speed_bonus = speed_bonus or {
            'cerebras': 0.1,
            'groq': 0.05,
        }
```

#### 2.3 UserNotifier Implementation

**File:** `src/orchestrator/rate_limiting/notifier.py`

```python
class RateLimitNotifier:
    """
    Delivers rate limit notifications to users.

    Integrates with existing OutputInterfaceProtocol.
    """

    def __init__(
        self,
        output: OutputInterfaceProtocol,
        *,
        quiet_mode: bool = False,
        notification_cooldown: int = 60,  # Seconds between repeat warnings
    ):
        self._output = output
        self._quiet_mode = quiet_mode
        self._cooldown = notification_cooldown
        self._last_notification: Dict[str, datetime] = {}
```

---

### Phase 3: Integration Points

#### 3.1 Modify RetryOrchestrator

**Location:** `src/orchestrator/retry_orchestrator.py`

**Changes:**

1. Inject `EnforcementPolicyProtocol` as dependency
2. Call `enforcement.evaluate()` BEFORE attempting request
3. Handle `EnforcementDecision` actions:
   - ALLOW: Proceed as normal
   - WARN: Notify user, then proceed
   - BLOCK: Use alternative provider without attempting original
   - FAIL: Raise `AllProvidersRateLimitedError` immediately

```python
class RetryOrchestrator:
    def __init__(
        self,
        *,
        registry: ProviderRegistryProtocol,
        rate_tracker: RateLimitTrackerProtocol,
        provider_selector: ProviderSelectorProtocol,
        output: OutputInterfaceProtocol,
        retry_config: Optional[RetryConfig] = None,
        enforcement: Optional[EnforcementPolicyProtocol] = None,  # NEW
        notifier: Optional[UserNotifierProtocol] = None,          # NEW
    ):
        ...
```

#### 3.2 Modify RateLimitRecommender

**Location:** `src/orchestrator/rate_limiting/recommender.py`

**Changes:**

1. Inject `QuotaScorerProtocol`
2. Replace boolean `is_rate_limited` check with score-based ranking
3. Return provider with highest score, not just first available

```python
class RateLimitRecommender:
    def __init__(
        self,
        usage_query: UsageQueryProtocol,
        scorer: Optional[QuotaScorerProtocol] = None,  # NEW
    ):
        ...

    def recommended(
        self,
        task_type: str,
        registry: ProviderRegistryProtocol,
        task_preferences: Dict[str, List[str]],
    ) -> Optional[str]:
        # Use scorer.rank_providers() instead of simple is_rate_limited check
        ...
```

#### 3.3 Update Factory

**Location:** `src/orchestrator/rate_limiting/factory.py`

**Changes:**

Add creation of new components:

```python
def create_rate_limit_tracker(
    persist_file: Optional[Path] = None,
    auto_load: bool = True,
) -> Tuple[RateLimitTracker, EnforcementPolicyProtocol, UserNotifierProtocol]:
    """
    Create rate limiting components with enforcement.

    Returns:
        Tuple of (tracker, enforcement_policy, notifier)
    """
    ...
```

---

### Phase 4: Testing Strategy

#### 4.1 Unit Tests (Behavior-Focused)

**File:** `tests/test_rate_limit_enforcement.py`

```python
class TestEnforcementPolicy:
    """Test enforcement decisions without real API calls."""

    def test_allows_request_when_quota_available(self):
        """ALLOW when provider has sufficient quota."""
        usage = FakeUsageQuery(remaining_percent=0.8)
        scorer = QuotaScorer(usage)
        policy = RateLimitEnforcementPolicy(usage, scorer)

        decision = policy.evaluate("cerebras", "llama-3.3-70b", 1000, fake_registry)

        assert decision.action == EnforcementAction.ALLOW

    def test_warns_when_approaching_limit(self):
        """WARN when below threshold but not exhausted."""
        usage = FakeUsageQuery(remaining_percent=0.08)  # 8% remaining
        ...

        assert decision.action == EnforcementAction.WARN
        assert decision.reason contains "approaching"

    def test_blocks_and_suggests_alternative(self):
        """BLOCK with alternative when quota exhausted."""
        usage = FakeUsageQuery(
            provider_quotas={
                'cerebras': 0.0,   # Exhausted
                'groq': 0.5,       # Available
            }
        )
        ...

        assert decision.action == EnforcementAction.BLOCK
        assert decision.alternative_provider == "groq"

    def test_fails_when_all_exhausted(self):
        """FAIL when no providers have quota."""
        usage = FakeUsageQuery(
            provider_quotas={
                'cerebras': 0.0,
                'groq': 0.0,
                'gemini': 0.0,
            }
        )
        ...

        assert decision.action == EnforcementAction.FAIL
```

#### 4.2 Integration Tests

**File:** `tests/integration/test_rate_limit_integration.py`

```python
class TestRateLimitIntegration:
    """Test enforcement integrated with retry orchestrator."""

    def test_proactive_fallback_skips_exhausted_provider(self):
        """Verify exhausted provider is never called."""
        mock_provider = Mock()
        exhausted_provider = Mock()

        # Setup: cerebras exhausted, groq available
        ...

        result = orchestrator.delegate("test prompt")

        # Verify: exhausted provider's chat() was never called
        exhausted_provider.chat.assert_not_called()
        mock_provider.chat.assert_called_once()
```

#### 4.3 Test Doubles

**File:** `tests/helpers.py` (extend existing)

```python
class FakeUsageQuery:
    """Controllable usage query for testing."""

    def __init__(
        self,
        remaining_percent: float = 1.0,
        provider_quotas: Optional[Dict[str, float]] = None,
    ):
        self._remaining = remaining_percent
        self._quotas = provider_quotas or {}

    def get_remaining_quota(self, provider, model, limits):
        quota = self._quotas.get(provider, self._remaining)
        return {
            'requests_today_remaining': int(limits.requests_per_day * quota),
            'tokens_today_remaining': int(limits.tokens_per_day * quota),
        }

class FakeNotifier:
    """Captures notifications for test assertions."""

    def __init__(self):
        self.notifications: List[Tuple[str, Any]] = []

    def notify_approaching_limit(self, provider, remaining_percent, remaining_requests):
        self.notifications.append(('approaching', provider, remaining_percent))
```

---

### Phase 5: Configuration

#### 5.1 Add to OrchestratorConfig

**File:** `src/orchestrator/config.py`

```python
@dataclass
class OrchestratorConfig(BaseConfig):
    # ... existing fields ...

    # Rate limit enforcement settings
    enforcement_enabled: bool = True
    warn_threshold: float = 0.1      # Warn at 10% remaining
    block_threshold: float = 0.0     # Block at 0% remaining
    notification_cooldown: int = 60  # Seconds between repeat warnings
    proactive_fallback: bool = True  # Switch before hitting limits
```

---

## File Changes Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `src/orchestrator/rate_limiting/protocols.py` | Extend | Add EnforcementPolicyProtocol, QuotaScorerProtocol, UserNotifierProtocol |
| `src/orchestrator/rate_limiting/enforcement.py` | New | EnforcementPolicy implementation |
| `src/orchestrator/rate_limiting/scorer.py` | New | QuotaScorer implementation |
| `src/orchestrator/rate_limiting/notifier.py` | New | RateLimitNotifier implementation |
| `src/orchestrator/rate_limiting/recommender.py` | Modify | Use scorer for ranking |
| `src/orchestrator/rate_limiting/factory.py` | Modify | Create new components |
| `src/orchestrator/retry_orchestrator.py` | Modify | Integrate enforcement policy |
| `src/orchestrator/config.py` | Extend | Add enforcement settings |
| `tests/test_rate_limit_enforcement.py` | New | Unit tests |
| `tests/integration/test_rate_limit_integration.py` | New | Integration tests |
| `tests/helpers.py` | Extend | Add FakeUsageQuery, FakeNotifier |

---

## Implementation Order

1. **Define protocols** (`protocols.py`) - Contracts first
2. **Implement QuotaScorer** (`scorer.py`) - Foundation for decisions
3. **Implement EnforcementPolicy** (`enforcement.py`) - Decision logic
4. **Implement UserNotifier** (`notifier.py`) - User feedback
5. **Write unit tests** - Prove implementations work
6. **Modify RateLimitRecommender** - Score-based routing
7. **Modify RetryOrchestrator** - Pre-request enforcement
8. **Update factory** - Wire components
9. **Write integration tests** - Prove system works
10. **Update config** - Make configurable

---

## Success Criteria

- [ ] No API calls made to exhausted providers
- [ ] Users warned before hitting limits (at configurable threshold)
- [ ] Automatic fallback happens before rate limit errors
- [ ] All decisions are testable without real API calls
- [ ] Existing tests continue to pass
- [ ] New tests achieve >90% coverage on new code
