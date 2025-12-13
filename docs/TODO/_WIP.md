
## Medium Effort Items

### 1. Startup display:
Current state (many lines):
```
 Initializing Scrappy...
 CLI initialized
 Brain: cerebras
 Available providers: cerebras
 Context: Not explored (use /context to explore)
 Loading semantic search...

 Completed.

 Semantic search ready
 --- Previous session (Dec 12, 08:21 PM) ---
 Restored 2 messages from previous conversation

 Previous session detected:
   Saved: 2025-12-13T07:40:02.118769
   Files cached: 0
   Searches: 0
   Discoveries: 0
   Tasks: 24
 Restore previous session? (auto-confirmed)
 Session restored successfully!

 Welcome to Scrappy!
   /help   - Show all commands
   /agent  - Run code agent
 Type a message to chat, or use a slash command.

 ============================================================
 Session resumed (stale - last activity > 4 hours ago)
 ============================================================
```
Desired state:
```
 Initializing Scrappy...
 Available providers: cerebras

 Welcome to Scrappy!
   /help   - Show all commands
   /agent  - Run code agent
 Type a message to chat, or use a slash command.
```
Note this is shown every load, i closed app, reopen -- it's displayed BUG
 ============================================================
 Session resumed (stale - last activity > 4 hours ago)
 ============================================================

 Plan: Simplify Startup Display (Item 1)

  Current State Analysis

  Messages come from multiple sources:

  | Source                      | Message                                    | Action                         |
  |-----------------------------|--------------------------------------------|--------------------------------|
  | core.py:146                 | "Initializing Scrappy..."                  | Keep                           |
  | core.py:153                 | Logger "CLI initialized"                   | Remove (verbose)               |
  | core.py:163                 | "Brain: cerebras"                          | Remove (internal detail)       |
  | core.py:168                 | "Available providers: cerebras"            | Keep                           |
  | core.py:174-176             | "Context: Not explored..."                 | Remove                         |
  | core.py:284-318             | Semantic search progress messages          | Remove (silent background)     |
  | core.py:182-186             | "Restored N messages..." + stale separator | Remove                         |
  | core.py:367                 | display_previous_session_detected()        | Remove (auto-restore silently) |
  | core.py:382                 | "Session restored successfully!"           | Remove                         |
  | interactive_banner.py:26-29 | Welcome banner                             | Keep                           |
  | main_screen.py:131-137      | "Session resumed (stale...)"               | Bug fix                        |

  Bug: Stale Session Shown Every Load

  Root cause: session_context.is_stale (line 155-168 in session_context.py) recalculates staleness in real-time by calling check_session_staleness(last_time). After a few minutes of use, if last_time was updated by new messages, the condition may become false/true unexpectedly.

  The real bug: The stale check at display time uses get_last_message_time() which returns the time of the most recent message. If you sent a message 5 minutes ago, is_stale returns false. The separator should only show once at startup if the session WAS stale when loaded.

  Implementation Steps

  Step 1: Add _was_stale_at_load flag to SessionContext

  In session_context.py, store a snapshot of staleness at construction time:

  def __init__(self, ..., was_stale_at_load: bool = False):
      ...
      self._was_stale_at_load = was_stale_at_load

  @property
  def was_stale_at_load(self) -> bool:
      """Check if session was stale when loaded (one-time snapshot)."""
      return self._was_stale_at_load

  Step 2: Pass staleness flag from CLI to SessionContext

  In core.py constructor, when creating SessionContext, pass the staleness state:

  self.session_context = SessionContext(
      conversation_history=loaded_history,
      conversation_store=conversation_store,
      was_stale_at_load=self._session_is_stale  # Already computed
  )

  Step 3: Simplify CLI.initialize()

  Remove these sections from initialize():
  - Logger info call (line 153-157)
  - Brain display (lines 161-165)
  - Context status display (lines 172-176)
  - _show_semantic_search_progress() call (line 179)
  - Conversation history restoration display (lines 182-186)
  - Session restore offer _check_and_offer_session_restore() (lines 189-190)

  Keep:
  - "Initializing Scrappy..." (line 146)
  - "Available providers: ..." (lines 166-170)
  - Final io.echo() blank line (line 192)

  Step 4: Fix main_screen.py

  Change line 131 to use the snapshot flag:

  if self.interactive_mode.session_context.was_stale_at_load:

  Step 5: Auto-restore session silently

  Modify _check_and_offer_session_restore() to just load without prompting (or remove the confirm dialog), or simply call orchestrator.load_session() directly in the constructor if session exists.

  ---
  Files to Modify

  1. src/scrappy/cli/session_context.py - Add was_stale_at_load parameter and property
  2. src/scrappy/cli/core.py - Simplify initialize(), pass staleness to SessionContext
  3. src/scrappy/cli/screens/main_screen.py - Use was_stale_at_load instead of is_stale

  Result

  Initializing Scrappy...
  Available providers: cerebras

  Welcome to Scrappy!
    /help   - Show all commands
    /agent  - Run code agent
  Type a message to chat, or use a slash command.


---

### 2. Dependency Check on Startup

```python
# src/cli/core.py

def check_dependencies() -> List[str]:
    """Check for required external tools."""
    missing = []

    # Git (required for checkpoints)
    if not shutil.which("git"):
        missing.append("git")

    # Optional but recommended
    if not shutil.which("rg"):
        logger.info("ripgrep (rg) not found - using slower grep")

    return missing

def startup():
    missing = check_dependencies()
    if missing:
        click.echo(f"[yellow]Missing dependencies: {', '.join(missing)}[/yellow]")
        click.echo("Some features may not work correctly.")
```

### 3. Fix Progress Bar (AGENT_BUGS.md issue)

The issue is that `UnifiedIOProgressReporter` loses numeric values. Fix by using `ProgressReporterProtocol` consistently:

```python
# Bridge callback should pass numeric values, not just strings
def progress_callback(current: int, total: int, message: str):
    self.post_message(IndexingProgress(
        message=message,
        progress=current,
        total=total,
    ))
```

---
