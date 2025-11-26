# UX Issues Implementation Plan

This document outlines the architectural design and implementation approach for fixing the UX issues documented in `UX_ISSUES.md`.

---

## Progress

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 1 | COMPLETE | All 5 trivial fixes implemented 2025-11-25 |
| Phase 2 | COMPLETE | ANSI artifacts fix, /usage styling, command consolidation 2025-11-25 |
| Phase 3 | COMPLETE | Research subclassification (Issue 6) 2025-11-25 |

---

## Overview

The issues are organized by complexity and dependency:

| Issue | Description | Complexity | Dependencies | Status |
|-------|-------------|------------|--------------|--------|
| 1 | /explore command fails | Trivial | None | DONE |
| 4 | /explore prompts unnecessarily | Trivial | Issue 1 | DONE |
| 7 | Cerebras not defaulted to instruct model | Trivial | None | DONE |
| 9 | Unneeded confirmation for /agent | Trivial | None | DONE |
| 10 | Duplicated commands in /help | Trivial | None | DONE |
| 2 | ANSI artifacts in /cache output | Medium | None | DONE |
| 3 | /usage inconsistent styling | Medium | Issue 2 (shared approach) | DONE |
| 8 | Two similar explore commands | Medium | Issues 1, 4 | DONE |
| 6 | Research query routed to code assistant | Complex | Architectural decision | DONE |

---

## Phase 1: Trivial Fixes (No Architectural Changes)

### Issue 1: /explore command fails

**Problem:** `io=self.io` kwarg passed to method that does not accept it.

**Location:** `src/cli/command_router.py:260`

**Fix:**
```python
# Before
self.codebase.explore_codebase(args, io=self.io)

# After
self.codebase.explore_codebase(args)
```

**Rationale:** `CLICodebaseAnalysis` already receives `io` via constructor injection. The `io` parameter is not part of the method signature.

**Testing:**
- Run `/explore` command and verify no error
- Run `/explore some/path` and verify path exploration works

---

### Issue 4: /explore prompts unnecessarily

**Problem:** When no path given, prompts user instead of using default.

**Location:** `src/cli/codebase.py:63-64`

**Fix:**
```python
# Before
if not path:
    path = self.io.prompt("Directory to explore", default=".")

# After
if not path:
    path = "."
```

**Rationale:**
- User explicitly invoked `/explore` - they want to explore current directory
- If they wanted a different path, they would provide it: `/explore /some/path`
- Prompting adds friction to the common case (current directory)

**Testing:**
- Run `/explore` with no args - should explore current directory without prompting
- Run `/explore /some/path` - should explore specified path

---

### Issue 7: Cerebras default model change

**Problem:** Defaults to base model `llama3.1-8b` instead of instruct-tuned model.

**Location:** `src/providers/cerebras_provider.py:108`

**Fix:**
```python
# Before
@property
def default_model(self) -> str:
    return 'llama3.1-8b'

# After
@property
def default_model(self) -> str:
    return 'qwen-3-235b-a22b-instruct-2507'
```

**Rationale:**
- Instruct models follow tool-calling instructions better
- The `qwen-3-235b` model has "excellent JSON compliance" per codebase comments
- Speed difference is minimal (still "fast" tier)
- Tool-following quality is critical for agent operations

**Testing:**
- Verify Cerebras provider uses correct default model
- Run a research task and confirm model selection

---

### Issue 9: Remove unnecessary /agent confirmation

**Problem:** "Start agent?" confirmation after user already invoked `/agent <task>`.

**Location:** `src/cli/agent_manager.py:96-98`

**Fix:**
```python
# Before
if not io.confirm("Start agent?", default=True):
    io.echo("Agent cancelled.")
    return

# After
# (Remove these lines entirely)
```

**Rationale:**
- User explicitly invoked `/agent <task>` - intent is clear
- Dry-run and checkpoint confirmations already provide safety
- Extra confirmation adds friction without benefit

**Testing:**
- Run `/agent "some task"` - should proceed without "Start agent?" prompt
- Dry-run and checkpoint prompts should still appear

---

### Issue 10: Consolidate /quit and /exit in help

**Problem:** Help shows both `/quit` and `/exit` as separate entries.

**Location:** `src/cli/display_rich.py:72-75`

**Fix:**
```python
# Before
'System': [
    ('/quit', 'Exit the CLI'),
    ('/exit', 'Exit the CLI'),
],

# After
'System': [
    ('/quit, /exit', 'Exit the CLI'),
],
```

**Rationale:**
- Both commands do the same thing (aliases)
- Showing both clutters the help output
- Single entry with both aliases is cleaner

**Testing:**
- Run `/help` and verify single combined entry
- Verify both `/quit` and `/exit` still work

---

## Phase 2: Medium Complexity Fixes

### Issue 2: ANSI artifacts in /cache output

**Problem:** Raw ANSI codes displayed when terminal does not support colors.

**Root Cause Analysis:**

The formatting chain:
1. `StatsFormatter.format_header()` uses `click.style()` to embed ANSI codes
2. Result string contains raw escape sequences: `\x1b[36m...\x1b[0m`
3. `io.echo()` outputs the string directly
4. If terminal does not interpret ANSI, raw codes appear

**Design Decision: Protocol-First Approach**

Create a `FormatterProtocol` that abstracts formatting behavior:

```python
# src/infrastructure/formatters/protocols.py

class FormatterProtocol(Protocol):
    """Protocol for text formatting."""

    def header(self, title: str, width: int = 60) -> str:
        """Format a header. May include styling or plain text."""
        ...

    def key_value(self, key: str, value: Any, indent: int = 0) -> str:
        """Format a key-value pair."""
        ...

    def percentage_bar(self, value: float, total: float, width: int = 20) -> str:
        """Format a percentage with optional bar."""
        ...


class ColorCapableIO(Protocol):
    """Protocol for IO that knows its color capability."""

    def supports_color(self) -> bool:
        """Return True if output supports ANSI colors."""
        ...
```

**Implementation Options:**

**Option A: Conditional Styling (Recommended)**

Modify `StatsFormatter` to accept color capability flag:

```python
class StatsFormatter:
    def __init__(self, use_color: bool = True):
        self._use_color = use_color

    def format_header(self, title: str, width: int = 60) -> str:
        if self._use_color:
            header = click.style(f"\n{title}", fg="cyan", bold=True)
            separator = click.style("-" * width, fg="cyan")
        else:
            header = f"\n{title}"
            separator = "-" * width
        return f"{header}\n{separator}"
```

**Option B: Strip ANSI on Output**

Add ANSI stripping to `UnifiedIO.echo()` when color not supported:

```python
import re

ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;]*m')

def echo(self, message: str) -> None:
    if not self._supports_color:
        message = ANSI_ESCAPE.sub('', message)
    # ... existing output logic
```

**Recommended: Option A**

- More explicit control
- Avoids regex overhead on every output
- Follows dependency injection principle

**Files to Modify:**
- `src/infrastructure/formatters/stats_formatter.py` - Add color flag
- `src/infrastructure/formatters/cache_formatter.py` - Add color flag
- `src/cli/unified_io.py` - Add `supports_color()` method
- `src/cli/cache_manager.py` - Pass color capability to formatter

**Testing:**
- Mock IO with `supports_color() -> False`
- Verify output contains no ANSI escape sequences
- Verify colored output still works when supported

---

### Issue 3: /usage inconsistent styling

**Problem:** Mix of panels (rounded) and tables (sharp corners).

**Design Decision:**

Unify to a single visual style. Two approaches:

**Option A: All Tables**
- More consistent
- Better for data comparison
- Simpler implementation

**Recommended: Option A - Use Tables**

```python
def show_usage_rich(io: UnifiedIO, report: Dict[str, Any]) -> None:
    # Summary as a single-row table
    summary_headers = ["Metric", "Value"]
    summary_rows = [
        ["Total Tasks", str(report.get('total_tasks', 0))],
        ["Cache Hits", str(report.get('cached_hits', 0))],
        ["API Calls", str(report.get('api_calls', 0))],
        ["Session Duration", report.get('session_duration', 'N/A')],
    ]
    io.table(summary_headers, summary_rows, title="Usage Summary")

    # Provider breakdown (already a table)
    # ... existing code ...

    # Cache statistics as a table
    cache_headers = ["Metric", "Value"]
    cache_rows = [
        ["Exact Hit Rate", cache_stats.get('exact_hit_rate', 'N/A')],
        ["Intent Hit Rate", cache_stats.get('intent_hit_rate', 'N/A')],
        ["Total Entries", str(total_entries)],
    ]
    io.table(cache_headers, cache_rows, title="Cache Statistics")
```

**Files to Modify:**
- `src/cli/display_rich.py:178-226` - Refactor `show_usage_rich()`

**Testing:**
- Run `/usage` and verify consistent table styling
- Verify all sections display correctly

---

### Issue 8: Consolidate explore commands

**Problem:** `/context explore` and `/explore` are too similar.

**Design Decision: Remove `/context explore`**

Rationale:
- `/explore` is more discoverable (single command)
- `/explore` already handles current project case
- `/context explore` adds confusion without value

**Implementation:**

1. **Remove from context_commands.py:**
```python
# Remove elif block at lines 104-115
elif validation.subcommand == "explore":
    # ... remove this entire block
```

2. **Update validator (if applicable):**
```python
# Remove "explore" from valid context subcommands
VALID_CONTEXT_SUBCOMMANDS = ["status", "refresh", "clear"]  # Remove "explore"
```

3. **Update help text in display_rich.py:**
```python
# Remove /context explore from help categories
# Ensure /explore is well-documented
```

**Files to Modify:**
- `src/cli/context_commands.py:104-115` - Remove explore subcommand
- `src/cli/validators/subcommand.py` - Remove from valid subcommands (if applicable)
- `src/cli/display_rich.py` - Update help text

**Testing:**
- Verify `/context explore` returns "unknown subcommand" error
- Verify `/explore` works for current directory
- Verify `/help` shows only `/explore`

---

## Phase 3: Complex Architectural Change

### Issue 6: Research query routed to code assistant

**Problem:** General knowledge questions ("who is the best coder, Dijkstra or Turing?") are routed to `ResearchExecutor` which uses codebase tools inappropriately.

**Root Cause Analysis:**

The classification is correct - it IS a research question. The problem is:
1. `ResearchExecutor` assumes all research is codebase-related
2. Tool bundle includes `read_file`, `search_code`, `git` tools
3. LLM uses these tools because they are available

**Design Decision: Sub-classify Research**

Introduce a distinction between:
- **Codebase Research:** Questions about this project's code
- **General Knowledge:** Questions about external topics

**Architectural Approach: Strategy Refinement**

Create a `ResearchSubclassifier` that determines research type:

```python
# src/task_router/classification_strategies/research_subclassifier.py

class ResearchType(Enum):
    CODEBASE = "codebase"  # Questions about project code
    GENERAL = "general"    # External knowledge questions


class ResearchSubclassifierProtocol(Protocol):
    """Protocol for sub-classifying research queries."""

    def classify(self, query: str, context: Optional[ProjectContext]) -> ResearchType:
        """Determine if query is about codebase or general knowledge."""
        ...


class ResearchSubclassifier:
    """
    Determines if a research query is about the codebase or general knowledge.

    Codebase indicators:
    - File paths, extensions (.py, .js, etc.)
    - Project-specific terms (from context summary)
    - Code references ("function", "class", "method", "variable")
    - Relative references ("this project", "our code", "the codebase")

    General knowledge indicators:
    - Named entities (people, places, historical events)
    - No file/code references
    - Asking about concepts not in project context
    """

    CODEBASE_INDICATORS = [
        r'\b(this|our|the)\s+(project|codebase|code|repo)',
        r'\b(file|function|class|method|variable|module|package)\b',
        r'\b[\w/\\]+\.(py|js|ts|jsx|tsx|java|cpp|go|rs)\b',
        r'\b(src|lib|test|app|components?)/\b',
    ]

    GENERAL_INDICATORS = [
        r'\b(who|what person|which person)\b.*\b(is|was|were)\b',
        r'\b(history|historically|invented|created by)\b',
        r'\b(best|worst|famous|greatest)\b.*\b(programmer|coder|scientist)\b',
    ]

    def classify(self, query: str, context: Optional[ProjectContext] = None) -> ResearchType:
        query_lower = query.lower()

        # Check for codebase indicators
        codebase_score = sum(
            1 for pattern in self.CODEBASE_INDICATORS
            if re.search(pattern, query_lower)
        )

        # Check for general knowledge indicators
        general_score = sum(
            1 for pattern in self.GENERAL_INDICATORS
            if re.search(pattern, query_lower)
        )

        # If context has project terms, check for matches
        if context and context.has_summary():
            project_terms = context.get_key_terms()
            term_matches = sum(1 for term in project_terms if term.lower() in query_lower)
            codebase_score += term_matches

        # Decide based on scores
        if general_score > codebase_score:
            return ResearchType.GENERAL
        elif codebase_score > 0:
            return ResearchType.CODEBASE
        else:
            # Default to general for ambiguous queries
            return ResearchType.GENERAL
```

**Modify ResearchExecutor:**

```python
class ResearchExecutor(ProviderAwareStrategy):
    def __init__(
        self,
        orchestrator: OrchestratorLike,
        # ... existing params ...
        subclassifier: Optional[ResearchSubclassifierProtocol] = None,
    ):
        # ... existing init ...
        self._subclassifier = subclassifier or ResearchSubclassifier()

    def execute(self, task: ClassifiedTask) -> ExecutionResult:
        # Step 0: Sub-classify research type
        research_type = self._subclassifier.classify(
            task.original_input,
            self._get_project_context()
        )

        if research_type == ResearchType.GENERAL:
            return self._execute_general_research(task)
        else:
            return self._execute_codebase_research(task)

    def _execute_general_research(self, task: ClassifiedTask) -> ExecutionResult:
        """
        Execute general knowledge research.

        - No codebase tools
        - Uses web_search and web_fetch if available
        - Falls back to direct LLM response
        """
        # Build tool bundle with only web tools
        web_tools = self._tool_bundle.get_web_tools_only()

        if not web_tools:
            # No web tools - simple LLM call
            return self._simple_llm_response(task)

        # Use web tools for general research
        # ... similar to existing research loop but with web tools only

    def _execute_codebase_research(self, task: ClassifiedTask) -> ExecutionResult:
        """Existing codebase research logic."""
        # ... existing execute() logic ...
```

**Modify ToolBundle:**

```python
class ToolBundle:
    def get_web_tools_only(self) -> Dict[str, Callable]:
        """Return only web-related tools (no codebase access)."""
        return {
            name: tool for name, tool in self._tools.items()
            if name in ['web_search', 'web_fetch']
        }

    def get_codebase_tools(self) -> Dict[str, Callable]:
        """Return codebase-related tools."""
        return {
            name: tool for name, tool in self._tools.items()
            if name in ['read_file', 'search_code', 'grep', 'git_status', 'git_log']
        }
```

**Files to Create:**
- `src/task_router/classification_strategies/research_subclassifier.py`

**Files to Modify:**
- `src/task_router/strategies/research_executor.py`
- `src/task_router/strategies/tool_bundle.py`
- `src/task_router/strategies/research_protocols.py` (add new protocol)

**Testing:**
- Test "who is the best coder" -> ResearchType.GENERAL
- Test "what does the auth module do" -> ResearchType.CODEBASE
- Test "explain the login function in src/auth.py" -> ResearchType.CODEBASE
- Test "who invented Python" -> ResearchType.GENERAL
- Verify general research does not use codebase tools

---

## Implementation Order

Recommended order based on dependencies and risk:

### Batch 1: Trivial Fixes (Safe, No Dependencies)
1. Issue 1: Fix /explore kwarg error
2. Issue 4: Remove /explore prompt
3. Issue 7: Change Cerebras default model
4. Issue 9: Remove /agent confirmation
5. Issue 10: Consolidate /quit and /exit in help

**Verification:** Run all affected commands, run test suite.

### Batch 2: Formatting Fixes
6. Issue 2: Fix ANSI artifacts (add color capability)
7. Issue 3: Unify /usage styling

**Verification:** Test with color and non-color terminals.

### Batch 3: Command Consolidation
8. Issue 8: Remove /context explore

**Verification:** Test /explore covers all use cases.

### Batch 4: Research Classification
9. Issue 6: Add research subclassification

**Verification:** Comprehensive testing of query classification.

---

## Testing Strategy

### Unit Tests

For each fix, add tests that:
1. Verify the fix works correctly
2. Prevent regression
3. Cover edge cases

Example for Issue 6:

```python
# tests/test_research_subclassifier.py

class TestResearchSubclassifier:
    def test_general_knowledge_person_question(self):
        classifier = ResearchSubclassifier()
        result = classifier.classify("who is the best coder, Dijkstra or Turing?")
        assert result == ResearchType.GENERAL

    def test_codebase_file_reference(self):
        classifier = ResearchSubclassifier()
        result = classifier.classify("what does src/auth.py do?")
        assert result == ResearchType.CODEBASE

    def test_codebase_relative_reference(self):
        classifier = ResearchSubclassifier()
        result = classifier.classify("explain how this project handles authentication")
        assert result == ResearchType.CODEBASE

    def test_general_historical_question(self):
        classifier = ResearchSubclassifier()
        result = classifier.classify("when was Python invented?")
        assert result == ResearchType.GENERAL
```

### Integration Tests

For command fixes, add CLI integration tests:

```python
# tests/integration/test_cli_commands.py

def test_explore_no_prompt(mock_io, cli):
    """Test /explore does not prompt when no args given."""
    cli.handle_command("/explore")
    assert mock_io.prompt.call_count == 0

def test_agent_no_start_confirmation(mock_io, cli):
    """Test /agent does not ask 'Start agent?' confirmation."""
    cli.handle_command("/agent 'test task'")
    # Verify no confirm call with "Start agent?"
    confirm_calls = [c for c in mock_io.confirm.call_args_list if "Start agent" in str(c)]
    assert len(confirm_calls) == 0
```

---

## Risk Assessment

| Issue | Risk Level | Mitigation |
|-------|------------|------------|
| 1, 4, 7, 9, 10 | Low | Simple changes, easy to verify |
| 2, 3 | Medium | Test with various terminal types |
| 8 | Medium | Ensure /explore covers all /context explore functionality |
| 6 | High | Comprehensive pattern testing, gradual rollout |

---

## Rollback Plan

Each change should be atomic and revertible:

1. **Trivial fixes:** Single-line changes, easy git revert
2. **Formatting changes:** Feature flag (`USE_ANSI_COLORS`) for quick disable
3. **Command consolidation:** Re-add subcommand if issues arise
4. **Research subclassification:** Add config flag to disable (`SKIP_RESEARCH_SUBCLASSIFICATION`)

---

## Success Criteria

- All 10 issues resolved
- No regression in existing functionality
- Test coverage for all changes
- Clean output in non-color terminals
- Consistent styling across commands
- Research queries handled appropriately
