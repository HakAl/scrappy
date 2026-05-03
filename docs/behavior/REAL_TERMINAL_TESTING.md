# Real Terminal Testing

## Purpose

Some Scrappy behaviors only fail in a real terminal environment:

- text selection in the output log
- clipboard copy/paste
- terminal focus and mouse delivery
- terminal state recovery after subprocess-heavy flows

Textual pilot tests and headless integration tests do not cover those boundaries well enough. This harness exists to test the real app in a real terminal while keeping the scenario itself platform-neutral.

## Design

The real-terminal test infrastructure is split into four layers:

- `tests/integration/real_terminal_harness.py`
  - Defines the shared protocol and scenario data types.
- `tests/integration/real_terminal_scenario.py`
  - Runs the shared `/help` selection-and-copy scenario against any harness implementation.
- `tests/integration/platform_terminal_harness.py`
  - Selects the best harness for the current platform.
- `tests/integration/*_terminal_harness.py`
  - Platform-specific drivers.

The shared scenario must not import platform APIs directly.

## Shared Contract

Every platform harness implements `RealTerminalHarnessProtocol`.

Required responsibilities:

- launch Scrappy in an isolated real terminal
- wait for app readiness using a real signal, not just process startup
- focus the input safely
- submit commands
- drag-select output text
- copy selection
- read clipboard
- append structured debug artifacts
- close owned resources and restore transient session state when the driver owns it

The shared scenario drives only these methods:

1. launch
2. wait until ready
3. focus input
4. submit `/help`
5. drag-select the output region
6. try primary copy
7. try fallback copy if needed
8. assert clipboard content
9. close and restore transient state

## Artifact Conventions

Each session gets workspace-local artifacts under `.tmp_terminal_spike_logs/`.

Expected artifacts:

- `*.jsonl`
  - structured debug log from both the app and harness
- `*.ready`
  - file-based readiness marker written by the app

Structured logs should include:

- timestamp
- source
- stage or event name
- key fields needed to reconstruct failure location

App-level startup instrumentation is opt-in via:

- `SCRAPPY_INTEGRATION_LOG_PATH`
- `SCRAPPY_READY_FILE`

These variables must only affect debug/integration behavior and must not change normal app behavior.

## Isolation Requirements

The harness must not run on the user's active desktop session unless the operator explicitly accepts that risk.

Minimum isolation properties:

- input is only sent after verifying the owned window has focus
- teardown only targets the owned process/window
- clipboard use is restored or explicitly contained
- logs and artifacts are preserved in the workspace

What does not count as sufficient isolation:

- headless Textual pilot tests
- plain subprocess execution without a real terminal
- Docker by itself for GUI selection/clipboard verification
- shared terminal hosts without exact ownership guarantees

## Platform Strategy

### Windows

Current implementation:

- `tests/integration/windows_console_harness.py`
- launches a dedicated PowerShell console with `CREATE_NEW_CONSOLE`
- verifies focus before input
- validates env names before building the PowerShell launch script
- restores prior clipboard state in `close()`

Isolation backends to consider:

- owned console on a disposable session
- Windows Sandbox
- Hyper-V VM

Avoid:

- shared Windows Terminal teardown by host process
- global input without hwnd verification

### macOS

Status:

- placeholder only

Likely driver directions:

- iTerm2 for owned window and session identity
- AppleScript for launch and ownership operations
- frontmost-app guards before input, similar to the Windows driver
- Accessibility-backed input for real typing and drag selection
- `pbcopy` and `pbpaste` for clipboard assertions
- isolated user session or VM for safe runs

Isolation model:

- macOS should be treated like the Windows driver, not the Linux nested-display driver
- the harness can verify owned window identity and frontmost-app state
- it cannot claim display-level isolation on the user's desktop

Questions to resolve:

- selection gesture reliability under Accessibility automation
- best isolation boundary for CI and local use

Important prerequisite:

- the automation runner must have Accessibility permission in macOS Privacy and Security settings
- CI will likely require a provisioned VM image with that permission already granted

### Linux

Status:

- placeholder only

First implementation target:

- X11-first driver, not a generic claim for every Linux desktop stack
- Xephyr over Xvfb for the first real selection driver
- isolated nested X server such as Xephyr, or a VM if nested X is unavailable
- `xterm` as the first terminal emulator target
- `xdotool` for focus, typing, and drag gestures
- clipboard via an X11 clipboard tool such as `xclip`

Why X11 first:

- the input automation story is much clearer
- nested-display isolation is practical
- clipboard semantics are easier to standardize than under Wayland

Why Xephyr over Xvfb:

- Xephyr provides a real nested X session with real pointer and selection semantics
- drag-selection behavior flows through the X input pipeline instead of a framebuffer-only test server
- this is closer to what a user experiences when selecting text in a terminal

Why `xterm` first:

- minimal dependencies beyond X11
- predictable geometry
- no tabs or terminal UI chrome that complicates coordinate calculations
- widely available in distro packages

Likely execution shape:

1. launch Xephyr on a free display
2. start `xterm` inside that display
3. run Scrappy in the isolated terminal
4. use `xdotool` against that display only
5. assert clipboard contents from that display context with `xclip`

Non-goal for the first Linux driver:

- full Wayland support in the same implementation

Concrete harness shape:

- `launch()`
  - start Xephyr on a free display
  - launch `xterm` on that display
  - run `python -m scrappy.cli.commands` inside the isolated terminal
  - record the Xephyr PID, xterm PID, and xterm window id
- `wait_until_ready()`
  - poll the shared `SCRAPPY_READY_FILE`
- `focus_input()`
  - focus the xterm window with `xdotool`
  - move to the window-relative input point
  - click button 1
- `drag_select()`
  - use `xdotool` mouse movement and button press/release in steps
- `copy_selection()`
  - use the terminal's configured copy shortcut if available
  - otherwise use the terminal/X11 selection path defined by the driver contract
- `read_clipboard()`
  - read from the isolated display with `xclip -selection clipboard -o`
- `close()`
  - kill the xterm process
  - kill the Xephyr process

Isolation property:

- all input is scoped to the nested X display owned by the harness
- the active host desktop does not need foreground-window guards in the same way as the Windows driver
- clipboard reads and writes are scoped to that display context

Questions to resolve:

- Wayland support strategy
- nested display choice
- whether `xterm` should rely on CLIPBOARD, PRIMARY, or an explicit selection-to-clipboard configuration
- clipboard behavior differences across desktop environments
- whether Linux CI should prefer VM-backed isolation over nested X

## Readiness

There are two different readiness problems:

- app startup readiness
- post-command render readiness

Current state:

- app startup readiness uses a file marker written after `ScrappyApp.on_cliready()` and a refresh pass
- post-`/help` render readiness still uses a timed wait

Tracked follow-up:

- `scrappy-dwk3`: replace the post-command render sleep with a stronger rendered-output readiness signal

## Test Scope

The shared scenario is intentionally narrow:

- fixture repo
- installed Scrappy
- startup
- `/help`
- drag selection
- copy
- clipboard assertion

This is not a full UI automation framework. The goal is to pin down real-terminal regressions that headless tests miss.

## Safety Rules

Before any live run:

- confirm the isolation backend is appropriate for the operator's current machine state
- never close shared terminal hosts without exact ownership proof
- never send global keyboard or mouse input without a foreground-window guard
- never discard debug artifacts on failure

If the harness cannot prove ownership or focus, it must fail closed.

## Current Gaps

- macOS driver is not implemented
- Linux driver is not implemented
- Linux needs an explicit X11-first driver and a separate Wayland follow-up
- post-command render readiness still uses a timed wait
- cross-platform isolated session orchestration is not implemented yet

Tracked work:

- `scrappy-1izp`: implement macOS and Linux drivers
- `scrappy-36xl`: Linux X11-first plan and explicit Wayland follow-up
- `scrappy-dwk3`: replace post-`/help` render sleep with a stronger readiness signal
