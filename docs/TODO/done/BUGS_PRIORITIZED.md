# Bug Report - Prioritized Analysis

---

## PRIORITY 1: CRITICAL (Broken Core Functionality)

### BUG-001: Semantic Search Indexing Never Triggers

**Status:** CONFIRMED - Root cause identified
**Impact:** High - Semantic search is completely non-functional
**Complexity:** Medium - Single handler registration missing

**Problem:**
The `.scrappy/lancedb/` directory remains empty despite initialization logs showing success. 
The embedding model loads correctly, but no files are ever indexed.

**Root Cause:**
`CodebaseContext._handle_semantic_event()` is defined (lines 310-334 in `codebase_context.py`) but **never registered** 
with the event queue. When `INIT_COMPLETE` is emitted, there's no listener to trigger `_index_for_semantic_search()`.

**Flow that should happen:**
```
SemanticSearchInitializer emits INIT_COMPLETE
    -> EventQueue routes to registered handlers
    -> CodebaseContext._handle_semantic_event() should be called
    -> _index_for_semantic_search() triggers indexing
    -> LanceDB tables are created and populated
```

**Flow that actually happens:**
```
SemanticSearchInitializer emits INIT_COMPLETE
    -> EventQueue routes to SemanticSearchManager._handle_event() only
    -> CodebaseContext handler is NEVER registered
    -> _index_for_semantic_search() is never called
    -> LanceDB directory remains empty
```

**Fix Location:**
`src/context/codebase_context.py` - `start_background_initialization()` (lines 278-295)

**Required Change:**
Add handler registration:
```python
def start_background_initialization(self) -> None:
    # Existing code...
    self._semantic_manager.start_background_init()

    # ADD THIS: Register event handler
    if self._event_queue:
        self._event_queue.register_handler(
            "semantic_search",
            self._handle_semantic_event
        )
```

**Files Involved:**
- `src/context/codebase_context.py:278-295` (missing registration)
- `src/context/codebase_context.py:310-334` (orphaned handler)
- `src/context/codebase_context.py:656-681` (indexing logic - never called)
- `src/context/semantic/initializer.py:316-352` (event emission - works correctly)

---

### BUG-002: .lancedb Created at Wrong Location

**Status:** CONFIRMED - Default path incorrect
**Impact:** Medium-High - Database in wrong location, potential gitignore issues
**Complexity:** Low - Single default value change

**Problem:**
`.lancedb` directory is created at project root instead of inside `.scrappy/lancedb/`.

**Root Cause:**
Default value in `SemanticIndexConfig` is hardcoded wrong:

```python
# src/context/semantic/config.py:44-45
db_dir_name: str = ".lancedb"  # WRONG - should be ".scrappy/lancedb"
```

The initializer (lines 251-265 of `initializer.py`) correctly overrides this with `.scrappy/lancedb`, but any direct instantiation of `LanceDBSearchProvider` uses the wrong default.

**Fix Location:**
`src/context/semantic/config.py:44`

**Required Change:**
```python
# Change from:
db_dir_name: str = ".lancedb"
# To:
db_dir_name: str = ".scrappy/lancedb"
```

**Test Update Required:**
`tests/context/test_semantic_config.py:46` - Update expected value

**Files Involved:**
- `src/context/semantic/config.py:44` (wrong default)
- `src/context/semantic/initializer.py:260` (correct override)
- `tests/context/test_semantic_config.py:46` (test assumes wrong default)

---

## PRIORITY 2: HIGH (User Experience Issues)

### BUG-004: Newline Characters Rejected in Commands

**Status:** CONFIRMED - By design, but causes paste issues
**Impact:** Medium - Users can't paste multiline content
**Complexity:** Low - Input sanitization needed

**Problem:**
Commands like `/agent` reject input containing newline characters:
```
Invalid command: Command cannot contain newline characters
```

**Root Cause:**
TextArea widget allows multiline input, but validator rejects newlines:

```python
# src/cli/validators/command.py:130-134
if NEWLINE_PATTERN.search(command_input):
    return CommandValidationResult(
        is_valid=False,
        error="Command cannot contain newline characters"
    )
```

The pattern is defined at `src/cli/validators/base.py:42`:
```python
NEWLINE_PATTERN = re.compile(r'[\r\n]')
```

**Recommended Fix:**
Sanitize input at source (textual_app.py:769):
```python
# Change from:
user_input = self._input.text.strip()
# To:
user_input = self._input.text.strip().replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ')
```

**Alternative:** Allow newlines in validator and collapse them there.

**Files Involved:**
- `src/cli/textual_app.py:769` (input collection)
- `src/cli/validators/command.py:130-134` (validation)
- `src/cli/validators/base.py:42` (pattern definition)

---

### BUG-005: Audit Log Saves Regardless of User Response

**Status:** CONFIRMED
**Impact:** Medium - User prompt is deceptive; selecting 'n' does not prevent save
**Complexity:** Low - Remove prompt and always-save logic, or fix conditional

**Problem:**
After agent execution, user is prompted to save audit log, but the audit file saves regardless of user response. The prompt gives users false control over audit persistence.

**Current Code:**
```python
# src/cli/agent_manager.py:143-146
if self._interaction.confirm("Save audit log to file?", default=False):
    log_path = agent.save_audit_log()
    self.io.secho(f"Saved to: {log_path}", fg="green")
```

**Observed Behavior:**
Audit log is written to disk even when user selects 'n'. The conditional only controls whether the success message is displayed, not whether the save occurs.

**Required Fix:**
1. Investigate where the unconditional save occurs (likely in agent execution or a separate handler)
2. Either:
   - Remove the prompt entirely since audits always save (simplest)
   - Fix the logic so 'n' actually prevents the save (if configurability is desired)

**Recommendation:** Remove the prompt. Audits are cheap, useful for debugging, and users expect them to exist.

**Files Involved:**
- `src/cli/agent_manager.py:143-146` (deceptive prompt)
- Investigate: agent execution path for unconditional save location

---

## PRIORITY 3: MEDIUM (Code Quality)

### BUG-006: Dead Code in InteractiveMode

**Status:** CONFIRMED
**Impact:** Low - Code clutter, no functional impact
**Complexity:** Low - Safe deletion

**Problem:**
When Textual TUI is used (default), the following methods are never called:
- `InteractiveMode.run()` (lines 83-139)
- `InteractiveMode._main_loop()` (lines 141-200)
- `InputHandler.read_interactive_input()` (lines 136-209)
- `InputHandler._read_first_line()` (lines 115-134)

**Call Flow Analysis:**
```
TextualInteractiveMode.run()
    -> Creates InteractiveMode instance
    -> Creates ScrappyApp
    -> app.run() (Textual framework takes over)
    -> ScrappyApp.process_command() calls InteractiveMode._process_input() directly

InteractiveMode.run() and _main_loop() are NEVER called in this path
```

**Evidence:**
- Tests mock `_main_loop()` to prevent execution
- `ScrappyApp` uses `TextArea` widget instead of `read_interactive_input()`

**Recommendation:**
Either:
1. Remove dead code entirely
2. Document as "legacy non-Textual fallback" if there's a use case

**Files Involved:**
- `src/cli/interactive.py:83-200` (dead methods)
- `src/cli/input_handler.py:115-209` (dead methods)
- `src/cli/textual_interactive.py:88-139` (bypasses InteractiveMode.run())
- `src/cli/textual_app.py:848-872` (calls _process_input directly)

---

### BUG-007: Chat Output Clutter and Missing User Query Echo

**Status:** CONFIRMED
**Impact:** Medium - Poor default UX, too much noise in output
**Complexity:** Medium - Requires output mode refactor and flag implementation

**Problem:**
Chat output is cluttered with metadata (execution status, time, tokens, provider) by default. User's query is not echoed back. The "Output:" label and dashed lines add unnecessary noise.

**Current Output (too verbose by default):**
```
Output:
--------------------------------------------------
Assistant: Hello! How can I help you today?
--------------------------------------------------
Execution successful
Execution time: 234ms
Tokens: 15
Provider: cerebras/llama-3.3-70b
```

**Required Output - Default Mode (clean):**
```
> how do we update the api?
To update an API, follow these general steps:
1. **Modify the API Code**: Update endpoints...
...
```

**Required Output - Verbose Mode (-v flag):**
```
> how do we update the api?
To update an API, follow these general steps:
1. **Modify the API Code**: Update endpoints...
...
[cerebras/llama-3.3-70b | 15 tokens | 234ms]
```

**Requirements:**
1. Both modes: Echo user query with `> ` prefix
2. Default mode: Response content only, no metadata, no labels, no dashes
3. Verbose mode (-v): Include metadata line `[provider | tokens | time]`
4. Remove "Output:", "Assistant:", dashed lines, "Execution successful" in all modes

**Files Involved:**
- `src/cli/interactive.py:246-249` (user logging)
- `src/cli/interactive.py:276,295-307` (output display - needs refactor)
- CLI argument parsing (add -v/--verbose flag)
- Reference screenshots: `docs/TODO/post-input.png`, `docs/TODO/pre-input.png`

---

### BUG-010: Remove auto_route_mode Flag

**Status:** CONFIRMED - Dead/useless code
**Impact:** Low - Code clutter, confusing parameter
**Complexity:** Low - Remove flag and related conditionals

**Problem:**
`auto_route_mode` is a boolean parameter only used to display text in the welcome banner. It provides no functional behavior and adds confusion about whether routing can be toggled.

**Current State:**
- Parameter exists in `render_welcome_banner()`
- Only affects banner display text
- No actual routing logic controlled by this flag
- Auto-routing is always the default behavior

**Required Fix:**
1. Remove `auto_route_mode` parameter from `render_welcome_banner()`
2. Remove any conditionals that check this flag
3. Ensure auto-routing remains the default (and only) behavior
4. Update banner to not reference "auto route mode" as a toggleable feature

**Files Involved:**
- `src/cli/utils/banner.py` - `render_welcome_banner()` function
- Any callers passing `auto_route_mode` parameter

---

## Summary Table

| ID | Bug | Priority | Complexity | Status |
|----|-----|----------|------------|--------|
| BUG-001 | Semantic search never indexes | P1-CRITICAL | Medium | Confirmed |
| BUG-002 | .lancedb wrong location | P1-CRITICAL | Low | Confirmed |
| BUG-004 | Newlines rejected in commands | P2-HIGH | Low | Confirmed |
| BUG-005 | Audit log saves regardless of user response | P2-HIGH | Low | Confirmed |
| BUG-006 | Dead code in InteractiveMode | P3-MEDIUM | Low | Confirmed |
| BUG-007 | Chat output clutter + missing query echo | P3-MEDIUM | Medium | Confirmed |
| BUG-010 | Remove auto_route_mode flag | P4-LOW | Low | Confirmed |

---

## Recommended Fix Order

1. **BUG-001** - Critical: Semantic search is completely broken
2. **BUG-002** - Quick fix, related to BUG-001
3. **BUG-005** - Remove deceptive prompt, simplify audit behavior
4. **BUG-004** - Common user pain point (paste multiline)
5. **BUG-007** - UX improvement (clean output + verbose flag)
6. **BUG-010** - Remove dead auto_route_mode flag
7. **BUG-006** - Code cleanup (can be done anytime)
