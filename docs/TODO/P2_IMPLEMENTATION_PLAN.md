# P2 Issues Implementation Plan

This document outlines the implementation plan for all Priority 2 (High Impact UX) issues from `ISSUES_PRIORITIZED.md`.

---

## Overview

| Issue | Summary | Complexity | Dependencies |
|-------|---------|------------|--------------|
| 2.1 | Prompt/Question Not Near Input | Low | Reuse existing status bar |
| 2.2 | Tool Output Poor UX | Low | ToolResult.__str__ + __rich__ |
| 2.3 | Command History Navigation | Medium | prompt_toolkit integration |
| 2.4 | /cache Command Output Broken | Low | Use io.table() |

**Recommended Order:** 2.2 -> 2.4 -> 2.1 -> 2.3

Rationale: Start with simpler fixes (2.2, 2.4) to build momentum, then tackle UI restructuring (2.1), finally input system overhaul (2.3).

---

## Issue 2.1: Prompt/Question Not Near Input

### Problem
- Question text ("Allow this action?") is written to scrollable RichLog at top
- Input prompt is fixed at bottom
- Gap grows with conversation length, confusing users

### Current Architecture
```
textual_app.py:770-795
  _update_capture_ui() writes prompt to RichLog

scrappy.tcss
  #output_container { height: 1fr; }  <- scrollable
  #input_container { height: auto; }  <- fixed bottom
```

### Solution Design

**Reuse the existing status bar** (currently unused) for prompts. This avoids creating a new widget and leverages existing infrastructure.

**Layout After Fix:**
```
+----------------------------------------+
|        RichLog (SCROLLABLE)            |
|  - Conversation history                |
+----------------------------------------+
| > [Input here]                         |
+----------------------------------------+
| [Status Bar: Question text] [y/n]      |
+----------------------------------------+
```

**Future Consideration:** When progress indicators are added later, the status bar can either:
- Share space (prompts take priority over progress)
- Split into zones (left: progress, right: prompt)

### Files to Modify

| File | Change |
|------|--------|
| `src/cli/textual_app.py:770-795` | Update `_update_capture_ui()` to use status bar |
| `src/cli/scrappy.tcss` | Update status bar styles for prompt display |
| `tests/cli/test_textual_app.py` | Add tests for prompt in status bar |

### Implementation Steps

1. **Add methods to status bar controller** (wherever status bar is managed)
   ```python
   def show_prompt(self, message: str, input_type: str, default: Optional[str] = None) -> None:
       """Display prompt message in status bar."""
       hint = " [y/n]" if input_type == "confirm" else ""
       default_hint = f" (default: {default})" if default else ""
       self.status_bar.update(f"{message}{hint}{default_hint}")
       self.status_bar.add_class("prompt-mode")

   def hide_prompt(self) -> None:
       """Clear prompt from status bar."""
       self.status_bar.update("")
       self.status_bar.remove_class("prompt-mode")
   ```

2. **Update TCSS** (src/cli/scrappy.tcss)
   ```css
   /* Status bar in prompt mode */
   #status_bar.prompt-mode {
       background: $panel-bg;
       color: #ffcc00;
       border-top: solid $accent;
   }
   ```

3. **Update _update_capture_ui()** (src/cli/textual_app.py)
   - Replace RichLog writes with status bar method calls
   - Call `show_prompt()` when entering capture mode
   - Call `hide_prompt()` when exiting capture mode

4. **Tests**
   - Test prompt visibility toggle
   - Test message formatting for confirm vs text input
   - Test default value display

### SOLID Compliance

- **SRP**: Status bar gains prompt responsibility (acceptable - still UI status)
- **OCP**: Adding methods, not modifying existing behavior
- **LSP**: N/A (no inheritance)
- **ISP**: Minimal new interface surface
- **DIP**: N/A (simple widget update)

---

## Issue 2.2: Tool Output Poor UX

### Problem
- `str(ToolResult(...))` uses default `__repr__()`
- Shows `ToolResult(success=True, output='Line 1\\nLine 2')`
- Newlines escaped as `\\n` literals

### Current Code
```python
# tool_runner.py:75
result = self.tools[tool_name](**parameters)
return str(result)  # Uses __repr__, escapes newlines

# base.py:95-102
@dataclass
class ToolResult:
    success: bool
    output: str
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    # No __str__ method
```

### Solution Design

Add both `__str__()` and `__rich__()` methods to `ToolResult` for proper display with syntax highlighting:

```python
from rich.syntax import Syntax
from rich.panel import Panel
from rich.text import Text
from typing import Union

@dataclass
class ToolResult:
    success: bool
    output: str
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def __str__(self) -> str:
        """Plain text fallback."""
        if self.error:
            return f"Error: {self.error}"
        return self.output

    def __rich__(self) -> Union[Panel, Text, Syntax]:
        """Rich-compatible rendering with syntax highlighting."""
        if self.error:
            return Text(f"Error: {self.error}", style="bold red")

        # Detect language from metadata or content
        language = self.metadata.get("language", "text")
        if language != "text" and "\n" in self.output:
            return Syntax(self.output, language, theme="monokai", line_numbers=True)

        return Text(self.output)
```

Rich's console automatically calls `__rich__()` when printing, providing:
- Syntax highlighting for code output
- Styled error messages
- Graceful fallback for plain text

### Files to Modify

| File | Change |
|------|--------|
| `src/agent_tools/tools/base.py:95-102` | Add `__str__()` and `__rich__()` methods |
| `tests/agent_tools/test_base.py` | Add tests for both methods |

### Implementation Steps

1. **Add imports** (src/agent_tools/tools/base.py)
   ```python
   from rich.syntax import Syntax
   from rich.text import Text
   from typing import Union
   ```

2. **Add __str__ to ToolResult** (src/agent_tools/tools/base.py)
   ```python
   def __str__(self) -> str:
       """Return human-readable output for display.

       Returns error message if present, otherwise the output string.
       This avoids escaped newlines and dataclass repr noise.
       """
       if self.error:
           return f"Error: {self.error}"
       return self.output
   ```

3. **Add __rich__ to ToolResult** (src/agent_tools/tools/base.py)
   ```python
   def __rich__(self) -> Union[Text, Syntax]:
       """Rich-compatible rendering with syntax highlighting.

       Rich's console automatically calls this when printing.
       """
       if self.error:
           return Text(f"Error: {self.error}", style="bold red")

       # Detect language from metadata
       language = self.metadata.get("language", "text")

       # Use syntax highlighting for code with multiple lines
       if language != "text" and "\n" in self.output:
           return Syntax(
               self.output,
               language,
               theme="monokai",
               line_numbers=True
           )

       return Text(self.output)
   ```

4. **Tests** (tests/agent_tools/test_base.py)
   ```python
   def test_tool_result_str_returns_output():
       result = ToolResult(success=True, output="Line 1\nLine 2")
       assert str(result) == "Line 1\nLine 2"
       assert "ToolResult" not in str(result)

   def test_tool_result_str_with_error():
       result = ToolResult(success=False, output="", error="Something failed")
       assert str(result) == "Error: Something failed"

   def test_tool_result_str_preserves_newlines():
       result = ToolResult(success=True, output="a\nb\nc")
       assert str(result).count("\n") == 2

   def test_tool_result_rich_returns_text_for_plain():
       result = ToolResult(success=True, output="plain text")
       rich_output = result.__rich__()
       assert isinstance(rich_output, Text)

   def test_tool_result_rich_returns_syntax_for_code():
       result = ToolResult(
           success=True,
           output="def foo():\n    pass",
           metadata={"language": "python"}
       )
       rich_output = result.__rich__()
       assert isinstance(rich_output, Syntax)

   def test_tool_result_rich_returns_styled_error():
       result = ToolResult(success=False, output="", error="Failed")
       rich_output = result.__rich__()
       assert isinstance(rich_output, Text)
       assert "bold red" in str(rich_output.style)
   ```

### SOLID Compliance

- **SRP**: `__str__` handles plain text, `__rich__` handles formatted output
- **OCP**: Adding methods, not modifying existing behavior
- **LSP**: Doesn't break existing `ToolResult` usage
- **ISP**: N/A (dataclass, not protocol)
- **DIP**: N/A (value object)

---

## Issue 2.3: Command History Navigation

### Problem
- No up/down arrow history navigation
- Click's `prompt()` uses `input()` with no history support
- User choices (y, Y, n, N, 1, 2, 3) should be excluded 
- -- MAYBE CONFIRMATION_RESPONSES ISNT NEEDED - EG: input > MIN_MEANINGFUL_LENGTH (includes the subset)

### Current Code
```python
# output.py:462
return self._click.prompt(text, default=default)  # No history support

# input_handler.py - No history storage or navigation
```

### Solution Design

**Protocol-First Approach with Injectable Filter:**

```python
# New protocol in src/cli/protocols.py
class InputHistoryProtocol(Protocol):
    """Contract for input history management."""

    def add(self, entry: str) -> None:
        """Add entry to history (filters short entries)."""
        ...

    def get_previous(self) -> Optional[str]:
        """Get previous history entry (up arrow)."""
        ...

    def get_next(self) -> Optional[str]:
        """Get next history entry (down arrow)."""
        ...

    def reset_position(self) -> None:
        """Reset navigation position to end."""
        ...
```

**Implementation Options:**

| Option | Pros | Cons |
|--------|------|------|
| A: prompt_toolkit | Full readline, native history | New dependency |
| B: In-memory + manual arrow keys | No new deps | Complex key handling |
| C: Leverage Textual Input | Already using Textual | TUI mode only |

**Recommended: Option A (prompt_toolkit)**

Textual already depends on prompt_toolkit internally. Add explicit dependency for CLI mode.

### Files to Modify

| File | Change |
|------|--------|
| `pyproject.toml` | Add `prompt-toolkit>=3.0.0` |
| `src/cli/protocols.py` | Add `InputHistoryProtocol` |
| `src/cli/input_history.py` | New file: `InputHistory` implementation |
| `src/cli/input_handler.py` | Inject history, use for prompts |
| `src/cli/output.py:456-462` | Update prompt to use prompt_toolkit |
| `tests/cli/test_input_history.py` | History behavior tests |

### Implementation Steps

1. **Add Dependency** (pyproject.toml)
   ```toml
   dependencies = [
       ...
       "prompt-toolkit>=3.0.0",
   ]
   ```

2. **Define Protocol** (src/cli/protocols.py)
   ```python
   class InputHistoryProtocol(Protocol):
       """Contract for input history with filtering."""

       def add(self, entry: str) -> None:
           """Add entry if it passes filter (not y/n/number)."""
           ...

       def get_previous(self) -> Optional[str]:
           """Navigate backwards in history."""
           ...

       def get_next(self) -> Optional[str]:
           """Navigate forwards in history."""
           ...

       def reset_position(self) -> None:
           """Reset to end of history."""
           ...

       def save(self) -> None:
           """Persist history to disk."""
           ...

       def load(self) -> None:
           """Load history from disk."""
           ...
   ```

3. **Create Implementation with Injectable Filter** (src/cli/input_history.py)
   ```python
   from pathlib import Path
   from typing import Optional, List, Callable

   class InputHistory:
       """Input history with filtering and persistence.

       Uses injectable filter function for testability and extensibility.
       Default filter excludes:
       - Confirmation responses (y, n, yes, no)
       - Numeric menu selections (1, 2, 3, etc.)
       - Very short inputs (< 3 chars)
       """

       # Named constants instead of magic regex
       CONFIRMATION_RESPONSES = frozenset({'y', 'n', 'yes', 'no'})
       MIN_MEANINGFUL_LENGTH = 3

       def __init__(
           self,
           history_file: Optional[Path] = None,
           max_entries: int = 1000,
           filter_func: Optional[Callable[[str], bool]] = None,
       ):
           self._history: List[str] = []
           self._position: int = 0
           self._history_file = history_file or Path.home() / ".scrappy_history"
           self._max_entries = max_entries
           self._should_store = filter_func or self._default_filter

       def _default_filter(self, entry: str) -> bool:
           """Returns True if entry should be stored in history.

           Filters out confirmations, menu selections, and short inputs.
           """
           entry = entry.strip().lower()

           # Too short to be meaningful
           if len(entry) < self.MIN_MEANINGFUL_LENGTH:
               return False

           # Confirmation responses
           if entry in self.CONFIRMATION_RESPONSES:
               return False

           # Numeric menu selections
           if entry.isdigit():
               return False

           return True

       def add(self, entry: str) -> None:
           """Add entry to history if it passes filter."""
           entry = entry.strip()
           if not entry or not self._should_store(entry):
               return

           # Avoid duplicates at end
           if self._history and self._history[-1] == entry:
               return

           self._history.append(entry)

           # Trim if over max
           if len(self._history) > self._max_entries:
               self._history = self._history[-self._max_entries:]

           self._position = len(self._history)

       def get_previous(self) -> Optional[str]:
           """Get previous entry (up arrow)."""
           if not self._history or self._position <= 0:
               return None
           self._position -= 1
           return self._history[self._position]

       def get_next(self) -> Optional[str]:
           """Get next entry (down arrow)."""
           if self._position >= len(self._history) - 1:
               self._position = len(self._history)
               return None
           self._position += 1
           return self._history[self._position]

       def reset_position(self) -> None:
           """Reset to end of history."""
           self._position = len(self._history)

       def save(self) -> None:
           """Persist history to disk."""
           self._history_file.parent.mkdir(parents=True, exist_ok=True)
           self._history_file.write_text("\n".join(self._history[-self._max_entries:]))

       def load(self) -> None:
           """Load history from disk."""
           if self._history_file.exists():
               content = self._history_file.read_text()
               self._history = [line for line in content.split("\n") if line.strip()]
               self._position = len(self._history)
   ```

4. **Integrate with prompt_toolkit** (src/cli/output.py)
   ```python
   from prompt_toolkit import PromptSession
   from prompt_toolkit.history import FileHistory

   class PromptToolkitOutput(FormattedOutputInterface):
       """Output implementation using prompt_toolkit for input."""

       def __init__(self, history_file: Optional[str] = None):
           self._session = PromptSession(
               history=FileHistory(history_file or str(Path.home() / ".scrappy_history"))
           )

       def prompt(self, text: str, default: str = "") -> str:
           """Get user input with history support."""
           return self._session.prompt(text, default=default)
   ```

5. **Update InputHandler** (src/cli/input_handler.py)
   - Accept `InputHistoryProtocol` via constructor
   - Call `history.add()` after getting input
   - Use prompt_toolkit session for actual input

6. **Tests** (tests/cli/test_input_history.py)
   ```python
   def test_filters_single_char_responses():
       history = InputHistory()
       history.add("y")
       history.add("n")
       history.add("Y")
       assert history.get_previous() is None

   def test_filters_numeric_responses():
       history = InputHistory()
       history.add("1")
       history.add("123")
       assert history.get_previous() is None

   def test_stores_real_commands():
       history = InputHistory()
       history.add("/help")
       history.add("explain this code")
       assert history.get_previous() == "explain this code"
       assert history.get_previous() == "/help"

   def test_navigation_wraps_correctly():
       history = InputHistory()
       history.add("first")
       history.add("second")
       assert history.get_previous() == "second"
       assert history.get_previous() == "first"
       assert history.get_previous() is None  # At start
       assert history.get_next() == "second"

   def test_custom_filter_function():
       # Custom filter that only stores commands starting with /
       custom_filter = lambda entry: entry.startswith("/")
       history = InputHistory(filter_func=custom_filter)

       history.add("/help")
       history.add("regular text")
       history.add("/status")

       assert history.get_previous() == "/status"
       assert history.get_previous() == "/help"
       assert history.get_previous() is None
   ```

### SOLID Compliance

- **SRP**: `InputHistory` only manages history, prompt_toolkit handles input
- **OCP**: New implementation, existing code unchanged; filter is injectable for extension
- **LSP**: Implements `InputHistoryProtocol`
- **ISP**: Protocol has focused interface
- **DIP**: InputHandler depends on protocol, not concrete class

---

## Issue 2.4: /cache Command Output Broken

### Problem
- ANSI codes displayed as literal text: `[36m[1m Cache Statistics:[0m`
- `CacheFormatter` embeds `click.style()` codes in strings
- `io.echo()` doesn't interpret embedded ANSI codes properly

### Current Code
```python
# cache_formatter.py:54
parts.append(self.format_header("Cache Statistics:"))  # Contains ANSI

# cache_manager.py:95
formatted_stats = self.formatter.format_stats(stats, enabled)
self.io.echo(formatted_stats)  # ANSI codes become literal text
```

### Solution Design

**Option A: Return structured data, use io.table()**
- Already works correctly (see `/usage` command)
- Consistent with other commands

**Option B: Fix formatter to return Rich-compatible objects**
- More complex, less benefit

**Recommended: Option A**

Refactor `CacheFormatter` to return structured data, use `io.table()` in `CacheManager`.

### Files to Modify

| File | Change |
|------|--------|
| `src/infrastructure/formatters/cache_formatter.py` | Return structured data |
| `src/cli/cache_manager.py:90-95` | Use `io.table()` |
| `tests/infrastructure/formatters/test_cache_formatter.py` | Update assertions |

### Implementation Steps

1. **Update CacheFormatter Protocol** (src/infrastructure/formatters/protocols.py or inline)
   ```python
   from typing import List, Tuple, Dict, Any

   class CacheFormatterProtocol(Protocol):
       def get_stats_data(
           self,
           stats: Dict[str, Any],
           enabled: bool
       ) -> Tuple[List[str], List[List[str]], str]:
           """Return (headers, rows, title) for table display."""
           ...
   ```

2. **Refactor CacheFormatter** (src/infrastructure/formatters/cache_formatter.py)
   ```python
   from typing import List, Tuple, Dict, Any

   class CacheFormatter(StatsFormatter):
       """Formatter for cache statistics displays."""

       def get_stats_data(
           self,
           stats: Dict[str, Any],
           enabled: bool
       ) -> Tuple[List[str], List[List[str]], str]:
           """Return structured data for table display.

           Returns:
               Tuple of (headers, rows, title) for io.table()
           """
           headers = ["Metric", "Value"]

           total_entries = stats.get('exact_cache_entries', 0) + stats.get('intent_cache_entries', 0)

           rows = [
               ["Total Entries", str(total_entries)],
               ["Exact Cache Hits", str(stats.get('exact_hits', 0))],
               ["Intent Cache Hits", str(stats.get('intent_hits', 0))],
               ["Cache Misses", str(stats.get('exact_misses', 0))],
               ["Cache Saves", str(stats.get('saves', 0))],
               ["Exact Hit Rate", stats.get('exact_hit_rate', '0.0%')],
               ["Intent Hit Rate", stats.get('intent_hit_rate', '0.0%')],
               ["Cache File", stats.get('cache_file', 'N/A')],
               ["Status", "Enabled" if enabled else "Disabled"],
           ]

           return headers, rows, "Cache Statistics"

       # Keep format_stats for backwards compatibility if needed
       def format_stats(self, stats: Dict[str, Any], enabled: bool) -> str:
           """Legacy method - returns plain text without ANSI codes."""
           headers, rows, title = self.get_stats_data(stats, enabled)
           lines = [title, "-" * 40]
           for row in rows:
               lines.append(f"{row[0]}: {row[1]}")
           return "\n".join(lines)
   ```

3. **Update CacheManager** (src/cli/cache_manager.py)
   ```python
   def manage_cache(self, args: str = "") -> None:
       # ... validation ...

       if validation.subcommand == "":
           stats = self.orchestrator.get_cache_stats()
           enabled = self.orchestrator.caching_enabled

           # Use structured data with io.table()
           headers, rows, title = self.formatter.get_stats_data(stats, enabled)
           self.io.table(headers, rows, title=title)

       # ... rest unchanged ...
   ```

4. **Tests**
   ```python
   def test_get_stats_data_returns_structured_format():
       formatter = CacheFormatter()
       stats = {
           'exact_cache_entries': 10,
           'intent_cache_entries': 5,
           'exact_hits': 3,
           'intent_hits': 2,
           'exact_misses': 5,
           'saves': 8,
           'exact_hit_rate': '37.5%',
           'intent_hit_rate': '28.6%',
           'cache_file': '/path/to/cache.json'
       }

       headers, rows, title = formatter.get_stats_data(stats, enabled=True)

       assert headers == ["Metric", "Value"]
       assert title == "Cache Statistics"
       assert len(rows) == 9
       assert ["Total Entries", "15"] in rows
       assert ["Status", "Enabled"] in rows

   def test_format_stats_no_ansi_codes():
       formatter = CacheFormatter(use_color=False)
       stats = {'exact_cache_entries': 0, 'intent_cache_entries': 0}
       result = formatter.format_stats(stats, enabled=True)
       assert "[36m" not in result
       assert "[0m" not in result
   ```

### SOLID Compliance

- **SRP**: Formatter returns data, CacheManager handles display
- **OCP**: Adding new method, keeping old for compatibility
- **LSP**: Still implements `CacheFormatterProtocol`
- **ISP**: Protocol remains focused
- **DIP**: CacheManager depends on protocol

---

## Testing Strategy

### Unit Tests (per issue)

| Issue | Test File | Key Tests |
|-------|-----------|-----------|
| 2.1 | `tests/cli/test_textual_app.py` | status bar prompt visibility, message formatting |
| 2.2 | `tests/agent_tools/test_base.py` | __str__ output, __rich__ rendering, error handling |
| 2.3 | `tests/cli/test_input_history.py` | filtering, navigation, persistence, custom filter |
| 2.4 | `tests/infrastructure/formatters/test_cache_formatter.py` | structured data, no ANSI |

### Integration Tests

```python
# tests/cli/test_cache_integration.py
def test_cache_command_displays_table(test_io):
    """Verify /cache displays as table without ANSI artifacts."""
    cache_mgr = CacheManager(mock_orchestrator, test_io)
    cache_mgr.manage_cache("")

    output = test_io.get_output()
    assert "Cache Statistics" in output
    assert "[36m" not in output  # No raw ANSI
```

---

## Risk Assessment

| Issue | Risk | Mitigation |
|-------|------|------------|
| 2.1 | Layout regression | Test on multiple terminal sizes |
| 2.2 | Breaks tools relying on repr | Search for `repr(ToolResult)` usage |
| 2.3 | prompt_toolkit conflicts | Already dependency of Textual |
| 2.4 | Backwards compatibility | Keep `format_stats()` method |

---

## Summary

| Issue | Effort | Impact | Files Changed |
|-------|--------|--------|---------------|
| 2.1 Prompt Near Input | Low | High | 2-3 files |
| 2.2 Tool Output | Low | Medium-High | 2 files |
| 2.3 History Navigation | Medium | High | 5-6 files |
| 2.4 Cache Output | Low | Medium | 2-3 files |

**Total Estimated Files:** 10-12 files
**New Files:** 1 (input_history)
