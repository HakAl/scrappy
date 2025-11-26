FIX PLAN: IMPLEMENTATION_PLAN_TEXTUAL_CLEANUP.md.md

Problem:
Users unable to interact with /agent (potentially other features)
existing features may have bugs because they output to console rather than textual in interactive mode.
console output should only occur in one shot command mode (commands.py)

---

## Root Cause Analysis

### Architecture Overview

The codebase has a well-designed two-mode output system:

**TUI Mode (Interactive/Textual):**
```
Textual TUI (ScrappyApp)
    -> TextualOutputAdapter (queue-based, thread-safe)
    -> OutputBridge (routes to OutputSink)
    -> Orchestrator.output (BaseOutputProtocol)
```

**CLI Mode (One-shot commands):**
```
Click Commands (e.g., /query, /agent, /task)
    -> ConsoleOutputBridge (direct print calls)
    -> Orchestrator.output (BaseOutputProtocol)
```

### Key Classes

1. **OutputBridge** (`src/cli/output_bridge.py:27-73`)
   - Implements BaseOutputProtocol
   - Routes to OutputSink (Textual queue)
   - Used in: TextualInteractiveMode

2. **ConsoleOutputBridge** (`src/cli/output_bridge.py:76-117`)
   - Direct console output with ANSI colors
   - Uses raw print() calls
   - Used in: One-shot command mode ONLY

3. **TextualOutputAdapter** (`src/cli/textual_app.py:297-341`)
   - Implements OutputSink protocol
   - Thread-safe queue for Textual message passing
   - No circular dependency with ScrappyApp

4. **UnifiedIO** (`src/cli/unified_io.py`)
   - Strategy pattern for output routing
   - Switches between DirectConsoleOutput and OutputSinkAdapter

---

## Identified Issues

### Issue 1: ConsoleOutputBridge Direct Print Calls
**Location:** `src/cli/output_bridge.py:76-117`
**Severity:** CRITICAL

ConsoleOutputBridge uses raw `print()` which bypasses Textual entirely:
- Line 96: `print(message)` in info()
- Line 101/103: print() in warn()
- Line 108/110: print() in error()
- Line 115/117: print() in success()

If ConsoleOutputBridge is ever used in Textual mode, output goes to console not TUI.

### Issue 2: Progress Output
**Location:** `src/infrastructure/progress.py:77, 91`
**Severity:** HIGH

Progress tracking may output directly to console.print() bypassing Textual routing.

### Issue 3: Output Formatter
**Location:** `src/agent_tools/formatters/output_formatter.py:249`
**Severity:** MEDIUM

Output formatting for tools may use direct console output.

### Issue 4: Task Router Output Handler
**Location:** `src/task_router/output_handler.py:360, 385, 397, 406`
**Severity:** MEDIUM

Task router output may bypass Textual routing.

### Issue 5: Logger Console Handler
**Location:** `src/infrastructure/logging/logger.py`
**Severity:** LOW

Logger may have StreamHandler outputting to console in Textual mode.

### Issue 6: DefaultConsoleInput Direct Print
**Location:** `src/task_router/protocols.py:638`
**Severity:** MEDIUM

`DefaultConsoleInput.output()` uses raw `print(message)`. If this fallback is used in TUI mode, output bypasses Textual.

### Issue 7: UnifiedIO Direct Console Print
**Location:** `src/cli/unified_io.py:107-122, 409-464, 512`
**Severity:** HIGH

`DirectConsoleOutput` class uses `self._console.print()` directly to Rich Console. This is correct for CLI mode but if this strategy is used in TUI mode (instead of `OutputSinkAdapter`), output bypasses Textual queue.

Critical lines:
- Lines 107-122: `_write_streaming()` and `_write_message()`
- Lines 409-464: `echo()`, `secho()`, `panel()`, `table()`, `syntax()`, `rule()`
- Line 512: `prompt()` uses `self._console.print()`

### Issue 8: Interactive Banner Direct Console
**Location:** `src/cli/interactive_banner.py:71`
**Severity:** MEDIUM

The banner display has a fallback at line 71 that calls `io.console.print(panel)` directly when `output_sink` is not available. This could bypass Textual in edge cases.

### Issue 9: Output Formatter Creates Own Console
**Location:** `src/agent_tools/formatters/output_formatter.py:169`
**Severity:** HIGH

`_get_console()` returns `Console()` - a new Rich Console instance. This console outputs directly to stdout, completely bypassing any Textual routing.

### Issue 10: Rich Dashboard Temp Console
**Location:** `src/cli/rich_dashboard.py:251`
**Severity:** LOW (Acceptable)

Uses `temp_console.print()` but writes to a StringIO buffer for `render_to_string()`. This is acceptable since it's for testing/string rendering.

### Issue 11: Console() Instantiation Points
**Location:** Multiple files
**Severity:** HIGH

New `Console()` instances bypass Textual:
- `src/cli/output.py:297` - `RichOutput` creates own Console
- `src/cli/rich_dashboard.py:41` - Dashboard creates own Console
- `src/cli/unified_io.py:821` - `DirectConsoleOutput` creates Console

These are problematic if the classes are used in TUI mode.

### Issue 12: Click.echo in commands.py
**Location:** `src/cli/commands.py` (multiple lines)
**Severity:** ACCEPTABLE (one-shot mode only)

Commands.py uses `click.echo()` extensively (lines 139-521). This is **correct** since commands.py is only used for one-shot CLI mode, not TUI mode.

### Issue 13: Blocking input() Calls
**Location:** Multiple files
**Severity:** CRITICAL (for TUI mode)

Direct `input()` calls will **block forever** in Textual worker threads:
- `src/cli/output.py:186, 356` - `get_input()` and `prompt()` use raw `input()`
- `src/cli/unified_io.py:514, 529` - `prompt()` and `read()` use raw `input()`
- `src/task_router/protocols.py:623, 631` - `DefaultConsoleInput.prompt()` and `confirm()` use `input()`

These are correctly used in CLI mode but must be replaced with async input in TUI mode.

---

## Bug Scenario Flow

When /agent command runs in Textual mode:

1. `/agent task` entered in Textual TUI
2. CommandRouter._handle_agent() called with proper IO (UnifiedIO)
3. CLIAgentManager.run_agent() uses self.display
4. AgentUI wraps UnifiedIO properly
5. **BUG:** If agent or orchestrator calls output methods:
   - If orchestrator.output is ConsoleOutputBridge -> direct print()
   - If ANY code directly calls print() -> bypasses Textual queue
   - If logger outputs to console handler -> bypasses Textual queue

---

## Files to Fix (Priority Order)

### Priority 1 - Critical (Direct print() or Console() that bypasses Textual)
| File | Line(s) | Issue |
|------|---------|-------|
| `src/cli/output_bridge.py` | 96-117 | ConsoleOutputBridge uses raw `print()` - ensure never used in TUI mode |
| `src/agent_tools/formatters/output_formatter.py` | 169, 249 | Creates own `Console()`, uses `console.print()` - bypasses Textual |
| `src/infrastructure/progress.py` | 77, 91 | Uses `self._console.print()` - must route through UnifiedIO |
| `src/task_router/output_handler.py` | 360, 385, 397, 406 | Uses `self._console.print()` - must use injected IO |
| `src/task_router/protocols.py` | 638 | `DefaultConsoleInput.output()` uses raw `print()` |
| `src/cli/output.py` | 186, 356 | Blocking `input()` calls - will hang in TUI mode |
| `src/cli/unified_io.py` | 514, 529 | Blocking `input()` calls in `DirectConsoleOutput` |
| `src/task_router/protocols.py` | 623, 631 | Blocking `input()` calls in `DefaultConsoleInput` |

### Priority 2 - High (Console() instantiation that could bypass Textual if used in TUI)
| File | Line(s) | Issue |
|------|---------|-------|
| `src/cli/output.py` | 297 | `RichOutput` creates `Console()` - verify not used in TUI mode |
| `src/cli/unified_io.py` | 821 | `DirectConsoleOutput` creates `Console()` - verify strategy selection |
| `src/cli/unified_io.py` | 107-122, 409-464, 512 | `DirectConsoleOutput` uses `_console.print()` - correct for CLI only |
| `src/cli/rich_dashboard.py` | 41 | Creates `Console()` - verify dashboard not used in TUI mode |
| `src/cli/interactive_banner.py` | 71 | Fallback to `io.console.print()` when no output_sink |

### Priority 3 - Medium (Verify correct usage)
| File | Issue |
|------|-------|
| `src/infrastructure/logging/logger.py` | Uses injected `io` - verify correct IO passed in TUI mode |
| `src/context/git_history.py:25` | `print()` in docstring example only - not a bug |
| `src/agent_tools/components/output_collector.py:35` | `print()` in docstring example only - not a bug |

### Priority 4 - Acceptable (One-shot CLI mode only)
| File | Status |
|------|--------|
| `src/cli/commands.py` | Uses `click.echo()` - correct, only used in one-shot CLI mode |
| `src/cli/rich_dashboard.py:251` | Uses temp Console with StringIO buffer for string rendering - acceptable |

### Priority 5 - Already Correct (Reference)
| File | Status |
|------|--------|
| `src/cli/textual_interactive.py` | Pattern is correct - uses OutputBridge |
| `src/cli/interactive.py` | Uses io properly |
| `src/agent/ui.py` | AgentUI wraps IO correctly |

---

## Solution

### Fix Strategy

1. **Add mode awareness** - Components need to know if running in TUI or CLI mode

2. **Audit all output paths** - Ensure every output path goes through:
   - TUI Mode: UnifiedIO -> OutputSink -> Textual queue
   - CLI Mode: ConsoleOutputBridge -> direct print

3. **Protocol enforcement** - All output must go through BaseOutputProtocol implementations

### Implementation Checklist

**Architecture Fixes:**
- [ ] Verify orchestrator.output is set to OutputBridge (not ConsoleOutputBridge) in TUI mode
- [ ] Ensure UnifiedIO strategy is set to OutputSinkAdapter (not DirectConsoleOutput) in TUI mode
- [ ] Verify RichOutput class is not used in TUI mode (or inject Console)

**File-Specific Fixes:**
- [ ] `output_formatter.py`: Inject Console/IO instead of creating own Console()
- [ ] `progress.py`: Use injected IO's progress context, not direct console.print()
- [ ] `task_router/output_handler.py`: Use injected IO, not self._console.print()
- [ ] `task_router/protocols.py`: DefaultConsoleInput should not be used in TUI mode
- [ ] `interactive_banner.py`: Ensure output_sink is always available in TUI mode
- [ ] `output.py`: Ensure blocking input() not called in TUI mode
- [ ] `unified_io.py`: Ensure DirectConsoleOutput not used in TUI mode (use OutputSinkAdapter)

**Logger Fixes:**
- [ ] Verify StructuredLogger receives correct IO in TUI mode
- [ ] Ensure logger output routes through Textual queue

**Testing:**
- [ ] Test /agent command in Textual TUI - output should appear in TUI not console
- [ ] Test progress indicators in TUI mode
- [ ] Test modal dialogs for user input (prompt/confirm)
- [ ] Test error messages route to TUI correctly

**Validation:**
- [ ] Grep for remaining direct print() calls in agent execution path
- [ ] Grep for Console() instantiation and verify each is acceptable
- [ ] Run full TUI session and verify no console output leakage
