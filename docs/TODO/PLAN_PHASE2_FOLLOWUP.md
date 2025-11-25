# Phase 2 Follow-up Issues

## Status: Identified during Phase 2 implementation

These issues were discovered while implementing the clarification config changes in Phase 2.

---

## 1. Import Path Inconsistency

**Location:** `src/task_router/router.py`

**Problem:** Mixed absolute and relative imports in the same file:

```python
# Absolute import (inconsistent)
from src.config.schema import ClarificationConfig

# Relative imports (standard for this file)
from .protocols import ClarificationConfigProtocol, DefaultConsoleInput, ...
```

**Risk:** Could cause import errors if package is installed or run from different contexts.

**Fix:** Standardize on relative imports or ensure `src.config` is always in the Python path.

---

## 2. Config Loading Not Implemented

**Problem:** `ClarificationConfig` values are not loaded from `.scrappy.yaml` / `.scrappy.json` files. The config infrastructure exists but there's no loader that:

1. Reads the `clarification` section from config files
2. Constructs a `ClarificationConfig` instance
3. Passes it to `TaskRouter`

**Current behavior:** Always uses defaults (0.7 / 0.9 thresholds).

**Fix:** Implement config loading in the application bootstrap/entry point that:

```python
# Pseudocode
config_data = load_config_file()  # existing loader
clarification_config = ClarificationConfig(
    confidence_threshold=config_data.get('clarification', {}).get('confidence_threshold', 0.7),
    high_confidence_bypass=config_data.get('clarification', {}).get('high_confidence_bypass', 0.9),
)
router = TaskRouter(..., clarification_config=clarification_config)
```

---

## 3. Default Threshold Changed (Breaking Change)

**Problem:** Confidence threshold default changed from 0.65 to 0.7.

| Location | Old Value | New Value |
|----------|-----------|-----------|
| `TaskRouter.__init__` | 0.65 | 0.7 (via ClarificationConfig) |

**Impact:** Tasks with confidence between 0.65-0.69 that previously triggered clarification will now skip it.

**Options:**
1. Accept the change (aligns with plan document)
2. Change `ClarificationConfig` default to 0.65 for backwards compatibility

---

## 4. Missing `__init__.py` Export

**Location:** `src/config/__init__.py`

**Problem:** `ClarificationConfig` not exported from config module.

**Fix:**
```python
# In src/config/__init__.py
from .schema import ClarificationConfig

__all__ = [
    # ... existing exports ...
    'ClarificationConfig',
]
```

---

## 5. Protocol vs ABC Duplication

**Problem:** Two abstractions for intent clarification exist:

| File | Name | Type |
|------|------|------|
| `protocols.py` | `IntentClarifierProtocol` | Protocol (structural typing) |
| `intent_clarifier.py` | `IntentClarifierInterface` | ABC (nominal typing) |

**Impact:** Confusing for developers, unclear which to use for type hints.

**Fix:** Consolidate to single Protocol-based approach (per CLAUDE.md guidelines):
1. Keep `IntentClarifierProtocol` in `protocols.py`
2. Have concrete classes implement the protocol (no ABC inheritance needed)
3. Deprecate/remove `IntentClarifierInterface`

---

## Priority

| Issue | Severity | Effort |
|-------|----------|--------|
| Config Loading Not Implemented | High | Medium |
| Import Path Inconsistency | Medium | Low |
| Missing `__init__.py` Export | Low | Trivial |
| Default Threshold Changed | Low | Trivial |
| Protocol vs ABC Duplication | Low | Medium |
