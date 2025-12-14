# LiteLLM Router Integration

## KEY RESEARCH
docs/TODO/litellm_exceptions.md
docs/TODO/litellm_python_api.md
docs/TODO/model_groupings.md
docs/TODO/litellm_providers.md
docs/TODO/litellm_decisions.md
docs/TODO/litellm_healthchecks.md

## Architecture

```
AgentOrchestrator (entry point)
    |
    v
TaskRouter (Brain - unchanged)
    |
    | classify task -> "fast" or "quality"
    v
DelegationManager (UPDATED - simpler interface)
    |
    | augment prompt, check cache
    v
LiteLLMService (NEW - replaces RetryOrchestrator + providers)
    |
    | model="fast" or model="quality"
    | LiteLLM handles: retry, fallback, rate limits internally
    v
LiteLLM Router
    |
    v
[Cerebras] [Groq] [Gemini] ...
```

**Key Insight:** LiteLLM's `num_retries` + `fallbacks` params handle what `RetryOrchestrator`
does today. We don't need to implement `RetryOrchestratorProtocol` - we create a simpler
`LiteLLMServiceProtocol` instead.

---

## Test Strategy

### Unit Tests (mock_response)

LiteLLM's `mock_response` param bypasses API entirely - perfect for testing our logic.

**File: `tests/orchestrator/test_litellm_service.py`**

```python
# Test Doubles

class MockRouter:
    """Test double for litellm.Router."""

    def __init__(self, mock_response=None, raise_exception=None):
        self.mock_response = mock_response
        self.raise_exception = raise_exception
        self.calls = []

    def completion(self, model, messages, **kwargs):
        self.calls.append({'model': model, 'messages': messages, **kwargs})
        if self.raise_exception:
            raise self.raise_exception
        return self.mock_response

    async def acompletion(self, model, messages, **kwargs):
        return self.completion(model, messages, **kwargs)


def make_mock_litellm_response(
    content="test response",
    model="groq/llama-3.1-8b-instant",
    prompt_tokens=10,
    completion_tokens=20,
    finish_reason="stop",
):
    """Factory for mock LiteLLM responses."""
    return Mock(
        choices=[Mock(
            message=Mock(content=content, tool_calls=None),
            finish_reason=finish_reason,
        )],
        model=model,
        usage=Mock(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        ),
    )
```
```python
def test_returns_actual_model_used_not_group_name(self):
    """Ensure we record 'groq/llama-3...' not 'fast' in our logs."""
    
    # The router was called with model="fast"
    # But the response object from the provider will contain the REAL model ID
    mock_resp = make_mock_litellm_response(model="groq/llama-3.1-8b-instant")
    
    # ... setup service ...
    
    response, task = service.completion_sync("fast", messages)
    
    # Critical: Use the model from the RESPONSE, not the REQUEST
    assert response.model == "groq/llama-3.1-8b-instant" 
    assert task["model"] == "groq/llama-3.1-8b-instant"
```

**Tests to write:**

1. **Response Conversion** (`_convert_response`):
   - `test_converts_standard_response` - content, tokens, latency correct
   - `test_extracts_provider_from_model_string` - "cerebras/llama-3.3-70b" -> "cerebras"
   - `test_handles_missing_usage_gracefully` - usage=None doesn't crash
   - `test_extracts_tool_calls_when_present`
   - `test_returns_task_record_with_metadata`

2. **Exception Mapping**:
   - `test_rate_limit_error_becomes_all_providers_exhausted`
   - `test_preserves_llm_provider_in_exception`
   - `test_handles_missing_llm_provider_attribute`

3. **Completion Flow**:
   - `test_completion_calls_router_with_correct_params`
   - `test_completion_sync_calls_router_completion`
   - `test_passes_through_kwargs` (max_tokens, temperature)

4. **Rate Tracking Callbacks**:
   - `test_on_success_records_to_rate_tracker`
   - `test_on_failure_records_error_to_rate_tracker`
   - `test_callbacks_noop_when_no_rate_tracker`

**File: `tests/orchestrator/test_litellm_callbacks.py`** (D9 verification)

```python
class MockRateLimitTracker:
    """Test double for RateLimitTrackerProtocol."""
    def __init__(self):
        self.recorded_requests = []

    def record_request(self, **kwargs):
        self.recorded_requests.append(kwargs)

    @property
    def last_recorded(self):
        return self.recorded_requests[-1] if self.recorded_requests else None
```

**Tests to write (D9 - MUST NOT DROP):**

1. **Usage Tracking Records Actual Provider**:
   - `test_callback_extracts_real_provider_not_group_name` - "groq" not "fast"
   - `test_callback_extracts_real_model_not_group_name` - "groq/llama-3.1-8b-instant" not "fast"
   - `test_callback_records_token_counts_correctly`
   - `test_callback_records_latency_correctly`

2. **Status Tracking (D10)**:
   - `test_success_updates_provider_status_healthy`
   - `test_failure_updates_provider_status_unhealthy`
   - `test_status_includes_last_error_message`

**File: `tests/orchestrator/test_litellm_config.py`**

```python
class MockApiKeyService:
    """Test double for ApiKeyConfigService."""

    def __init__(self, keys: dict[str, str | None]):
        self._keys = keys

    def get_key(self, name: str) -> str | None:
        return self._keys.get(name)
```

**Tests to write:**

1. **Router Configuration**:
   - `test_adds_fast_models_when_groq_key_present`
   - `test_adds_fast_models_when_cerebras_key_present`
   - `test_adds_quality_models_when_gemini_key_present`
   - `test_skips_models_when_api_key_missing`
   - `test_fast_tier_priority_groq_before_cerebras`
   - `test_quality_tier_excludes_cerebras_70b`
   - `test_empty_model_list_raises_configuration_error`

2. **Edge Cases (CRITICAL)**:
   - `test_context_window_exceeded_on_fast_escalates_to_quality`
   - `test_context_window_exceeded_on_quality_raises_fatal`
   - `test_all_providers_in_group_fail_raises_all_providers_exhausted`
   - `test_handles_response_with_no_usage_field`
   - `test_handles_response_with_empty_model_string`

3. **Escalation & Recursion Safety (NEW)**:
   - `test_max_escalation_depth_raises_runtime_error`
   - `test_escalation_records_metrics_to_callback`
   - `test_escalated_from_included_in_task_record`
   - `test_escalated_from_included_in_response_metadata`

**File: `tests/orchestrator/test_litellm_escalation.py`**

```python
import pytest
from unittest.mock import Mock, AsyncMock
from litellm import ContextWindowExceededError

from scrappy.orchestrator.litellm_service import LiteLLMService, MAX_ESCALATION_DEPTH
from scrappy.orchestrator.litellm_callbacks import RateTrackingCallback, EscalationMetrics


class TestEscalationDepthGuard:
    """Tests for recursion safety in context window escalation."""

    def test_max_escalation_depth_raises_runtime_error_sync(self):
        """Verify sync method raises RuntimeError when max depth exceeded."""
        mock_router = Mock()
        mock_output = Mock()
        service = LiteLLMService(router=mock_router, output=mock_output)

        # Directly call with depth at limit
        with pytest.raises(RuntimeError) as exc_info:
            service.completion_sync(
                model="quality",
                messages=[{"role": "user", "content": "test"}],
                _escalation_depth=MAX_ESCALATION_DEPTH,
            )

        assert "Max escalation depth" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_max_escalation_depth_raises_runtime_error_async(self):
        """Verify async method raises RuntimeError when max depth exceeded."""
        mock_router = Mock()
        mock_router.acompletion = AsyncMock()
        mock_output = Mock()
        service = LiteLLMService(router=mock_router, output=mock_output)

        with pytest.raises(RuntimeError) as exc_info:
            await service.completion(
                model="quality",
                messages=[{"role": "user", "content": "test"}],
                _escalation_depth=MAX_ESCALATION_DEPTH,
            )

        assert "Max escalation depth" in str(exc_info.value)

    def test_escalation_increments_depth(self):
        """Verify escalation increments depth counter."""
        mock_router = Mock()
        # First call raises ContextWindowExceeded, second succeeds
        mock_router.completion = Mock(
            side_effect=[
                ContextWindowExceededError(message="too long", model="fast"),
                make_mock_litellm_response(model="groq/llama-3.3-70b-versatile"),
            ]
        )
        mock_output = Mock()
        mock_callback = Mock(spec=RateTrackingCallback)
        service = LiteLLMService(
            router=mock_router, output=mock_output, callback=mock_callback
        )

        response, task_record = service.completion_sync(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        )

        # Verify escalation was recorded
        mock_callback.record_escalation.assert_called_once_with("fast", "quality")

        # Verify task_record has escalation info
        assert task_record["escalated_from"] == "fast"


class TestEscalationMetrics:
    """Tests for escalation metrics tracking."""

    def test_escalation_metrics_records_event(self):
        """Verify EscalationMetrics correctly records escalation."""
        metrics = EscalationMetrics()

        metrics.record_escalation("fast", "quality")
        metrics.record_escalation("fast", "quality")

        summary = metrics.get_summary()
        assert summary["total_escalations"] == 2
        assert summary["by_path"]["fast->quality"] == 2

    def test_callback_record_escalation_updates_metrics(self):
        """Verify callback properly updates escalation metrics."""
        mock_rate_tracker = Mock()
        callback = RateTrackingCallback(rate_tracker=mock_rate_tracker)

        callback.record_escalation("fast", "quality")

        assert callback.escalation_metrics.total_escalations == 1


class TestEscalationMetadataInResponse:
    """Tests for escalation info in response/task_record."""

    def test_escalated_from_in_response_metadata(self):
        """Verify escalated_from appears in LLMResponse.metadata."""
        mock_router = Mock()
        mock_router.completion = Mock(
            side_effect=[
                ContextWindowExceededError(message="too long", model="fast"),
                make_mock_litellm_response(model="groq/llama-3.3-70b-versatile"),
            ]
        )
        mock_output = Mock()
        service = LiteLLMService(router=mock_router, output=mock_output)

        response, _ = service.completion_sync(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        )

        assert response.metadata.get("escalated_from") == "fast"

    def test_no_escalation_no_metadata(self):
        """Verify escalated_from not in metadata when no escalation."""
        mock_router = Mock()
        mock_router.completion = Mock(
            return_value=make_mock_litellm_response(model="groq/llama-3.1-8b-instant")
        )
        mock_output = Mock()
        service = LiteLLMService(router=mock_router, output=mock_output)

        response, task_record = service.completion_sync(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        )

        assert "escalated_from" not in response.metadata
        assert task_record.get("escalated_from") is None
```

**NOTE: Test Double Consolidation**

Move all test doubles to `tests/helpers.py` per CLAUDE.md guidelines:
- `MockRouter` - from test_litellm_service.py
- `MockRateLimitTracker` - from test_litellm_callbacks.py
- `MockApiKeyService` - from test_litellm_config.py
- `MockOutputInterface` - shared output mock
- `make_mock_litellm_response()` - factory function

Add this test to tests/orchestrator/test_delegation_flow.py. 
It does not need to hit a real API; it just needs to prove the wiring maps the intent to the router group.

```
import pytest
from unittest.mock import AsyncMock, Mock
from scrappy.orchestrator.delegation import DelegationManager
# ... imports ...

@pytest.mark.asyncio
async def test_cognitive_routing_end_to_end():
    """
    Verify TaskRouter classification correctly targets the LiteLLM model group.
    """
    # 1. Setup Mocks
    mock_llm_service = Mock(spec=LiteLLMServiceProtocol)
    # return simple valid response
    mock_llm_service.completion_sync.return_value = (
        LLMResponse(content="ok", model="groq/llama...", ...), 
        {}
    )
    
    # 2. Setup Real Components
    task_router = TaskRouter() # Real logic
    manager = DelegationManager(
        llm_service=mock_llm_service,
        # ... other mocks ...
    )

    # 3. Execution - Test "Quality" Path
    # Using a prompt known to trigger 'quality' in TaskRouter (e.g., "analyze complex code")
    manager.delegate(
        provider_name="auto", 
        prompt="Analyze this complex 500 line code file deeply.",
        # ...
    )

    # 4. Verification
    # Check that LiteLLMService was called with model="quality", NOT "fast"
    args, _ = mock_llm_service.completion_sync.call_args
    assert args[0] == "quality" 

    # 5. Execution - Test "Fast" Path
    manager.delegate(
        provider_name="auto", 
        prompt="Say hi.",
        # ...
    )
    
    args, _ = mock_llm_service.completion_sync.call_args
    assert args[0] == "fast"
```

---

### Post-MVP: Integration Tests (VCR.py)

Record real API calls, replay in CI. Proves integration actually works.

**Scope (deferred):**
- Record responses from each provider
- Verify fallback triggers on rate limit
- Test tool_calls extraction with real response
- Verify streaming works (if implemented)

**Setup:**
```python
import vcr

@vcr.use_cassette('cassettes/groq_completion.yaml')
def test_groq_real_response():
    # First run: hits real API, records to cassette
    # Future runs: replays cassette
    ...
```

**Value:** Catches when providers change their response format.

## Model Group Definitions

Current requirement: `MIN_CONTEXT_FOR_BRAIN = 32768` (quality tasks need 32k+ context)

### "fast" tier (speed priority, any context OK)

| Priority | Model | Context | Speed | Quality | RPD |
|----------|-------|---------|-------|---------|-----|
| 1 | groq/llama-3.1-8b-instant | 128k | VERY_FAST | GOOD | 7000 |
| 2 | cerebras/llama3.1-8b | 8k | ULTRA_FAST | GOOD | 14400 |

### "quality" tier (quality priority, >= 32k context required)

| Priority | Model | Context | Speed | Quality | RPD |
|----------|-------|---------|-------|---------|-----|
| 1 | gemini/gemini-2.5-flash | ~1M | MODERATE | VERY_GOOD | 250 |
| 2 | groq/llama-3.3-70b-versatile | 32k | FAST | EXCELLENT | 1000 |
| 3 | groq/moonshotai/kimi-k2-instruct | 128k | ULTRA_FAST | EXCELLENT | 7000 |

### NOT in quality tier (insufficient context)

- `cerebras/llama-3.3-70b` - Only 8k context despite EXCELLENT quality
- `cerebras/qwen-3-235b-a22b-instruct` - Only 8k context despite EXCELLENT quality

---

## Migration Path

### Phase 1: Reroute Provider Selection Functionality

**Goal:** Map all current ProviderSelector/ProviderResolver functionality to the new LiteLLM-based architecture. Ensure no gaps.

---

#### 1a: Current Functionality Audit

**ProviderResolver** (`task_router/provider_resolver.py`):
| Method | Current Behavior | After LiteLLM |
|--------|-----------------|---------------|
| `resolve(selection_type)` | Calls `ProviderSelector.get_model()` -> returns `(provider, model)` | Return `(group, None)` directly: FAST->"fast", QUALITY->"quality" |

**ProviderSelector** (`orchestrator/provider_selector.py`):
| Method | Current Behavior | After LiteLLM |
|--------|-----------------|---------------|
| `get_model(FAST)` | Scans providers for fastest model | Not needed - Router handles |
| `get_model(QUALITY)` | Scans for quality model with 32k+ context | Not needed - "quality" group defined |
| `get_model(INSTRUCT)` | Scans for instruction-tuned model | Map to "quality" or create "instruct" group |
| `get_provider_for_fallback()` | Returns next provider excluding tried ones | Not needed - Router handles fallback |
| `setup_brain()` | Selects brain provider for orchestrator | Use "quality" group |
| `select_for_planning()` | Selects instruction-tuned model | Use "quality" group |
| `_get_providers_with_context()` | Filters by context length | Not needed - baked into group definitions |
| `recommend()` | Recommends based on requirements dict | Simplify to return "fast" or "quality" |

**AgentOrchestratorAdapter** (`orchestrator_adapter.py`):
| Method | Current Behavior | After LiteLLM |
|--------|-----------------|---------------|
| `delegate(selection_type=...)` | Passes to orchestrator | Pass model group name |
| `delegate_with_tools()` | Gets provider instance, checks `supports_tool_calling` | Pass tools via kwargs to LiteLLMService |

---

#### 1b: Update ProviderResolver (Simplify)

```python
# src/scrappy/task_router/provider_resolver.py

from ..orchestrator.model_selection import ModelSelectionType

# Direct mapping - no ProviderSelector needed
SELECTION_TO_GROUP = {
    ModelSelectionType.FAST: "fast",
    ModelSelectionType.QUALITY: "quality",
    ModelSelectionType.INSTRUCT: "quality",  # Instruct maps to quality tier
    ModelSelectionType.EMBED: "fast",        # Embeddings use fast tier
}


class ProviderResolver:
    """
    Resolves selection types to LiteLLM model groups.

    Simplified: No longer needs ProviderSelector or orchestrator reference.
    """

    def __init__(self, orchestrator=None):
        # orchestrator param kept for backward compatibility but not used
        pass

    def resolve(
        self,
        selection_type: Optional[ModelSelectionType]
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Resolve selection type to model group.

        Returns:
            Tuple of (model_group, None) - model is selected by LiteLLM Router
        """
        if selection_type is None:
            return (None, None)

        group = SELECTION_TO_GROUP.get(selection_type, "fast")
        return (group, None)  # Model is None - Router picks actual model
```

---

#### 1c: Update ProviderSelector (Reduce Scope)

Most methods become obsolete. Keep only what's needed for status display.

```python
# src/scrappy/orchestrator/provider_selector.py

class ProviderSelector:
    """
    REDUCED SCOPE: After LiteLLM integration, this class only handles:
    - setup_brain() -> returns "quality" (no longer scans providers)
    - Status display helpers (if needed)

    Selection logic is now handled by:
    - TaskRouter -> classifies as "fast" or "quality"
    - LiteLLM Router -> handles fallback within group
    """

    def __init__(self, config: Optional[OrchestratorConfig] = None):
        self.config = config or OrchestratorConfig()
        # NOTE: No registry needed anymore

    def setup_brain(self, preferred_provider: Optional[str] = None) -> str:
        """
        Return the model group to use for brain/reasoning.

        Returns:
            Model group name ("quality" for brain tasks)
        """
        # If user explicitly requested a provider, warn and use quality
        if preferred_provider and preferred_provider not in ("fast", "quality"):
            # Legacy provider name - map to group
            return "quality"  # Brain always uses quality tier
        return preferred_provider or "quality"

    def get_model(self, selection_type: ModelSelectionType) -> tuple[str, None]:
        """
        Map selection type to model group.

        DEPRECATED: Use ProviderResolver.resolve() or pass group directly.
        Kept for backward compatibility during migration.
        """
        from .model_selection import ModelSelectionType

        mapping = {
            ModelSelectionType.FAST: "fast",
            ModelSelectionType.QUALITY: "quality",
            ModelSelectionType.INSTRUCT: "quality",
            ModelSelectionType.EMBED: "fast",
        }
        return (mapping.get(selection_type, "fast"), None)

    # REMOVED: get_provider_for_fallback() - Router handles this
    # REMOVED: _get_providers_with_context() - Baked into group definitions
    # REMOVED: _select_by_speed/quality/instruct() - Router handles this
    # REMOVED: recommend() - Simplified to group selection
```

---

#### 1d: Update AgentOrchestratorAdapter

```python
# src/scrappy/orchestrator_adapter.py

class AgentOrchestratorAdapter:
    # ... existing code ...

    def delegate_with_tools(
        self,
        provider_name: Optional[str] = None,
        prompt: str = "",
        tools: List[dict] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1500,
        temperature: float = 0.3,
        tool_choice: str = "auto",
        **kwargs
    ) -> LLMResponse:
        """
        Delegate to provider with native tool calling support.

        UPDATED: No longer checks provider.supports_tool_calling.
        LiteLLM handles tool calling natively via kwargs.
        """
        if tools is None:
            tools = []

        # Resolve provider name to model group
        model_group = self._resolve_model_group(provider_name or "quality")

        # Build messages
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Delegate through normal path - tools passed as kwargs
        return self._orch.delegate(
            provider_name=model_group,
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=tools,           # LiteLLM handles this
            tool_choice=tool_choice,
            **kwargs
        )

    def _resolve_model_group(self, provider_or_group: str) -> str:
        """Resolve legacy provider names to model groups."""
        MODEL_GROUPS = {"fast", "quality"}
        PROVIDER_TO_GROUP = {
            "groq": "fast",
            "cerebras": "fast",
            "gemini": "quality",
            "auto": "fast",
        }
        if provider_or_group in MODEL_GROUPS:
            return provider_or_group
        return PROVIDER_TO_GROUP.get(provider_or_group, "fast")
```

---

#### 1e: Model Metadata for Status Display

For `/status` and `/limits` commands, we need model metadata. Store alongside router config:

```python
# src/scrappy/orchestrator/litellm_config.py

from dataclasses import dataclass
from enum import Enum

class SpeedRank(Enum):
    ULTRA_FAST = "ultra_fast"
    VERY_FAST = "very_fast"
    FAST = "fast"
    MODERATE = "moderate"

class QualityRank(Enum):
    EXCELLENT = "excellent"
    VERY_GOOD = "very_good"
    GOOD = "good"

@dataclass
class ModelMetadata:
    """Metadata for status display. NOT used for routing."""
    model_id: str
    provider: str
    group: str          # "fast" or "quality"
    context_length: int
    speed: SpeedRank
    quality: QualityRank
    rpd: int
    tpm: int

# Static metadata for display purposes
MODEL_METADATA: dict[str, ModelMetadata] = {
    "groq/llama-3.1-8b-instant": ModelMetadata(
        model_id="groq/llama-3.1-8b-instant",
        provider="groq",
        group="fast",
        context_length=131072,
        speed=SpeedRank.VERY_FAST,
        quality=QualityRank.GOOD,
        rpd=7000,
        tpm=20000,
    ),
    "cerebras/llama3.1-8b": ModelMetadata(
        model_id="cerebras/llama3.1-8b",
        provider="cerebras",
        group="fast",
        context_length=8192,
        speed=SpeedRank.ULTRA_FAST,
        quality=QualityRank.GOOD,
        rpd=14400,
        tpm=60000,
    ),
    # ... etc for all models
}

def get_models_for_group(group: str) -> list[ModelMetadata]:
    """Get all models in a group (for status display)."""
    return [m for m in MODEL_METADATA.values() if m.group == group]

def get_configured_models(api_key_service) -> list[ModelMetadata]:
    """Get models that have API keys configured."""
    configured = []
    for model in MODEL_METADATA.values():
        key_name = f"{model.provider.upper()}_API_KEY"
        if api_key_service.get_key(key_name):
            configured.append(model)
    return configured
```

---

#### 1f: Success Criteria

- [ ] `ProviderResolver.resolve()` returns model groups directly (no ProviderSelector call)
- [ ] `ProviderSelector.get_model()` returns model groups (for backward compat)
- [ ] `ProviderSelector.setup_brain()` returns "quality"
- [ ] `AgentOrchestratorAdapter.delegate_with_tools()` passes tools via kwargs
- [ ] `/status` command still works using `MODEL_METADATA`
- [ ] All existing tests pass (may need mocking updates)

---

### Phase 2: LiteLLM Integration Layer

**Goal:** Create the integration layer that maps LiteLLM to our interfaces.

#### 2a: Protocol Definition

```python
# src/scrappy/orchestrator/protocols.py (add to existing)

class LLMServiceProtocol(Protocol):
    """Simple LLM completion interface. LiteLLM handles retry/fallback internally."""

    async def completion(
        self,
        model: str,
        messages: list[dict],
        **kwargs
    ) -> tuple[LLMResponse, dict]:
        """Returns (response, task_record)."""
        ...

    def completion_sync(
        self,
        model: str,
        messages: list[dict],
        **kwargs
    ) -> tuple[LLMResponse, dict]:
        """Sync version for Textual worker threads."""
        ...
```

#### 2b: LiteLLMService Implementation
## CRITICAL

Context Window Exception Handling
ContextWindowExceededError  catch block in LiteLLMService
This is fatal for the "Fast" tier if a user accidentally sends 9k tokens to an 8k model.
Update LiteLLMService.completion:
```
from litellm import ContextWindowExceededError

# ... inside try/except block ...
except ContextWindowExceededError as e:
    # Option A: Fail fast (let caller handle)
    # raise e 
    
    # Option B: Smart Recovery (try quality tier)
    if model == "fast":
        self._output.warn("Context window exceeded on fast tier, retrying with quality tier...")
        # Recursive call to quality group
        return await self.completion("quality", messages, **kwargs)
    
    raise e # logic failure if quality tier also fails
```

```python
# src/scrappy/orchestrator/litellm_service.py

import json
import time
import litellm
from litellm import (
    RateLimitError as LiteLLMRateLimitError,
    ContextWindowExceededError,
)

# Maximum escalation depth to prevent infinite recursion
MAX_ESCALATION_DEPTH = 2


class LiteLLMService:
    """
    LiteLLM integration layer.
    Replaces: RetryOrchestrator + all individual providers

    LiteLLM handles internally:
    - Retries with exponential backoff (num_retries)
    - Provider fallback (multiple models with same model_name)
    - Rate limit detection and handling
    - AuthenticationError -> triggers fallback to next provider (D6)

    We handle:
    - Response normalization to LLMResponse
    - Exception mapping to our types
    - ContextWindowExceededError -> escalate fast->quality (with depth guard)
    - Request/response logging

    NOTE: Rate tracking is handled by RateTrackingCallback (see litellm_callbacks.py),
    NOT by methods on this class. Callbacks are wired at Router creation time (D4).
    """

    def __init__(
        self,
        router: litellm.Router,
        output: OutputInterfaceProtocol,
        callback: Optional[RateTrackingCallback] = None,
    ):
        self._router = router
        self._output = output
        self._callback = callback  # For escalation tracking
        # NOTE: Router-level callbacks handle rate tracking (D4).
        # The callback reference here is for escalation metrics only.

    async def completion(
        self,
        model: str,
        messages: list[dict],
        _escalation_depth: int = 0,
        **kwargs
    ) -> tuple[LLMResponse, dict]:
        """
        Execute completion via LiteLLM Router.

        Args:
            model: Model group name ("fast" or "quality")
            messages: Chat messages
            _escalation_depth: Internal counter to prevent infinite recursion (do not set)
            **kwargs: Additional params (max_tokens, temperature, tools, tool_choice, etc.)
                      Tools are passed through to provider: tools=[...], tool_choice="auto"

        Returns:
            Tuple of (LLMResponse, task_record dict)

        Raises:
            AllProvidersRateLimitedError: When all providers exhausted
            ContextWindowExceededError: When quality tier also exceeds context (fatal)
            RuntimeError: When max escalation depth exceeded (safety guard)
        """
        # Safety guard against infinite recursion
        if _escalation_depth >= MAX_ESCALATION_DEPTH:
            raise RuntimeError(
                f"Max escalation depth ({MAX_ESCALATION_DEPTH}) exceeded. "
                "Context window too small for all available model tiers."
            )

        start = time.time()
        escalated_from = None

        try:
            response = await self._router.acompletion(
                model=model,
                messages=messages,
                num_retries=3,
                **kwargs
            )
            elapsed = time.time() - start
            return self._convert_response(response, elapsed, escalated_from=escalated_from)

        except ContextWindowExceededError as e:
            # Smart recovery: fast tier -> try quality tier (has larger context models)
            if model == "fast":
                self._output.warn(
                    "Context window exceeded on fast tier, retrying with quality tier..."
                )
                # Track escalation for monitoring
                if self._callback:
                    self._callback.record_escalation("fast", "quality")
                return await self.completion(
                    "quality", messages,
                    _escalation_depth=_escalation_depth + 1,
                    _escalated_from="fast",
                    **kwargs
                )
            # Quality tier failed too - fatal, re-raise
            raise

        except LiteLLMRateLimitError as e:
            raise AllProvidersRateLimitedError(
                message=e.message,
                attempted_providers=[e.llm_provider] if hasattr(e, 'llm_provider') else [],
            )
        # NOTE: AuthenticationError is NOT caught here.
        # LiteLLM Router handles auth failures internally by trying next provider in group.
        # If all providers in group fail auth, Router raises the error which propagates up.

    def completion_sync(
        self,
        model: str,
        messages: list[dict],
        _escalation_depth: int = 0,
        **kwargs
    ) -> tuple[LLMResponse, dict]:
        """
        Sync version for non-async contexts (Textual workers).

        Args:
            model: Model group name ("fast" or "quality")
            messages: Chat messages
            _escalation_depth: Internal counter to prevent infinite recursion (do not set)
            **kwargs: Additional params (max_tokens, temperature, tools, tool_choice, etc.)

        Returns:
            Tuple of (LLMResponse, task_record dict)

        Raises:
            AllProvidersRateLimitedError: When all providers exhausted
            ContextWindowExceededError: When quality tier also exceeds context (fatal)
            RuntimeError: When max escalation depth exceeded (safety guard)
        """
        # Safety guard against infinite recursion
        if _escalation_depth >= MAX_ESCALATION_DEPTH:
            raise RuntimeError(
                f"Max escalation depth ({MAX_ESCALATION_DEPTH}) exceeded. "
                "Context window too small for all available model tiers."
            )

        start = time.time()

        try:
            response = self._router.completion(
                model=model,
                messages=messages,
                num_retries=3,
                **kwargs
            )
            elapsed = time.time() - start
            return self._convert_response(response, elapsed, escalated_from=kwargs.get('_escalated_from'))

        except ContextWindowExceededError as e:
            # Smart recovery: fast tier -> try quality tier (has larger context models)
            if model == "fast":
                self._output.warn(
                    "Context window exceeded on fast tier, retrying with quality tier..."
                )
                # Track escalation for monitoring
                if self._callback:
                    self._callback.record_escalation("fast", "quality")
                return self.completion_sync(
                    "quality", messages,
                    _escalation_depth=_escalation_depth + 1,
                    _escalated_from="fast",
                    **kwargs
                )
            # Quality tier failed too - fatal, re-raise
            raise

        except LiteLLMRateLimitError as e:
            raise AllProvidersRateLimitedError(
                message=e.message,
                attempted_providers=[e.llm_provider] if hasattr(e, 'llm_provider') else [],
            )
        # NOTE: AuthenticationError is NOT caught here. See async version for rationale.

    def _convert_response(
        self,
        response,
        elapsed: float,
        escalated_from: Optional[str] = None,
    ) -> tuple[LLMResponse, dict]:
        """Map LiteLLM ModelResponse to our LLMResponse."""
        choice = response.choices[0]
        usage = response.usage or {}

        # Extract provider from model string "cerebras/llama-3.3-70b" -> "cerebras"
        model_str = response.model or ""
        provider = model_str.split("/")[0] if "/" in model_str else "unknown"

        # Build metadata with escalation info for observability
        metadata = {"finish_reason": choice.finish_reason}
        if escalated_from:
            metadata["escalated_from"] = escalated_from

        llm_response = LLMResponse(
            content=choice.message.content or "",
            model=model_str,
            provider=provider,
            tokens_used=(usage.prompt_tokens or 0) + (usage.completion_tokens or 0),
            input_tokens=usage.prompt_tokens or 0,
            output_tokens=usage.completion_tokens or 0,
            latency_ms=elapsed * 1000,
            raw_response=response,
            metadata=metadata,
            tool_calls=self._extract_tool_calls(choice.message),
        )

        task_record = {
            "provider": provider,
            "model": model_str,
            "tokens_used": llm_response.tokens_used,
            "latency_ms": llm_response.latency_ms,
            "escalated_from": escalated_from,  # Track escalation for monitoring
        }

        return llm_response, task_record

    def _extract_tool_calls(self, message) -> Optional[list[ToolCall]]:
        """Extract tool calls from response message if present."""
        if not hasattr(message, 'tool_calls') or not message.tool_calls:
            return None

        return [
            ToolCall(
                id=tc.id,
                name=tc.function.name,
                arguments=json.loads(tc.function.arguments)
            )
            for tc in message.tool_calls
        ]
```

#### 2c: Rate Tracking Callback (D9) + Escalation Metrics

```python
# src/scrappy/orchestrator/litellm_callbacks.py

from litellm.integrations.custom_logger import CustomLogger
from typing import Optional
from datetime import datetime
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class EscalationMetrics:
    """Track context window escalation events for monitoring."""
    total_escalations: int = 0
    escalations_by_source: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def record_escalation(self, from_tier: str, to_tier: str):
        """Record an escalation event."""
        self.total_escalations += 1
        self.escalations_by_source[f"{from_tier}->{to_tier}"] += 1

    def get_summary(self) -> dict:
        """Get escalation summary for monitoring/display."""
        return {
            "total_escalations": self.total_escalations,
            "by_path": dict(self.escalations_by_source),
        }


class RateTrackingCallback(CustomLogger):
    """
    LiteLLM callback for usage tracking and provider status.
    Implements D9 (usage tracking) and D10 (status display).

    Also tracks escalation metrics (context window fallbacks).
    """

    def __init__(
        self,
        rate_tracker: RateLimitTrackerProtocol,
        usage_reporter: Optional[UsageReporterProtocol] = None,
        status_tracker: Optional[ProviderStatusTracker] = None,
        escalation_metrics: Optional[EscalationMetrics] = None,
    ):
        self._rate_tracker = rate_tracker
        self._usage_reporter = usage_reporter
        self._status_tracker = status_tracker
        self._escalation_metrics = escalation_metrics or EscalationMetrics()

    @property
    def escalation_metrics(self) -> EscalationMetrics:
        """Access escalation metrics for monitoring."""
        return self._escalation_metrics

    def record_escalation(self, from_tier: str, to_tier: str):
        """
        Record a context window escalation event.
        Called by LiteLLMService when escalating fast->quality.
        """
        self._escalation_metrics.record_escalation(from_tier, to_tier)

    def log_success_event(self, kwargs, response_obj, start_time, end_time):
        """Called by LiteLLM after successful request."""
        # Extract actual provider/model (not group name)
        model_str = getattr(response_obj, 'model', '') or ''
        provider = model_str.split("/")[0] if "/" in model_str else "unknown"

        usage = getattr(response_obj, 'usage', None)
        input_tokens = getattr(usage, 'prompt_tokens', 0) if usage else 0
        output_tokens = getattr(usage, 'completion_tokens', 0) if usage else 0
        latency_ms = (end_time - start_time).total_seconds() * 1000

        # Record to rate tracker
        self._rate_tracker.record_request(
            provider=provider,
            model=model_str,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            success=True,
        )

        # Record to usage reporter
        if self._usage_reporter:
            self._usage_reporter.record(
                provider=provider,
                model=model_str,
                tokens_used=input_tokens + output_tokens,
                latency_ms=latency_ms,
            )

        # Update status tracker
        if self._status_tracker:
            self._status_tracker.on_success(provider, model_str, latency_ms)

    def log_failure_event(self, kwargs, response_obj, start_time, end_time):
        """Called by LiteLLM after failed request."""
        exception = kwargs.get('exception', None)
        provider = getattr(exception, 'llm_provider', 'unknown')
        model = kwargs.get('model', 'unknown')
        error_msg = str(exception) if exception else 'Unknown error'

        # Record failure
        self._rate_tracker.record_request(
            provider=provider,
            model=model,
            input_tokens=0,
            output_tokens=0,
            success=False,
            error_message=error_msg,
        )

        # Update status tracker
        if self._status_tracker:
            self._status_tracker.on_failure(provider, error_msg)
```

**LiteLLMService must notify callback on escalation:**

```python
# In LiteLLMService.__init__, accept callback reference:
def __init__(
    self,
    router: litellm.Router,
    output: OutputInterfaceProtocol,
    callback: Optional[RateTrackingCallback] = None,  # For escalation tracking
):
    self._router = router
    self._output = output
    self._callback = callback

# In completion() escalation block:
except ContextWindowExceededError as e:
    if model == "fast":
        self._output.warn("Context window exceeded on fast tier, retrying with quality tier...")
        # Track escalation for monitoring
        if self._callback:
            self._callback.record_escalation("fast", "quality")
        return await self.completion(
            "quality", messages,
            _escalation_depth=_escalation_depth + 1,
            _escalated_from="fast",
            **kwargs
        )
    raise
```

#### 2d: Router Configuration

```python
# src/scrappy/orchestrator/litellm_config.py

import litellm
from scrappy.infrastructure.config.api_keys import ApiKeyConfigService

def create_litellm_router(
    api_key_service: ApiKeyConfigService,
    callbacks: list | None = None,  # D4: Router-level callbacks
) -> litellm.Router:
    """
    Create LiteLLM Router with model groups.

    Model Groups:
    - "fast": 8B models, speed priority, any context OK
    - "quality": 70B+ models, quality priority, >= 32k context required

    Priority within groups determined by order (first = primary).
    """

    model_list = []

    # --- Fast Models (8B class, speed priority) ---
    # Priority: Groq (128k context) > Cerebras (8k context)

    if api_key_service.get_key("GROQ_API_KEY"):
        model_list.append({
            "model_name": "fast",
            "litellm_params": {
                "model": "groq/llama-3.1-8b-instant",
                "api_key": api_key_service.get_key("GROQ_API_KEY"),
            },
            "tpm": 20000,
            "rpm": 30,
        })

    if api_key_service.get_key("CEREBRAS_API_KEY"):
        model_list.append({
            "model_name": "fast",
            "litellm_params": {
                "model": "cerebras/llama3.1-8b",
                "api_key": api_key_service.get_key("CEREBRAS_API_KEY"),
            },
            "tpm": 60000,
            "rpm": 30,
        })

    # --- Quality Models (70B+ class, >= 32k context required) ---
    # Priority: Gemini (1M) > Groq 70B (32k) > Groq Kimi (128k)
    # NOTE: Cerebras 70B excluded - only 8k context, fails 32k requirement

    if api_key_service.get_key("GEMINI_API_KEY"):
        model_list.append({
            "model_name": "quality",
            "litellm_params": {
                "model": "gemini/gemini-2.5-flash",
                "api_key": api_key_service.get_key("GEMINI_API_KEY"),
            },
            "tpm": 250000,
            "rpm": 10,
        })

    if api_key_service.get_key("GROQ_API_KEY"):
        model_list.append({
            "model_name": "quality",
            "litellm_params": {
                "model": "groq/llama-3.3-70b-versatile",
                "api_key": api_key_service.get_key("GROQ_API_KEY"),
            },
            "tpm": 12000,
            "rpm": 30,
        })

        model_list.append({
            "model_name": "quality",
            "litellm_params": {
                "model": "groq/moonshotai/kimi-k2-instruct",
                "api_key": api_key_service.get_key("GROQ_API_KEY"),
            },
            "tpm": 20000,
            "rpm": 30,
        })

    if not model_list:
        raise ConfigurationError(
            "No API keys configured. Set at least one of: "
            "GROQ_API_KEY, CEREBRAS_API_KEY, GEMINI_API_KEY"
        )

    return litellm.Router(
        model_list=model_list,
        routing_strategy="simple-shuffle",  # D5: No Redis needed for MVP
        num_retries=3,
        timeout=60,
        retry_after=5,
        callbacks=callbacks,  # D4: Router-level callbacks for rate tracking
    )
```

#### 2d: Exception Mapping Reference

LiteLLM exceptions all have these attributes:
- `e.status_code` - HTTP status code
- `e.message` - Error message
- `e.llm_provider` - Provider that raised it ("cerebras", "groq", etc.)

| LiteLLM Exception | Status | Our Exception | Notes |
|-------------------|--------|---------------|-------|
| `RateLimitError` | 429 | `AllProvidersRateLimitedError` | After all retries exhausted |
| `Timeout` | 408 | (handled by LiteLLM) | `num_retries` handles this |
| `ServiceUnavailableError` | 503 | (handled by LiteLLM) | Triggers fallback |
| `ContextWindowExceededError` | 400 | Could use `context_window_fallback_dict` | Special handling available |
| `APIConnectionError` | 500 | Generic error | Base case for unmapped |

Helper: `litellm._should_retry(e.status_code)` returns whether to retry.

---

### Phase 3: Wire Into DelegationManager

**Goal:** Update DelegationManager to use LiteLLMService.

 The "Provider Name" Mapping Trap
 CRITICAL FIX: You cannot pass "groq" or "cerebras" to the Router if your Router config only defines model_name="fast" 
 and model_name="quality". The Router will look for a group named "groq" and fail.
Update DelegationManager.delegate:

```
model_group = provider_name  # or map from selection_type
# If the caller forces a specific provider (legacy behavior), you might lose the automatic fallback.
# Better to map legacy selection types to your new groups:
if request.selection_type == "quality":
    model_group = "quality"
else:
    # Default to fast for everything else ("fast", "auto", or explicit provider names if mapped)
    model_group = "fast"
```

#### 3a: Update DelegationManager

```python
# Changes to src/scrappy/orchestrator/delegation.py

class DelegationManager:
    def __init__(
        self,
        *,
        llm_service: LLMServiceProtocol,  # NEW - replaces retry_orchestrator
        cache: CacheProtocol,
        output: OutputInterfaceProtocol,
        prompt_augmenter: PromptAugmenterProtocol,
        batch_scheduler: BatchSchedulerProtocol,  # KEPT - refactored per D2
        context_aware: bool = False,
    ):
        self._llm_service = llm_service
        # ... rest unchanged

    def delegate(self, provider_name: str, prompt: str, ...) -> tuple[LLMResponse, dict]:
        # ... cache check, prompt augmentation unchanged ...

        # Build messages
        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': final_prompt})

        # Map provider_name to model group
        # TaskRouter already classifies as "fast" or "quality"
        model_group = provider_name  # or map from selection_type

        # Execute via LiteLLMService (retry/fallback handled internally)
        response, task_record = self._llm_service.completion_sync(
            model=model_group,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        # ... cache storage, record creation unchanged ...
```

#### 3b: Update Factory

```python
# Changes to src/scrappy/orchestrator/factory.py

from scrappy.infrastructure.config.api_keys import ApiKeyConfigService, create_api_key_service
from scrappy.orchestrator.litellm_config import create_litellm_router
from scrappy.orchestrator.litellm_service import LiteLLMService
from scrappy.orchestrator.litellm_callbacks import RateTrackingCallback

def create_delegation_manager(self, ...) -> DelegationManagerProtocol:
    api_key_service = create_api_key_service()

    # Build callback for rate tracking + escalation metrics (D4: router-level, not global)
    rate_callback = None
    if rate_tracker:
        rate_callback = RateTrackingCallback(
            rate_tracker=rate_tracker,
            usage_reporter=usage_reporter,  # Optional
            status_tracker=status_tracker,  # Optional
        )

    # Create LiteLLM Router with callbacks
    callbacks = [rate_callback] if rate_callback else []
    router = create_litellm_router(api_key_service, callbacks=callbacks)

    # Create LiteLLMService with callback reference for escalation tracking
    llm_service = LiteLLMService(
        router=router,
        output=output,
        callback=rate_callback,  # For escalation metrics
    )

    # Create DelegationManager with new service
    # NOTE: BatchScheduler kept but refactored to use llm_service (D2)
    return DelegationManager(
        llm_service=llm_service,
        cache=cache,
        output=output,
        prompt_augmenter=prompt_augmenter,
        context_aware=self.context_aware,
    )
```

#### 3c: Refactor BatchScheduler (D2)

BatchScheduler keeps its interface but delegates to LiteLLMService:

```python
# Changes to src/scrappy/orchestrator/batch_scheduler.py

class BatchScheduler:
    def __init__(
        self,
        *,
        llm_service: LLMServiceProtocol,  # CHANGED from retry_orchestrator
        output: OutputInterfaceProtocol,
    ):
        self._llm_service = llm_service
        self._output = output

    async def execute_batch(
        self,
        requests: list[LLMRequest],
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
    ) -> list[tuple[Any, dict]]:
        """Execute via LiteLLMService instead of RetryOrchestrator."""
        semaphore = asyncio.Semaphore(max_concurrent)

        async def execute_single(request: LLMRequest) -> tuple[Any, dict]:
            async with semaphore:
                try:
                    # Build messages from request
                    messages = []
                    if request.system_prompt:
                        messages.append({'role': 'system', 'content': request.system_prompt})
                    messages.append({'role': 'user', 'content': request.prompt})

                    # Delegate to LiteLLMService
                    return await self._llm_service.completion(
                        model=request.selection_type or "fast",  # Map to model group
                        messages=messages,
                        max_tokens=request.max_tokens,
                        temperature=request.temperature,
                    )
                except Exception as e:
                    self._output.print_error(f"Request failed: {e}")
                    return None, {"error": str(e)}

        results = await asyncio.gather(*[execute_single(req) for req in requests])
        return list(results)
```

#### 3d: Human Checkpoint

```
--- CHECKPOINT: HUMAN TEST ---
Manual verification that delegation works end-to-end:
1. Fast query routes to fast models
2. Quality query routes to quality models
3. Fallback works when primary rate limited
4. Rate tracking shows in /limits
5. Batch execution still works with concurrency control
```

#### 3e: OrchestratorAdapter Provider Mapping (D11)

**NOTE:** This is implemented in Phase 1d. See `AgentOrchestratorAdapter._resolve_model_group()`.

The mapping ensures legacy provider names ("groq", "cerebras", "gemini") are
translated to model groups ("fast", "quality") before reaching DelegationManager.

---

### Phase 4: Cleanup

**Delete dead code:**

- [ ] `src/scrappy/orchestrator/retry_orchestrator.py`
- [ ] `src/scrappy/orchestrator/registration.py`
- [ ] `src/scrappy/providers/cerebras_provider.py`
- [ ] `src/scrappy/providers/groq_provider.py`
- [ ] `src/scrappy/providers/gemini_provider.py`
- [ ] `src/scrappy/providers/cohere_provider.py`
- [ ] `src/scrappy/providers/github_models_provider.py`

**Keep:**
- `src/scrappy/providers/base.py` - for `LLMResponse`, `ModelType`, `ToolCall`, enums
- `src/scrappy/orchestrator/batch_scheduler.py` - Refactored to use LiteLLMService (see D2)

**Files requiring import updates:**

Based on grep for deleted module references:

| File | Update Required |
|------|-----------------|
| `src/scrappy/agent/core.py` | Remove RetryOrchestrator import, keep AllProvidersRateLimitedError |
| `src/scrappy/orchestrator/core.py` | Remove RetryOrchestrator, update to use LiteLLMService |
| `src/scrappy/orchestrator/delegation.py` | Remove RetryOrchestrator, inject LiteLLMService |
| `src/scrappy/orchestrator/factory.py` | Remove RetryOrchestrator creation, add LiteLLMService creation |
| `src/scrappy/orchestrator/protocols.py` | Remove RetryOrchestratorProtocol, add LLMServiceProtocol |
| `src/scrappy/orchestrator/provider_definitions.py` | Remove `provider_class` imports |
| `src/scrappy/orchestrator/provider_selector.py` | Reduce scope per Phase 1c (remove most methods) |
| `src/scrappy/task_router/provider_resolver.py` | Simplify per Phase 1b (direct group mapping) |
| `src/scrappy/orchestrator_adapter.py` | Add `_resolve_model_group()` per Phase 1d |
| `src/scrappy/providers/__init__.py` | Remove deleted provider exports |

**Test files requiring updates:**

| Test File | Update Required |
|-----------|-----------------|
| `tests/orchestrator/test_provider_selector.py` | Most tests obsolete, keep setup_brain test |
| `tests/orchestrator/test_retry_orchestrator.py` | DELETE - functionality moved to LiteLLM |
| `tests/task_router/test_provider_resolver.py` | Update to test direct group mapping |
| `tests/providers/test_*.py` | DELETE - provider classes deleted |

**Documentation requiring updates:**

| Doc File | Update Required |
|----------|-----------------|
| `docs/ORCHESTRATOR.md` | Update architecture diagram, remove RetryOrchestrator, add LiteLLMService |
| `docs/TASK_ROUTER.md` | Update provider resolution to show model groups ("fast"/"quality") |
| `docs/PROVIDERS.md` | Rewrite - no longer individual providers, now LiteLLM Router with model groups |

Key doc changes:
- Remove references to individual provider classes (GroqProvider, CerebrasProvider, etc.)
- Document model groups ("fast", "quality") instead of provider names
- Update delegation flow diagrams to show LiteLLMService
- Document escalation behavior (fast -> quality on context window exceeded)
- Update configuration section (API keys still needed, but routing is automatic)

**Success Criteria:**
- `orchestrator.delegate()` works end-to-end
- All tests pass
- No imports from deleted files remain
- `/limits` command shows usage data
- `grep -r "RetryOrchestrator" src/` returns no results
- `grep -r "cerebras_provider\|groq_provider\|gemini_provider" src/` returns no results

---

## Reference: Current Defaults

From existing code (for parity):
- `DEFAULT_MAX_RETRIES = 3`
- `base_delay = 0.5s, multiplier = 2.0x, max_delay = 60s`
- `DEFAULT_QUOTA_THRESHOLD = 100`

LiteLLM equivalents:
- `num_retries=3`
- `retry_after=5` (fixed delay, not exponential)
- Quota tracking via callbacks

### BEHAVIORAL CHANGE: Fixed Delay vs Exponential Backoff

**Current implementation:** Exponential backoff (0.5s, 1s, 2s, 4s...)
**LiteLLM:** Fixed 5s delay between retries

**Impact:**
- First retry: Current=0.5s, LiteLLM=5s (slower)
- Third retry: Current=2s, LiteLLM=5s (slower)
- Under heavy rate limiting: LiteLLM is more conservative

**Tradeoff accepted because:**
1. Free-tier providers have generous limits; rarely hit retries
2. Fixed delay is simpler and more predictable
3. LiteLLM handles the retry loop internally (less code to maintain)
4. Can tune `retry_after` param if needed

**Alternative (if exponential needed later):**
LiteLLM Router supports `allowed_fails` + `cooldown_time` per model for more
sophisticated rate limit handling. See LiteLLM docs for advanced configuration.

---

## Reference: Provider Model Info

For `model_registry.py` - extract from current providers:

**Cerebras** (all 8k context - fast tier only):
| Model | Context | Speed | Quality | RPD | TPM |
|-------|---------|-------|---------|-----|-----|
| llama3.1-8b | 8,192 | ULTRA_FAST | GOOD | 14,400 | 60,000 |
| llama-3.3-70b | 8,192 | VERY_FAST | EXCELLENT | 14,400 | 60,000 |
| qwen-3-32b | 8,192 | VERY_FAST | VERY_GOOD | 14,400 | 60,000 |

**Groq** (mixed context - both tiers):
| Model | Context | Speed | Quality | RPD | TPM |
|-------|---------|-------|---------|-----|-----|
| llama-3.1-8b-instant | 131,072 | VERY_FAST | GOOD | 7,000 | 20,000 |
| llama-3.3-70b-versatile | 32,768 | FAST | EXCELLENT | 1,000 | 12,000 |
| llama-3.1-70b-versatile | 32,768 | FAST | EXCELLENT | 1,000 | 12,000 |
| mixtral-8x7b-32768 | 32,768 | FAST | VERY_GOOD | 14,400 | 5,000 |
| kimi-k2-instruct | 131,072 | ULTRA_FAST | EXCELLENT | 7,000 | 20,000 |

**Gemini** (~1M context - quality tier):
| Model | Context | Speed | Quality | RPD | TPM |
|-------|---------|-------|---------|-----|-----|
| gemini-2.5-flash | ~1M | MODERATE | VERY_GOOD | 250 | 250,000 |
| gemini-2.5-flash-lite | ~1M | FAST | GOOD | 1,000 | 250,000 |
| gemini-2.0-flash | ~1M | FAST | GOOD | 200 | 1,000,000 |
