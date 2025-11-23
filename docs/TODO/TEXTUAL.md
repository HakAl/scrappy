[//]: # (GOAL)
 
Integrate textual 
- create an area at the bottom of terminal below user input to display status
  - phase 1 -- integrate textual and display our existing app (header, static, input, RichLog, etc)
  - phase 2 -- add the footer to serve as our status area.
  - phase 3 -- integrate status elements eg: progress into status area

[//]: # (START PLAN)

## Architecture: Proper Library Separation

**Click** - CLI argument parsing and commands ONLY (input layer)
**Rich** - All styled output (Panels, Tables, Text, Syntax highlighting, etc.)
**Textual** - Layout and organization (widgets, TUI structure, event handling)

### Current Architecture Understanding (Complete)

**Entry Flow:**
```
scrappy.py → CLI.interactive_mode() → TextualInteractiveMode.run()
    ↓
ScrappyApp (Textual event loop - async)
    ↓
on_input_submitted() → run_worker(_process_input_worker)
    ↓
asyncio.to_thread(InteractiveMode._process_input) [runs in thread pool]
    ↓
CommandRouter.route() OR Orchestrator.delegate() [blocking I/O]
    ↓
Output via TextualIO.echo/secho → RichLog widget
```

**Thread Safety Issue:**
- InteractiveMode runs in worker thread (via asyncio.to_thread)
- TextualIO writes to RichLog widget from worker thread
- Textual widgets are NOT thread-safe
- Widget updates from threads are lost → no visible output

---

## Current Status: BROKEN

### Fix Plan

  Problem Analysis

  1. What works: Main thread widget writes (banner, test message showed)
  2. What doesn't work: Worker thread trying to write to widgets when processing commands
  3. Root cause: Textual widgets aren't thread-safe, but InteractiveMode._process_input() runs in a worker thread
  and calls IO methods

  The Plan

  Solution: Use Textual's message system for thread-safe output

  Instead of having TextualIO write directly to widgets, create a custom message that the app handles:

  1. Create a WriteOutput message class
  2. TextualIO posts messages instead of writing directly
  3. ScrappyApp handles messages and updates widgets on main thread
  4. This works from any thread (main or worker)

  This is the clean, Textual-native way. Want me to implement this approach, or do you have a different solution in
  mind?


## Expected Outcome

- App behaves as it did previous to textual integration with all existing features.

[//]: # (END PLAN)

       