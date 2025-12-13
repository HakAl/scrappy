# Release Readiness Assessment

## Current State: Beta -> Release Candidate

With conversation history (Phase 1/1.5) complete, scrappy is significantly closer to release. This document identifies remaining gaps.

## Sources Scanned

| Document | Key Items Found |
|----------|-----------------|
| _BUGS.md | Cryptic error messages, progress bar issues, UI quirks |
| AGENT_BUGS.md | Progress bar numeric values lost in bridge |
| HIGH_VALUE_FEATURES.md | platformdirs, VCR.py, provider performance tracking |
| TODO_TOOL.md | Agent task persistence (add_task, list_tasks, update_task) |
| TEST_RUNNER_TOOL.md | run_tests tool with framework detection |
| RATE_LIMITING.md | Proactive enforcement (block before API call) |
| IDEAL_UX.md | Smart staleness detection (JIT reindex) |
| RESEARCHED_FEATURES.md | Diff preview, streaming, structured output validation |
| OFFLINE_MODE.md | Graceful degradation, local model support |
| PARALLEL_TOOL.md | Concurrent tool execution with thread safety |
| FEATURE_IDEAS.md | Textual command palette, agent memory |

---

## What's Done (Verify Only)

| Feature | Status | Notes |
|---------|--------|-------|
| Semantic search (LanceDB) | Done | Hybrid search, incremental indexing |
| Conversation persistence | Done | SQLite, token-budgeted recall, staleness detection |
| Safety confirmation gates | Done | SafetyChecker + ActionExecutor |
| Dangerous command blocking | Done | CommandSecurity blocks rm -rf, format, etc. |
| Slash commands | Done | /help, /clear, /quit, /plan, /agent, etc. |
| Ctrl+C handling | Done | KeyboardInterrupt caught |
| Session working memory | Done | File reads, searches, git ops cached |
| Agent loop | Done | Think-plan-execute with tool calling |
| Multiple providers | Done | GitHub, Cerebras, Groq, Gemini, Cohere |

---

## Critical Gaps for Release

### Tier 1: Must Fix (Blocks Release)

| Gap | Severity | Effort | Source | Rationale |
|-----|----------|--------|--------|-----------|
| **Error messages are cryptic** | High | Low | _BUGS.md | Users see "Error: Unknown" instead of actionable messages |
| **No version/changelog** | High | Low | - | Beta users need to know what's new |
| **No disclaimer banner** | High | Low | - | Legal/social liability for file system access |
| **.git/ not explicitly blocked** | High | Low | - | LLM could corrupt git index |

### Tier 2: Must Polish (RC Quality Bar)

These items separate "beta" from "release candidate." A buggy-feeling UI undermines confidence in the whole tool.

| Gap | Severity | Effort | Source | Rationale |
|-----|----------|--------|--------|-----------|
| **TUI text selection broken** | High | Medium | _BUGS.md | Can't scroll to copy, shift-select required, click changes bg |
| **UI polish pass** | High | Medium | _BUGS.md | Welcome banner too large, stale check verbose, log scroll issues |
| **Agent verbose mode toggle** | High | Low | _BUGS.md | Too much agent output, no way to reduce |
| **Agent safeguards review** | High | Low | _BUGS.md | Is max_steps=10 right? Review existing limits |
| **Progress bar broken** | Medium | Medium | AGENT_BUGS | Shows 0% during indexing - numeric values lost |
| **No `scrappy init` command** | Medium | Medium | HIGH_VALUE_FEATURES | Users manually edit .env - bad UX |
| **No dependency check on startup** | Medium | Low | - | App starts then fails if git/pytest missing |

### Tier 3: Nice for RC (New Features)

| Gap | Severity | Effort | Source | Rationale |
|-----|----------|--------|--------|-----------|
| **Diff preview before writes** | Medium | Medium | RESEARCHED_FEATURES | Users can't see what will change |
| **Streaming responses** | Medium | Medium | RESEARCHED_FEATURES | Better UX for long responses |

### Tier 4: High Value Post-RC

| Feature | Priority | Effort | Source | Rationale |
|---------|----------|--------|--------|-----------|
| **Todo Tool** | High | Medium | TODO_TOOL | Agent forgets progress on complex tasks |
| **Test Runner Tool** | High | Medium | TEST_RUNNER_TOOL | Closes the TDD verification loop |
| **Proactive rate limiting** | High | High | RATE_LIMITING | Stop wasting API calls on exhausted providers |
| **Smart staleness detection** | Medium | Medium | IDEAL_UX | JIT reindex only referenced files |
| **Provider performance tracking** | Medium | Medium | HIGH_VALUE_FEATURES | Score-based intelligent routing |

### Tier 5: Nice to Have (v1.1+)

| Feature | Priority | Effort | Source | Rationale |
|---------|----------|--------|--------|-----------|
| Episodic Memory (Phase 2) | Medium | High | _WIP | Long conversation recall |
| Parallel tool execution | Medium | Medium | PARALLEL_TOOL | Speed up multi-file operations |
| VCR.py for tests | Low | Low | HIGH_VALUE_FEATURES | Deterministic API tests |
| platformdirs (XDG paths) | Low | Low | HIGH_VALUE_FEATURES | Cross-platform config |
| Offline/local mode | Low | Medium | OFFLINE_MODE | Graceful degradation when no API |
| Local model support (Ollama) | Low | High | OFFLINE_MODE | Privacy-conscious users |
| Structured output validation | Low | Medium | RESEARCHED_FEATURES | Pydantic schemas for LLM responses |

---

## Release Checklist

### Release Candidate (RC))
- [ ] Add diff preview for file writes
- [ ] Fix TUI text selection (scroll-copy, shift-select, click bg)
- [ ] Add agent verbose mode toggle (/verbose agent or config)
- [ ] Review agent safeguards (max_steps, confirm thresholds)
- [ ] UI polish pass (see details below)
- [ ] Test on Windows, macOS, Linux
- [ ] Tag v0.9.0-rc1

### Post-RC (v1.0 Road)
- [ ] Todo Tool for agent planning
- [ ] Test Runner Tool for verification
- [ ] Streaming responses
- [ ] Proactive rate limiting

### Post-Release (v1.1+)
- [ ] Episodic Memory (Phase 2)
- [ ] Provider performance tracking
- [ ] Smart staleness detection
- [ ] Parallel tool execution

---

## UI Polish Details (RC)

### TUI Text Selection Issues
- **Can't scroll to copy**: Only visible text is selectable
- **Shift required**: Must hold shift to select text
- **Click changes background**: Clicking in chat log changes bg color unexpectedly

### Agent Output Issues
- **Too verbose**: Agent logs every thought/action, overwhelming for simple tasks
- **No toggle**: No way to reduce verbosity (`/verbose agent` or config option)
- **Consider**: Compact mode showing only tool calls + final result

### Agent Safeguards Review
- **max_steps=10**: Is this appropriate? Too low = incomplete tasks, too high = runaway
- **Confirmation thresholds**: When to auto-approve vs prompt?
- **Dangerous command detection**: Is blocklist complete?

### General UI Polish
| Issue | Location | Fix |
|-------|----------|-----|
| Welcome banner too large | display.py/display_rich.py | Condense to 3-4 lines |
| Stale session check verbose | core.py | Single line: "Restored 5 msgs (last: 2h ago)" |
| Log doesn't scroll well | main_screen.py | Auto-scroll to bottom on new content |
| Click changes bg color | RichLog widget | Investigate Textual focus behavior |
| Provider output truncated | _BUGS.md | Show full model list or "show more" |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| LLM corrupts .git/ | Medium | High | Block .git/ paths |
| User loses work on Ctrl+C | High | Medium | Document /quit, consider signal handler |
| API key in logs/cassettes | Low | High | Filter in VCR config, audit logging |
| Provider outage | Medium | Medium | Multi-provider fallback works |
| Semantic search unavailable | Low | Low | Graceful degradation in place |

---

## Summary

**Should have for RC (Tier 2):**
5. `scrappy init` wizard
6. Dependency check
7. Progress bar fix
8. TUI text selection fixes
9. Agent verbose mode toggle
10. Agent safeguards review
11. UI polish pass

**Post-RC (v1.0):**
12. Todo Tool
13. Test Runner
14. Streaming responses

**Post-Release (v1.1+):**
15. Episodic Memory
16. Proactive rate limiting

Estimated effort to Release Candidate: 5-7 days of focused work.


#### 1. The "Visual Proof" (Missing GIF/Screenshot)
Text is abstract. Users need to see what the CLI looks like.
*   **Action:** Add an ASCII cinema recording (using a tool like `asciinema` or `vhs`) or a high-quality GIF right after the "Quick Start" header. Show the tool answering a question or performing a simple refactor.

Add this section after **"Key Features"** or replace the existing **"Requirements"** section with a broader **"Providers & Architecture"** section.

Since you mentioned a **"clear progress indicator at the bottom status bar,"** this is the **perfect** image to put at the top of your README.

**Why?**
*   It proves the tool has a robust UI (TUI), not just a basic `input()` loop.
*   It shows "liveness" and polish.

**Recommendation:**
Take a screenshot capturing the setup wizard or the main chat window with the status bar visible at the bottom showing `Indexing: [====..] 45%`.
