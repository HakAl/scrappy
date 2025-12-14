## DECISIONS (Consensus Reached)

### D1: Drop Proactive Quota Checking
**Status:** DECIDED - Drop it
**Rationale:** We're orchestrating free services and expect them to fail. LiteLLM handles retry/fallback automatically. "Try-fail-retry" is a valid permanent strategy.
- Cost: ~200-500ms per failed attempt (one extra round-trip)
- Benefit: Simpler code, no local state drift, fewer code paths
- LiteLLM's `retry_after` cooldown handles backing off rate-limited providers

### D2: Keep BatchScheduler (Refactored)
**Status:** DECIDED - Keep and refactor
**Rationale:** LiteLLM is an executor, not a scheduler. It has no queue concept.
- BatchScheduler provides: semaphore-based concurrency, multi-provider parallel queries, order preservation
- Refactor to delegate execution to LiteLLMService instead of RetryOrchestrator

### D3: Selection-Aware Fallback via Model Groups
**Status:** DECIDED - Handled by architecture
**Rationale:** "quality" group only contains 32k+ context models.
- LiteLLM can't fall back to Cerebras 8k for quality tasks because Cerebras isn't in the quality group
- No custom wrapper logic needed

### D4: Router-Level Callbacks (Not Global)
**Status:** DECIDED - Use router-level
**Rationale:** Global `litellm.success_callback` causes issues with multiple instances/tests.
- Use `callbacks` parameter on Router constructor
- Avoids callback pollution across test runs

### D5: Routing Strategy
**Status:** DECIDED - simple-shuffle for MVP
**Rationale:** "usage-based-routing" requires Redis for persistence.
- Use `routing_strategy="simple-shuffle"` for MVP
- Can upgrade to usage-based later if Redis added

### D6: AuthenticationError Handling
**Status:** DECIDED - Warn and continue with remaining providers
**Rationale:** Keys are validated at wizard, but can expire. Need resilient + actionable UX.
- Catch `AuthenticationError`, extract `e.llm_provider`
- Log warning: "API key for {provider} is invalid/expired. Run `scrappy config` to update."
- Continue with remaining valid providers (don't hard stop)
- Don't retry auth errors (pointless)

### D7: Empty Router Guard
**Status:** DECIDED - Fail fast with clear error
**Rationale:** Edge case (manual config tampering), but should be defensive.
- Check `if not model_list` at router creation
- Raise `ConfigurationError` with message: "No valid API keys found. Run `scrappy config` to reconfigure."
- Don't auto-launch wizard from deep in stack (messy)

### D8: auto_fallback Parameter
**Status:** DECIDED - Drop for MVP
**Rationale:** No use case identified. YAGNI.
- Easy to add later if needed: `completion(..., allow_fallback: bool = True)`

### D9: Usage Tracking (MUST NOT DROP)
**Status:** DECIDED - Maintain feature parity via callbacks
**Rationale:** `/limits` command depends on per-provider, per-model usage data. Must preserve.

**Current behavior:**
- `UsageReporter` tracks: provider, model, tokens_used, request_count, latency
- `RateLimitTracker` tracks: requests per provider, remaining quota

**With LiteLLM:**
- Router-level callbacks receive actual provider/model (not group name)
- `response.model` = "groq/llama-3.1-8b-instant" (real model, not "fast")
- `response.usage` = prompt_tokens, completion_tokens

**Implementation requirements:**
1. `RateTrackingCallback` class that implements LiteLLM callback interface
2. Extract real provider from `response.model.split("/")[0]`
3. Pass to existing `RateLimitTracker.record_request()` and `UsageReporter.record()`
4. Ensure callback is wired at Router creation (D4)

**Verification test:**
```python
def test_usage_tracking_records_actual_provider():
    """Ensure we track 'groq', not 'fast' in usage reports."""
    tracker = MockRateLimitTracker()
    # ... setup with callback ...
    service.completion_sync("fast", messages)

    # Must record actual provider, not group name
    assert tracker.last_recorded_provider == "groq"
    assert tracker.last_recorded_model == "groq/llama-3.1-8b-instant"
```

### D10: Provider Status Display
**Status:** DECIDED - Use LiteLLM SDK health checks + callback tracking
**Rationale:** LiteLLM SDK provides `health_check()` and `ahealth_check()` for real health checks.

**LiteLLM Health Check API:**
```python
import litellm

# Sync health check - returns {'healthy': bool, 'error_message': str|None}
response = litellm.health_check(model="groq/llama-3.1-8b-instant", api_key="...")

# Async health check
response = await litellm.ahealth_check(model="gemini/gemini-2.5-flash", api_key="...")

# Key validation only
is_valid = litellm.check_valid_key(model="...", api_key="...")

# Environment check (no network call)
res = litellm.validate_environment(model="...")  # {'keys_in_environment': bool, 'missing_keys': [...]}
```

**Implementation approach:**
1. **On-demand health checks** - `/status` command runs `ahealth_check()` for each configured model
2. **Callback tracking** - Track last success/failure per provider via callbacks (real-time status)
3. **Startup validation** - Use `check_valid_key()` in wizard to validate keys before storage

**ProviderStatusTracker:**
```python
class ProviderStatusTracker:
    def __init__(self):
        self._status: dict[str, ProviderStatus] = {}

    def on_success(self, provider: str, model: str, latency_ms: float):
        self._status[provider] = ProviderStatus(
            healthy=True,
            last_success=datetime.now(),
            last_latency_ms=latency_ms,
        )

    def on_failure(self, provider: str, error: str):
        self._status[provider] = ProviderStatus(
            healthy=False,
            last_error=error,
            last_failure=datetime.now(),
        )

    async def run_health_checks(self, models: list[dict]) -> dict[str, HealthCheckResponse]:
        """Run health checks for all configured models."""
        results = {}
        for model_config in models:
            model_id = model_config["litellm_params"]["model"]
            api_key = model_config["litellm_params"]["api_key"]
            results[model_id] = await litellm.ahealth_check(
                model=model_id,
                api_key=api_key,
                timeout=15,
            )
        return results
```

**Not in MVP:**
- Background health monitoring (periodic checks)
- Auto-disable unhealthy providers

### D11: OrchestratorAdapter Integration
**Status:** DECIDED - No interface change, add internal provider->group mapping
**Rationale:** OrchestratorAdapter is a facade that sits above DelegationManager. Interface stays the same.

**Architecture:**
```
Agent -> OrchestratorAdapter -> DelegationManager -> LiteLLMService -> LiteLLM Router
```

**Provider parameter handling:**
- Accept both model groups ("fast", "quality") and provider names ("groq", "cerebras")
- Map provider names to model groups internally for backward compatibility

```python
MODEL_GROUPS = {"fast", "quality"}
PROVIDER_TO_GROUP = {"groq": "fast", "cerebras": "fast", "gemini": "quality"}

def _resolve_model_group(provider: str) -> str:
    if provider in MODEL_GROUPS:
        return provider
    return PROVIDER_TO_GROUP.get(provider, "fast")
```

### D12: Tool Calling Integration
**Status:** DECIDED - Keep delegate_with_tools(), pass through as kwargs
**Rationale:** LiteLLM handles tools natively via kwargs. No special handling needed.

**Implementation:**
- Keep `delegate_with_tools()` method for API clarity
- Internally calls `completion()` with `tools` and `tool_choice` kwargs
- `_extract_tool_calls()` already handles response parsing

```python
# LiteLLM passes through tools natively
response = router.completion(
    model="quality",
    messages=messages,
    tools=tools,        # Passed through to provider
    tool_choice="auto", # Passed through to provider
)
```

**Note:** Not all providers support tool calling equally. Groq and Gemini support it; Cerebras support varies by model.

  3. Duplicate Mapping Constants

  SELECTION_TO_GROUP is defined in three places:
  - provider_resolver.py
  - provider_selector.py
  - litellm_config.py

  This violates DRY and risks inconsistency.

RESOLUTION
 The mapping belongs in model_selection.py alongside the enum it maps from.

● Update(src\scrappy\orchestrator\model_selection.py)
  ⎿  Updated src\scrappy\orchestrator\model_selection.py with 10 additions
        7        QUALITY = "quality"  # Best output quality
        8        INSTRUCT = "instruct"  # Instruction-tuned for JSON/structured output
        9        EMBED = "embed"      # Embeddings
       10 +
       11 +
       12 +  # Canonical mapping from ModelSelectionType to LiteLLM model groups.
       13 +  # Single source of truth - import this instead of defining your own.
       14 +  SELECTION_TYPE_TO_GROUP: dict[ModelSelectionType, str] = {
       15 +      ModelSelectionType.FAST: "fast",
       16 +      ModelSelectionType.QUALITY: "quality",
       17 +      ModelSelectionType.INSTRUCT: "quality",  # Instruct maps to quality tier
       18 +      ModelSelectionType.EMBED: "fast",        # Embeddings use fast tier
       19 +  }



---
DECISION: Add SambaNova because great models. Note only 40 RPD

## NOTES

**Reviewed:** 2024-12-14
**Status:** Ready for implementation with fixes below applied

### Key Fixes Applied
1. AuthenticationError - Don't catch/re-raise; let LiteLLM Router handle fallback
2. ContextWindowExceededError - Added to both async and sync methods
3. Callback duplication - Removed `_on_success/_on_failure` from LiteLLMService (use RateTrackingCallback only)
4. Tool calling - Documented kwargs passthrough for `tools` param
5. OrchestratorAdapter - Added Phase 3e with provider->group mapping
6. Import cleanup - Added explicit file list to Phase 4
7. Behavioral change - Documented fixed delay vs exponential backoff tradeoff

### Out of Scope (Future Phase)
- Streaming support - Will build when needed, no stubs