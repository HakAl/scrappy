### 1. Click + Select Text Bug
---

**Symptoms:**
- When users click chat log, background changes color
- To select text, users must hold shift (terminal fallback)
- Shift selection is broken - can't 'unselect' once a point is selected
- Can't use mouse scroll during selection

**Root Causes (Confirmed):**

Textual is awfule.

**Solution: Replace Textual w/propmt_toolkit**
prompt_toolkit is a much better fit for your use case:

  Why prompt_toolkit wins:

  1. Native text selection - Click+drag works out of the box, no hacks needed
  2. Rich integration - Works seamlessly with Rich, no need to remove styling
  3. Simpler architecture - Single-threaded async, no message-passing overhead
  4. Cleaner code - No ThreadSafeAsyncBridge, no worker threads, no message queues
  5. Proven combo - IPython, pgcli, mycli all use prompt_toolkit + Rich successfully

  Textual's threading is indeed crazy:
  - You saw it: ThreadSafeAsyncBridge, @work(exclusive=False, thread=True), message queues
  - Everything requires routing through messages: WriteOutput, WriteRenderable, RequestInlineInput
  - Worker threads posting messages to the main thread just to update UI
  - Way more complexity than you need for a chat interface

  Migration effort:
  - Rip out all the Textual screens/widgets/messages
  - Replace with prompt_toolkit Application and Layout
  - Use Rich renderables directly - no adapter layer needed
  - Simpler input handling with prompt_toolkit's key bindings
  - Less code overall

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
