# Prioritized Issues

---

## PRIORITY 1: Critical / Blocking Issues

IF USER SELECTS NO, WE SHOULD BREAK CYCLE NOT CONTINUE. 
WE SHOULD REPROMPT FOR USER INPUT OR SIMPLY BREAK.

### 1.1 Agent Keeps Trying After User Declines
**Status:** CONFIRMED - BY DESIGN (but may not match user expectations)
**Impact:** Blocking - users cannot stop unwanted actions
**Location:** `src/agent/agent_loop.py:466-483`, `src/agent/action_executor.py:98-106`

**Problem:** Agent continues attempting changes after user answers "no" to approval prompt.

**Root Cause Analysis (Code Review Completed):**

The agent loop is designed to continue after denial:

1. **User denies action** in `action_executor.py:98-106`:
   ```python
   if not self._check_safety_and_get_approval(action, state):
       return ActionResult(
           success=False,
           output="Action denied by user",
           approved=False,
           executed=False
       )
   ```

2. **Denial handling** in `agent_loop.py:466-483` (`_handle_denied_action`):
   ```python
   state.messages.append({
       'role': 'user',
       'content': (
           f"User denied the {result.action} action. "
           "Please try a different approach or explain why this action is necessary."
       ),
   })
   ```
   This explicitly tells the agent to retry with a different approach.

3. **Loop continues** in `agent_loop.py:621-656` - no exit condition for denied actions.

**Partial Safety Net:** Duplicate detector (`action_executor.py:108-119`) catches exact repeats but NOT variations.

**Missing Test Coverage:** No tests for denied action flow in `tests/agent/test_agent_loop.py`.

**Solution Options:**
1. **Add explicit exit option:** When user denies, offer "Stop task entirely? [y/n]"
2. **Track denial count:** After N denials of similar actions, auto-stop
3. **Change default behavior:** Make denial stop the loop (breaking change)

**Files to modify:**
- `src/agent/agent_loop.py` - Add exit condition in `_handle_denied_action()`
- `src/agent/action_executor.py` - Add "stop entirely" option after denial
- `tests/agent/test_agent_loop.py` - Add test coverage for denial flow

---

### 1.2 Duplicate Audit Logs Created Outside .scrappy/
**Status:** CONFIRMED (Code Review Completed)
**Impact:** High - data scattered, potential data loss
**Location:** `src/agent/core.py:764`, `src/agent/audit.py`, `src/cli/commands.py:499`, `src/cli/agent_manager.py:145`

**Problem:** Two audit logs created:
- `.agent_audit.json` (root directory) - from hardcoded default
- `.scrappy/audit.json` (correct location) - from auto-save via path_provider

**Root Cause Analysis (Code Review Completed):**

1. **Hardcoded default** in `core.py:764`:
   ```python
   def save_audit_log(self, path: str = ".agent_audit.json"):
       return self._audit_logger.save(self.project_root, path)
   ```

2. **Auto-save uses correct path** in `audit.py:46-64` (`enable_auto_save`):
   - Uses `self._path_provider.audit_file()` -> `.scrappy/audit.json`

3. **Manual save ignores path_provider** in `commands.py:499` and `agent_manager.py:145`:
   ```python
   log_path = code_agent.save_audit_log()  # Uses hardcoded default
   ```

4. **Result:** Auto-save writes to `.scrappy/audit.json`, manual save writes to `.agent_audit.json`

**Code Flow:**
```
run() -> enable_auto_save() -> .scrappy/audit.json (correct)
save_audit_log() -> .agent_audit.json (hardcoded default)
```

**Solution:**
1. **Remove hardcoded default** in `core.py:764`:
   ```python
   def save_audit_log(self) -> str:
       return self._audit_logger.save()  # Uses path_provider
   ```
2. **Update `audit.py`** `save()` method to work with no arguments when path_provider is set
3. **Update `examples/agent_demo.py:284`** to call `save_audit_log()` without arguments

**Files to modify:**
- `src/agent/core.py:764` - Remove default parameter
- `src/agent/audit.py` - Ensure `save()` works without arguments
- `examples/agent_demo.py:284` - Remove explicit path argument

---

### 1.3 Multiline Input Not Supported
**Status:** CONFIRMED (Code Review Completed)
**Impact:** High - blocks common workflows (pasting code/prompts)
**Location:** `src/cli/input_handler.py:86-145`, `src/cli/output.py:456-462`

**Problem:** Users cannot paste multiline content - each line runs as separate command. Right-click paste may not work on Windows.

**Root Cause Analysis (Code Review Completed):**

1. **Input library:** Click 8.3.0 via `io.prompt()` (output.py:462)
   - Click's `prompt()` uses standard `input()` with no multiline support
   - No readline integration for paste detection

2. **Multiline mode logic** in `input_handler.py:96-130`:
   ```python
   if not line.rstrip().endswith("\\"):
       lines.append(line)
       break  # PROBLEM: Breaks after first line without continuation marker
   ```
   - Requires explicit `\` continuation marker
   - No detection of pasted vs. typed input
   - Pasted lines arrive faster than stdin can read them

3. **Windows right-click paste:**
   - Windows Terminal paste buffer not exposed to stdin properly
   - Click has no native clipboard integration

4. **Textual TUI mode** (textual_app.py:540) handles paste correctly:
   - Native Input widget supports clipboard paste
   - Ctrl+V and right-click work in TUI mode

**Current Workarounds:**
- Use `\` at end of each line for multiline
- Use Textual TUI mode (better paste support)

**Solution Options:**
1. **Switch to prompt_toolkit** for better readline/paste support:
   ```python
   from prompt_toolkit import PromptSession
   from prompt_toolkit.history import FileHistory
   session = PromptSession(history=FileHistory('~/.scrappy_history'))
   ```
2. **Detect stdin buffer** - Check if more data is available before breaking
3. **Default to TUI mode** - Textual already handles paste correctly

**Files to modify:**
- `src/cli/input_handler.py:96-130` - Add paste detection or prompt_toolkit
- `src/cli/output.py:456-462` - Replace Click prompt with prompt_toolkit
- Consider adding `pyreadline3` or `prompt_toolkit` to requirements

---

## PRIORITY 2: High Impact UX Issues

### 2.1 Prompt/Question Not Near Input
**Status:** CONFIRMED (Code Review Completed)
**Impact:** High - confusing UX, suggestions look like placeholders
**Location:** `src/cli/textual_app.py:750-795`, `src/cli/scrappy.tcss`

**Problem:**
- Question text ("Allow this action?") is far from input area
- Suggestions like "Type y or n..." look like placeholder text
- Input prompt is at bottom, context is at top

**Root Cause Analysis (Code Review Completed):**

1. **Layout architecture** in `scrappy.tcss`:
   ```css
   #output_container { height: 1fr; }  /* Scrollable, takes all space */
   #input_container { height: auto; }  /* Fixed at bottom */
   ```

2. **Prompt written to RichLog** in `textual_app.py:770-795`:
   ```python
   def _update_capture_ui(self, request):
       output = self.query_one("#output", RichLog)
       if request.input_type == "confirm":
           output.write(f"{request.message} [y/n]")  # Written to scrollable area
       self._input.focus()
   ```

3. **Result:** Prompt is in scrollable RichLog (top), input is fixed at bottom. Gap grows with conversation length.

**Layout Diagram:**
```
+----------------------------------------+
|        RichLog (SCROLLABLE)            |
|  - Conversation history                |
|  - [Question text here] [y/n]  <- FAR  |
+----------------------------------------+
| > [Input here]                 <- HERE |
+----------------------------------------+
```

**Solution Options:**
1. **Create prompt area widget** between output and input containers
2. **Floating/overlay prompt** that appears above input field
3. **Status bar integration** - show prompt in status bar area

**Files to modify:**
- `src/cli/textual_app.py:770-795` - Change where prompt is written
- `src/cli/scrappy.tcss` - Add prompt area styling
- Consider new widget class for inline prompts

---

### 2.2 Tool Output Poor UX
**Status:** CONFIRMED (Code Review Completed)
**Impact:** Medium-High - hard to read tool results
**Location:** `src/agent/tool_runner.py:73-77`, `src/agent_tools/tools/base.py:95-102`

**Problem:** Tool output shows raw `ToolResult(success=True, output='...')` format with escaped newlines.

**Root Cause Analysis (Code Review Completed):**

1. **ToolResult dataclass** in `base.py:95-102`:
   ```python
   @dataclass
   class ToolResult:
       success: bool
       output: str
       error: Optional[str] = None
       metadata: dict = field(default_factory=dict)
   ```
   No custom `__str__()` method - uses default `__repr__()`.

2. **String conversion** in `tool_runner.py:75`:
   ```python
   result = self.tools[tool_name](**parameters)
   return str(result)  # Uses __repr__, escapes newlines
   ```

3. **Result:** `str(ToolResult(...))` produces:
   ```
   ToolResult(success=True, output='Line 1\\nLine 2\\nLine 3', ...)
   ```
   Newlines become `\\n` literals.

**Solution:**
```python
# In tool_runner.py:75
if isinstance(result, ToolResult):
    return result.output  # Extract actual output
return str(result)
```

Or add `__str__()` to ToolResult:
```python
def __str__(self) -> str:
    return self.output
```

**Files to modify:**
- `src/agent/tool_runner.py:75` - Extract `.output` instead of `str(result)`
- OR `src/agent_tools/tools/base.py:95-102` - Add `__str__()` method

---

### 2.3 Command History Navigation
**Status:** CONFIRMED (Code Review Completed)
**Impact:** Medium-High - common expected feature missing
**Location:** `src/cli/input_handler.py`, `src/cli/output.py:456-462`, `src/cli/session_context.py`

**Problem:**
- No up/down arrow history navigation
- User choices (y, Y, n, N, 1, 2, 3) should be excluded from history

**Root Cause Analysis (Code Review Completed):**

1. **No readline integration** - Click's `prompt()` uses `input()`:
   ```python
   # output.py:462
   return self._click.prompt(text, default=default)  # No history support
   ```

2. **Conversation history exists** but not for input history:
   - `session_context.py:23-29` - Stores chat messages, not command history
   - No `~/.scrappy_history` file
   - No arrow key handling

3. **Routing history exists** (`task_router_handler.py:98-99`) but only for display, not navigation.

**What's Missing:**
- No `FileHistory` or in-memory history
- No arrow key navigation (up/down)
- No history filtering (exclude y/n/1/2/3)

**Solution:**
```python
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory

class HistoryAwareInputHandler:
    def __init__(self, history_file: str = "~/.scrappy_history"):
        self.session = PromptSession(history=FileHistory(history_file))

    def prompt(self, text: str) -> str:
        return self.session.prompt(text)
```

**Files to modify:**
- `src/cli/input_handler.py` - Add prompt_toolkit integration
- `src/cli/output.py:456-462` - Replace Click prompt with prompt_toolkit
- Add `prompt_toolkit` to requirements.txt

---

### 2.4 /cache Command Output Broken
**Status:** CONFIRMED (Code Review Completed)
**Impact:** Medium - ANSI codes displayed as text
**Location:** `src/cli/cache_manager.py:54-105`, `src/infrastructure/formatters/cache_formatter.py`

**Problem:** Output shows raw ANSI codes:
```
[36m[1m
 Cache Statistics:[0m
```

**Root Cause Analysis (Code Review Completed):**

1. **CacheFormatter embeds ANSI codes** in `cache_formatter.py:32-80`:
   ```python
   def format_stats(self, stats, enabled):
       parts.append(self.format_header("Cache Statistics:"))  # Contains click.style()
       return "\n".join(parts)  # Returns string with embedded ANSI codes
   ```

2. **Cache manager uses io.echo()** in `cache_manager.py:95`:
   ```python
   formatted_stats = self.formatter.format_stats(stats, enabled)
   self.io.echo(formatted_stats)  # PROBLEM: echo() treats ANSI as literal text
   ```

3. **Contrast with /usage command** (`display_rich.py:177-232`):
   ```python
   io.table(summary_headers, summary_rows, title="Usage Summary")  # Uses Rich Table
   ```
   Rich Tables render correctly via `console.print(table)`.

**Why ANSI Codes Appear as Text:**
- `click.style()` embeds escape codes in string
- `io.echo()` passes string to console as-is
- Terminal receives codes but formatting is broken by string joining

**Solution - Use io.table() like /usage:**
```python
# In cache_manager.py
headers = ["Metric", "Value"]
rows = [
    ["Total Entries", str(stats.get('total_entries', 0))],
    ["Exact Hit Rate", stats.get('exact_hit_rate', 'N/A')],
    ["Status", "Enabled" if enabled else "Disabled"],
]
self.io.table(headers, rows, title="Cache Statistics")
```

**Files to modify:**
- `src/cli/cache_manager.py:54-105` - Use `io.table()` instead of formatter
- OR `src/infrastructure/formatters/cache_formatter.py` - Return structured data, not pre-styled strings

---

## PRIORITY 3: Medium Impact Issues

### 3.1 .lancedb Directory at Project Root
**Status:** CONFIRMED (Code Review Completed)
**Impact:** Medium - clutter, but not breaking
**Location:** `src/context/semantic/config.py:44`, `src/context/semantic/initializer.py:251-265`

**Problem:** Default `db_dir_name = ".lancedb"` creates directory at root instead of `.scrappy/lancedb/`.

**Root Cause Analysis (Code Review Completed):**

1. **Default config** in `config.py:44`:
   ```python
   db_dir_name: str = ".lancedb"
   ```

2. **Production override** in `initializer.py:260`:
   ```python
   config = SemanticIndexConfig(db_dir_name=".scrappy/lancedb")
   ```

3. **Provider uses config** in `provider.py:155`:
   ```python
   self._db_path = self._project_path / self._config.db_dir_name
   ```

4. **Directory created** in `provider.py:185`:
   ```python
   self._db_path.mkdir(parents=True, exist_ok=True)
   ```

**When .lancedb at root is created:**
- Direct use of `LanceDBSearchProvider()` without config override
- Tests that don't specify config
- Any code path that skips `SemanticSearchInitializer`

**File collector excludes both directories** (`file_collector.py:36-44`):
```python
ignore_names: Set[str] = {..., '.scrappy', '.lancedb'}
```

**Test that needs updating** in `test_semantic_config.py:43-46`:
```python
def test_default_db_dir_name(self):
    config = SemanticIndexConfig()
    assert config.db_dir_name == ".lancedb"  # Will fail after fix
```

**Solution:**
1. Change default to `.scrappy/lancedb` in `config.py:44`
2. Update test assertion in `test_semantic_config.py:44-46`
3. Remove override in `initializer.py:260` (no longer needed)

**Files to modify:**
- `src/context/semantic/config.py:44` - Change default value
- `tests/context/test_semantic_config.py:44-46` - Update assertion
- `src/context/semantic/initializer.py:260` - Remove redundant override

---

### 3.2 Color Theme Inconsistency ### 3.3 Help Table All White
SAME ISSUE -- CONSISTENT THEME CSS NEEDED FOR ALL UX ELEMENTS
**Status:** CONFIRMED
**Impact:** Medium - visual inconsistency
**Location:** Various formatters and display code

**Problem:** Rainbow of colors for tools/commands without consistent theme.

**Solution:** Create theme system. Standardize on colors from welcome banner. Apply consistently.
**Status:** CONFIRMED
**Impact:** Low-Medium - hard to read
**Location:** Help command output

**Problem:** Help table output lacks styling/colors.

**Solution:** Add table styling capability if needed, apply consistent theme.

---

### 3.4 Semantic Search Indexing Progress Not in Status Bar
ALSO ONLY SHOW INDEXING ON FIRST APP USE OR FOR LARGE PROCESSING TIMES > 10 seconds?

**Status:** CONFIRMED
**Impact:** Medium - users don't see indexing progress
**Location:** Status bar integration

**Problem:** Status bar exists, semantic search indexing exists, but not integrated to display indexing progress.

**Solution:** Integrate `LanceDBSearchProvider` progress reporting with status bar display.

---

## PRIORITY 5: Previously Unconfirmed Issues (Now Investigated)

---

### 5.2 Context Summary Always Written
**Status:** PARTIALLY CONFIRMED (Code Review Completed)
**Impact:** Low - API call happens but file write respects user choice
**Location:** `src/cli/codebase.py:100,136-142`, `src/orchestrator/context_coordinator.py:158-165`

**Finding:**
- Context summary **generation** (LLM API call) happens unconditionally during exploration
- File **writing** respects user choice via `self.io.confirm()` (codebase.py:136-142)

**Code Flow:**
```python
# codebase.py:100 - Generation happens unconditionally
summary = self.orchestrator.context.generate_summary(llm_summary)

# codebase.py:136-142 - File write is conditional
if self.io.confirm("Save context summary?"):
    summary_file.write_text(summary)
```

**Optimization Opportunity:** Generate summary lazily only when user requests save.

---

### 5.3 Auto-explore Stale Context
**Status:** CONFIRMED BUG (Code Review Completed)
**Impact:** Medium - semantic search may miss new files
**Location:** `src/orchestrator/context_coordinator.py:80-106`

**Finding:**
Auto-explore skips re-indexing if context is cached:

```python
# context_coordinator.py:98
if self._context.is_explored():
    return {'status': 'cached', ...}  # Skips semantic indexing refresh
```

**Bug:** If files are added after initial exploration:
1. `auto_explore()` returns cached context
2. Semantic index is NOT updated with new files
3. Semantic search won't find content in new files

**Solution:**
- Add staleness check (compare file count/modification times)
- Trigger semantic re-index if files changed

**Files to modify:**
- `src/orchestrator/context_coordinator.py:80-106` - Add staleness detection

---

### 5.4 Premature Task Completion
**Status:** PARTIALLY CONFIRMED (Code Review Completed)
**Impact:** Medium - agent may stop early on complex tasks
**Location:** `src/agent/agent_loop.py:311-360,536-564`, `src/cli/commands.py:427`

**Finding:**

1. **Iteration limit** in `agent_loop.py:621`:
   ```python
   while state.iteration < state.max_iterations:
   ```
   Default `max_iterations` can be set via CLI (`commands.py:427`).

2. **Write-file completion guard** in `agent_loop.py:338-346`:
   ```python
   if not meaningful_actions and not self._dry_run:
       return EvaluationResult(is_complete=False, ...)
   ```
   Guards against premature completion if no meaningful work done.

3. **Premature completion detection** in `agent_loop.py:536-564`:
   - `_handle_premature_completion()` forces agent to continue
   - Shows error message if agent tries to complete without work

**Issues Found:**
- Guard bypassed in dry-run mode (`if not self._dry_run`)
- No automatic task decomposition for complex tasks
- Agent gets full task in one shot, may declare completion if overwhelmed

**Solution Options:**
1. Apply meaningful_actions check in dry-run mode too
2. Add task decomposition before agent loop
3. Increase max_iterations default for complex tasks

---

## Summary by Priority (Updated)

| Priority | Count | Status |
|----------|-------|--------|
| P1 Critical | 3 | All analyzed, root causes identified |
| P2 High UX | 4 | All analyzed, solutions documented |
| P3 Medium | 4 | Key issues analyzed |
| P5 Investigated | 5 | 1 not-a-bug, 2 confirmed, 2 need user reproduction |