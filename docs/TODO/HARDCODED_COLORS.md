# Hardcoded Colors Cleanup

**Status:** In Progress
**Goal:** Replace all hardcoded colors with theme colors via `io.theme`

## Architecture Principle

All display output should use `io.theme` properties instead of hardcoded color strings:

```python
# ❌ BAD - Hardcoded colors
io.secho("Success!", fg="green")
io.style(text, fg="cyan")

# ✅ GOOD - Theme colors
io.secho("Success!", fg=io.theme.success)
io.style(text, fg=io.theme.primary)
```

## Theme Color Mapping

| Hardcoded Color | Light Theme    | Dark Theme     | Theme Property      |
|----------------|----------------|----------------|---------------------|
| `"cyan"`       | `#0000ff` (blue) | `#00ffff` (cyan) | `io.theme.primary`  |
| `"yellow"`     | `#ffff00` (yellow) | `#ffff00` (yellow) | `io.theme.warning`  |
| `"green"`      | `#00ff00` (green) | `#00ff00` (green) | `io.theme.success`  |
| `"red"`        | `#ff0000` (red) | `#ff0000` (red) | `io.theme.error`    |
| `"magenta"`    | `#ff00ff` (magenta) | `#ff00ff` (magenta) | `io.theme.accent`   |
| `"blue"`       | `#0000ff` (blue) | `#0000ff` (blue) | `io.theme.info`     |

## Completed ✅

### Core Initialization (src/cli/core.py)
- [x] "Initializing Scrappy..." - now uses `io.theme.primary`
- [x] "Verbose provider selection enabled" - now uses `io.theme.warning`
- [x] Brain name display - now uses `io.theme.success`
- [x] "Brain: None" warning - now uses `io.theme.warning`
- [x] Available providers list - now uses `io.theme.primary`
- [x] "No providers available" - now uses `io.theme.warning`
- [x] Context status (cached) - now uses `io.theme.primary`
- [x] Context status (not explored) - now uses `io.theme.warning`
- [x] "Session restored successfully!" - now uses `io.theme.success`
- [x] Semantic search status - now uses theme colors

### Session Management (src/cli/utils/session_utils.py)
- [x] "Previous session detected:" - now uses `io.theme.warning`

### Display Functions (src/cli/display_rich.py)
- [x] All functions updated to use `io.theme` instead of separate theme parameter
- [x] Removed `DEFAULT_THEME` import

### Banner (src/cli/interactive_banner.py)
- [x] Updated to use `io.theme` from UnifiedIO

## Remaining Work 🚧

### High Priority (User-Facing Output)

#### src/cli/display.py (50+ occurrences)
Main display functions for help, status, providers, usage:
- [ ] Lines 47-48: Help header - `fg="cyan"` → `io.theme.primary`
- [ ] Lines 92-93: Status header - `fg="cyan"` → `io.theme.primary`
- [ ] Line 95: Brain display - `fg='green'` → `io.theme.success`
- [ ] Lines 113-114: Providers header - `fg="cyan"` → `io.theme.primary`
- [ ] Lines 121-122: Active provider - `fg="green"` → `io.theme.success`
- [ ] Lines 134-135: Unconfigured provider - `fg="red"` → `io.theme.error`
- [ ] Line 164: Validation error - `fg="red"` → `io.theme.error`
- [ ] Line 169: Brain switch success - `fg="green"` → `io.theme.success`
- [ ] Lines 194-195: Usage header - `fg="cyan"` → `io.theme.primary`
- [ ] Line 205: Provider name - `fg="cyan"` → `io.theme.primary`
- [ ] Line 240: Error message - `fg="red"` → `io.theme.error`
- [ ] Lines 249, 262: "(default)" label - `fg="green"` → `io.theme.success`

#### src/cli/command_router.py (10+ occurrences)
Command handling and feedback:
- [ ] Line 136: "Goodbye!" - `fg="cyan"` → `io.theme.primary`
- [ ] Line 247: Smart query toggle - `fg="green"/"yellow"` → theme colors
- [ ] Line 272: "Conversation history cleared" - `fg="green"` → `io.theme.success`
- [ ] Line 292: "No active plan" - `fg="yellow"` → `io.theme.warning`
- [ ] Lines 302, 305: Verbose mode - `fg="green"/"yellow"` → theme colors
- [ ] Line 331: Invalid command - `fg="red"` → `io.theme.error`
- [ ] Line 350: Unknown command - `fg="yellow"` → `io.theme.warning`

#### src/cli/input_handler.py (3 occurrences)
User input prompts:
- [ ] Line 62: Multiline input prompt - `fg="cyan"` → `io.theme.primary`
- [ ] Line 133: "You> " prompt - `fg="green"` → `io.theme.accent`
- [ ] Line 174: "... " continuation - `fg="green"` → `io.theme.accent`

#### src/cli/smart_query.py (3 occurrences)
Smart query workflow:
- [ ] Line 94: "[Smart Query] Analyzing intent..." - `fg="cyan"` → `io.theme.primary`
- [ ] Line 120: "[Smart Query] Researching..." - `fg="cyan"` → `io.theme.primary`
- [ ] Line 159: "Assistant: " - `fg="blue"` → `io.theme.info`

### Medium Priority (Feature-Specific)

#### src/cli/codebase.py (4 occurrences)
Context/codebase operations:
- [ ] Line 68: Path not exist error - `fg="red"` → `io.theme.error`
- [ ] Line 72: Not a directory error - `fg="red"` → `io.theme.error`
- [ ] Line 133: "Context saved!" - `fg="green"` → `io.theme.success`
- [ ] Line 142: "Saved to:" - `fg="green"` → `io.theme.success`

#### src/cli/agent_manager.py (10 occurrences)
Code agent operations:
- [ ] Line 99: Checkpoint created - `fg="green"` → `io.theme.success`
- [ ] Line 101: Checkpoint warning - `fg="yellow"` → `io.theme.warning`
- [ ] Line 113: DRY RUN mode - `fg="yellow"` → `io.theme.warning`
- [ ] Line 129: Task completed - `fg="green"` → `io.theme.success`
- [ ] Line 131: Task not complete - `fg="yellow"` → `io.theme.warning`
- [ ] Line 146: Audit log - `fg="cyan"` → `io.theme.primary`
- [ ] Line 152: Rollback success - `fg="green"` → `io.theme.success`
- [ ] Line 154: Rollback failed - `fg="red"` → `io.theme.error`
- [ ] Line 169: Agent error - `fg="red"` → `io.theme.error`

#### src/cli/tasks.py (3 occurrences)
Task planning and reasoning:
- [ ] Line 74: Planning error - `fg="red"` → `io.theme.error`
- [ ] Line 90: Recommended provider - `fg="cyan"` → `io.theme.primary`
- [ ] Line 161: Reasoning error - `fg="red"` → `io.theme.error`

#### src/cli/multiprovider.py (7 occurrences)
Multi-provider synthesis:
- [ ] Line 79: "Need at least 2 providers" - `fg="yellow"` → `io.theme.warning`
- [ ] Line 90: " Done (tokens)" - `fg="green"` → `io.theme.success`
- [ ] Line 92: " Error:" - `fg="red"` → `io.theme.error`
- [ ] Line 95: "Not enough responses" - `fg="yellow"` → `io.theme.warning`
- [ ] Line 151: Missing args - `fg="yellow"` → `io.theme.warning`
- [ ] Line 159: Validation error - `fg="red"` → `io.theme.error`
- [ ] Line 180: Error - `fg="red"` → `io.theme.error`

#### src/cli/persistence.py (7 occurrences)
Session persistence:
- [ ] Line 104: Validation error - `fg="red"` → `io.theme.error`
- [ ] Lines 117-118: Session header - `fg="magenta"` → `io.theme.accent`
- [ ] Line 148: Session saved - `fg="green"` → `io.theme.success`
- [ ] Line 151: Save error - `fg="red"` → `io.theme.error`
- [ ] Line 156: Session loaded - `fg="green"` → `io.theme.success`
- [ ] Line 172: Session cleared - `fg="green"` → `io.theme.success`

#### src/cli/state_manager.py (17 occurrences)
Plan execution state:
- [ ] Lines 126-127: Task progress separator - `fg="cyan"` → `io.theme.primary`
- [ ] Line 137: Task separator - `fg="cyan"` → `io.theme.primary`
- [ ] Line 154: Plan summary - `fg="cyan"` → `io.theme.primary`
- [ ] Lines 174-175: Current plan header - `fg="cyan"` → `io.theme.primary`
- [ ] Line 213: Non-interactive mode - `fg="yellow"` → `io.theme.warning`
- [ ] Line 218: "What next?" - `fg="cyan"` → `io.theme.primary`
- [ ] Line 229: Ending session - `fg="yellow"` → `io.theme.warning`
- [ ] Line 235: Task complete - `fg="green"` → `io.theme.success`
- [ ] Line 240: All tasks complete - `fg="green"` → `io.theme.success`
- [ ] Line 249: Continuing - `fg="yellow"` → `io.theme.warning`
- [ ] Line 254: Skipped task - `fg="yellow"` → `io.theme.warning`
- [ ] Line 259: Plan complete (skipped) - `fg="yellow"` → `io.theme.warning`
- [ ] Line 268: Ending session - `fg="yellow"` → `io.theme.warning`

### Low Priority (Error Handling & Utilities)

#### src/cli/cache_manager.py (1 occurrence)
- [ ] Line 82: Validation error - `fg="red"` → `io.theme.error`

#### src/cli/rate_limiter.py (3 occurrences)
- [ ] Line 97: Validation error - `fg="red"` → `io.theme.error`
- [ ] Line 112: Provider reset success - `fg="green"` → `io.theme.success`
- [ ] Line 117: All reset success - `fg="green"` → `io.theme.success`

#### src/cli/utils/session_utils.py (remaining)
- [ ] Line 52: Resumed session - `fg="green"` → `io.theme.success`
- [ ] Line 78: No session found - `fg="yellow"` → `io.theme.warning`
- [ ] Line 81: Load error - `fg="red"` → `io.theme.error`
- [ ] Line 99: Session saved - `fg="green"` → `io.theme.success`
- [ ] Line 114: Save warning - `fg="yellow"` → `io.theme.warning`
- [ ] Line 154: Last conversation - `fg="cyan"` → `io.theme.primary`
- [ ] Line 179: Not saved - `fg="yellow"` → `io.theme.warning`

#### src/cli/utils/error_utils.py (5 occurrences)
- [ ] Line 33: Click error - `fg="red"` → `io.theme.error`
- [ ] Lines 50, 52: Error messages - `fg="red"` → `io.theme.error`
- [ ] Line 62: Error message - `fg="red"` → `io.theme.error`
- [ ] Lines 101, 105: Interrupted - `fg="yellow"` → `io.theme.warning`

#### src/cli/utils/error_handler.py (7 occurrences)
- [ ] Lines 226, 253, 270, 287, 306, 332: All errors - `fg="red"` → `io.theme.error`

#### src/cli/error_recovery/ (4 occurrences)
- [ ] fallback.py lines 117, 119: Degraded mode - `fg="yellow"` → `io.theme.warning`
- [ ] context.py lines 107, 294, 384: Errors - `fg="red"` → `io.theme.error`

#### src/cli/commands.py (30+ occurrences)
**Note:** commands.py uses `click.secho` directly instead of `io.secho`. This needs different handling - either:
1. Pass `io` to these functions and use `io.secho`
2. Accept theme and map to Click color names

### Special Cases

#### ToolResult.__rich__() (src/agent_tools/tools/base.py)
```python
# Line 125
return Text(f"Error: {self.error}", style=f"bold {DEFAULT_THEME.error}")
```
**Issue:** Called automatically by Rich, doesn't have access to io.
**Solution:** Either keep using DEFAULT_THEME or pass theme when creating ToolResult.

## Implementation Strategy

### Phase 1: Core User Experience (Completed ✅)
- [x] Initialization flow (core.py)
- [x] Session restore (session_utils.py)
- [x] Welcome banner (interactive_banner.py)
- [x] Display functions (display_rich.py)

### Phase 2: Interactive Commands (In Progress)
- [ ] Command routing and feedback (command_router.py)
- [ ] User input prompts (input_handler.py)
- [ ] Help and status displays (display.py)
- [ ] Smart query workflow (smart_query.py)

### Phase 3: Feature Operations
- [ ] Agent management (agent_manager.py)
- [ ] Task planning (tasks.py, state_manager.py)
- [ ] Context/codebase (codebase.py)
- [ ] Multi-provider (multiprovider.py)
- [ ] Session persistence (persistence.py)

### Phase 4: Error Handling
- [ ] Error utilities (error_utils.py, error_handler.py)
- [ ] Error recovery (error_recovery/)

### Phase 5: One-Off Commands
- [ ] Refactor commands.py to use io instead of click directly

## Testing Checklist

After each phase, test with both themes:
- [ ] `preset: light` - Verify blue/magenta colors (not cyan/yellow)
- [ ] `preset: dark` - Verify cyan/yellow colors unchanged

## Notes

- Priority based on user visibility and frequency of use
- Error messages can remain red (consistent across themes)
- Success messages can remain green (consistent across themes)
- Primary accent colors (cyan → blue) are the most critical changes
