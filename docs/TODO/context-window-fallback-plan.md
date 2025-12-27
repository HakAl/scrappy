# Context Window Fallback - Minimal Fix

**Bead**: scrappy-8za (plan) -> scrappy-j8h (implementation)
**Status**: Ready for implementation
**Priority**: P1

## Problem

Research streaming fails with `ContextWindowExceededError` (90K tokens vs 65K limit).
Router has no fallback configured, and model selection ignores context requirements.

## Root Cause

1. `context_window_fallbacks` not configured on Router
2. `ModelSelectionService.select()` ignores context requirements
3. Research doesn't specify context needs

## Fix (3 things)

### 1. Add context_window_fallbacks to Router (~5 min)

```python
# litellm_config.py - create_litellm_router()
return litellm.Router(
    model_list=[],
    routing_strategy="simple-shuffle",
    num_retries=3,
    timeout=60,
    retry_after=5,
    context_window_fallbacks=[  # NEW - safety net
        {"cerebras/qwen-3-235b-a22b-instruct-2507": ["groq/moonshotai/kimi-k2-instruct", "gemini/gemini-2.5-flash"]},
        {"groq/moonshotai/kimi-k2-instruct": ["gemini/gemini-2.5-flash"]},
    ],
)
```

### 2. Add min_context to ModelSelectionService.select() (~20 min)

```python
# model_selection.py
def select(
    self,
    selection_type: ModelSelectionType,
    min_context: int = 0,  # NEW
    session_preferred: Optional[str] = None,
) -> str:
    configured = self.get_models_for_type(selection_type)

    # NEW: Filter by context requirement
    if min_context > 0:
        from .litellm_config import MODEL_METADATA
        configured = [m for m in configured
                     if MODEL_METADATA.get(m, ModelMetadata(...)).context_length >= min_context]

        if not configured:
            raise AllModelsRateLimitedError(  # Reuse existing error
                f"No models with >= {min_context} context available"
            )

    # ... rest unchanged
```

### 3. Update ResearchLoop to estimate context (~10 min)

```python
# research_loop.py - run()
import litellm

# Before delegation, estimate token count
messages = [{"role": "system", "content": system_prompt},
            {"role": "user", "content": full_prompt}]
token_count = litellm.token_counter(model="gpt-4", messages=messages)

response = self.orchestrator.delegate(
    provider,
    full_prompt,
    system_prompt=system_prompt,
    min_context=token_count + 4000,  # Buffer for response
    ...
)
```

## What We're NOT Doing

- ~~New MODEL_CONTEXT mapping~~ - use existing MODEL_METADATA
- ~~Token counting utility module~~ - inline the litellm call
- ~~Migration path~~ - just fix it
- ~~Deprecations~~ - out of scope
- ~~NoSufficientContextModelError~~ - reuse existing error

## Tests

1. Unit: `ModelSelectionService.select()` with min_context filters correctly
2. Unit: Router has context_window_fallbacks configured
3. Integration: Research with large context doesn't fail

## Acceptance Criteria

- [ ] Research with 90K context succeeds (falls back to Gemini if needed)
- [ ] Router catches ContextWindowExceededError and retries with fallback
- [ ] All existing tests pass

## Future Improvements (separate beads)

- Token counting utility if multiple callers need it
- Context truncation strategy for edge cases
- Per-model tokenizer selection for accuracy
- Dynamic context re-evaluation in research loop iterations
