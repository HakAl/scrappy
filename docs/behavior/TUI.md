# TUI Behavior

This document defines the user-visible behavior expected from Scrappy's Textual UI.

## Zones

The TUI is organized into stable zones:

- Transcript: scrollable conversation and output history.
- Activity: current long-running work state.
- Task progress: active task list when present.
- Composer: fixed input area for chat, commands, wizard input, and capture prompts.
- Status: provider, metrics, indexing, prompt, and other status information.

Only the transcript owns transcript scrolling. Activity, task progress, composer, and status are outside transcript scrollback.

## Transcript Scrolling

The transcript uses normal Textual scrollbars. Hidden scrollbars are only acceptable for widgets that are intentionally not scrollable.

The transcript has two scroll modes:

- Following: the viewport stays at the live bottom as new transcript output arrives.
- Reviewing: the user has scrolled away from the live bottom, and new output does not move the viewport.

The user enters reviewing mode by scrolling upward with mouse wheel, PageUp or Home while the transcript has focus, Ctrl+Home, or scrollbar interaction.

The user returns to following mode with Ctrl+End, submitting a command, or scrolling back within the bottom tolerance. The bottom tolerance is 1-2 terminal rows from the maximum scroll offset.

Ctrl+Home and Ctrl+End are transcript shortcuts regardless of focus. They override TextArea's default cursor-to-buffer-start/end behavior.

## Composer And History

Printable input goes to the composer. Command history is available with Up and Down only when composer focus is active and the composer cursor is at the relevant boundary.

History navigation must not block transcript scrollback. Up navigates history only when the composer cursor is on the first line. Down navigates history only when the composer cursor is on the last line. Outside the composer, Up and Down scroll the transcript. In multiline composer input, Up and Down first move the TextArea cursor within the current text.

Multiline input keeps normal TextArea cursor behavior: arrow keys move between lines, Home and End move within the current input line, and history navigation only takes over at the text boundary described above.

## Copy, Cancel, And Exit

Ctrl+C priority is:

1. Copy selected composer text.
2. Copy selected transcript text.
3. Cancel running work when no selection is active.
4. Exit on the existing double-tap escape hatch when no copy or cancel action applies.

Ctrl+Shift+C copies selected composer or transcript text without entering the cancel or exit cascade.

Escape remains the app-level cancel key.

Paste shortcuts are Ctrl+V, Ctrl+Shift+V, and Shift+Insert. They paste the OS clipboard into the focused input. Transcript mouse interactions must not steal transcript selection or scroll position by pasting into the composer.

## Prompts And Wizard

Main chat, setup wizard, capture prompts, copy, paste, focus, and transcript behavior use the same chat surface infrastructure. Screens vary by feature configuration and command handler, not by reimplementing interaction policy.

During capture mode, transcript scroll and composer cursor keys remain functional. Command history is blocked until capture mode exits.

Wizard-specific transcript output routes to the wizard surface while the wizard is active. Main transcript events posted while a non-main surface is active are buffered and replayed when the main surface becomes active again.

Activity, indexing progress, and metrics shown after a wizard or non-main surface closes reflect the latest state at that moment, not a replay of every intermediate change.

On Windows terminals, Scrappy keeps `restore_mouse_support()` as the supported recovery layer for terminal mouse reporting after startup, command execution, or native-library noise. Subprocess output must still be captured or routed through the TUI sink; raw stdout/stderr writes while Textual owns the terminal are a bug.

## Resize

Existing transcript content reflows on terminal resize. Active transcript selection is cleared on width changes so selection cannot point at stale rendered rows.

The runtime transcript model is separate from SQLite conversation persistence and session conversation history.

## Verification Notes

Pilot tests cover keyboard and app-level behavior when Textual exposes the needed state. Scrollbar visibility may require manual smoke testing if the pilot harness cannot expose a reliable scrollbar attribute.

Manual Windows terminal smoke should include:

- scroll up through old transcript output.
- new output while reviewing old output.
- Ctrl+End returning to live bottom.
- mouse selection and Ctrl+C copy.
- setup wizard input and paste behavior.
- terminal resize during active output.
