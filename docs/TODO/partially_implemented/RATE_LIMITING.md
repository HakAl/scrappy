# Rate Limiting Implementation Plan

-- enables richer UX with metrics display

## Implementation Complete

  All phases complete:
  - Phase 1-3 and Phase 5: COMPLETE
  - Phase 4 Unit Tests: COMPLETE (23 tests)
  - Phase 4 Integration Tests: COMPLETE (7 tests)
  - Production Wiring: COMPLETE

  Known Design Decisions:

  1. Speed Bonuses Affect Tests - Tests must use speed_bonus={} to avoid unexpected threshold behavior
  2. Model Groups Not Enforced - "fast"/"quality" groups skip enforcement (LiteLLM Router handles internally)
  3. Token Tracking Uses Actual Values - LiteLLM callback records real prompt_tokens/completion_tokens from API responses
  4. QUEUE Action Not Implemented - Defined but not handled

  Potential Future Enhancements (Low Priority):

  1. Metrics/observability
  2. QUEUE action implementation
  3. Per-model limits

---

## Implementation Status

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 1: Protocol Design | COMPLETE | All protocols defined in `protocols.py` |
| Phase 2: Core Implementation | COMPLETE | QuotaScorer, EnforcementPolicy, Notifier implemented |
| Phase 3: Integration | COMPLETE | DelegationManager integrated (not RetryOrchestrator - see notes) |
| Phase 4: Unit Tests | COMPLETE | 23 tests in `test_enforcement.py`, all passing |
| Phase 4: Integration Tests | COMPLETE | 7 tests in `test_enforcement_integration.py`, all mocked |
| Phase 5: Configuration | COMPLETE | Settings added to OrchestratorConfig |
| Production Wiring | COMPLETE | `create_enforcement_components()` wired in factory |

### Implementation Notes

**Architecture Change:** The plan referenced `RetryOrchestrator` but the codebase now uses `DelegationManager` with LiteLLM Router. Integration was done in `DelegationManager` instead. LiteLLM handles retries internally.

**Files Created:**
- `src/scrappy/orchestrator/rate_limiting/scorer.py`
- `src/scrappy/orchestrator/rate_limiting/enforcement.py`
- `src/scrappy/orchestrator/rate_limiting/notifier.py`
- `tests/rate_limiting/test_enforcement.py` - Unit tests (23 tests)
- `tests/rate_limiting/test_enforcement_integration.py` - Integration tests (7 tests, all mocked)

**Files Modified:**
- `protocols.py` - Added enforcement types and protocols
- `recommender.py` - Now accepts optional QuotaScorerProtocol
- `rate_limiting/factory.py` - Added `create_rate_limit_components()`, `create_enforcement_components()`, `RateLimitComponents`, `EnforcementComponents`
- `rate_limiting/__init__.py` - Updated exports
- `config.py` - Added enforcement settings
- `delegation.py` - Added `_check_enforcement()` method, integrated into delegate/delegate_async/stream_delegate
- `orchestrator/factory.py` - Wired enforcement components in `create_delegation_manager()`

---

## Known Issues and Bugs

### 1. Speed Bonuses Affect Test Expectations
Speed bonuses (cerebras +0.1, groq +0.05) can push scores above thresholds unexpectedly. Tests must use `speed_bonus={}` when testing threshold behavior.

### 2. Model Groups Not Enforced
Enforcement only works for specific provider names (e.g., "cerebras", "groq"). Model groups ("fast", "quality") skip enforcement and rely on LiteLLM Router. This is by design but may need revisiting.

### 3. Token Tracking Uses Actual Values
Token tracking now uses actual `prompt_tokens` and `completion_tokens` from LiteLLM API responses via `RateTrackingCallback`. Pre-request estimation still uses `max_tokens` but post-request tracking is accurate.

### 4. QUEUE Action Not Implemented
The `EnforcementAction.QUEUE` is defined but not handled - marked as "future" feature.

---

## Remaining Work

### High Priority
1. **Production Wiring** - DelegationManager accepts enforcement/notifier/registry but they need to be passed when the manager is created in production code
2. **Integration Tests** - Test full flow from DelegationManager through enforcement

### Medium Priority
3. **Better Token Estimation** - Count prompt tokens for more accurate quota prediction
4. **Metrics/Observability** - Track enforcement decisions for debugging

### Low Priority
5. **QUEUE Action** - Implement request queuing when approaching limits
6. **Per-Model Limits** - Current implementation is per-provider, not per-model

---

## Problem Statement

The current rate limiting system **tracks** usage but does not **enforce** limits. Rate limiting is reactive (triggered on API error) 
rather than proactive (prevented before API call). This leads to:

1. Unnecessary API calls that fail due to rate limits
2. Wasted time on retries and fallback cascades
3. Users not warned until limits are already hit
4. No intelligent routing based on remaining quota

## Current Architecture Analysis

### What Exists (Updated)

| Component | Location | Purpose |
|-----------|----------|---------|
| `RateLimitTracker` | `src/orchestrator/rate_limiting/tracker.py` | Facade coordinating usage tracking |
| `RateLimitStorage` | `src/orchestrator/rate_limiting/storage.py` | JSON persistence |
| `RateLimitPolicy` | `src/orchestrator/rate_limiting/policy.py` | Daily/monthly reset logic |
| `RateLimitCalculator` | `src/orchestrator/rate_limiting/calculator.py` | Remaining quota math |
| `RateLimitRecommender` | `src/orchestrator/rate_limiting/recommender.py` | Provider selection (now with scorer) |
| `QuotaScorer` | `src/orchestrator/rate_limiting/scorer.py` | **NEW** - Score providers by quota |
| `RateLimitEnforcementPolicy` | `src/orchestrator/rate_limiting/enforcement.py` | **NEW** - Pre-request decisions |
| `RateLimitNotifier` | `src/orchestrator/rate_limiting/notifier.py` | **NEW** - User notifications |
| `DelegationManager` | `src/orchestrator/delegation.py` | LLM delegation (replaces RetryOrchestrator) |

> **Note:** `RetryOrchestrator` no longer exists. LiteLLM Router handles retries internally. Enforcement is integrated into `DelegationManager`.

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

- [x] No API calls made to exhausted providers (when enforcement enabled and specific provider used)
- [x] Users warned before hitting limits (at configurable threshold)
- [x] Automatic fallback happens before rate limit errors
- [x] All decisions are testable without real API calls
- [x] Existing tests continue to pass (72 rate limiting + 513 orchestrator tests)
- [x] New tests achieve >90% coverage on new code (23 unit tests covering all enforcement scenarios)
- [ ] Integration tests verify end-to-end flow (PENDING)
- [ ] Production wiring complete (PENDING - components created but not wired in app startup)


---


# Rate Limiting: Production Wiring

## Problem Summary

Rate limiting components exist but are not wired up:
- `QuotaScorer`, `EnforcementPolicy`, `Notifier` are implemented
- `DelegationManager` has `_check_enforcement()` method
- BUT: Factory creates DelegationManager WITHOUT passing enforcement components
- Result: All enforcement logic is dead code

## Investigation Results

### Token Tracking: ALREADY WORKING

Token tracking from API responses is fully implemented:

1. **LiteLLM extracts tokens** (`litellm_service.py:829-846`):
   ```python
   prompt_tokens = getattr(usage, 'prompt_tokens', 0) or 0
   completion_tokens = getattr(usage, 'completion_tokens', 0) or 0
   ```

2. **Callback records to tracker** (`litellm_callbacks.py:143-156`):
   ```python
   input_tokens = getattr(usage, 'prompt_tokens', 0) if usage else 0
   output_tokens = getattr(usage, 'completion_tokens', 0) if usage else 0
   self._rate_tracker.record_request(
       provider=provider,
       model=model_str,
       input_tokens=input_tokens,
       output_tokens=output_tokens,
       success=True,
   )
   ```

3. **Tracker stores separately** (`tracker.py:433-434`):
   ```python
   data["input_tokens_today"] += input_tokens
   data["output_tokens_today"] += output_tokens
   ```

4. **Callback is wired** (`factory.py:468-471`):
   ```python
   callback = RateTrackingCallback(
       rate_tracker=rate_tracker,
       status_tracker=status_tracker,
   )
   ```

**Conclusion:** Phase 1 is DONE. No changes needed for token tracking.

---

## Remaining Work

### Phase 2: Wire Enforcement in Factory

**Goal:** Connect enforcement components to DelegationManager.

Location: `src/scrappy/orchestrator/factory.py:503-537`

Current code (BROKEN):
```python
def create_delegation_manager(
    self,
    llm_service: LLMServiceProtocol,
    cache: CacheProtocol,
    output: BaseOutputProtocol,
    working_memory: WorkingMemoryProtocol,
    context_manager: ContextManagerProtocol
) -> DelegationManagerProtocol:
    # ... creates augmenter and scheduler ...
    return DelegationManager(
        llm_service=llm_service,
        cache=cache,
        output=output,
        prompt_augmenter=prompt_augmenter,
        batch_scheduler=batch_scheduler,
        context_aware=self.context_aware,
        # MISSING: enforcement, notifier, registry
    )
```

#### 2.1 Changes needed

- [ ] Add `rate_tracker` parameter to `create_delegation_manager()`
- [ ] Call `create_rate_limit_components()` to get enforcement/notifier
- [ ] Add `registry` parameter (or create it internally)
- [ ] Pass `enforcement`, `notifier`, `registry` to DelegationManager

#### 2.2 Handle model groups

Current: `delegation.py:196-197` skips enforcement for "fast"/"quality" groups.

```python
# Skip enforcement for model groups (let LiteLLM handle it)
if provider_name in MODEL_GROUPS:
    return provider_name, model
```

Decision needed:
- **Option A:** Keep skipping (LiteLLM Router handles internally) - SIMPLE
- **Option B:** Enforce for groups by checking ALL providers in that group - COMPLEX
- **Option C:** Map group to preferred provider and enforce on that - MEDIUM

Recommendation: Start with Option A, add Option C later if needed.

### Phase 3: Integration Testing

**CRITICAL: NO REAL API CALLS. ALL TESTS MUST USE MOCKS/FAKES.**

Test strategy:
- Use `FakeUsageQuery` (already exists in `test_enforcement.py`)
- Use `FakeLLMService` that returns canned responses
- Use `FakeRegistry` with `FakeProvider` objects
- Use `FakeOutput` to capture notifications

Tests to write:
- [ ] Test: Exhausted provider triggers BLOCK and uses alternative
- [ ] Test: Approaching limit triggers WARN notification
- [ ] Test: All exhausted triggers FAIL with proper error
- [ ] Test: Enforcement is skipped when enforcement=None (backwards compat)
- [ ] Test: Enforcement is skipped for model groups ("fast", "quality")

---

## Files to Modify

| File | Change |
|------|--------|
| `src/scrappy/orchestrator/rate_limiting/factory.py` | Add `create_enforcement_components()` |
| `src/scrappy/orchestrator/rate_limiting/__init__.py` | Export new function |
| `src/scrappy/orchestrator/factory.py` | Wire enforcement in `create_delegation_manager()` |
| `tests/rate_limiting/test_integration.py` | New: integration tests |

Files NOT needing changes:
- `tracker.py` - Already tracks input/output tokens
- `litellm_callbacks.py` - Already records tokens from responses
- `delegation.py` - Already has enforcement logic (just not wired)

---

## Implementation Steps

### Step 1: Update factory.py signature

Both `rate_tracker` and `registry` are already available at the call site (lines 180, 185):
```python
components.rate_tracker = self.create_rate_tracker(...)
components.registry = ...
```

**Changes to `create_delegation_manager()`:**

```python
from .rate_limiting import create_rate_limit_components

def create_delegation_manager(
    self,
    llm_service: LLMServiceProtocol,
    cache: CacheProtocol,
    output: BaseOutputProtocol,
    working_memory: WorkingMemoryProtocol,
    context_manager: ContextManagerProtocol,
    rate_tracker: RateLimitTrackerProtocol,  # ADD
    registry: ProviderRegistryProtocol,       # ADD
) -> DelegationManagerProtocol:

    # Create enforcement components from existing tracker
    rate_components = create_rate_limit_components(
        config=self.config,
        output=output,
    )
    # Note: rate_components.tracker is created fresh - we need to use
    # the EXISTING rate_tracker that's already wired to callbacks!

    # Actually, we should create enforcement/notifier using existing tracker
    # Let me check if create_rate_limit_components can accept an existing tracker...
```

**ISSUE FOUND:** `create_rate_limit_components()` creates a NEW tracker internally.
We need to either:
1. Modify factory to accept existing tracker, OR
2. Create scorer/enforcement/notifier manually using the existing tracker

### Step 2: Update call site (line 223)

```python
components.delegation_manager = self.create_delegation_manager(
    components.llm_service,
    components.cache,
    components.output,
    components.working_memory,
    components.context_manager,
    components.rate_tracker,   # ADD - already exists
    components.registry        # ADD - already exists
)
```

### Step 3: Add factory function for enforcement from existing tracker

Add to `rate_limiting/factory.py`:

```python
@dataclass
class EnforcementComponents:
    """Enforcement components that use an existing tracker."""
    scorer: QuotaScorerProtocol
    enforcement: EnforcementPolicyProtocol
    notifier: UserNotifierProtocol


def create_enforcement_components(
    tracker: RateLimitTracker,
    config: Optional[OrchestratorConfig] = None,
    output: Optional[OutputProtocol] = None,
    quiet_mode: bool = False,
) -> EnforcementComponents:
    """
    Create enforcement components using an existing tracker.

    Use when tracker is already created and wired to callbacks.
    """
    if config is None:
        config = OrchestratorConfig()

    scorer = QuotaScorer(
        usage_query=tracker,
        warn_threshold=config.enforcement_warn_threshold,
    )

    enforcement = RateLimitEnforcementPolicy(
        usage_query=tracker,
        scorer=scorer,
        warn_threshold=config.enforcement_warn_threshold,
        block_threshold=config.enforcement_block_threshold,
    )

    notifier: UserNotifierProtocol
    if output is not None:
        notifier = RateLimitNotifier(
            output=output,
            quiet_mode=quiet_mode,
            notification_cooldown=config.notification_cooldown,
        )
    else:
        notifier = NullNotifier()

    return EnforcementComponents(scorer=scorer, enforcement=enforcement, notifier=notifier)
```

### Step 4: Update create_delegation_manager

In `orchestrator/factory.py`:

```python
from .rate_limiting import create_enforcement_components

def create_delegation_manager(
    self,
    llm_service: LLMServiceProtocol,
    cache: CacheProtocol,
    output: BaseOutputProtocol,
    working_memory: WorkingMemoryProtocol,
    context_manager: ContextManagerProtocol,
    rate_tracker: RateLimitTrackerProtocol,
    registry: ProviderRegistryProtocol,
) -> DelegationManagerProtocol:

    enforcement_components = create_enforcement_components(
        tracker=rate_tracker,
        config=self.config,
        output=output,
    )

    # ... existing augmenter/scheduler code ...

    return DelegationManager(
        llm_service=llm_service,
        cache=cache,
        output=output,
        prompt_augmenter=prompt_augmenter,
        batch_scheduler=batch_scheduler,
        context_aware=self.context_aware,
        enforcement=enforcement_components.enforcement,
        notifier=enforcement_components.notifier,
        registry=registry,
    )
```

### Step 5: Write integration tests

**CRITICAL: NO REAL API CALLS.**

Existing test doubles to reuse:

| Double | Location | Purpose |
|--------|----------|---------|
| `FakeUsageQuery` | `test_enforcement.py:34` | Controllable quota values |
| `FakeRegistry` | `test_enforcement.py:66` | Controllable provider list |
| `FakeProvider` | `test_enforcement.py:79` | Provider with fake limits |
| `FakeLimits` | `test_enforcement.py:26` | Controllable limits |
| `FakeOutput` | `test_enforcement.py:90` | Capture notifications |
| `MockLLMService` | `test_delegation_manager_unit.py:85` | Fake LLM service |
| `MockLLMResponse` | `conftest.py:30` | Canned responses |

New test doubles if needed:

```python
class FakeLLMService:
    """Returns canned responses without API calls."""
    def __init__(self, response: LLMResponse):
        self.response = response
        self.calls = []  # Track what was called

    def completion_sync(self, model, messages, **kwargs):
        self.calls.append((model, messages, kwargs))
        return self.response, {"provider": "fake", "model": model}

    async def completion(self, model, messages, **kwargs):
        return self.completion_sync(model, messages, **kwargs)


class FakeRegistry:
    """Registry with controllable providers."""
    def __init__(self, providers: dict[str, FakeProvider]):
        self._providers = providers

    def get(self, name: str) -> Optional[FakeProvider]:
        return self._providers.get(name)

    def list_available(self) -> list[str]:
        return list(self._providers.keys())
```

Test pattern:
```python
def test_exhausted_provider_triggers_block():
    # Setup: provider_a exhausted, provider_b available
    usage = FakeUsageQuery(provider_quotas={"provider_a": 0.0, "provider_b": 0.5})
    scorer = QuotaScorer(usage, speed_bonus={})
    enforcement = RateLimitEnforcementPolicy(usage, scorer)
    notifier = FakeNotifier()
    llm_service = FakeLLMService(fake_response)
    registry = FakeRegistry({"provider_a": FakeProvider(), "provider_b": FakeProvider()})

    manager = DelegationManager(
        llm_service=llm_service,
        enforcement=enforcement,
        notifier=notifier,
        registry=registry,
        # ... other fakes
    )

    # Act: request provider_a (exhausted)
    response, record = manager.delegate(provider_name="provider_a", prompt="test")

    # Assert: should have used provider_b instead
    assert llm_service.calls[0][0] != "provider_a"  # Did NOT call exhausted provider
    assert notifier.notifications[0][0] == "fallback"  # Notified about fallback
```

---

## Current Status

- [x] Phase 1: Token tracking - ALREADY DONE (was already working)
- [x] Phase 2: Factory wiring - COMPLETE
- [x] Phase 3: Integration tests - COMPLETE (7 tests, all mocked)
- [x] Phase 4: HTTP Header Capture - COMPLETE
- [x] Phase 5: Header Data Integration - COMPLETE (enforcement uses real data)

## Completed Changes

### Phase 2-3: Enforcement Wiring
1. **`rate_limiting/factory.py`**: Added `EnforcementComponents` dataclass and `create_enforcement_components()` function
2. **`rate_limiting/__init__.py`**: Exported new function and dataclass
3. **`orchestrator/factory.py`**: Updated `create_delegation_manager()` to accept `rate_tracker` and `registry`, wire enforcement
4. **`tests/rate_limiting/test_enforcement_integration.py`**: New file with 7 integration tests (all use mocks, NO API calls)

### Phase 4: HTTP Header Capture
5. **`rate_limiting/httpx_patcher.py`**: NEW - Patches httpx.Client and httpx.AsyncClient to capture rate limit headers
   - Async-safe hooks for both sync and async clients
   - Provider detection from URL (groq, cerebras, sambanova, gemini)
   - Thread-safe installation/uninstallation
6. **`rate_limiting/tracker.py`**: Added `update_from_headers()` and `get_provider_headers()` methods
   - Parses all provider header formats (Groq, Cerebras, SambaNova)
   - Stores raw headers for debugging
   - Normalizes to common format (remaining_requests_day, limit_requests, etc.)
7. **`rate_limiting/__init__.py`**: Exported `install_rate_limit_hooks`, `uninstall_rate_limit_hooks`, `is_rate_limit_hooks_installed`
8. **`orchestrator/factory.py`**: Installs httpx hooks when creating rate tracker
9. **`tests/rate_limiting/test_httpx_patcher.py`**: NEW - 21 tests for header capture (all mocked)
10. **`tests/rate_limiting/test_tracker_headers.py`**: NEW - 13 tests for tracker header parsing

### Phase 5: Header Data Integration
11. **`rate_limiting/tracker.py`**: Modified `get_remaining_quota()` to prefer header data
    - Added `_get_remaining_from_headers()` helper method
    - Freshness check (5 minute default, configurable via `config.header_freshness_seconds`)
    - Falls back to calculated values when headers stale or unavailable
    - Marks source with `_source: "headers"` for debugging
12. **`tests/rate_limiting/test_tracker_headers.py`**: Added 6 integration tests for quota calculation

## Test Results

- 119 rate limiting tests: PASS (was 79, added 40 new)
- All tests use mocks, NO real API calls

## Data Flow (Complete)

```
API Request
    |
    v
httpx.Client (patched)
    |
    v
Response with headers
    |
    +---> _capture_sync_response()
    |         |
    |         v
    |     tracker.update_from_headers("groq", {...})
    |         |
    |         v
    |     tracker._usage["provider_headers"]["groq"] = {
    |         "remaining_requests": 14399,
    |         "last_updated": "2024-01-15T10:30:00"
    |     }
    |
    v
QuotaScorer.score_provider()
    |
    v
tracker.get_remaining_quota()
    |
    +---> _get_remaining_from_headers() --> if fresh, return header data
    |
    +---> (fallback) calculator.remaining() --> return calculated estimate
    |
    v
EnforcementPolicy.check_provider()
    |
    v
ALLOW / WARN / BLOCK / FAIL
```

---

## Investigation: Rate Limit Headers from API Responses

### Question

Do API responses include rate limit data (remaining requests, limits, reset times)?

### Findings

**YES - Rate limit headers exist in HTTP responses.**

Checked VCR cassettes at `tests/integration/cassettes/`. Here's what providers return:

#### Groq Headers (from cassette)
```
x-ratelimit-limit-requests: 14400
x-ratelimit-limit-tokens: 6000
x-ratelimit-remaining-requests: 14399
x-ratelimit-remaining-tokens: 5956
x-ratelimit-reset-requests: 6s
x-ratelimit-reset-tokens: 440ms
```

#### Cerebras Headers (from cassette)
```
x-ratelimit-remaining-requests-day: 14375
x-ratelimit-remaining-requests-hour: 875
x-ratelimit-remaining-requests-minute: 21
x-ratelimit-remaining-tokens-day: 988171
x-ratelimit-remaining-tokens-hour: 988171
x-ratelimit-remaining-tokens-minute: 48171
```

### Problem: LiteLLM Doesn't Expose Headers

Tested with actual API calls:

1. `ModelResponse` object has no header attributes
2. `_hidden_params` dict doesn't include headers
3. `original_response` in callback is just the JSON body string (not HTTP response)
4. No `response_headers` or similar attribute exists

```python
# What _hidden_params contains (no headers):
{
    'optional_params': {...},
    'litellm_call_id': '...',
    'api_base': 'https://api.groq.com/openai/v1',
    'response_cost': 2.25e-06,
    'additional_headers': {},  # Empty!
    '_response_ms': 357.76
}
```

### Current State

| What We Have | What We're Missing |
|--------------|-------------------|
| Token usage from response body (`prompt_tokens`, `completion_tokens`) | Actual remaining quota from provider |
| Hardcoded limits in `ProviderLimits` | Provider-reported limits |
| Our own usage counting | Reset times |

### Options to Get Headers

1. **Accept current approach** - Track our own counts against hardcoded limits (current)
2. **Patch LiteLLM upstream** - Contribute to expose headers in `_hidden_params`
3. **Custom HTTP middleware** - Wrap httpx client to intercept headers before LiteLLM

### Recommendation

For now, current approach works. The hardcoded limits match what providers report in headers
(e.g., Groq shows 14400 req/day, we have that in ProviderLimits).

The main benefit of getting real headers would be:
- Knowing ACTUAL remaining quota (not just our estimate)
- Detecting when other apps use the same API key
- Getting exact reset times

~~This is a "nice to have" enhancement, not critical for enforcement to work.~~

**UPDATE:** User disagrees - hardcoded limits are fragile. Planning HTTP middleware.

---

## Plan: HTTP Middleware for Rate Limit Headers

### Approach

LiteLLM's `HTTPHandler` accepts a custom `httpx.Client`. We can create a client with `event_hooks` to capture response headers.

```python
# httpx event hooks
client = httpx.Client(
    event_hooks={
        'response': [capture_rate_limit_headers]
    }
)
```

### Unified Approach: Patch httpx.Client

**Key discovery:** Patching `httpx.Client.__init__` to inject event hooks captures headers for ALL providers uniformly.

```python
# Patch once at startup - works for groq, cerebras, sambanova
import httpx

original_init = httpx.Client.__init__

def patched_init(self, *args, **kwargs):
    existing_hooks = kwargs.get('event_hooks', {})
    response_hooks = list(existing_hooks.get('response', []))
    response_hooks.append(capture_rate_limit_headers)
    existing_hooks['response'] = response_hooks
    kwargs['event_hooks'] = existing_hooks
    original_init(self, *args, **kwargs)

httpx.Client.__init__ = patched_init
```

**Tested and working for:**
- Groq: `x-ratelimit-limit-requests`, `x-ratelimit-remaining-requests`, etc.
- Cerebras: `x-ratelimit-remaining-requests-day/hour/minute`, tokens too
- SambaNova: `x-ratelimit-limit-requests-day`, `x-ratelimit-remaining-requests-day`, `x-ratelimit-reset-requests-day`

**Gemini special case:** Rate limits come in error response body (429 status), not headers. Parse from `RateLimitError` exception message.

### Scope

#### 1. Create httpx patcher module

```python
# New file: src/scrappy/orchestrator/rate_limiting/httpx_patcher.py

def install_rate_limit_hooks(tracker: RateLimitTrackerProtocol) -> None:
    """Patch httpx.Client to capture rate limit headers."""

    def capture_response(response: httpx.Response) -> None:
        provider = _extract_provider(response.request.url)
        headers = {k: v for k, v in response.headers.items()
                   if 'ratelimit' in k.lower()}
        if headers:
            tracker.update_from_headers(provider, headers)

    # Patch httpx.Client.__init__
    ...
```

#### 2. Parse Gemini error responses

```python
# In exception handling or callback

def parse_gemini_rate_limit(error: RateLimitError) -> dict:
    """Extract quota info from Gemini 429 error."""
    # Parse: "Please retry in 7.215400659s"
    # Parse: quota violations from details
```

#### 3. Extend RateLimitTracker

```python
def update_from_headers(self, provider: str, headers: dict) -> None:
    """Update limits based on actual provider headers."""
```

### Files to Create/Modify

| File | Change |
|------|--------|
| `rate_limiting/httpx_patcher.py` | NEW: Unified httpx patching |
| `rate_limiting/tracker.py` | Add `update_from_headers()` |
| `factory.py` | Call `install_rate_limit_hooks()` at startup |
| `litellm_callbacks.py` | Parse Gemini errors in `log_failure_event()` |

### Provider Header Formats (Discovered)

**Supported providers:** cerebras, groq, gemini, sambanova

| Provider | Remaining Requests | Limit | Reset |
|----------|-------------------|-------|-------|
| Groq | `x-ratelimit-remaining-requests` | `x-ratelimit-limit-requests` | `x-ratelimit-reset-requests` |
| Cerebras | `x-ratelimit-remaining-requests-day` | (not in headers) | (not in headers) |
| Gemini | (in error response body, not headers) | (in error body) | `retryDelay` in error |
| SambaNova | `x-ratelimit-remaining-requests-day` | `x-ratelimit-limit-requests-day` | `x-ratelimit-reset-requests-day` |

### Key Discovery: LiteLLM Header Exposure is Provider-Specific

| Provider | `_response_headers` available? | Headers captured |
|----------|-------------------------------|------------------|
| Cerebras | YES | `x-ratelimit-remaining-requests-day/hour/minute`, `x-ratelimit-remaining-tokens-day/hour/minute` |
| SambaNova | YES | `x-ratelimit-limit-requests-day`, `x-ratelimit-remaining-requests-day`, `x-ratelimit-reset-requests-day` |
| Groq | NO | Headers exist (seen in VCR) but LiteLLM doesn't expose them |
| Gemini | N/A | Rate limits in error body (429), not headers |

**Cerebras example:**
```python
response._response_headers = {
    'x-ratelimit-remaining-requests-minute': '29',
    'x-ratelimit-remaining-requests-hour': '899',
    'x-ratelimit-remaining-requests-day': '14399',
    'x-ratelimit-remaining-tokens-minute': '59997',
    'x-ratelimit-remaining-tokens-hour': '999997',
    'x-ratelimit-remaining-tokens-day': '999997',
}
```

**SambaNova example:**
```python
response._response_headers = {
    'x-ratelimit-limit-requests-day': '40',
    'x-ratelimit-remaining-requests-day': '39',
    'x-ratelimit-reset-requests-day': '1766229945',  # Unix timestamp
}
```

### Revised Approach

Two-pronged strategy:
1. **For Cerebras/SambaNova**: Extract from `response._response_headers` in callback
2. **For Groq**: Need HTTP middleware (httpx event hooks) since LiteLLM doesn't expose
3. **For Gemini**: Parse error responses for quota info

### Gemini Note

Gemini returns rate limit info in error response body (429), not headers:
```json
{
  "error": {
    "code": 429,
    "details": [
      {"@type": "google.rpc.RetryInfo", "retryDelay": "15s"},
      {"@type": "google.rpc.QuotaFailure", "violations": [...]}
    ]
  }
}
```

Need to handle Gemini differently - parse error responses for quota info.

### Considerations

1. **Thread safety** - Header capture must be thread-safe (multiple concurrent requests)
2. **Async support** - Need both sync and async httpx clients
3. **Provider detection** - Extract provider from request URL
4. **Header normalization** - Different providers use different formats
5. **Graceful fallback** - If headers missing, use existing hardcoded limits

### Estimated Effort

**Unified approach (all providers):**
- `httpx_patcher.py`: ~80 lines (patch + provider detection + header parsing)
- `tracker.update_from_headers()`: ~40 lines
- Gemini error parsing: ~30 lines
- Wiring in `factory.py`: ~10 lines
- Tests: ~100 lines

**Total: ~260 lines**

---

## Remaining Work

### Gemini Error Parsing (Future)

Gemini rate limits come in error responses (429), not headers. To complete header capture for all providers:

1. Add error parsing in `litellm_callbacks.py` `log_failure_event()`:
   ```python
   def parse_gemini_rate_limit(error: RateLimitError) -> dict:
       # Parse: "Please retry in 7.215400659s"
       # Parse: quota violations from details
   ```

2. Update tracker when rate limit error occurs:
   ```python
   tracker.update_from_error("gemini", parsed_error_data)
   ```

This is lower priority since:
- Gemini only provides info when rate limited (reactive, not proactive)
- Other providers (groq, cerebras, sambanova) now provide real-time quota via headers
- Gemini fallback to hardcoded limits still works
