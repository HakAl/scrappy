
## Phase 4: Blocking Re-index UX

**Goal:** User never sees unexplained hangs during re-indexing.

Status -- Fingerprinting / indexing are displayed in status bar, but the UX isn't ideal
Additionally, we should a loading indicator for Q/A displayed in the chat area.

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
