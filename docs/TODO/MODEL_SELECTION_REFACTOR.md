# Model Selection Refactor

## Problem

Two issues with model selection:

### 1. Policy Logic in Providers

`get_model_for_task()` is scattered across 5 providers:
- `cerebras_provider.py`
- `groq_provider.py`
- `gemini_provider.py`
- `cohere_provider.py`
- `github_models_provider.py`

Providers should expose capabilities, not make orchestration decisions.

### 2. String-Based Selection API

Selection types are passed as magic strings throughout the codebase:

```python
# Scattered string literals - no type safety
delegate_smart(task_type='planning')
select_for_task('fast')
resolver.resolve('quality')
get_recommended_provider('general')
```

These strings are mapped/validated in multiple places:
- `ProviderSelector.select_for_task()`
- `ProviderResolver.resolve()`
- `ProviderResolver._resolve_fast_hint()` / `_resolve_quality_hint()`
- `OrchestratorConfig.task_provider_priority`

## Current State

```python
# Provider (WRONG - orchestration logic in provider)
class CerebrasProvider:
    def get_model_for_task(self, task_type: str) -> str:
        if task_type == 'fast':
            return 'llama3.1-8b'  # Policy decision!
        return self.default_model

# String-based API (WRONG - no type safety)
class ProviderSelector:
    def select_for_task(self, task_type: str):  # Magic strings
        if task_type in ['fast', 'high_volume', 'general']:
            provider = self.registry.get('cerebras')
            model = provider.get_model_for_task(task_type)
            return ('cerebras', model)

# Duplicate mapping logic (WRONG - DRY violation)
class ProviderResolver:
    def resolve(self, hint: str):  # More magic strings
        if hint in ['fast', 'high_volume', 'general']:
            return self._resolve_fast_hint(available)
        elif hint == 'quality':
            return ('cerebras', 'llama-3.3-70b')  # Hardcoded!
```

## Target State

```python
# Enum for selection types - single source of truth
class ModelSelectionType(Enum):
    FAST = "fast"        # Quick responses, high throughput
    QUALITY = "quality"  # Best output quality
    INSTRUCT = "instruct"  # Instruction-tuned for JSON/structured output
    EMBED = "embed"      # Embeddings

# Provider (RIGHT - only capabilities)
class CerebrasProvider:
    @property
    def available_models(self) -> list[str]: ...
    def get_model_info(self, model_id: str) -> ModelInfo: ...
    # NO get_model_for_task()

# Orchestrator owns ALL selection logic via single method
class ProviderSelector:
    def get_model(self, selection_type: ModelSelectionType) -> tuple[str, str]:
        """Single entry point for all model selection."""
        ...

# All callers use enum directly
orchestrator.delegate_smart(ModelSelectionType.INSTRUCT)
selector.get_model(ModelSelectionType.FAST)
resolver.resolve(ModelSelectionType.QUALITY)
```

---

## Implementation Plan

### Step 1: Create ModelSelectionType Enum

**File**: `src/orchestrator/model_selection.py` (new file)

```python
from enum import Enum


class ModelSelectionType(Enum):
    """Types of model selection strategies."""
    FAST = "fast"        # Quick responses, high throughput
    QUALITY = "quality"  # Best output quality
    INSTRUCT = "instruct"  # Instruction-tuned for JSON/structured output
    EMBED = "embed"      # Embeddings
```

---

### Step 2: Add get_model() to ProviderSelector

**File**: `src/orchestrator/provider_selector.py`

Add single entry point for model selection:

```python
from .model_selection import ModelSelectionType

def get_model(self, selection_type: ModelSelectionType) -> tuple[str, str]:
    """
    Select provider and model based on selection type.

    Args:
        selection_type: What kind of model is needed

    Returns:
        Tuple of (provider_name, model_id)

    Raises:
        RuntimeError: If no providers available
    """
    self._log(f"Selecting model for: {selection_type.value}")
    available = self.registry.list_available()

    if not available:
        self._log("No providers available!", "ERROR")
        raise RuntimeError("No providers available!")

    self._log(f"Available providers: {', '.join(available)}")

    if selection_type == ModelSelectionType.FAST:
        return self._select_by_speed(available)
    elif selection_type == ModelSelectionType.QUALITY:
        return self._select_by_quality(available)
    elif selection_type == ModelSelectionType.INSTRUCT:
        return self._select_by_instruct(available)
    elif selection_type == ModelSelectionType.EMBED:
        return self._select_for_embed(available)

    # Fallback
    self._log(f"Unknown selection type, using first available", "WARN")
    return (available[0], None)

def _select_by_speed(self, available: list[str]) -> tuple[str, str]:
    """Select fastest model with good quota."""
    candidates = []
    for provider_name in available:
        provider = self.registry.get(provider_name)
        for model_id in provider.available_models:
            info = provider.get_model_info(model_id)
            candidates.append((provider_name, model_id, info))

    speed_rank = {'ultra_fast': 0, 'very_fast': 1, 'fast': 2, 'moderate': 3, 'slow': 4}
    candidates.sort(key=lambda x: (speed_rank.get(x[2].speed, 5), -(x[2].rpd or 0)))

    if candidates:
        best = candidates[0]
        self._log(f"Selected {best[0]}/{best[1]} (speed: {best[2].speed})", "SELECTED")
        return (best[0], best[1])

    self._log(f"No candidates, using {available[0]}", "WARN")
    return (available[0], None)

def _select_by_quality(self, available: list[str]) -> tuple[str, str]:
    """Select highest quality model."""
    candidates = []
    for provider_name in available:
        provider = self.registry.get(provider_name)
        for model_id in provider.available_models:
            info = provider.get_model_info(model_id)
            candidates.append((provider_name, model_id, info))

    quality_rank = {'excellent': 0, 'very_good': 1, 'good': 2, 'moderate': 3}
    candidates.sort(key=lambda x: (quality_rank.get(x[2].quality, 4), -(x[2].rpd or 0)))

    if candidates:
        best = candidates[0]
        self._log(f"Selected {best[0]}/{best[1]} (quality: {best[2].quality})", "SELECTED")
        return (best[0], best[1])

    self._log(f"No candidates, using {available[0]}", "WARN")
    return (available[0], None)

def _select_by_instruct(self, available: list[str]) -> tuple[str, str]:
    """Select best instruction-tuned model."""
    candidates = []
    for provider_name in available:
        provider = self.registry.get(provider_name)
        for model_id in provider.available_models:
            info = provider.get_model_info(model_id)
            if info.is_instruction_tuned:
                candidates.append((provider_name, model_id, info))

    # Sort by RPD (prefer high quota)
    candidates.sort(key=lambda x: -(x[2].rpd or 0))

    if candidates:
        best = candidates[0]
        self._log(f"Selected {best[0]}/{best[1]} (instruct, {best[2].rpd} RPD)", "SELECTED")
        return (best[0], best[1])

    # Fallback to quality if no instruct models
    self._log("No instruction-tuned models, falling back to quality", "WARN")
    return self._select_by_quality(available)

def _select_for_embed(self, available: list[str]) -> tuple[str, str]:
    """Select embedding model."""
    if 'cohere' in available:
        self._log("Selected cohere for embeddings", "SELECTED")
        return ('cohere', None)

    self._log(f"No embedding provider, using {available[0]}", "WARN")
    return (available[0], None)
```

**Tests**: `tests/orchestrator/test_provider_selector.py`

```python
from src.orchestrator.model_selection import ModelSelectionType


def test_get_model_fast_prefers_speed():
    """FAST selection prioritizes speed over quality."""
    registry = create_mock_registry_with_models([
        ('cerebras', 'llama3.1-8b', {'speed': 'ultra_fast', 'quality': 'good'}),
        ('cerebras', 'llama-3.3-70b', {'speed': 'fast', 'quality': 'excellent'}),
    ])
    selector = ProviderSelector(registry)

    provider, model = selector.get_model(ModelSelectionType.FAST)

    assert model == 'llama3.1-8b'


def test_get_model_quality_prefers_quality():
    """QUALITY selection prioritizes quality over speed."""
    registry = create_mock_registry_with_models([
        ('cerebras', 'llama3.1-8b', {'speed': 'ultra_fast', 'quality': 'good'}),
        ('cerebras', 'llama-3.3-70b', {'speed': 'fast', 'quality': 'excellent'}),
    ])
    selector = ProviderSelector(registry)

    provider, model = selector.get_model(ModelSelectionType.QUALITY)

    assert model == 'llama-3.3-70b'


def test_get_model_instruct_filters_instruction_tuned():
    """INSTRUCT selection only considers instruction-tuned models."""
    registry = create_mock_registry_with_models([
        ('cerebras', 'llama3.1-8b', {'speed': 'ultra_fast', 'model_type': ModelType.CHAT}),
        ('cerebras', 'qwen-instruct', {'speed': 'fast', 'model_type': ModelType.INSTRUCT}),
    ])
    selector = ProviderSelector(registry)

    provider, model = selector.get_model(ModelSelectionType.INSTRUCT)

    assert model == 'qwen-instruct'


def test_get_model_instruct_falls_back_to_quality():
    """INSTRUCT falls back to QUALITY when no instruct models available."""
    registry = create_mock_registry_with_models([
        ('cerebras', 'llama3.1-8b', {'quality': 'good', 'model_type': ModelType.CHAT}),
        ('cerebras', 'llama-3.3-70b', {'quality': 'excellent', 'model_type': ModelType.CHAT}),
    ])
    selector = ProviderSelector(registry)

    provider, model = selector.get_model(ModelSelectionType.INSTRUCT)

    assert model == 'llama-3.3-70b'  # Best quality


def test_get_model_embed_prefers_cohere():
    """EMBED selection prefers cohere when available."""
    registry = create_mock_registry(['cerebras', 'cohere'])
    selector = ProviderSelector(registry)

    provider, model = selector.get_model(ModelSelectionType.EMBED)

    assert provider == 'cohere'


def test_get_model_raises_when_no_providers():
    """Raises RuntimeError when no providers available."""
    registry = create_mock_registry([])
    selector = ProviderSelector(registry)

    with pytest.raises(RuntimeError, match="No providers available"):
        selector.get_model(ModelSelectionType.FAST)
```

---

### Step 3: Remove select_for_task()

**File**: `src/orchestrator/provider_selector.py`

Delete the entire `select_for_task()` method (lines 69-135). All callers will use `get_model()` directly.

---

### Step 4: Update Orchestrator Core

**File**: `src/orchestrator/core.py`

Update `delegate_smart()` and `get_recommended_provider()`:

```python
from .model_selection import ModelSelectionType

def delegate_smart(
    self,
    prompt: str,
    selection_type: ModelSelectionType = ModelSelectionType.FAST,
    **kwargs
) -> LLMResponse:
    """
    Delegate with automatic provider/model selection.

    Args:
        prompt: The prompt to send
        selection_type: What kind of model to use
        **kwargs: Additional arguments for delegate()

    Returns:
        LLMResponse from selected provider
    """
    provider_name, model = self.provider_selector.get_model(selection_type)
    return self.delegate(provider_name, prompt, model=model, **kwargs)


def get_recommended_provider(
    self,
    selection_type: ModelSelectionType = ModelSelectionType.FAST
) -> Optional[str]:
    """
    Get recommended provider for a selection type.

    Args:
        selection_type: What kind of model is needed

    Returns:
        Provider name or None
    """
    try:
        provider_name, _ = self.provider_selector.get_model(selection_type)
        return provider_name
    except RuntimeError:
        return None
```

---

### Step 5: Update OrchestratorAdapter

**File**: `src/orchestrator_adapter.py`

Update signature to use enum:

```python
from src.orchestrator.model_selection import ModelSelectionType

def delegate_smart(
    self,
    prompt: str,
    selection_type: ModelSelectionType = ModelSelectionType.FAST,
    **kwargs
) -> LLMResponse:
    return self._orch.delegate_smart(prompt, selection_type=selection_type, **kwargs)
```

---

### Step 6: Simplify ProviderResolver

**File**: `src/task_router/provider_resolver.py`

Replace entire file with thin wrapper:

```python
"""
Provider hint resolution utility.

Resolves ModelSelectionType to actual provider names and models.
"""

from typing import Optional, Tuple

from ..orchestrator.model_selection import ModelSelectionType


class ProviderResolver:
    """
    Resolves selection types to provider/model tuples.

    Thin wrapper around ProviderSelector for TaskRouter integration.
    """

    def __init__(self, orchestrator=None):
        """
        Initialize provider resolver.

        Args:
            orchestrator: Orchestrator instance with provider_selector
        """
        self.orchestrator = orchestrator

    def resolve(
        self,
        selection_type: Optional[ModelSelectionType]
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Resolve selection type to provider and model.

        Args:
            selection_type: What kind of model is needed

        Returns:
            Tuple of (provider_name, model_name) or (None, None)
        """
        if selection_type is None or self.orchestrator is None:
            return (None, None)

        try:
            return self.orchestrator.provider_selector.get_model(selection_type)
        except (AttributeError, RuntimeError):
            return (None, None)
```

Delete all the following methods:
- `_try_provider_selector()`
- `_resolve_with_simple_mapping()`
- `_get_available_providers()`
- `_resolve_fast_hint()`
- `_resolve_quality_hint()`

Remove `use_provider_selector` parameter.

---

### Step 7: Update TaskRouter

**File**: `src/task_router/router.py`

Update to use enum:

```python
from ..orchestrator.model_selection import ModelSelectionType

# Update any hint parameters to use ModelSelectionType
def _resolve_provider_hint(
    self,
    selection_type: Optional[ModelSelectionType]
) -> Tuple[Optional[str], Optional[str]]:
    return self.provider_resolver.resolve(selection_type)
```

Update callers within TaskRouter to pass `ModelSelectionType` values.

---

### Step 8: Update Agent Code

**File**: `src/agent/agent_loop.py`

```python
from ..orchestrator.model_selection import ModelSelectionType

# Change:
#   task_type='planning'
# To:
#   selection_type=ModelSelectionType.INSTRUCT
```

**File**: `src/agent/provider_strategy.py`

```python
from ..orchestrator.model_selection import ModelSelectionType

# Change:
#   get_recommended_provider('planning')
# To:
#   get_recommended_provider(ModelSelectionType.INSTRUCT)
```

---

### Step 9: Update Task Executor

**File**: `src/orchestrator/task_executor.py`

Update string literals to enum:

```python
from .model_selection import ModelSelectionType

# Change:
#   'provider_type': 'fast'
#   'provider_type': 'quality'
#   'task_type': 'planning'
# To:
#   'selection_type': ModelSelectionType.FAST
#   'selection_type': ModelSelectionType.QUALITY
#   'selection_type': ModelSelectionType.INSTRUCT
```

---

### Step 10: Update OrchestratorConfig

**File**: `src/orchestrator/config.py`

Update `task_provider_priority` to use enum keys:

```python
from .model_selection import ModelSelectionType

# Change:
#   'planning': ['cerebras', 'groq', 'gemini'],
#   'general': ['cerebras', 'groq', 'gemini'],
# To:
#   ModelSelectionType.INSTRUCT: ['cerebras', 'groq', 'gemini'],
#   ModelSelectionType.FAST: ['cerebras', 'groq', 'gemini'],
```

---

### Step 11: Remove get_model_for_task from All Providers

**Files**:
- `src/providers/cerebras_provider.py` - Delete `get_model_for_task()` method
- `src/providers/groq_provider.py` - Delete `get_model_for_task()` method
- `src/providers/gemini_provider.py` - Delete `get_model_for_task()` method
- `src/providers/cohere_provider.py` - Delete `get_model_for_task()` method
- `src/providers/github_models_provider.py` - Delete `get_model_for_task()` method

Each provider loses ~15 lines. No replacement needed.

---

### Step 12: Update Tests

**Files to update**:
- `tests/providers/test_cerebras_provider.py` - Remove `get_model_for_task` tests
- `tests/providers/test_groq_provider.py` - Remove `get_model_for_task` tests
- `tests/providers/test_gemini_provider.py` - Remove `get_model_for_task` tests
- `tests/providers/test_cohere_provider.py` - Remove `get_model_for_task` tests
- `tests/providers/test_github_models_provider.py` - Remove `get_model_for_task` tests
- `tests/providers/test_provider_resolver.py` - Update to use enum, remove string tests
- `tests/task_router/test_task_router_dependency_injection.py` - Update mock signatures
- `tests/orchestrator/test_provider_selector.py` - Remove `select_for_task` tests, add `get_model` tests

---

### Step 13: Clean Up Documentation

**File**: `docs/TODO/NO_OUTPUT.md`

Update line 84 reference to old pattern.

---

### Step 14: Final Verification

```bash
# Run all tests
python -m pytest tests/ -v

# Verify no remaining string-based selection
grep -r "select_for_task" src/
# Should return nothing

grep -r "get_model_for_task" src/
# Should return nothing

grep -r "'fast'\|'quality'\|'planning'\|'high_volume'\|'general'" src/orchestrator/ src/task_router/ src/agent/
# Should only return model attribute strings (speed/quality metadata), not selection types
```

---

## Checklist

### Step 1: Create Enum
- [ ] Create `src/orchestrator/model_selection.py`
- [ ] Define `ModelSelectionType` enum with FAST, QUALITY, INSTRUCT, EMBED

### Step 2: Add get_model()
- [ ] Add `get_model(ModelSelectionType)` to ProviderSelector
- [ ] Add `_select_by_speed()`
- [ ] Add `_select_by_quality()`
- [ ] Add `_select_by_instruct()`
- [ ] Add `_select_for_embed()`
- [ ] Add tests for each selection type
- [ ] Add test for fallback behavior
- [ ] Add test for no providers error

### Step 3: Remove select_for_task
- [ ] Delete `select_for_task()` from ProviderSelector

### Step 4: Update Orchestrator Core
- [ ] Update `delegate_smart()` signature to use enum
- [ ] Update `get_recommended_provider()` signature to use enum

### Step 5: Update OrchestratorAdapter
- [ ] Update `delegate_smart()` signature to use enum

### Step 6: Simplify ProviderResolver
- [ ] Replace `resolve(str)` with `resolve(ModelSelectionType)`
- [ ] Delete `_try_provider_selector()`
- [ ] Delete `_resolve_with_simple_mapping()`
- [ ] Delete `_get_available_providers()`
- [ ] Delete `_resolve_fast_hint()`
- [ ] Delete `_resolve_quality_hint()`
- [ ] Remove `use_provider_selector` parameter

### Step 7: Update TaskRouter
- [ ] Update hint parameters to use enum

### Step 8: Update Agent Code
- [ ] Update `agent_loop.py` to use enum
- [ ] Update `provider_strategy.py` to use enum

### Step 9: Update Task Executor
- [ ] Replace string literals with enum values

### Step 10: Update OrchestratorConfig
- [ ] Update `task_provider_priority` keys to use enum

### Step 11: Remove get_model_for_task from Providers
- [ ] Remove from `cerebras_provider.py`
- [ ] Remove from `groq_provider.py`
- [ ] Remove from `gemini_provider.py`
- [ ] Remove from `cohere_provider.py`
- [ ] Remove from `github_models_provider.py`

### Step 12: Update Tests
- [ ] Remove `get_model_for_task` tests from provider tests
- [ ] Update `test_provider_resolver.py` to use enum
- [ ] Update `test_task_router_dependency_injection.py`
- [ ] Update/add `test_provider_selector.py` for `get_model()`

### Step 13: Clean Up Documentation
- [ ] Update `docs/TODO/NO_OUTPUT.md`

### Step 14: Final Verification
- [ ] All tests pass
- [ ] `grep -r "select_for_task" src/` returns nothing
- [ ] `grep -r "get_model_for_task" src/` returns nothing
- [ ] No string-based selection types in orchestrator/task_router/agent code
