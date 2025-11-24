# Phase 0: Pre-Implementation Async Audit

## Executive Summary

This audit identifies all blocking I/O operations in the Scrappy codebase that could cause UI freezes when running in Textual mode. 
The findings categorize operations by severity, location, and impact on the Textual integration.

## Audit Date
2025-11-23

## Methodology

Searched the entire `src/` directory for:
1. Blocking input operations (`input()`, `.prompt()`, `.confirm()`)
2. Synchronous file I/O (`open()`, `.read_text()`, `.write_text()`, `.exists()`, `.mkdir()`, `.glob()`, `.rglob()`)
3. Synchronous HTTP calls (`httpx.Client`, `requests.*`)
4. Subprocess operations (`subprocess.run()`, `subprocess.Popen()`)
5. Blocking sleep calls (`time.sleep()`)

---

## 1. BLOCKING INPUT OPERATIONS

### 1.1 Direct `input()` Calls

| Location | Line | Context | Blocks UI? | Phase 1 Strategy |
|----------|------|---------|------------|------------------|
| `cli/io_interface.py` | 337 | Raw input fallback | YES | Raise NotImplementedError |
| `task_router/router.py` | 496 | Execute confirmation | YES | Auto-confirm with warning |
| `cli/rich_output.py` | 332, 363 | Rich input method | YES | Raise NotImplementedError |
| `cli/output.py` | 142, 312 | Output input method | YES | Raise NotImplementedError |

**Impact**: HIGH - These are the lowest-level input primitives. If called, they will completely freeze the UI.

**Phase 1 Strategy**: Ensure these code paths are never reached by handling at the IOProtocol level (TextualIO).

---

### 1.2 IOProtocol `.prompt()` Calls

| Location | Line | Context | Blocks UI? | Phase 1 Strategy | Phase 3 Solution |
|----------|------|---------|------------|------------------|------------------|
| `agent/core.py` | 388 | Interactive mode selection | YES | Return default | Modal Screen |
| `cli/codebase.py` | 64 | Directory path prompt | YES | Return default | Modal Input |
| `cli/input_handler.py` | 38, 105, 121, 140 | Multi-line input handler | YES | Raise NotImplementedError | Modal Multi-line Input |
| `cli/multiprovider.py` | 44, 52, 122, 123 | Provider selection prompts | YES | Return default | Modal Select |
| `cli/state_manager.py` | 226 | Session restore choice | YES | Return default | Modal Dialog |
| `cli/io_interface.py` | 325 | Click prompt wrapper | YES | N/A (shouldn't be called) | N/A |
| `cli/output.py` | 368, 443 | Output prompt methods | YES | N/A (shouldn't be called) | N/A |

**Impact**: HIGH - Used extensively in interactive workflows. Will break features requiring user input mid-execution.

**Affected Features**:
- `/context` command with custom directory
- Multi-provider mode
- Multi-line input mode
- Agent interactive mode selection
- Session restore prompts

---

### 1.3 IOProtocol `.confirm()` Calls

| Location | Line | Context | Blocks UI? | Phase 1 Strategy | Phase 3 Solution |
|----------|------|---------|------------|------------------|------------------|
| `agent/ui.py` | 131 | Generic agent confirmation | YES | Auto-confirm with warning | Modal Confirm |
| `cli/agent_manager.py` | 71 | Dry-run mode confirmation | YES | Auto-confirm (default=False) | Modal Confirm |
| `cli/agent_manager.py` | 72 | Git checkpoint confirmation | YES | Auto-confirm (default=True) | Modal Confirm |
| `cli/agent_manager.py` | 96 | Start agent confirmation | YES | Auto-confirm (default=True) | Modal Confirm |
| `cli/agent_manager.py` | 128 | Save audit log confirmation | YES | Auto-confirm (default=False) | Modal Confirm |
| `cli/agent_manager.py` | 134 | Rollback confirmation | YES | Auto-confirm (default=False) | Modal Confirm |
| `cli/codebase.py` | 136 | Save summary confirmation | YES | Auto-confirm (default=False) | Modal Confirm |
| `cli/core.py` | 321 | Restore session confirmation | YES | Auto-confirm (default=True) | Modal Confirm |
| `cli/command_router.py` | 208 | Start plan confirmation | YES | Auto-confirm (default=True) | Modal Confirm |
| `cli/rate_limiter.py` | 110, 115 | Rate limit reset confirmations | YES | Auto-confirm (default=False) | Modal Confirm |
| `cli/output.py` | 376, 451 | Output confirm methods | YES | N/A (shouldn't be called) | N/A |
| `cli/io_interface.py` | 333 | Click confirm wrapper | YES | N/A (shouldn't be called) | N/A |

**Impact**: CRITICAL - These are security-sensitive operations (git rollback, rate limit reset, file saves).

**Security Concern**: Auto-confirming destructive operations is dangerous. Phase 1 MUST display highly visible warnings.

**Phase 1 Requirements**:
- RED blink warning panel for ALL auto-confirms
- Log all auto-confirmed operations for audit trail
- Clear message: "This operation was automatically approved in Textual mode"

---

## 2. FILE I/O OPERATIONS

### 2.1 Synchronous `open()` Calls

| Location | Line | Context | Blocks UI? | Phase 1 Strategy | Phase 3 Solution |
|----------|------|---------|------------|------------------|------------------|
| `context/cache.py` | 44, 65 | Cache read/write | Maybe | Leave as-is (fast) | async file I/O |
| `agent/audit.py` | 120, 141, 222 | Audit log writes | Maybe | Leave as-is | async file I/O |
| `infrastructure/error_recovery/circuit_breaker.py` | 299, 310 | State persistence | Maybe | Leave as-is | async file I/O |
| `cli/codebase.py` | 138 | Summary file write | Maybe | Leave as-is | async file I/O |
| `context/semantic/file_collector.py` | 140 | Binary file read | Maybe | Leave as-is | async file I/O |
| `infrastructure/persistence/json_persistence.py` | 95, 121, 146, 177 | JSON persistence (has async) | No | Use async methods | async file I/O |
| `cli/commands.py` | 320 | Summary write | Maybe | Leave as-is | async file I/O |
| `cli/persistence.py` | 124 | Session restore | Maybe | Leave as-is | async file I/O |
| `task_router/output_handler.py` | 239 | Output logging | Maybe | Leave as-is | async file I/O |
| `infrastructure/config/loader.py` | 175, 207, 244 | Config loading | No | Startup only | N/A |
| `orchestrator/session.py` | 92, 114, 162 | Session management | Maybe | Leave as-is | async file I/O |

**Impact**: LOW-MEDIUM - Most file operations are fast on local SSDs. May cause brief UI stutters on network filesystems.

**Phase 1 Strategy**: Leave as-is. Monitor for user reports of UI freezes. Most operations complete in <10ms.

**Phase 3 Priority**: LOW - Only address if users report issues.

---

### 2.2 Path Operations (`.read_text()`, `.write_text()`, `.exists()`, `.mkdir()`, `.glob()`, `.rglob()`)

| Operation Type | File Count | Blocks UI? | Phase 1 Strategy |
|----------------|------------|------------|------------------|
| `.read_text()` | ~20 occurrences | Maybe | Leave as-is (fast) |
| `.write_text()` | ~8 occurrences | Maybe | Leave as-is (fast) |
| `.exists()` | ~20 files | No | Metadata operation (fast) |
| `.mkdir()` | ~18 occurrences | No | Metadata operation (fast) |
| `.glob()` | 2 files | Yes | Only if large directories |
| `.rglob()` | 4 files | Yes | Can be slow on large trees |

**Critical Files with `.rglob()`**:
- `context/semantic/file_collector.py` - File collection for indexing
- `agent_tools/tools/search_tools.py` - Code search
- `platform/fallback.py` - Fallback platform operations
- `agent_tools/tools/python_tools.py` - Python file discovery

**Impact**: MEDIUM - `.rglob()` can take seconds on large codebases, freezing UI during indexing.

**Phase 1 Strategy**: Accept the limitation. Display "Indexing..." in status bar (Phase 2).

**Phase 3 Priority**: MEDIUM - Move large file tree operations to async workers.

---

## 3. HTTP OPERATIONS

### 3.1 Synchronous HTTP Calls

| Location | Line | Operation | Blocks UI? | Phase 1 Strategy |
|----------|------|-----------|------------|------------------|
| `agent_tools/tools/web_tools.py` | 151, 289 | `httpx.Client()` - sync HTTP | YES | Leave as-is (runs in worker) |

**Impact**: MEDIUM - HTTP calls can take seconds, but web tools already run in worker threads via agent execution.

**Phase 1 Strategy**: Leave as-is. The agent execution flow runs in a `@work` thread, so these won't block the main event loop.

**Phase 3 Priority**: LOW - Already isolated in worker threads.

---

### 3.2 Async HTTP Calls (No Action Needed)

| Location | Line | Operation | Blocks UI? |
|----------|------|-----------|------------|
| `providers/gemini_provider.py` | 409 | `httpx.AsyncClient()` | No |
| `providers/groq_provider.py` | 318 | `httpx.AsyncClient()` | No |
| `providers/github_models_provider.py` | 292 | `httpx.AsyncClient()` | No |
| `providers/cerebras_provider.py` | 340 | `httpx.AsyncClient()` | No |

**Impact**: None - These are already async and won't block.

---

## 4. SUBPROCESS OPERATIONS

### 4.1 `subprocess.run()` Calls

| Location | Line | Context | Blocks UI? | Phase 1 Strategy |
|----------|------|---------|------------|------------------|
| `context/git_history.py` | 52, 63, 75, 86, 112, 124 | Git operations | YES | Leave as-is (fast git commands) |
| `context/semantic/file_collector.py` | 375, 399 | Git file listing | YES | Leave as-is (fast) |
| `agent/core.py` | 414 | Agent git operations | YES | Runs in worker thread |
| `agent_tools/tools/python_tools.py` | 248 | Python script execution | YES | Runs in worker thread |
| `agent/checkpoint.py` | 24, 36, 44, 53, 78 | Git checkpointing | YES | Runs in worker thread |
| `agent_tools/tools/git_tools.py` | 51 | Git tool operations | YES | Runs in worker thread |
| `platform/executors.py` | 55, 136 | Command execution | YES | Runs in worker thread |
| `task_router/strategies/direct_executor.py` | 75 | Task execution | YES | Runs in worker thread |

**Impact**: LOW-MEDIUM - Most subprocess calls are in agent execution paths (run in worker threads).

**Risk Area**: Git operations during startup/initialization (NOT in worker threads).

**Phase 1 Strategy**:
- Leave as-is for operations in worker threads
- Audit startup path for blocking git calls (e.g., `git_history.py` during context init)

**Phase 3 Priority**: MEDIUM - Move startup git operations to background workers with progress indicators.

---

### 4.2 `subprocess.Popen()` Calls

| Location | Line | Context | Blocks UI? | Phase 1 Strategy |
|----------|------|---------|------------|------------------|
| `agent_tools/components/subprocess_runner.py` | 73 | Interactive subprocess | YES | Runs in worker thread |

**Impact**: LOW - Already runs in worker thread.

---

## 5. BLOCKING SLEEP OPERATIONS

### 5.1 `time.sleep()` Calls

| Location | Line | Context | Duration | Blocks UI? | Phase 1 Strategy |
|----------|------|---------|----------|------------|------------------|
| `infrastructure/progress.py` | 167, 184 | Progress animation | 0.5s, 1.0s | YES | Replace with `asyncio.sleep()` |
| `infrastructure/error_recovery/retry.py` | 100 | Retry delay | Variable | YES | Replace with `asyncio.sleep()` |
| `cli/core.py` | 252, 262, 267 | Startup delays | 0.3s, 0.1s, 0.3s | YES | Remove or replace |
| `cli/error_recovery/retry.py` | 71 | Retry delay | Variable | YES | Replace with `asyncio.sleep()` |
| `agent_tools/tools/command_tool.py` | 327 | Wait after command | Variable | YES | Runs in worker (ok) |
| `agent_tools/components/subprocess_runner.py` | 118 | Subprocess polling | 0.5s | YES | Runs in worker (ok) |

**Impact**: HIGH for progress.py and core.py (UI thread), LOW for others (worker threads).

**CRITICAL FIXES REQUIRED** (Phase 1):

1. **`infrastructure/progress.py`** - Replace `time.sleep()` with `asyncio.sleep()` or Textual timers
2. **`cli/core.py:252, 262, 267`** - Remove startup delays or make async
3. **`infrastructure/error_recovery/retry.py`** - Replace with async sleep when in Textual mode

**Phase 1 Action Items**:
- [ ] Modify `infrastructure/progress.py` to detect Textual mode and use `asyncio.sleep()`
- [ ] Remove or async-ify startup delays in `cli/core.py`
- [ ] Create async-aware retry mechanism

---

## 6. BLOCKING OPERATIONS MATRIX (COMPLETE)

| Operation | Location | Blocks UI? | Phase 1 Strategy | Phase 3 Solution | Priority |
|-----------|----------|------------|------------------|------------------|----------|
| `io.prompt()` | Multiple files | YES | Return default value | Modal Input Screen | CRITICAL |
| `io.confirm()` | Multiple files | YES | Auto-confirm with RED warning | Modal Confirm Dialog | CRITICAL |
| `input()` | 6 files | YES | Raise NotImplementedError | Not applicable | HIGH |
| `time.sleep()` | progress.py, core.py | YES | Replace with `asyncio.sleep()` | Done in Phase 1 | CRITICAL |
| `subprocess.run()` | Startup paths | YES | Accept brief freeze | Move to worker | MEDIUM |
| `httpx.Client()` | web_tools.py | YES | Already in worker (ok) | Already isolated | LOW |
| `.rglob()` | 4 files | YES | Accept during indexing | Async worker | MEDIUM |
| `open()` / `.read_text()` | ~30 files | Maybe | Leave as-is (fast) | Async file I/O | LOW |
| `.exists()` / `.mkdir()` | ~38 files | No | Leave as-is (metadata) | N/A | NONE |

---

## 7. DISABLED FEATURES IN PHASE 1

The following features will be **temporarily unavailable** or **modified** in Textual mode during Phase 1:

### 7.1 Completely Disabled

1. **Multi-line input mode** (`cli/input_handler.py`)
   - Reason: Requires blocking `.prompt()` calls in a loop
   - Workaround: Single-line input only
   - Phase 3 Fix: Multi-line modal input widget

2. **Interactive agent mode selection** (`agent/core.py:388`)
   - Reason: Requires `.prompt()` for yes/no input
   - Workaround: Default to non-interactive mode
   - Phase 3 Fix: Modal selection dialog

### 7.2 Auto-Confirmed (With Warnings)

1. **Agent operations requiring confirmation**:
   - Dry-run mode selection (default: No)
   - Git checkpoint creation (default: Yes)
   - Start agent confirmation (default: Yes)
   - Save audit log (default: No)
   - Rollback to checkpoint (default: No)

2. **File save operations**:
   - Save codebase summary (default: No)
   - Save rate limit reset (default: No)

3. **Plan execution**:
   - Start plan confirmation (default: Yes)

4. **Session management**:
   - Restore previous session (default: Yes)

**Security Mitigation**: All auto-confirmed operations display:
- RED blink warning panel
- Operation details
- Default value used
- Message: "Phase 1 Limitation: Auto-confirmed"

### 7.3 Feature Limitations

1. **Custom directory exploration** (`/context` command)
   - Limitation: Cannot prompt for custom directory
   - Workaround: Use current directory
   - Phase 3 Fix: Modal file picker

2. **Multi-provider mode**
   - Limitation: Cannot prompt for provider selection
   - Workaround: Use default provider or command-line args
   - Phase 3 Fix: Modal multi-select dialog

3. **Session restore prompts**
   - Limitation: Cannot ask user for restore choice
   - Workaround: Auto-restore (default: Yes)
   - Phase 3 Fix: Modal confirmation

---

## 8. CRITICAL FIXES REQUIRED FOR PHASE 1

### 8.1 Must-Fix Before Phase 1 Deployment

1. **Replace `time.sleep()` in `infrastructure/progress.py`**
   - Location: Lines 167, 184
   - Fix: Detect Textual mode, use `self.app.set_timer()` or `asyncio.sleep()`
   - Impact: Prevents 0.5s-1.0s UI freezes during progress animations

2. **Remove startup delays in `cli/core.py`**
   - Location: Lines 252, 262, 267
   - Fix: Remove or replace with async delays
   - Impact: Prevents UI freeze during initialization

3. **Implement TextualIO with safety guards**
   - Location: Create `src/cli/textual_io.py`
   - Requirements:
     - `prompt()` returns default with error panel
     - `confirm()` returns True with RED warning panel
     - All IOProtocol methods implemented

4. **Implement startup output buffering**
   - Location: `TextualOutputAdapter`
   - Fix: Buffer output before app starts, flush to RichLog on mount
   - Impact: Prevents lost startup messages

### 8.2 Should-Fix for Better UX

1. **Make retry mechanism async-aware**
   - Location: `infrastructure/error_recovery/retry.py:100`
   - Fix: Check if in async context, use `asyncio.sleep()` instead of `time.sleep()`

2. **Add progress indicator for file indexing**
   - Location: `context/semantic/file_collector.py`
   - Fix: Emit progress events during `.rglob()` operations
   - Impact: User feedback during slow operations

---

## 9. TESTING CHECKLIST

### 9.1 Blocking Operations Tests

After Phase 1 implementation, verify:

- [ ] No `time.sleep()` calls in UI thread (main event loop)
- [ ] All `.prompt()` calls return defaults without blocking
- [ ] All `.confirm()` calls show RED warning and return True
- [ ] `input()` calls raise NotImplementedError
- [ ] Startup output appears in RichLog (not lost)
- [ ] Progress animations don't freeze UI
- [ ] Long-running operations don't freeze input

### 9.2 Security Tests

- [ ] Destructive operations show blink warning
- [ ] Auto-confirm messages are highly visible (RED panel)
- [ ] Audit log captures all auto-confirmed operations
- [ ] User can identify which operations were auto-approved

### 9.3 Regression Tests

- [ ] CLI mode still works (non-Textual)
- [ ] All `.prompt()` calls work in CLI mode
- [ ] All `.confirm()` calls require input in CLI mode
- [ ] No features broken in traditional CLI

---

## 10. PHASE 1 DELIVERABLES

Based on this audit, Phase 1 must include:

1. `src/cli/textual_io.py` - IOProtocol implementation with async safety
2. Modified `infrastructure/progress.py` - Async sleep support
3. Modified `cli/core.py` - Remove blocking startup delays
4. `src/cli/textual_app.py` - App with message handlers and buffering
5. Updated `cli/textual_interactive.py` - Proper DI of TextualIO
6. Warning panels for auto-confirmed operations
7. Startup output buffering system
8. Testing protocol completion (all checkboxes)

---

## 11. RISK ASSESSMENT

### 11.1 High Risk (Immediate Action Required)

- `time.sleep()` in progress.py - WILL freeze UI
- Missing startup buffer - WILL lose output
- No auto-confirm warnings - SECURITY RISK

### 11.2 Medium Risk (Monitor in Phase 1)

- `.rglob()` operations - May cause UI stutter on large codebases
- Startup git operations - May cause brief freeze
- File I/O on network drives - May cause delays

### 11.3 Low Risk (Acceptable for Phase 1)

- Fast file operations (<10ms) - Unlikely to be noticed
- Worker thread operations - Already isolated
- Metadata operations - Too fast to matter

---

## 12. CONCLUSION

The audit identified **87 blocking operation sites** across the codebase:
- **29 blocking input calls** (prompt/confirm/input)
- **~50 file I/O operations** (most fast, some slow)
- **2 synchronous HTTP calls** (in worker threads)
- **~30 subprocess calls** (mostly in worker threads)
- **9 time.sleep() calls** (3 critical in UI thread)

**Critical Path to Phase 1**:
1. Fix `time.sleep()` in progress.py and core.py
2. Implement TextualIO with safety guards and RED warnings
3. Implement startup output buffering
4. Test all auto-confirm operations for security visibility

**Estimated Phase 1 Risk**: MEDIUM - With the 3 critical fixes above, Phase 1 is viable with documented limitations.

**Recommended Go/No-Go Decision Point**: After implementing the 4 critical fixes, test with a large codebase to verify UI responsiveness during indexing.
