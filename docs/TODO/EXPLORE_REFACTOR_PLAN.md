# Explore Refactor Plan

## Problem Statement

The "zen script" query fails because:
1. `file_index` is NOT populated (requires explicit `explore()` call)
2. `ResearchSubclassifier` uses `file_index` for term matching
3. Result: query classified as GENERAL instead of CODEBASE

Root cause: `file_index` requires manual `explore()` but should be available automatically.

---

## Design Decisions

1. **Lazy explore (file walk)**: Runs on first query if `file_index` empty. Fast (~50ms), no blocking, no indicator needed.

2. **Semantic indexing**:
   - **Initial indexing**: Non-blocking, runs in background, queries proceed with file_index only
   - **Re-indexing (staleness)**: Blocking - user expects up-to-date results if files changed

3. **File index source**: Use `_scan_files()` directly (fast filesystem walk), not semantic index paths.

---

## Phase 1: Lazy File Index -- COMPLETE

**Goal:** `file_index` populated automatically on first query.

**Approach:** Lazy `_scan_files()` when file_index first requested.

**Changes:**

1. Add `ensure_file_index()` method to `CodebaseContext`
   - If `file_index` empty, run `_scan_files()`
   - Cache result for subsequent calls

2. Update `ResearchExecutor._get_file_index()` to call `ensure_file_index()`

3. Add safety cap for large projects
   - Timeout: 500ms max for file walk
   - File limit: 10k files max before bailing
   - If exceeded, return partial results + log warning

**Files:**
- `src/scrappy/context/codebase_context.py` - add `ensure_file_index()`
- `src/scrappy/context/file_scanner.py` - add timeout/limit guards
- `src/scrappy/task_router/strategies/research_executor.py` - use `ensure_file_index()`

**Tests:**
- `test_file_index_populated_lazily_on_first_access`
- `test_zen_query_matches_after_lazy_scan`
- `test_large_project_returns_partial_results`
- `test_scan_timeout_does_not_block`

**Success Criteria:**
- [ ] "how do we fix the zen script?" classifies as CODEBASE without manual explore
- [ ] No regression when file_index already populated
- [ ] Lazy scan only runs once (cached)
- [ ] Large projects (100k files) don't block main thread

---

## Phase 2: Staleness Detection + Blocking Re-index

**Goal:** Detect stale files and re-index them (blocking).

**Approach:** File fingerprinting (mtime + size). Block on re-index because user expects current results.

**Changes:**

1. Create `StalenessChecker` class
   - Store fingerprints after scan/index
   - Compare on subsequent queries
   - Return `StalenessReport` with added/modified/deleted files

2. Integrate with `CodebaseContext.ensure_file_index()`
   - If stale: re-scan files (fast)
   - If stale + semantic index exists: trigger re-index (blocking)

3. Integrate with `SemanticSearchManager`
   - `refresh_files(changed: Set[str])` for incremental re-index
   - Block until complete when staleness detected

4. Add debounce for filesystem changes
   - Wait 300ms for file events to settle before triggering re-index
   - Prevents thundering herd from rapid autosaves/IDE reformatting
   - Track last check timestamp, skip if < 300ms since last

**Files:**
- `src/scrappy/context/staleness.py` - NEW: StalenessChecker + debounce logic
- `src/scrappy/context/protocols.py` - StalenessCheckerProtocol
- `src/scrappy/context/codebase_context.py` - integrate staleness check
- `src/scrappy/context/semantic_manager.py` - add `refresh_files()`

**Tests:**
- `test_new_file_detected_as_stale`
- `test_modified_file_detected_as_stale`
- `test_stale_triggers_blocking_reindex`
- `test_fingerprint_performance` (< 100ms for 1000 files)
- `test_debounce_prevents_rapid_reindex`
- `test_debounce_allows_reindex_after_settle`

**Success Criteria:**
- [ ] New files detected and indexed before query proceeds
- [ ] Modified files re-indexed before query proceeds
- [ ] Deleted files removed from index
- [ ] Fingerprinting fast (< 100ms)
- [ ] Rapid file changes don't trigger multiple re-index calls

---

## Phase 3: Auto-trigger Semantic Indexing on Startup

**Goal:** Semantic indexing starts automatically, non-blocking.

**Approach:** Trigger on orchestrator init, run in background.

**Changes:**

1. `AgentOrchestrator.initialize()` triggers semantic indexing
   - If no index exists: start background indexing
   - If index exists but stale: handled by Phase 2

2. Ensure `ensure_file_index()` is called before semantic indexing
   - Semantic indexer needs file list
   - File index populated first (instant), then semantic begins

3. Progress indicator for semantic indexing (already exists)

**Files:**
- `src/scrappy/orchestrator/orchestrator.py` - trigger indexing in `initialize()`
- `src/scrappy/context/codebase_context.py` - coordinate file scan + semantic start

**Tests:**
- `test_semantic_indexing_starts_on_init`
- `test_queries_work_before_semantic_ready`
- `test_semantic_results_available_after_indexing`

**Success Criteria:**
- [ ] Zero manual setup required
- [ ] First query works immediately (with file_index)
- [ ] Semantic search available after background indexing completes
- [ ] Progress indicator shows indexing status

---

## Phase 4: Blocking Re-index UX

**Goal:** User never sees unexplained hangs during re-indexing.

**Approach:** Progressive micro-copy, time-to-interactive cap, debounce.

**Changes:**

1. Add "Syncing" UI state with progressive messages
   - "Detecting file changes..."
   - "Refreshing context..."
   - Messages appear after 500ms threshold

2. Time-to-interactive cap (5 seconds)
   - If re-indexing exceeds 5s, proceed with warning
   - "I'm still processing changes, but based on previous state..."

3. Debounce filesystem changes (~300ms)
   - Wait for file events to settle before triggering re-index
   - Prevents thundering herd from rapid autosaves

**Files:**
- `src/scrappy/cli/output.py` or similar - syncing state UI
- `src/scrappy/context/staleness.py` - debounce logic
- `src/scrappy/context/codebase_context.py` - timeout + fallback

**Tests:**
- `test_syncing_message_shown_after_threshold`
- `test_timeout_proceeds_with_warning`
- `test_debounce_prevents_rapid_reindex`

**Success Criteria:**
- [ ] User sees "Detecting file changes..." not just spinner
- [ ] Re-index never blocks longer than 5s without feedback/fallback
- [ ] Rapid file saves don't trigger multiple re-index calls

---

## Phase 5: Degraded Mode Awareness

**Goal:** Agent acknowledges when operating without full semantic search.

**Approach:** Track indexing state, inject awareness into responses.

**Changes:**

1. Add `is_semantic_ready()` to CodebaseContext
   - Returns False during initial indexing
   - Returns True once semantic index available

2. Surface degraded state to agent/prompts
   - When semantic not ready, agent knows to caveat responses
   - "I'm still indexing the codebase. Here's what I found based on filenames..."

3. Optional: Re-answer prompt after indexing completes
   - "Indexing complete. Would you like me to search again?"

**Files:**
- `src/scrappy/context/codebase_context.py` - `is_semantic_ready()`
- `src/scrappy/task_router/strategies/research_executor.py` - inject degraded mode awareness
- `src/scrappy/prompts/` - degraded mode prompt fragments

**Tests:**
- `test_degraded_mode_detected_during_indexing`
- `test_response_includes_degraded_caveat`
- `test_full_mode_after_indexing_complete`

**Success Criteria:**
- [ ] Agent knows when semantic search unavailable
- [ ] Responses include appropriate caveats during gap window
- [ ] No silent failures or unexplained poor results

---

## Implementation Order

| Phase | Effort | Risk | Blocking |
|-------|--------|------|----------|
| 1     | Small  | Low  | No       |
| 2     | Medium | Medium | Yes (re-index only) |
| 3     | Small  | Low  | No       |
| 4     | Medium | Low  | No       |
| 5     | Medium | Low  | No       |

Order: 1 -> 2 -> 3 -> 4 -> 5

Phase 4 and 5 can be done in parallel after Phase 2.

---

## Summary

| Scenario | Behavior |
|----------|----------|
| First query, no prior explore | Lazy file scan (instant), query proceeds |
| Query after files changed | Staleness detected, blocking re-index, then query |
| App startup | Semantic indexing starts in background |
| Query during initial indexing | Works with file_index only, semantic unavailable |
| Query after indexing complete | Full semantic search available |

---