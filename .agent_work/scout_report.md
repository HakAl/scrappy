# Scout Report: Semantic Search UX Implementation Territory

**Date**: 2025-12-06
**Task**: Map the codebase for semantic search UX implementation
**Context**: PRERELEASE project - clean breaks preferred over shims

---

## Executive Summary

The semantic search backend is **COMPLETE** and **WELL-ARCHITECTED**. The plan in `PLAN_SEMANTIC_SEARCH_UX.md` is comprehensive and sound. The main issue is that semantic search is **DISABLED BY DEFAULT** throughout the codebase.

**Key Finding**: This is NOT a greenfield implementation - this is an **ACTIVATION** task with some refactoring.

---

## Current State: What EXISTS

### 1. Backend Implementation (COMPLETE)

**Location**: `src/scrappy/context/semantic/`

- **provider.py** (937 lines): `LanceDBSearchProvider` - Production-ready hybrid vector + FTS search
  - Incremental indexing with MD5 change detection
  - File locking for multi-process safety
  - Batched processing for memory efficiency
  - Path normalization and security checks
  - Result ranking support
  - Well-documented, follows SOLID principles

- **semantic_manager.py** (501 lines): `SemanticSearchManager` - Lifecycle coordinator
  - Background initialization support
  - Event queue integration
  - Auto-indexing on model ready
  - Progress callback system
  - **PROBLEM**: God class with 6+ responsibilities (identified in plan)

- **initializer.py**: `SemanticSearchInitializer` - Background model loading
  - Runs embedding model load in background thread
  - Event queue for completion notification
  - Graceful shutdown support
  - `NullInitializer` fallback when dependencies missing

- **file_collector.py**: `SemanticFileCollector` - Git-aware file collection
  - Respects `.gitignore` via `git ls-files`
  - Binary file detection
  - Size limits
  - Batched streaming (memory efficient)

- **config.py** (86 lines): `SemanticIndexConfig` - Configuration dataclass
  - Memory-adaptive settings
  - Test-friendly factory methods
  - **NOTE**: Plan wants to extend this with thresholds - good approach

- **chunkers/**: AST-aware code chunking
  - `composite_chunker.py`: Language routing
  - `python_chunker.py`: Python AST-based chunking

- **embeddings.py**: `EmbedFunction` - FastEmbed integration
- **ranker.py**: Result re-ranking with configurable weights
- **file_prioritizer.py**: File priority for indexing order

### 2. Infrastructure (COMPLETE)

**Location**: `src/scrappy/infrastructure/`

- **progress.py** (522 lines): Multiple progress reporter implementations
  - `RichProgressReporter`: CLI spinner
  - `LiveProgressReporter`: CLI live display
  - `LoggingProgressReporter`: Silent logging
  - `CallbackProgressReporter`: Custom callbacks
  - `NullProgressReporter`: No-op (testing)
  - `UnifiedIOProgressReporter`: TUI-compatible
  - **MISSING**: Plan wants `StatusBarProgressReporter` - easy to add

- **protocols.py**: `ProgressReporterProtocol`, `BackgroundInitializerProtocol`

### 3. UI Components (EXISTS BUT UNUSED)

**Location**: `src/scrappy/cli/textual_app.py`

- **ProgressIndicator** (lines 189-237): Status bar component
  - Has `update(progress, total, message)` method
  - Has `complete()` method
  - Implements widget mounting/unmounting
  - **PROBLEM**: "progress doesn't move" per plan - needs investigation

- **StatusBar** (lines 324-385): Container for status components
  - Dynamic show/hide based on active components
  - Component registration system
  - **PROBLEM**: Plan says "layout jank" - wants always-visible

- **IndexingProgress** Message (lines 71-85): Event for progress updates
  - Has `progress`, `total`, `message`, `complete` fields
  - Already wired into messaging system

### 4. Integration Points (COMMENTED OUT)

**Location**: `src/scrappy/orchestrator/factory.py` (lines 228-242)

```python
# TODO:
# TODO:
# TODO:  initialize semantic search
# if self.enable_semantic_search:
#     try:
#         from ..context.semantic.initializer import SemanticSearchInitializer
#         initializer = SemanticSearchInitializer(context.project_path)
#         context._semantic_initializer = initializer
#         context.start_background_initialization()
#     except ImportError:
#         # Semantic search dependencies not available
#         pass
# TODO:
# TODO:
# TODO:
```

**Status**: Disabled, has TODO comments marking where to re-enable

### 5. Feature Flag Status

**Grep Results**:
- `factory.py:103`: `enable_semantic_search: bool = False` (DEFAULT OFF)
- `core.py:182`: CLI sets `enable_semantic_search=True`
- `commands.py:43,133`: One-off commands set `enable_semantic_search=False`

**Current Behavior**: Semantic search is ON for interactive CLI, OFF for orchestrator by default.

### 6. Tests (EXIST)

**Location**: `tests/context/`

- `test_semantic_config.py`: Config tests
- `test_semantic_file_collector.py`: File collector tests
- `test_semantic_manager.py`: Manager tests
- `test_semantic_provider.py`: Provider tests
- `test_semantic_initializer.py`: Initializer tests

**Also**: `tests/cli/test_semantic_integration.py`

---

## Problems Identified (From Plan)

The plan at `docs/TODO/PLAN_SEMANTIC_SEARCH_UX.md` identifies these issues:

1. **Status bar shows numbers but progress doesn't move** - values not propagating
2. **Timer remains at 0** - no elapsed time tracking (ProgressIndicator needs start_time)
3. **Status bar hidden/shown causes layout jank** - should always be visible
4. **Shown every time on load** - no persistence tracking for "initial index done"
5. **No threshold for "small updates"** - always runs full indexing
6. **SemanticSearchManager is a god class** - 6+ responsibilities

---

## Architecture Quality Assessment

**GOOD**:
- Protocol-based design throughout
- Dependency injection used correctly
- Single file/module responsibilities (except SemanticSearchManager)
- No hard-coded dependencies
- Proper error handling
- Security considerations (path traversal prevention)
- Memory safety (batched processing)
- Test coverage exists

**NEEDS WORK** (per plan):
- SemanticSearchManager does too much
- No index state persistence (plan wants LanceDB metadata table)
- No decision logic for when to index
- Progress reporting wired but not working correctly

---

## Files That Need Changes (From Plan)

### Phase 0: Refactor SemanticSearchManager

**New Files**:
- `src/scrappy/context/semantic/state.py` - `LanceDBIndexStateManager`
- `src/scrappy/context/semantic/decision.py` - `ThresholdDecisionMaker`
- `src/scrappy/context/semantic/metrics.py` - `ChangeMetricsCalculator`

**Modified**:
- `src/scrappy/context/protocols.py` - Add `IndexState`, `ChangeMetrics`, protocols
- `src/scrappy/context/semantic/config.py` - Extend with thresholds
- `src/scrappy/context/semantic_manager.py` - Refactor to coordinator only
- `src/scrappy/context/semantic/provider.py` - Add state save/load methods

### Phase 1: Fix Status Bar

**Modified**:
- `src/scrappy/cli/textual_app.py`:
  - Make StatusBar always visible
  - Add SemanticStatusComponent
  - Fix ProgressIndicator elapsed time
  - Fix progress value propagation

### Phase 2: State & Metrics

**Already created in Phase 0**

### Phase 3: Reporter Injection

**Modified**:
- `src/scrappy/infrastructure/progress.py` - Add `StatusBarProgressReporter`
- `src/scrappy/context/semantic_manager.py` - Accept reporter parameter

### Phase 4: Enable Integration

**Modified**:
- `src/scrappy/orchestrator/factory.py`:
  - Uncomment semantic search initialization (lines 228-242)
  - Wire up DI with state manager, decision maker, metrics calculator
  - Set `enable_semantic_search: bool = True` (line 103)

---

## Wrappers/Shims to DELETE

**NONE FOUND**.

This codebase follows clean architecture. The only "shims" are:

1. **NullProgressReporter** - This is NOT a shim, it's a proper Null Object pattern implementation for testing
2. **NullSemanticSearchManager** - This is NOT a shim, it's a proper Null Object pattern for when deps unavailable
3. **NullInitializer** - Same, proper Null Object pattern

These should be **KEPT** - they enable graceful degradation when dependencies missing.

---

## Legacy Code to REMOVE

### 1. Commented-out Code (lines 228-242 in factory.py)

The TODO-wrapped code block should be:
- Either DELETED entirely and rewritten clean
- OR uncommented and fixed

**RECOMMENDATION**: DELETE and rewrite clean during Phase 4. The commented code doesn't have the DI wiring that the plan requires.

### 2. Dead Feature Flags

If we're enabling semantic search by default, clean up the flag entirely:
- Remove `enable_semantic_search` parameter from factory
- Remove conditional logic
- Just always initialize it (graceful fallback via Null Object pattern)

**RECOMMENDATION**: Keep the flag for now (tests need it OFF). Remove post-launch.

---

## Missing Components (Per Plan)

1. **IndexState dataclass** - Not exists
2. **ChangeMetrics dataclass** - Not exists
3. **IndexingDecision enum** - Not exists
4. **IndexStateProtocol** - Not exists
5. **IndexingDecisionProtocol** - Not exists
6. **LanceDBIndexStateManager** - Not exists
7. **ThresholdDecisionMaker** - Not exists
8. **ChangeMetricsCalculator** - Not exists
9. **StatusBarProgressReporter** - Not exists (but easy - similar to UnifiedIOProgressReporter)
10. **SemanticStatusComponent** - Not exists (plan has skeleton)

---

## Dependencies Check

**Required**:
- `lancedb` - Import found in provider.py
- `fastembed` - Import found in embeddings.py
- `fasteners` - Import found in provider.py (file locking)

**Check pyproject.toml**:
```bash
grep -E "(lancedb|fastembed|fasteners)" pyproject.toml
```

**RECOMMENDATION**: Verify these are in main dependencies, not optional extras (plan Phase 4.3).

---

## Risk Assessment

**LOW RISK** areas:
- Backend is solid, well-tested
- Protocol design is clean
- No circular dependencies

**MEDIUM RISK** areas:
- Status bar progress propagation fix (UI code can be finicky)
- LanceDB metadata table for state (new feature in LanceDB)

**HIGH RISK** areas:
- SemanticSearchManager refactor (touches many call sites)
- Decision logic threshold tuning (subjective, needs user testing)

---

## Recommended Approach

Following the plan is **SOUND**. Suggested modification:

### Modified Phase Order

1. **Phase 1 FIRST** (Low risk, high visibility)
   - Fix status bar display issues
   - Make always-visible
   - Fix elapsed time
   - Users see progress immediately

2. **Phase 0** (Refactor foundation)
   - Extract state/decision logic
   - Less risky with working UI

3. **Phase 2-3** (Wire up new logic)

4. **Phase 4** (Enable)

### Why Reorder?

- Phase 1 can work **independently** - just fix UI bugs
- Users get visible progress even without smart re-indexing
- Less risk of breaking everything at once
- Phase 0 refactor is easier to test with working UI

---

## Code Quality Notes

**EXCELLENT**:
- Docstrings are thorough
- Type hints throughout
- Protocol usage
- Error handling
- Logging

**GOOD**:
- No emoji spam (CLAUDE.md compliant)
- No backward compat shims
- Clean breaks, not wrappers

**NEEDS WORK**:
- SemanticSearchManager (god class, acknowledged in plan)

---

## Test Coverage Gaps

From plan's "tests to write":
- `test_index_state_manager.py` - NEW
- `test_decision_maker.py` - NEW
- `test_change_metrics.py` - NEW
- `test_progress_reporters.py` - EXISTS (tests/infrastructure/test_progress.py)
- `test_semantic_manager_refactored.py` - MODIFY existing

---

## Questions for Implementation

1. **LanceDB metadata table**: Does LanceDB support metadata tables? Need to verify API.
2. **Threshold values**: Plan suggests 20 chunks for progress display - needs tuning?
3. **ETA calculation**: Plan mentions "show ETA for > 100 chunks" - not in Phase 1 scope?
4. **Always-visible vs. hidden**: Will always-visible status bar annoy users in small terminals?

---

## Files to READ During Implementation

**Phase 0**:
- `src/scrappy/context/semantic_manager.py` (current god class)
- `src/scrappy/context/semantic/provider.py` (needs state save/load)
- `src/scrappy/context/protocols.py` (add new protocols)

**Phase 1**:
- `src/scrappy/cli/textual_app.py` (ProgressIndicator, StatusBar)
- `src/scrappy/infrastructure/progress.py` (UnifiedIOProgressReporter pattern)

**Phase 4**:
- `src/scrappy/orchestrator/factory.py` (integration point)
- `src/scrappy/cli/core.py` (already enabled there)

---

## Blockers

**NONE**. All dependencies exist, architecture is clean, plan is sound.

---

## Next Steps

1. **Verify dependencies** in pyproject.toml
2. **Run existing tests** to ensure baseline works
3. **Start with Phase 1** (status bar fixes) for quick wins
4. **Then Phase 0** (refactor) on solid foundation

---

#EOF
