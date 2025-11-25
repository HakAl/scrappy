# UX Issues

---

## Issue 1: /explore command fails

**Problem:**
```
/explore - command fails.
Error: CLICodebaseAnalysis.explore_codebase() got an unexpected keyword argument 'io'
```

**Root Cause:**
In `src/cli/command_router.py:260`, the `_handle_explore` method passes `io=self.io`:
```python
def _handle_explore(self, args: str) -> bool:
    """Handle /explore command."""
    self.codebase.explore_codebase(args, io=self.io)  # <-- BUG: 'io' kwarg not accepted
    return True
```

However, `CLICodebaseAnalysis.explore_codebase()` in `src/cli/codebase.py:38` only accepts `path`:
```python
def explore_codebase(self, path: str = ""):
    # ... io is already set in __init__, not passed per-call
```

**Solution:**
Remove the `io=self.io` argument from the call in `command_router.py:260`. The `CLICodebaseAnalysis` class already receives `io` via its constructor.

**Files:**
- `src/cli/command_router.py:260` - Bug location
- `src/cli/codebase.py:38` - Method signature

---

## Issue 2: ANSI artifacts in /cache command output

**Problem:**
```
/cache:
 [36m[1m
 Cache Statistics:[0m
 [36m--------------------------------------------------[0m
 Total Entries: 0
 ...
```

**Root Cause:**
The `CacheFormatter` class (`src/infrastructure/formatters/cache_formatter.py`) uses `click.style()` to generate ANSI color codes. The `StatsFormatter.format_header()` method (`src/infrastructure/formatters/stats_formatter.py:28`) applies styling:
```python
def format_header(self, title: str, width: int = 60) -> str:
    header = click.style(f"\n{title}", fg="cyan", bold=True)
    separator = click.style("-" * width, fg="cyan")
    return f"{header}\n{separator}"
```

The formatted string with embedded ANSI codes is then passed to `io.echo()`, which outputs it raw without interpreting the codes (happens when terminal doesn't support ANSI or when output is redirected).

**Solution Options:**
1. Strip ANSI codes when outputting to non-color-capable terminals
2. Use `io.secho()` with color parameters instead of embedding `click.style()` in strings
3. Check terminal capability before adding color codes

**Files:**
- `src/infrastructure/formatters/cache_formatter.py` - Uses click.style()
- `src/infrastructure/formatters/stats_formatter.py:28` - format_header() method
- `src/cli/cache_manager.py:89` - Calls `io.echo(formatted_stats)`

---

## Issue 3: /usage command has inconsistent styling

**Problem:**
```
/usage - command output is 3 tables with different styles:
- Panel with rounded corners for "Usage Summary"
- Table with sharp corners for "By Provider"
- Panel with rounded corners for "Cache Statistics"
```

**Root Cause:**
In `src/cli/display_rich.py:178-226`, `show_usage_rich()` uses three different Rich components:
1. `io.panel()` for summary (line 195)
2. `io.table()` for provider breakdown (line 212)
3. `io.panel()` for cache stats (line 226)

Panels use rounded corners (default Rich style) while tables use sharp corners.

**Solution:**
Consolidate to a single unified display format - either all panels, all tables, or a single combined panel/table structure.

**Files:**
- `src/cli/display_rich.py:178-226` - show_usage_rich() function

---

## Issue 4: /explore prompts unnecessarily

**Problem:**
```
You>  /explore
Directory to explore [.]
```

**Root Cause:**
In `src/cli/codebase.py:63-64`:
```python
if not path:
    path = self.io.prompt("Directory to explore", default=".")
```

The method prompts for a path when none is provided instead of using the default directly.

**Solution:**
Remove the prompt and default to current directory:
```python
if not path:
    path = "."
```

Or accept path from args without prompting.

**Files:**
- `src/cli/codebase.py:63-64` - Prompt logic


---

## Issue 6: Research query routed to code assistant

**Problem:**
```
You>  who is the best coder to live dijkstra, turing?
Task Classification:
  Type: research
  ...
  Executing with: ResearchExecutor

Output:
To answer the user's request, I'll use the Scrappy AI coding assistant...
Using the `grep` tool, I'll search for any mentions of "Dijkstra" and "Turing"...
```

**Root Cause:**
The `ResearchExecutor` (`src/task_router/strategies/research_executor.py`) is designed for code-related research. Its system prompt in `PromptBuilder` likely instructs it to search the codebase. The tool bundle includes code-searching tools (`read_file`, `search_code`, `git tools`).

When given a general knowledge question, the research executor still tries to use its codebase-focused tools instead of providing a direct answer or using web search.

**Analysis:**
The classification ("research") is arguably correct - it IS a research question. The problem is that ResearchExecutor assumes all research is codebase-related. Two approaches:

1. **Sub-classify research** (recommended): Add detection for "general knowledge" vs "codebase research"
   - General knowledge: No codebase references, asking about external topics
   - Codebase research: References files, code, "this project", etc.

2. **Route to CONVERSATION**: Simpler but loses the "research" semantic - these aren't really conversations

**Recommended Solution:**
Modify `ResearchExecutor` or add a pre-check in the classifier to detect general knowledge queries. When detected:
- Skip codebase tools entirely
- Use only `web_search` and `web_fetch` tools (if available)
- Or route to a simple LLM call without tools

Detection heuristics for "general knowledge":
- No file paths or code references
- Questions about people, history, concepts not in codebase
- No project-specific terminology

**Files:**
- `src/task_router/strategies/research_executor.py:44` - Tool descriptions
- `src/task_router/strategies/prompt_builder.py` - System prompt construction
- `src/task_router/classifier.py` - Task classification logic (add sub-classification)

---

## Issue 7: Cerebras not defaulted to instruct model

**Problem:**
Cerebras defaults to `llama3.1-8b` instead of an instruct-tuned model.

**Root Cause:**
In `src/providers/cerebras_provider.py:108`:
```python
@property
def default_model(self) -> str:
    return 'llama3.1-8b'
```

Available models include instruct-tuned options:
- `qwen-3-235b-a22b-instruct-2507` (excellent JSON compliance, explicitly noted in comments)

**Current Model Configuration:**
```python
MODELS = {
    'llama3.1-8b': {...},  # Current default - ultra_fast
    'llama-3.3-70b': {...},  # very_fast, excellent quality
    'qwen-3-32b': {...},  # very_fast, very_good quality
    'qwen-3-235b-a22b-instruct-2507': {...},  # fast, excellent - BEST FOR TOOLS
}
```

**Decision:** Change default to instruct model
- Speed is already very fast even with larger model
- Tool-following quality is crucial for agent operations
- JSON compliance matters for structured outputs

**Solution:**
Change default_model to `qwen-3-235b-a22b-instruct-2507` in `cerebras_provider.py:108`

**Files:**
- `src/providers/cerebras_provider.py:108` - default_model property

---

## Issue 8: Two similar explore commands exist

**Problem:**
There are 2 very similar commands: `/context explore` and `/explore`

**Root Cause Analysis:**

**`/context explore`** (in `src/cli/context_commands.py:104-115`):
```python
elif validation.subcommand == "explore":
    self.io.echo("Exploring current project...")
    result = self.orchestrator.explore_project(force=False)
    # Uses cached exploration if available
    # Shows generated summary
```
- Uses orchestrator's explore_project()
- Uses cache if available
- Shows summary from context

**`/explore`** (in `src/cli/codebase.py:38-142`):
```python
def explore_codebase(self, path: str = ""):
    # Can explore any directory (prompts for path)
    # Has different behavior for current project vs external
    # Offers to save summary to CODEBASE_SUMMARY.md
```
- Can explore any directory (not just current project)
- For current project: Uses context.explore() (similar to /context explore)
- For external dirs: Uses standalone exploration
- Offers to save summary file

**Decision:** Merge - remove `/context explore`
- Too similar to distinguish for end users
- `/explore` already handles current project case
- Keep `/explore [path]` as the single entry point

**Solution:**
1. Remove "explore" from `/context` subcommands in `context_commands.py`
2. Remove from validators if applicable
3. Update help text to clarify `/explore` is the only explore command
4. Ensure `/explore` (no args) defaults to current directory without prompting (see Issue 4)

**Files:**
- `src/cli/context_commands.py:104-115` - Remove explore subcommand
- `src/cli/validators/subcommand.py` - Remove "explore" from context subcommands
- `src/cli/display_rich.py` - Update help text

---

## Issue 9: Unneeded confirmation prompt for /agent

**Problem:**
```
Start agent? [y/n] (y): y
```

**Root Cause:**
In `src/cli/agent_manager.py:96`:
```python
if not io.confirm("Start agent?", default=True):
    io.echo("Agent cancelled.")
    return
```

This comes AFTER already asking about dry-run mode (line 71) and git checkpoint (line 72).

**Context:**
The user explicitly invoked `/agent <task>`, so they clearly want to run the agent. The additional confirmation adds friction without much safety benefit (especially since dry-run and checkpoint options already provide safety).

**Solution:**
Remove the "Start agent?" confirmation since the user already explicitly invoked the command. The dry-run and checkpoint confirmations provide sufficient safety.

**Files:**
- `src/cli/agent_manager.py:96-98` - Confirmation prompt

---

## Issue 10: Duplicated commands in /help

**Problem:**
```
| System               |                             |
|   /quit              | Exit the CLI                |
|   /exit              | Exit the CLI
```

**Root Cause:**
In `src/cli/display_rich.py:72-75`, the help table explicitly lists both:
```python
'System': [
    ('/quit', 'Exit the CLI'),
    ('/exit', 'Exit the CLI'),
],
```

Both commands map to the same handler in `command_router.py:82-84`:
```python
"/quit": self._handle_exit,
"/exit": self._handle_exit,
"/q": self._handle_exit,
```

**Solution:**
Combine in help display:
```python
'System': [
    ('/quit or /exit', 'Exit the CLI'),
],
```

Note: `/q` is also an alias but not shown in help.

**Files:**
- `src/cli/display_rich.py:72-75` - Help table definition
- `src/cli/display.py:68` - Fallback help text (already shows `/quit or /exit`)

---
