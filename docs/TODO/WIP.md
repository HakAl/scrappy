# Code Cleanup - Work In Progress


## Status

---

Completed: Items 13-16

Item 13 - Standardize Parameter Names in orchestrator_adapter.py
Item 14 - Replace OperationalOutputProtocol with BaseOutputProtocol
Item 15 - Remove styled_echo() backward compatibility method
Item 16 - Remove string-to-enum conversion in providers/base.py

### Item 13 - Standardize Parameter Names in orchestrator_adapter.py

  Changed in src/orchestrator_adapter.py:
  - Renamed 'provider' parameter to 'provider_name' in delegate() method
  - Removed duplicate 'provider_name' alias parameter
  - Renamed 'provider' parameter to 'provider_name' in delegate_with_tools() method
  - Removed duplicate 'provider_name' alias parameter
  - Removed compatibility code that merged both parameter values
  - Updated all internal references from 'actual_provider' to 'provider_name'

  Test Results: 4,076 tests PASSED
  Impact: Removed approximately 15 lines of dual-parameter compatibility code.

### Item 14 - Replace OperationalOutputProtocol with BaseOutputProtocol

  Changed across entire codebase:
  - Removed alias definitions in src/protocols/output.py and src/orchestrator/protocols.py
  - Updated all imports to use BaseOutputProtocol directly
  - Updated 10+ source files in src/orchestrator/
  - Updated test files to remove OperationalOutputProtocol references
  - Removed test class TestOperationalOutputProtocolConformance (alias no longer exists)

  Test Results: 359 output-related tests PASSED
  Impact: Removed 2 alias definitions and ~30 references, standardized on BaseOutputProtocol.

### Item 15 - Remove styled_echo() backward compatibility method

  Changed across protocol and implementations:
  - Removed styled_echo() from CLIIOProtocol in src/protocols/io.py
  - Removed method from src/cli/io_interface.py (TestIO)
  - Removed method from src/cli/unified_io.py (UnifiedIO)
  - Removed method from src/cli/output.py (TestOutput)
  - Removed method from test helpers in tests/helpers.py (2 instances)
  - Updated test usages to call secho() instead
  - Removed tests for styled_echo() method itself

  Test Results: 77 CLI IO tests PASSED
  Impact: Removed ~40 lines of backward compatibility code.

### Item 16 - Remove string-to-enum conversion in providers/base.py

  Changed in src/providers/base.py:
  - Removed string-to-enum conversion for QualityRank (lines 137-144)
  - Removed string-to-enum conversion for SpeedRank (lines 148-155)
  - Simplified from_config() method to directly use enum values
  - All provider MODELS dictionaries already use enum values (verified)

  Test Results: 176 provider tests PASSED
  Impact: Removed ~20 lines of unnecessary conversion code.

---

This document tracks backward compatibility, legacy, bridge, fallback, and dead code that can be removed given the project's prerelease status.

**Project Status:** PRERELEASE - No external users, no backward compatibility needed.

---

## Summary

| Category | Files | Lines | Priority |
|----------|-------|-------|----------|
| Shim files to delete | 4 | ~200 | HIGH |
| Wrapper methods in agent/core.py | 1 | ~180 | HIGH |
| Legacy constants | 1 | ~20 | HIGH |
| Deprecated parameters | 5+ | ~100 | MEDIUM |
| Dead/commented code | 10+ | ~50 | HIGH |

**Total estimated removable code:** 500-600 lines

---

## HIGH PRIORITY - Delete Entire Files

### 1. `src/orchestrator.py` (~65 lines)
**Type:** Pure backward compatibility shim

Lines 1-29 contain deprecation notice explaining code is kept for backward compatibility. Lines 32-54 have try/except fallback imports with duplicate code paths.

**Action:** Delete entire file, update imports to use `orchestrator.core` or `orchestrator` package directly.

---

### 2. `src/agent.py` (~39 lines)
**Type:** Pure backward compatibility shim

Lines 1-10 contain deprecation notice: "This module re-exports from the agent package for backward compatibility". Lines 13-27 re-export all agent components.

**Action:** Delete entire file, update imports to use `from agent.core import CodeAgent`.

---

### 3. `src/cli.py` (~37 lines)
**Type:** Pure backward compatibility shim

Lines 1-7 contain deprecation notice: "This module re-exports from the modular CLI package for backward compatibility". Lines 10-21 re-export CLI components.

**Action:** Delete entire file.

---

### 4. `src/orchestrator/rate_limiter.py` (~21 lines)
**Type:** Legacy compatibility shim

Entire file is a "Legacy compatibility shim for RateLimitTracker" that imports and re-exports from `rate_limiting` module.

**Action:** Delete entire file, update imports to use `orchestrator.rate_limiting` directly.

---

## HIGH PRIORITY - Delete Method Sections

### 5. `src/agent/core.py` - Backward Compatibility Wrappers

**Lines 522-601 (~80 lines):** Section titled "Backward Compatibility Wrappers"

Methods that just delegate to other components:
- `_show_thinking()` (line 524) - delegates to UI
- `_show_tool_request()` (line 528) - delegates to UI
- `_show_command()` (line 532) - delegates to UI
- `_show_error()` (line 536) - delegates to UI
- `_show_result()` (line 540) - delegates to UI
- `_show_warning()` (line 544) - delegates to UI
- `_show_progress()` (line 548) - delegates to UI
- `_show_provider_status()` (line 552) - delegates to UI
- `_show_rule()` (line 556) - delegates to UI
- `_check_retry_pattern()` (line 560) - delegates to command executor
- `_check_duplicate_action()` (line 568) - delegates to DuplicateDetector
- `_get_user_confirmation()` (line 577) - delegates to SafetyChecker

**Action:** Delete entire section.

---

### 6. `src/agent/core.py` - Decoupled Agent Loop Methods

**Lines 603-701 (~100 lines):** Section titled "Decoupled Agent Loop Methods (Backward Compatibility)"

Methods that delegate to AgentLoop:
- `_think()` (line 606) - delegates to AgentLoop
- `_plan_action()` (line 624) - delegates to AgentLoop
- `_execute()` (line 639) - delegates to AgentLoop
- `_evaluate()` (line 671) - delegates to AgentLoop
- `_update_conversation()` (line 693) - delegates to AgentLoop

**Action:** Delete entire section. Update any tests that call these methods directly.

---

## HIGH PRIORITY - Delete Legacy Constants

### 7. `src/orchestrator/config.py` - Legacy Constants Section

**Lines 123-142 (~20 lines):** Entire section marked as deprecated

```python
# Legacy constants for backward compatibility
# DEPRECATED: Use OrchestratorConfig instance instead
# These will be removed in a future version

PROVIDER_PRIORITY = _default_config.provider_priority
BRAIN_PRIORITY = _default_config.brain_priority
FALLBACK_PRIORITY = _default_config.fallback_priority
TASK_PREFERENCES = _default_config.task_preferences
PROVIDER_INFO = { ... }
```

**Action:** Delete lines 123-142. Search for imports of `PROVIDER_PRIORITY`, `BRAIN_PRIORITY`, etc. and update to use `OrchestratorConfig`.

---


### 9. `src/agent_tools/tools/command_tool.py`

**Line 29:** Comment about removed code
```python
# Removed safe_print() - output should go through injected IO protocol, not print()
```

**Action:** Delete comment (code is already removed, no need for tombstone).

---

### 10. `src/providers/groq_provider.py`

**Line 56:** Comment about removed model
```python
# gemma2-9b-it removed - decommissioned by Groq as of 2025-11
```

**Action:** Delete comment.

---

## MEDIUM PRIORITY - Deprecated Parameters

### 11. `src/context/codebase_context.py`

**Lines 80-81:** Deprecated parameter documentation
```python
auto_load_cache: If True, automatically load cache in constructor (for backwards compatibility)
semantic_initializer: Background initializer for semantic search (deprecated, use semantic_manager)
```

**Lines 142-144:** Backward compatibility fields
```python
self._semantic_search = None  # Cached for backward compatibility
self._semantic_initializer = semantic_initializer  # Backward compatibility
```

**Lines 151-153:** Auto-load cache logic
```python
if auto_load_cache:
    self._load_cache()
```

**Lines 312-313:** Callback bridge
```python
# Set up callback bridge for backward compatibility
```

**Action:** Remove `auto_load_cache` and `semantic_initializer` parameters. Update callers to use `semantic_manager`.

---

### 12. `src/task_router/intent_clarifier.py`

**Lines 31-49:** Legacy parameters
```python
input_fn: Optional[Callable[[str], str]] = None,
output_fn: Optional[Callable[[str], None]] = None,
```

**Lines 110-141:** `LegacyIOInputAdapter` class (entire class exists for legacy support)

**Action:** Remove legacy `input_fn`/`output_fn` parameters and `LegacyIOInputAdapter` class. All callers should use `io` parameter.

---

### 13. `src/orchestrator_adapter.py`

**Lines 105-177:** Legacy parameter support
```python
# Support both 'provider' and 'provider_name' for compatibility
```

**Action:** Pick one parameter name (`provider_name`) and remove the other.

---

## MEDIUM PRIORITY - Protocol Aliases

### 14. `src/protocols/output.py`

**Lines 216-218:** Alias definition
```python
# Backward compatibility alias
OperationalOutputProtocol = BaseOutputProtocol
```

**Action:** Search for `OperationalOutputProtocol` usage. If none, delete alias.

---

### 15. `src/protocols/io.py` and `src/cli/io_interface.py`

**Lines 67-68 (io.py), Line 96 (io_interface.py):** Backward compat method
```python
def styled_echo(self, message: str, fg: Optional[str] = None, bold: bool = False, nl: bool = True) -> None:
    """Alias for secho() for backwards compatibility."""
```

**Action:** Search for `styled_echo` callers. If none, delete method.

---

## MEDIUM PRIORITY - Type Conversion

### 16. `src/providers/base.py`

**Lines 138-154:** String-to-enum conversion
```python
# Convert string to enum for backward compatibility
try:
    quality = QualityRank(quality_val)
except ValueError:
    quality = QualityRank.GOOD
```

**Action:** Enforce strict enum typing. Remove string conversion try/except.

---

## LOW PRIORITY - Keep or Verify

### Items to Keep

1. **`src/platform/fallback.py`** - Legitimate cross-platform feature (Python command fallback for Windows)
2. **Provider fallback logic** - Necessary for resilience
3. **Try/except defensive patterns** - Generally good practice

### Items to Verify

1. `src/agent/core.py` lines 145-146: `self.orch = self.adapter` alias
2. `src/agent/core.py` lines 176-180: `self.tools` dictionary mapping
3. `src/agent/core.py` lines 246-249: `planner`/`executor` properties
4. `src/agent/agent_loop.py` line 77: `tools` dict parameter

---

## Implementation Plan

### Phase 1 - Quick Wins (Estimated: 4 files, ~200 lines)
1. Delete `src/orchestrator.py`
2. Delete `src/agent.py`
3. Delete `src/cli.py`
4. Delete `src/orchestrator/rate_limiter.py`
5. Update all imports across codebase
6. Run tests

### Phase 2 - Agent Core Cleanup (Estimated: ~180 lines)
1. Delete backward compat wrapper methods (lines 522-601)
2. Delete decoupled agent loop methods (lines 603-701)
3. Update tests that call these methods
4. Run tests

### Phase 3 - Config & Dead Code (Estimated: ~70 lines)
1. Delete legacy constants from `orchestrator/config.py`
2. Delete commented-out code blocks
3. Delete tombstone comments
4. Resolve or delete TODO comments
5. Run tests

### Phase 4 - Deprecated Parameters (Estimated: ~100 lines)
1. Remove `auto_load_cache` and `semantic_initializer` from CodebaseContext
2. Remove legacy `input_fn`/`output_fn` from IntentClarifier
3. Remove `LegacyIOInputAdapter` class
4. Standardize provider parameter naming
5. Run tests

### Phase 5 - Protocol Cleanup (Estimated: ~20 lines)
1. Audit and remove unused protocol aliases
2. Remove `styled_echo` if unused
3. Enforce strict enum typing
4. Run tests

---

## Testing Notes

After each phase:
1. Run full test suite: `python -m pytest tests/ -v`
2. Check for import errors: `python -c "from src import *"`
3. Verify CLI still works: `python -m src.cli --help`
4. Run any integration tests

---

## Files to Update Imports

When deleting shim files, these files likely need import updates:
- `src/__init__.py`
- `src/main.py`
- `tests/test_*.py` (multiple test files)
- Any scripts in project root
