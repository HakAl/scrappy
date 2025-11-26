# Implementation Plan: Unified TUI/CLI Output Routing

## Problem Summary

Users cannot interact with `/agent` (and potentially other features) in TUI mode because output bypasses the Textual queue and goes directly to console via `print()` or direct `Console()` instantiation.

---

## Architectural Analysis

### Current Architecture (Good Parts)

The codebase has a well-designed protocol-based output system:

```
BaseOutputProtocol (info, warn, error, success)
    |
    +-- OutputBridge (TUI mode) -> OutputSink -> Textual queue
    |
    +-- ConsoleOutputBridge (CLI mode) -> direct print()

CLIIOProtocol (echo, secho, panel, etc.)
    |
    +-- UnifiedIO
         |
         +-- OutputSinkAdapter (TUI mode) -> OutputSink -> Textual queue
         |
         +-- DirectConsoleOutput (CLI mode) -> Rich Console
```

### Root Cause

The architecture is sound, but several components violate the abstraction:

1. **Direct `print()` calls** - Bypass all routing
2. **Direct `Console()` instantiation** - Creates independent output channels
3. **Blocking `input()` calls** - Will hang in TUI worker threads
4. **Missing mode awareness** - Components don't know if they're in TUI or CLI mode

---

## Design Principles Applied

### 1. Dependency Inversion Principle

**Current Violation:**
```python
class RichDirectoryFormatter:
    def _create_default_console(self) -> Console:
        return Console()  # Hardcoded dependency
```

**Fix:**
```python
class RichDirectoryFormatter:
    def __init__(self, console: Optional[Console] = None):
        self._console = console  # Injected dependency, no default creation
```

### 2. Interface Segregation Principle

Create a `ModeAwareProtocol` to allow components to check their execution context:

```python
class ModeAwareProtocol(Protocol):
    """Allows components to check execution mode."""

    @property
    def is_tui_mode(self) -> bool:
        """Returns True if running in TUI (Textual) mode."""
        ...
```

### 3. Strategy Pattern (Already Used)

UnifiedIO already uses strategy pattern. Ensure strategy selection is explicit and mode-aware.

---

## Implementation Tasks

### Phase 1: Mode-Aware Infrastructure (Foundation)

#### Task 1.1: Add Mode Awareness to UnifiedIO

**File:** `src/cli/unified_io.py`

**Changes:**
- Add `is_tui_mode` property that returns `True` when `output_sink` is not `None`
- This property will be the single source of truth for mode detection

```python
@property
def is_tui_mode(self) -> bool:
    """Check if running in TUI (Textual) mode."""
    return self._output_sink is not None
```

#### Task 1.2: Create Mode Check Utility

**File:** `src/cli/mode_utils.py` (new file)

**Purpose:** Provide utilities for mode checking without circular imports

```python
"""Mode detection utilities for CLI/TUI output routing."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .io_interface import CLIIOProtocol

def is_tui_mode(io: "CLIIOProtocol") -> bool:
    """Check if the IO interface is in TUI mode.

    Args:
        io: CLIIOProtocol instance

    Returns:
        True if in TUI mode (Textual), False for CLI mode
    """
    return getattr(io, 'is_tui_mode', False)
```

---

### Phase 2: Fix Critical Direct Output Issues

#### Task 2.1: Fix RichOutputHandler

**File:** `src/task_router/output_handler.py`

**Problem:** Lines 360, 385, 397, 406 use `self._console.print()` directly

**Solution:** Replace `RichOutputHandler` usage with `CLIIOOutputHandler` in TUI mode, or inject the console from the IO context.

**Option A (Preferred):** Deprecate `RichOutputHandler`, always use `CLIIOOutputHandler`
```python
# Remove RichOutputHandler or mark as CLI-only
# In TUI mode, use CLIIOOutputHandler which routes through IO
```

**Option B:** Inject console from UnifiedIO
```python
class RichOutputHandler:
    def __init__(self, io: CLIIOProtocol):
        # Get console from IO (which respects mode)
        self._io = io
        # Use io.panel(), io.table() instead of direct console
```

#### Task 2.2: Fix RichProgressReporter and LiveProgressReporter

**File:** `src/infrastructure/progress.py`

**Problem:** Lines 77, 91 use `self._console.print()` directly

**Solution:** Create `TUIProgressReporter` or modify existing to route through IO

```python
class TUIProgressReporter:
    """Progress reporter for TUI mode - uses IO for output."""

    def __init__(self, io: CLIIOProtocol):
        self._io = io
        self._description: Optional[str] = None

    def complete(self, message: str = "Complete") -> None:
        self._io.secho(message, fg="green")

    def error(self, message: str) -> None:
        self._io.secho(f"Error: {message}", fg="red")
```

**Factory pattern for progress reporters:**
```python
def create_progress_reporter(io: CLIIOProtocol) -> ProgressReporterProtocol:
    """Create appropriate progress reporter based on mode."""
    if is_tui_mode(io):
        return UnifiedIOProgressReporter(io)  # Already exists!
    else:
        return RichProgressReporter()
```

#### Task 2.3: Fix RichDirectoryFormatter

**File:** `src/agent_tools/formatters/output_formatter.py`

**Problem:** Line 169 creates `Console()`, line 249 uses `console.print()`

**Solution:** Remove default console creation, require injection

```python
class RichDirectoryFormatter:
    def __init__(self, console: Console):  # Required, no default
        if not HAS_RICH:
            raise ImportError("Rich library is required")
        self._console = console

    # Remove _create_default_console method
```

**Usage sites must provide console from IO:**
```python
# In caller code:
formatter = RichDirectoryFormatter(console=io.console)
```

#### Task 2.4: Fix DefaultConsoleInput

**File:** `src/task_router/protocols.py`

**Problem:** Lines 623, 631, 638 use blocking `input()` and `print()`

**Solution:** This class should ONLY be used in CLI mode. Add documentation and guards.

```python
class DefaultConsoleInput:
    """
    Fallback implementation using stdin.

    WARNING: CLI MODE ONLY. Do NOT use in Textual/TUI mode.
    In TUI mode, use the prompt/confirm methods from CLIIOProtocol
    which route through Textual's modal system.
    """

    def __init__(self):
        # Could add a mode check here if we want to fail fast
        pass
```

**Better solution:** Create a TUI-aware input adapter:
```python
class IOBasedInput:
    """Input implementation that delegates to CLIIOProtocol."""

    def __init__(self, io: CLIIOProtocol):
        self._io = io

    def prompt(self, text: str, default: str = "") -> str:
        return self._io.prompt(text, default=default)

    def confirm(self, text: str, default: bool = False) -> bool:
        return self._io.confirm(text, default=default)

    def output(self, message: str) -> None:
        self._io.echo(message)
```

---

### Phase 3: Fix High-Priority Console Instantiation

#### Task 3.1: Audit and Fix RichOutput

**File:** `src/cli/output.py`

**Problem:** Line 297 creates `Console()`

**Analysis:** Need to verify if `RichOutput` is used in TUI mode. If yes, inject console.

**Solution:**
```python
class RichOutput:
    def __init__(self, console: Optional[Console] = None):
        self._console = console or Console()  # Allow injection
```

But better: ensure `RichOutput` is only used in CLI mode and document this.

#### Task 3.2: Verify DirectConsoleOutput Strategy Selection

**File:** `src/cli/unified_io.py`

**Analysis:** `DirectConsoleOutput` (line 821) creates `Console()`. This is correct for CLI mode but must verify it's never selected in TUI mode.

**Solution:** Add assertion/guard in UnifiedIO:
```python
def _ensure_correct_strategy(self):
    """Verify strategy matches mode."""
    if self._output_sink is not None:
        assert isinstance(self._output_strategy, OutputSinkAdapter), \
            "TUI mode must use OutputSinkAdapter, not DirectConsoleOutput"
```

#### Task 3.3: Fix Interactive Banner Fallback

**File:** `src/cli/interactive_banner.py`

**Problem:** Line 71 has fallback to `io.console.print()`

**Solution:** Ensure `output_sink` is always available in TUI mode, or route through IO methods:
```python
# Instead of:
if output_sink:
    output_sink.post_renderable(panel)
else:
    io.console.print(panel)

# Use:
io.panel(title, content)  # Let IO handle routing
```

---

### Phase 4: Fix Blocking Input Calls

#### Task 4.1: Fix output.py Input Methods

**File:** `src/cli/output.py`

**Problem:** Lines 186, 356 use blocking `input()`

**Analysis:** These methods in `RichOutput` will hang in TUI mode.

**Solution:** `RichOutput` should only be used in CLI mode. Add mode guard or remove input methods from `RichOutput` and use IO protocol instead.

#### Task 4.2: Fix unified_io.py Input Methods

**File:** `src/cli/unified_io.py`

**Problem:** Lines 514, 529 use `input()` in `DirectConsoleOutput`

**Analysis:** `DirectConsoleOutput` should only be selected in CLI mode.

**Solution:** This is likely already correct if strategy selection is mode-aware. Add guards:
```python
class DirectConsoleOutput:
    """CLI mode output strategy. DO NOT use in TUI mode."""

    def prompt(self, text: str, default: str = "") -> str:
        # This method should never be called in TUI mode
        # TUI mode uses OutputSinkAdapter.prompt() which routes through Textual
        result = self._console.input(text)
        return result or default
```

---

### Phase 5: Verification and Testing

#### Task 5.1: Create Mode Verification Test

**File:** `tests/test_output_mode_routing.py`

```python
"""Tests to verify output routing in TUI vs CLI mode."""

def test_tui_mode_uses_output_sink_adapter():
    """Verify TUI mode routes through OutputSinkAdapter."""
    from src.cli.unified_io import UnifiedIO
    from src.cli.textual_app import TextualOutputAdapter

    adapter = TextualOutputAdapter()
    io = UnifiedIO(output_sink=adapter)

    assert io.is_tui_mode
    # Verify output goes to adapter, not console

def test_cli_mode_uses_direct_console():
    """Verify CLI mode uses DirectConsoleOutput."""
    from src.cli.unified_io import UnifiedIO

    io = UnifiedIO(output_sink=None)

    assert not io.is_tui_mode

def test_progress_reporter_respects_mode():
    """Verify progress reporter creation respects mode."""
    # ...
```

#### Task 5.2: Create Integration Test for /agent in TUI

**File:** `tests/integration/test_agent_tui.py`

```python
"""Integration tests for agent command in TUI mode."""

async def test_agent_output_routes_to_textual():
    """Verify /agent output appears in Textual, not console."""
    # Mock TextualOutputAdapter
    # Run agent command
    # Verify output was posted to adapter, not printed
```

---

## Implementation Order

```
Phase 1 (Foundation) [COMPLETED 2025-11-26]
    |
    +-- 1.1 Add is_tui_mode to UnifiedIO [DONE]
    |
    +-- 1.2 Create mode_utils.py [DONE]
    |
    v
Phase 2 (Critical Fixes) [COMPLETED 2025-11-26]
    |
    +-- 2.1 Fix RichOutputHandler [DONE]
    +-- 2.2 Fix Progress Reporters [DONE]
    +-- 2.3 Fix RichDirectoryFormatter [DONE]
    +-- 2.4 Fix DefaultConsoleInput [DONE]
    |
    v
Phase 3 (High Priority) [COMPLETED 2025-11-26]
    |
    +-- 3.1 Audit RichOutput [DONE]
    +-- 3.2 Verify strategy selection [DONE]
    +-- 3.3 Fix banner fallback [DONE]
    |
    v
Phase 4 (Blocking Input) [COMPLETED 2025-11-26]
    |
    +-- 4.1 Fix output.py input [DONE]
    +-- 4.2 Verify unified_io.py input [DONE]
    |
    v
Phase 5 (Verification) [COMPLETED 2025-11-26]
    |
    +-- 5.1 Mode routing tests [DONE]
    +-- 5.2 Integration tests [DONE]
```

---

## Summary of Files to Modify

| File | Priority | Changes | Status |
|------|----------|---------|--------|
| `src/cli/unified_io.py` | P1 | Add `is_tui_mode` property | DONE |
| `src/cli/mode_utils.py` | P1 | New file for mode utilities | DONE |
| `src/task_router/output_handler.py` | P2 | Deprecate/fix RichOutputHandler | DONE |
| `src/infrastructure/progress.py` | P2 | Add factory for mode-aware progress | DONE |
| `src/agent_tools/formatters/output_formatter.py` | P2 | Remove default Console creation | DONE |
| `src/task_router/protocols.py` | P2 | Add IOBasedInput, document DefaultConsoleInput | DONE |
| `src/cli/output.py` | P3 | Document CLI-only usage | DONE |
| `src/cli/interactive_banner.py` | P3 | Fix fallback path | DONE |
| `tests/test_output_mode_routing.py` | P5 | New test file | DONE |
| `tests/integration/test_agent_tui.py` | P5 | New integration test file | DONE |

## Progress Log

### 2025-11-26: Phase 1 Completed

**Task 1.1: Added `is_tui_mode` property to UnifiedIO**
- Location: `src/cli/unified_io.py:828-839`
- Returns `True` when `output_sink` is not `None`
- Single source of truth for mode detection

**Task 1.2: Created `mode_utils.py` utility module**
- New file: `src/cli/mode_utils.py`
- `is_tui_mode(io)` - Safely checks if IO is in TUI mode
- `get_output_sink(io)` - Gets the OutputSink if in TUI mode

**Tests Added**
- 8 new tests in `tests/cli/test_unified_io.py`
- All 50 tests pass

### 2025-11-26: Phase 2 Completed

**Task 2.1: Fixed RichOutputHandler**
- Added CLI-only warning documentation
- Created `create_output_handler(io, rich_tables)` factory function
- Factory returns CLIIOOutputHandler in TUI mode, RichOutputHandler only in CLI mode with rich_tables=True

**Task 2.2: Fixed Progress Reporters**
- Added CLI-only warning documentation to RichProgressReporter and LiveProgressReporter
- Created `create_progress_reporter(io, use_live, use_spinner)` factory function
- Factory returns UnifiedIOProgressReporter in TUI mode

**Task 2.3: Documented RichDirectoryFormatter**
- Clarified that RichDirectoryFormatter only uses Console for string rendering (via capture())
- It does NOT output to console directly, so it's safe for both CLI and TUI modes
- Added documentation explaining the rendering-only usage

**Task 2.4: Added IOBasedInput**
- Added CLI-only warning documentation to DefaultConsoleInput
- Created `IOBasedInput` class that delegates to CLIIOProtocol
- Created `create_task_router_input(io)` factory function
- Factory returns IOBasedInput when io is provided, DefaultConsoleInput as fallback

**Tests Verified**
- 93 tests pass for modified files
- 158 protocol conformance tests pass (7 skipped)
- No regressions introduced

### 2025-11-26: Phase 3 Completed

**Task 3.1: Documented RichOutput as CLI-only**
- Location: `src/cli/output.py:288-305`
- Added comprehensive CLI-only warning documentation
- Documented that class creates its own Console and outputs directly to stdout
- Listed alternatives for TUI-compatible output (UnifiedIO, CLIIOProtocol)
- Also added warning to `input_line()` method about blocking behavior

**Task 3.2: Verified strategy selection in UnifiedIO**
- Location: `src/cli/unified_io.py:392-404`
- Strategy selection logic is correct: DirectConsoleOutput only when output_sink is None
- Added CLI-only warning documentation to DirectConsoleOutput class
- Documented that input methods use blocking calls unsuitable for TUI

**Task 3.3: Fixed interactive_banner.py fallback path**
- Location: `src/cli/interactive_banner.py:66-76`
- Changed from checking `output_sink` directly to using `is_tui_mode` property
- `is_tui_mode` is the single source of truth for mode detection
- Updated comments to clarify routing logic

**Tests Verified**
- 65 tests pass in test_unified_io.py and test_output_interface.py
- 24 protocol conformance tests pass (1 skipped)
- 765 task_router and infrastructure tests pass
- No regressions introduced

### 2025-11-26: Phase 4 Completed

**Task 4.1: Added CLI-only warnings to RichOutput input methods**
- Location: `src/cli/output.py:365-401`
- Added method-level CLI-only warnings to `prompt()` and `confirm()` methods
- Warnings explain blocking behavior and point to TUI alternatives
- `input_line()` in PlainOutput already had warnings from earlier work

**Task 4.2: Added CLI-only warnings to DirectConsoleOutput input methods**
- Location: `src/cli/unified_io.py:508-553`
- Added method-level CLI-only warnings to `input_prompt()`, `input_confirm()`, and `input_line()`
- Warnings explain blocking behavior and point to OutputSinkAdapter alternatives
- Class-level warning was already added in Phase 3

**Tests Verified**
- 50 tests pass in test_unified_io.py
- 15 tests pass in test_output_interface.py
- No regressions introduced

### 2025-11-26: Phase 5 Completed

**Task 5.1: Created mode routing unit tests**
- New file: `tests/test_output_mode_routing.py`
- 28 tests covering:
  - Mode detection utilities (is_tui_mode, get_output_sink)
  - Progress reporter factory mode selection
  - Output handler factory mode selection
  - TUI output routing through OutputSink
  - CLI mode direct output
  - Progress reporter and output handler TUI behavior

**Task 5.2: Created agent TUI integration tests**
- New file: `tests/integration/test_agent_tui.py`
- 12 tests covering:
  - Agent output routing through TUI sink
  - Styled output and panel routing
  - Progress reporter mode-aware selection
  - Output handler mode-aware selection
  - CLI mode compatibility
  - Verification that TUI mode never outputs directly to console

**Tests Verified**
- 28 mode routing tests pass
- 12 integration tests pass
- No regressions in existing tests

---

## Implementation Complete

All phases have been completed successfully. The unified TUI/CLI output routing system is now in place with:

1. Mode detection via `is_tui_mode` property on UnifiedIO
2. Factory functions that select appropriate implementations
3. CLI-only warnings on blocking input methods
4. Comprehensive test coverage

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Breaking CLI mode while fixing TUI | High | Run all CLI tests after each change |
| Circular imports from mode checking | Medium | Use TYPE_CHECKING and late imports |
| Performance impact from mode checks | Low | Mode check is simple property access |
| Missing edge cases | Medium | Comprehensive grep for print/Console |

---

## Definition of Done

1. All `print()` calls in agent execution path route through IO
2. All `Console()` instantiations either inject or are CLI-only
3. All `input()` calls either route through IO or are CLI-only
4. `/agent` command in Textual displays output in TUI (not console)
5. Progress indicators display in TUI correctly
6. All existing tests pass
7. New tests verify mode routing
