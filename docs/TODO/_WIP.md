# ModelSelectionService Implementation Plan

## Problem

LiteLLM Router's `simple-shuffle` strategy randomly distributes requests across all models in a group (e.g., "quality"). This causes:

1. **Inconsistent behavior** - different models mid-conversation
2. **Unpredictable debugging** - can't reproduce issues when model keeps changing
3. **No session stickiness** - user preference not respected

## Solution

Create `ModelSelectionService` that owns model selection logic, separate from Orchestrator.

## LLM Usage Paths (All Covered)

All LLM calls funnel through `Orchestrator.delegate()`, so fixing model selection there covers everything:

```
TaskRouter._classify_with_llm()  --+
TaskRouter strategies              |
  - ResearchExecutor               |
  - ConversationExecutor           +-->  Orchestrator.delegate()  -->  LiteLLMService
  - AgentExecutor                  |
Slash commands (/plan, /reason)    |
Agent loop                       --+
```

### Slash Commands

Slash commands are NOT a separate LLM path. `CommandRouter` is purely a dispatcher:

1. User types `/plan fix the bug`
2. `CommandRouter.route()` dispatches to `_handle_plan()`
3. Handler calls `task_executor.plan()` which uses the orchestrator

No direct LLM calls in command routing.

### TaskRouter

TaskRouter already passes `selection_type` to orchestrator (router.py:284-291):

```python
response = self.orchestrator.delegate(
    provider_name="fast",
    selection_type=ModelSelectionType.FAST  # Already passing this
)
```

Once Orchestrator uses ModelSelectionService, TaskRouter automatically benefits.

### ProviderResolver (task_router/provider_resolver.py)

Currently maps selection types to group names. After this change:
- **Keep it** for backward compatibility (returns group name)
- Orchestrator resolves group name OR specific model ID
- No changes needed in TaskRouter

## Current Flow (The Problem)

```
Orchestrator.delegate(selection_type=FAST)
    |
    v
provider_selector.get_model(FAST)
    |
    v
Returns group name "fast"
    |
    v
delegation_manager.delegate(provider_name="fast")
    |
    v
LiteLLMService.complete() with group "fast"
    |
    v
Router uses simple-shuffle --> RANDOM model pick (BAD)
```

## New Flow (The Fix)

```
Orchestrator.delegate(selection_type=FAST)
    |
    v
model_selector.select(FAST, session_preferred)
    |
    v
Returns specific model: "groq/llama-3.1-8b-instant"
    |
    v
delegation_manager.delegate(model="groq/llama-3.1-8b-instant")
    |
    v
LiteLLMService calls Router with exact model --> DETERMINISTIC (GOOD)
```

## Architecture

```
ModelSelectionService (new)
    - Injected: RateLimitTracker, model_config
    - select(selection_type, session_preferred) -> specific_model_id
    - Testable in isolation

Orchestrator
    - Injected: ModelSelectionService
    - Calls service.select() before delegation
    - Passes specific model_id down

DelegationManager
    - Receives specific model_id (not group name)
    - Passes through to LiteLLMService

LiteLLMService
    - Calls Router with specific model_id
    - Router handles retries on that model
```

## Implementation Steps

### 1. Define Protocol

File: `src/scrappy/orchestrator/model_selection.py`

```python
class ModelSelectionServiceProtocol(Protocol):
    """Protocol for model selection."""

    def select(
        self,
        selection_type: ModelSelectionType,
        session_preferred: Optional[str] = None,
    ) -> str:
        """
        Select specific model ID.

        Args:
            selection_type: FAST or QUALITY
            session_preferred: Previously selected model for this session

        Returns:
            Specific model ID (e.g., 'groq/llama-3.1-8b-instant')
        """
        ...

    def get_models_for_type(self, selection_type: ModelSelectionType) -> list[str]:
        """Get available models for selection type, ordered by priority."""
        ...
```

### 2. Implement Service

File: `src/scrappy/orchestrator/model_selection.py`

```python
class ModelSelectionService:
    """
    Selects specific model based on session preference and rate limits.

    Selection logic:
    1. If session_preferred is set and has headroom -> use it
    2. Otherwise, iterate priority list and pick first with headroom
    3. If all at limit, return highest priority anyway (let it fail)
    """

    def __init__(
        self,
        rate_tracker: RateLimitTrackerProtocol,
        model_priorities: dict[ModelSelectionType, list[str]],
        headroom_threshold: float = 0.1,  # 10% remaining = "at limit"
    ):
        self._tracker = rate_tracker
        self._priorities = model_priorities
        self._threshold = headroom_threshold

    def select(
        self,
        selection_type: ModelSelectionType,
        session_preferred: Optional[str] = None,
    ) -> str:
        models = self._priorities.get(selection_type, [])
        if not models:
            raise ValueError(f"No models configured for {selection_type}")

        # 1. Try session preferred if it has headroom
        if session_preferred and session_preferred in models:
            if self._has_headroom(session_preferred):
                return session_preferred

        # 2. Pick first model with headroom
        for model_id in models:
            if self._has_headroom(model_id):
                return model_id

        # 3. All at limit - return first (let it fail with proper error)
        return models[0]

    def _has_headroom(self, model_id: str) -> bool:
        """Check if model has sufficient rate limit headroom."""
        provider, model = self._parse_model_id(model_id)
        # Use tracker to check remaining quota
        # Return False if below threshold
        ...

    def _parse_model_id(self, model_id: str) -> tuple[str, str]:
        """Parse 'provider/model' into (provider, model)."""
        parts = model_id.split('/', 1)
        return (parts[0], parts[1]) if len(parts) == 2 else (parts[0], parts[0])
```

### 3. Define Model Priorities

File: `src/scrappy/orchestrator/litellm_config.py`

```python
# Priority order for each selection type
# First model is highest priority, tried first
MODEL_PRIORITIES: dict[ModelSelectionType, list[str]] = {
    ModelSelectionType.FAST: [
        "groq/llama-3.1-8b-instant",      # Fast, 128k context
        "cerebras/llama3.1-8b",            # Ultra-fast, 8k context
        "sambanova/Meta-Llama-3.1-8B-Instruct",  # Low RPD
    ],
    ModelSelectionType.QUALITY: [
        "cerebras/qwen-3-235b-a22b-instruct-2507",  # Best quality
        "groq/meta-llama/llama-4-scout-17b-16e-instruct",  # Fast, good
        "groq/moonshotai/kimi-k2-instruct",  # Fast, 128k
        "gemini/gemini-2.5-flash",          # Huge context, JSON issues
    ],
}

def get_model_priorities(api_key_service: ApiKeyConfigServiceProtocol) -> dict:
    """Get priorities filtered to only configured models."""
    # Filter MODEL_PRIORITIES to only include models with API keys
    ...
```

### 4. Add to Session

File: `src/scrappy/orchestrator/session.py`

```python
@dataclass
class SessionState:
    # ... existing fields ...
    preferred_model_id: Optional[str] = None  # Sticky model for session
```

### 5. Wire in Factory

File: `src/scrappy/orchestrator/factory.py`

```python
def create_model_selection_service(
    self,
    rate_tracker: RateLimitTrackerProtocol,
) -> ModelSelectionServiceProtocol:
    """Create model selection service."""
    priorities = get_model_priorities(create_api_key_service())
    return ModelSelectionService(
        rate_tracker=rate_tracker,
        model_priorities=priorities,
    )
```

### 6. Update Orchestrator

File: `src/scrappy/orchestrator/core.py`

```python
class AgentOrchestrator:
    def __init__(
        self,
        # ... existing params ...
        model_selector: Optional[ModelSelectionServiceProtocol] = None,
    ):
        # ... existing init ...
        self.model_selector = model_selector or components.model_selector

    def delegate(self, provider_name: str, prompt: str, ...):
        # Get selection type from provider_name
        selection_type = ModelSelectionType(provider_name)

        # Get session preferred model
        session_preferred = self.session_manager.get_preferred_model()

        # Select specific model
        model_id = self.model_selector.select(selection_type, session_preferred)

        # Update session preference (sticky)
        self.session_manager.set_preferred_model(model_id)

        # Delegate with specific model
        return self.delegation_manager.delegate(
            model=model_id,  # specific, not group
            prompt=prompt,
            ...
        )
```

### 7. Update DelegationManager

File: `src/scrappy/orchestrator/delegation.py`

- Change `_resolve_model_group(provider_name)` to just pass through model_id
- Or remove that function entirely since Orchestrator now provides specific model

### 8. Tests

File: `tests/orchestrator/test_model_selection.py`

```python
class TestModelSelectionService:
    def test_returns_session_preferred_when_has_headroom(self):
        tracker = MockRateLimitTracker(has_headroom=True)
        service = ModelSelectionService(tracker, MODEL_PRIORITIES)

        result = service.select(
            ModelSelectionType.QUALITY,
            session_preferred="groq/llama-4-scout"
        )

        assert result == "groq/llama-4-scout"

    def test_skips_session_preferred_when_no_headroom(self):
        tracker = MockRateLimitTracker(
            headroom_by_model={"groq/llama-4-scout": False, "cerebras/qwen": True}
        )
        service = ModelSelectionService(tracker, MODEL_PRIORITIES)

        result = service.select(
            ModelSelectionType.QUALITY,
            session_preferred="groq/llama-4-scout"
        )

        assert result == "cerebras/qwen"  # First with headroom

    def test_returns_first_priority_when_all_limited(self):
        tracker = MockRateLimitTracker(has_headroom=False)
        service = ModelSelectionService(tracker, MODEL_PRIORITIES)

        result = service.select(ModelSelectionType.QUALITY)

        assert result == MODEL_PRIORITIES[ModelSelectionType.QUALITY][0]
```

## Migration Notes

1. **Backward compatible** - existing code using group names still works until migrated
2. **Incremental** - can migrate Orchestrator first, then agent loop, etc.
3. **No breaking changes** - LiteLLMService already accepts specific model IDs

## Future Enhancements

1. **Proactive limit avoidance** - switch before hitting 429, not after
2. **Cost-aware selection** - prefer cheaper models when quality is similar
3. **Latency-aware selection** - track actual latencies, prefer faster
4. **Per-task model preference** - some tasks might prefer specific models
