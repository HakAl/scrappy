# P3 Issues Implementation Plan

This document outlines the implementation plan for all Priority 3 (Medium Impact) issues from `ISSUES_PRIORITIZED.md`.

---

## Overview

| Issue | Description | Complexity | Dependencies |
|-------|-------------|------------|--------------|
| 3.1 | .lancedb Directory at Project Root | Low | None |
| 3.2/3.3 | Color Theme Inconsistency / Help Table All White | Medium | Theme system first |
| 3.4 | Semantic Search Indexing Progress Not in Status Bar | Medium | Status bar integration |

---

## Issue 3.1: .lancedb Directory at Project Root

### Problem Summary
Default `db_dir_name = ".lancedb"` creates database directory at project root instead of `.scrappy/lancedb/`. This causes clutter and inconsistency with other Scrappy data files.

### Root Cause
- `src/context/semantic/config.py:44` has hardcoded default `.lancedb`
- `src/context/semantic/initializer.py:260` overrides this to `.scrappy/lancedb` only when using the initializer
- Direct usage of `LanceDBSearchProvider` without the initializer uses the wrong default

### Design Approach

**Single Source of Truth**: Change the default in `SemanticIndexConfig` dataclass so ALL code paths use `.scrappy/lancedb` by default.

**Protocol Compliance**: No protocol changes needed - `SemanticIndexConfig` is a dataclass, not a protocol.

**Backward Compatibility**: Existing code that explicitly sets `db_dir_name` will continue to work.

### Implementation Steps

#### Step 1: Update Default Configuration
**File**: `src/context/semantic/config.py`

```python
# Line 44: Change from
db_dir_name: str = ".lancedb"

# To
db_dir_name: str = ".scrappy/lancedb"
```

**Rationale**: Single source of truth - all code using `SemanticIndexConfig()` without explicit override will get the correct path.

#### Step 2: Remove Redundant Override in Initializer
**File**: `src/context/semantic/initializer.py`

```python
# Lines 260-264: Change from
config = SemanticIndexConfig(db_dir_name=".scrappy/lancedb")
search_provider = LanceDBSearchProvider(
    self._project_path,
    chunker,
    config=config,
)

# To
search_provider = LanceDBSearchProvider(
    self._project_path,
    chunker,
    # Uses default config with correct db_dir_name
)
```

**Rationale**: Default is now correct, override is unnecessary noise.

#### Step 3: Update Test Assertion
**File**: `tests/context/test_semantic_config.py`

```python
# Lines 43-46: Change from
def test_default_db_dir_name(self):
    """Default db dir name should be .lancedb."""
    config = SemanticIndexConfig()
    assert config.db_dir_name == ".lancedb"

# To
def test_default_db_dir_name(self):
    """Default db dir name should be .scrappy/lancedb."""
    config = SemanticIndexConfig()
    assert config.db_dir_name == ".scrappy/lancedb"
```

#### Step 4: Verify File Collector Exclusion
**File**: `src/context/file_collector.py`

Review `ignore_names` set to ensure `.scrappy` is excluded (it already is). Remove `.lancedb` from exclusions since it will no longer be created at root.

```python
# Line 36-44: Update ignore_names set
ignore_names: Set[str] = {
    '.scrappy',  # Keep - main data directory
    # Remove '.lancedb' - no longer created at root
    ...
}
```

### Testing Strategy

1. **Unit Test**: Verify `SemanticIndexConfig()` default is `.scrappy/lancedb`
2. **Integration Test**: Create provider without explicit config, verify DB created in `.scrappy/lancedb/`
3. **Regression Test**: Verify existing code with explicit `db_dir_name` still works

### Files Modified
- `src/context/semantic/config.py` (1 line)
- `src/context/semantic/initializer.py` (3 lines)
- `tests/context/test_semantic_config.py` (2 lines)
- `src/context/file_collector.py` (1 line - optional cleanup)

---

## Issues 3.2/3.3: Color Theme Inconsistency / Help Table All White

### Problem Summary
- Colors used inconsistently across the application (rainbow of colors for tools/commands)
- Help table output lacks consistent styling
- No centralized theme system

### Root Cause Analysis
1. **Scattered Color Definitions**: Colors defined inline throughout codebase
   - `interactive_banner.py`: cyan, yellow, white, green
   - `display_rich.py`: Uses io.table() (no explicit colors)
   - `cache_formatter.py`: cyan, green, yellow, red via click.style()
   - `stats_formatter.py`: cyan (headers), green/yellow/red (percentages)
   - `scrappy.tcss`: $surface, $text, $text-muted, $accent

2. **Two Styling Systems**:
   - Rich markup for CLI mode
   - Textual CSS for TUI mode

3. **No Theme Protocol**: Components directly use color strings instead of theme abstraction

### Design Approach

**Protocol-First**: Define `ThemeProtocol` that provides color values for semantic purposes (not literal colors).

**Dependency Injection**: Components receive theme via constructor, enabling testing and customization.

**Single Source of Truth**: One theme definition used by both formatters and CSS generation.

### Architecture

```
ThemeProtocol (Protocol)
    |
    +-- ScrappyTheme (Default implementation)
    |
    +-- TestTheme (For testing)

Theme Colors (Semantic):
    - primary: Main accent color (cyan)
    - secondary: Secondary accent (yellow)
    - success: Positive/enabled states (green)
    - warning: Caution states (yellow)
    - error: Error/disabled states (red)
    - text: Normal text (white/gray)
    - text_muted: Dimmed text (gray)
    - border: Panel/table borders (cyan)
```

### Implementation Steps

#### Step 1: Define Theme Protocol
**New File**: `src/infrastructure/theme.py`

```python
"""
Theme system for consistent color styling.

Provides a protocol-based theme system that works across CLI and TUI modes.
"""

from typing import Protocol
from dataclasses import dataclass


class ThemeProtocol(Protocol):
    """Protocol for application theming.

    Defines semantic color names that map to actual colors.
    Components should use semantic names (primary, success, error)
    instead of literal colors (cyan, green, red).
    """

    @property
    def primary(self) -> str:
        """Primary accent color for headers, borders, highlights."""
        ...

    @property
    def secondary(self) -> str:
        """Secondary accent for commands, keywords."""
        ...

    @property
    def success(self) -> str:
        """Success/enabled/positive states."""
        ...

    @property
    def warning(self) -> str:
        """Warning/caution states."""
        ...

    @property
    def error(self) -> str:
        """Error/disabled/negative states."""
        ...

    @property
    def text(self) -> str:
        """Normal text color."""
        ...

    @property
    def text_muted(self) -> str:
        """Dimmed/secondary text."""
        ...


@dataclass(frozen=True)
class ScrappyTheme:
    """Default Scrappy theme.

    Colors derived from welcome banner and existing CSS.
    """
    primary: str = "cyan"
    secondary: str = "yellow"
    success: str = "green"
    warning: str = "yellow"
    error: str = "red"
    text: str = "white"
    text_muted: str = "bright_black"


@dataclass(frozen=True)
class TestTheme:
    """Theme for testing - no colors."""
    primary: str = ""
    secondary: str = ""
    success: str = ""
    warning: str = ""
    error: str = ""
    text: str = ""
    text_muted: str = ""


# Default theme instance
DEFAULT_THEME = ScrappyTheme()
```

#### Step 2: Update StatsFormatter Base Class
**File**: `src/infrastructure/formatters/stats_formatter.py`

```python
"""
Base stats formatter implementation with theme support.
"""

from typing import Any, Optional
from ..theme import ThemeProtocol, DEFAULT_THEME


class StatsFormatter:
    """Base formatter for statistics displays with theme support."""

    def __init__(
        self,
        use_color: bool = True,
        theme: Optional[ThemeProtocol] = None
    ):
        """Initialize formatter.

        Args:
            use_color: Whether to use ANSI color codes
            theme: Theme for colors (defaults to ScrappyTheme)
        """
        self._use_color = use_color
        self._theme = theme or DEFAULT_THEME

    def format_header(self, title: str, width: int = 60) -> str:
        """Format header using theme primary color."""
        if self._use_color:
            header = f"[bold {self._theme.primary}]{title}[/bold {self._theme.primary}]"
            separator = f"[{self._theme.primary}]{'-' * width}[/{self._theme.primary}]"
        else:
            header = f"\n{title}"
            separator = "-" * width
        return f"{header}\n{separator}"

    def format_boolean_status(
        self,
        value: bool,
        true_label: str = "Enabled",
        false_label: str = "Disabled"
    ) -> str:
        """Format boolean with theme success/error colors."""
        label = true_label if value else false_label
        if not self._use_color:
            return label

        color = self._theme.success if value else self._theme.error
        return f"[{color}]{label}[/{color}]"

    def _get_percentage_color(self, percentage: float) -> str:
        """Get theme color based on percentage."""
        if percentage < 75:
            return self._theme.success
        elif percentage < 90:
            return self._theme.warning
        else:
            return self._theme.error
```

#### Step 3: Update CacheFormatter
**File**: `src/infrastructure/formatters/cache_formatter.py`

```python
"""Cache formatter with theme support."""

from typing import Dict, Any, Optional
from ..theme import ThemeProtocol, DEFAULT_THEME
from .stats_formatter import StatsFormatter


class CacheFormatter(StatsFormatter):
    """Formatter for cache statistics with theme support."""

    def __init__(
        self,
        use_color: bool = True,
        theme: Optional[ThemeProtocol] = None
    ):
        super().__init__(use_color=use_color, theme=theme)

    def format_hit_rate(self, rate_str: str, label: str = "Hit Rate") -> str:
        """Format hit rate with theme colors."""
        if not self._use_color:
            return f"{label}: {rate_str}"

        try:
            rate_value = float(rate_str.rstrip('%'))
        except (ValueError, AttributeError):
            rate_value = 0.0

        color = self._theme.success if rate_value > 50 else self._theme.warning
        return f"{label}: [{color}]{rate_str}[/{color}]"
```

#### Step 4: Update Help Display with Theme
**File**: `src/cli/display_rich.py`

```python
"""Rich-enhanced display functions with theme support."""

from typing import Optional
from rich.table import Table
from .unified_io import UnifiedIO
from src.infrastructure.theme import ThemeProtocol, DEFAULT_THEME


def show_help_table(
    io: UnifiedIO,
    category: Optional[str] = None,
    theme: Optional[ThemeProtocol] = None
) -> None:
    """Display help with themed styling."""
    theme = theme or DEFAULT_THEME

    # ... existing category definitions ...

    # Build styled table
    table = Table(
        title=f"[bold {theme.primary}]Available Commands[/bold {theme.primary}]",
        title_style=theme.primary,
        header_style=f"bold {theme.primary}",
        border_style=theme.primary
    )

    table.add_column("Command", style=theme.secondary)
    table.add_column("Description", style=theme.text)

    for cat_name, commands in categories.items():
        # Category header row
        table.add_row(
            f"[bold {theme.text_muted}]--- {cat_name} ---[/bold {theme.text_muted}]",
            ""
        )
        for cmd, desc in commands:
            table.add_row(cmd, desc)
        table.add_row("", "")

    # Output via unified IO
    if hasattr(io, '_strategy'):
        io._strategy.output_table(
            ["Command", "Description"],
            [[cmd, desc] for _, cmds in categories.items() for cmd, desc in cmds],
            title="Available Commands"
        )
    else:
        io.console.print(table)
```

#### Step 5: Update Banner with Theme
**File**: `src/cli/interactive_banner.py`

```python
"""Welcome banner with theme support."""

from typing import TYPE_CHECKING, Optional
from rich.panel import Panel
from rich.text import Text
from src.infrastructure.theme import ThemeProtocol, DEFAULT_THEME

if TYPE_CHECKING:
    from src.cli.protocols import UnifiedIOProtocol


def display_banner(
    io: "UnifiedIOProtocol",
    theme: Optional[ThemeProtocol] = None
) -> None:
    """Display themed banner."""
    theme = theme or DEFAULT_THEME

    title_text = Text()
    title_text.append("SCRAPPY", style=f"bold {theme.primary}")
    title_text.append(" - ", style="dim")
    title_text.append("Interactive Mode", style="bold white")

    commands_text = Text()
    commands_text.append("\nQuick Commands:\n", style="bold")
    commands_text.append("  /help", style=theme.secondary)
    commands_text.append("    - Show all commands\n")
    # ... rest of commands using theme.secondary ...

    panel = Panel(
        content,
        title=f"[bold {theme.primary}]Welcome[/bold {theme.primary}]",
        border_style=theme.primary,
        padding=(1, 2)
    )

    # ... existing routing logic ...
```

#### Step 6: Synchronize Textual CSS with Theme
**File**: `src/cli/scrappy.tcss`

Ensure CSS variables match theme defaults:

```css
/* Theme-aligned color variables */
$surface: #1e1e1e;
$text: #d4d4d4;
$text-muted: #808080;
$primary: #00ffff;      /* cyan - matches theme.primary */
$secondary: #ffff00;    /* yellow - matches theme.secondary */
$success: #00ff00;      /* green - matches theme.success */
$warning: #ffcc00;      /* yellow - matches theme.warning */
$error: #ff0000;        /* red - matches theme.error */
$accent: $primary;      /* Alias for backwards compatibility */
```

#### Step 7: Update Cache Manager to Use io.table()
**File**: `src/cli/cache_manager.py`

Replace formatter string output with structured table:

```python
def manage_cache(self, args: str = "") -> None:
    """Manage cache with table output."""
    # ... validation ...

    if validation.subcommand == "":
        stats = self.orchestrator.get_cache_stats()
        enabled = self.orchestrator.caching_enabled

        # Use structured table instead of formatted string
        headers = ["Metric", "Value"]
        rows = [
            ["Total Entries", str(
                stats.get('exact_cache_entries', 0) +
                stats.get('intent_cache_entries', 0)
            )],
            ["Exact Cache Hits", str(stats.get('exact_hits', 0))],
            ["Intent Cache Hits", str(stats.get('intent_hits', 0))],
            ["Cache Misses", str(stats.get('exact_misses', 0))],
            ["Cache Saves", str(stats.get('saves', 0))],
            ["Exact Hit Rate", stats.get('exact_hit_rate', '0.0%')],
            ["Intent Hit Rate", stats.get('intent_hit_rate', '0.0%')],
            ["Cache File", stats.get('cache_file', 'N/A')],
            ["Status", "Enabled" if enabled else "Disabled"],
        ]
        self.io.table(headers, rows, title="Cache Statistics")
```

### Testing Strategy

1. **Unit Tests**: Test theme protocol implementation
2. **Integration Tests**: Verify theme colors applied consistently
3. **Visual Tests**: Manual inspection of CLI and TUI output
4. **Regression Tests**: Ensure existing formatters still work

### Files Modified/Created
- `src/infrastructure/theme.py` (new)
- `src/infrastructure/formatters/stats_formatter.py`
- `src/infrastructure/formatters/cache_formatter.py`
- `src/cli/display_rich.py`
- `src/cli/interactive_banner.py`
- `src/cli/cache_manager.py`
- `src/cli/scrappy.tcss`

---

## Issue 3.4: Semantic Search Indexing Progress Not in Status Bar

### Problem Summary
Status bar exists, semantic search indexing reports progress, but they are not integrated. Users don't see indexing progress in the TUI status bar.

### Root Cause Analysis
1. **SemanticSearchManager** uses `_notify_progress()` callback internally
2. **LanceDBSearchProvider** accepts `ProgressReporterProtocol` for indexing
3. **TextualProgressReporter** can update status bar widget
4. **Gap**: No connection between semantic initialization/indexing and status bar

### Design Approach

**Event-Driven**: Use existing `EventQueueProtocol` for progress events.

**Protocol Extension**: Add progress events to existing event system.

**Status Bar Integration**: Connect progress events to `TextualProgressReporter`.

### Architecture

```
SemanticSearchManager
    |
    +-- progress_callback (existing)
    |
    +-- EventQueue (existing)
            |
            +-- PROGRESS event type (new)
                    |
                    +-- TextualProgressReporter
                            |
                            +-- Status bar widget
```

### Implementation Steps

#### Step 1: Add Progress Event Type
**File**: `src/infrastructure/threading/protocols.py`

```python
class EventType(Enum):
    """Background event types."""
    INIT_COMPLETE = "init_complete"
    INIT_FAILED = "init_failed"
    PROGRESS = "progress"  # NEW: Progress update event


@dataclass
class BackgroundEvent:
    """Event from background operation."""
    event_type: EventType
    source: str
    data: Optional[Any] = None
    error: Optional[Exception] = None
    progress: Optional[float] = None  # NEW: 0.0 to 1.0
    message: Optional[str] = None      # NEW: Progress message
```

#### Step 2: Update SemanticSearchManager to Emit Progress Events
**File**: `src/context/semantic_manager.py`

```python
def _notify_progress(self, message: str, progress: Optional[float] = None) -> None:
    """Notify progress via callback AND event queue."""
    # Existing callback
    if self._progress_callback:
        try:
            self._progress_callback(message)
        except Exception as e:
            logger.debug(f"Error in progress callback: {e}")

    # NEW: Emit progress event for status bar
    if self._event_queue:
        from ..infrastructure.threading.protocols import BackgroundEvent, EventType
        self._event_queue.put(
            BackgroundEvent(
                event_type=EventType.PROGRESS,
                source="semantic_search",
                message=message,
                progress=progress,
            )
        )

def index_files(self, file_collector: 'FileCollectorProtocol') -> None:
    """Index files with progress events."""
    # ... existing setup ...

    total_indexed = 0
    batch_count = 0

    for batch in file_collector.collect_files_batched(batch_size=20):
        batch_count += 1
        batch_size = len(batch)
        total_indexed += batch_size

        # Calculate progress (estimate based on typical project size)
        estimated_total = max(total_indexed, 100)  # Assume at least 100 files
        progress = min(0.95, total_indexed / estimated_total)

        self._notify_progress(
            f"Indexing: batch {batch_count} ({total_indexed} files)",
            progress=progress
        )

        provider.index_files(batch, is_batch=True)

    self._notify_progress("Indexing complete", progress=1.0)
```

#### Step 3: Register Progress Handler in TextualInteractiveMode
**File**: `src/cli/textual_interactive.py`

```python
def _setup_event_handlers(self) -> None:
    """Set up event handlers for background operations."""
    # Existing semantic search handlers
    self._event_queue.register_handler(
        "semantic_search",
        self._handle_semantic_event,
    )

def _handle_semantic_event(self, event: BackgroundEvent) -> None:
    """Handle semantic search events including progress."""
    if event.event_type == EventType.PROGRESS:
        # Update status bar with progress
        self._update_status_bar(event.message, event.progress)
    elif event.event_type == EventType.INIT_COMPLETE:
        self._update_status_bar("Semantic search ready", 1.0)
    elif event.event_type == EventType.INIT_FAILED:
        self._update_status_bar(f"Failed: {event.error}", None)

def _update_status_bar(self, message: str, progress: Optional[float]) -> None:
    """Update status bar with message and optional progress."""
    if self._app:
        # Post message to app's message queue for thread-safe update
        self._app.post_message(UpdateStatusBar(message, progress))
```

#### Step 4: Add Status Bar Update Message
**File**: `src/cli/textual_app.py`

```python
from textual.message import Message


class UpdateStatusBar(Message):
    """Message to update status bar from worker thread."""

    def __init__(self, message: str, progress: Optional[float] = None):
        super().__init__()
        self.message = message
        self.progress = progress


class ScrappyApp(App):
    """Main Textual application."""

    def on_update_status_bar(self, message: UpdateStatusBar) -> None:
        """Handle status bar update message."""
        try:
            status_bar = self.query_one("#status_bar")
            status_content = self.query_one("#status_content", Static)

            # Show status bar
            status_bar.add_class("show")

            # Update content
            if message.progress is not None:
                pct = int(message.progress * 100)
                status_content.update(f"{message.message} [{pct}%]")
            else:
                status_content.update(message.message)

            # Auto-hide when complete
            if message.progress == 1.0:
                self.set_timer(3.0, lambda: status_bar.remove_class("show"))

        except Exception:
            pass  # Fail silently if status bar not available
```

#### Step 5: Only Show for Long Operations
Add threshold check to avoid flashing status bar for quick operations:

```python
class SemanticSearchManager:
    """Manager with timing-aware progress."""

    def __init__(self, ...):
        # ... existing ...
        self._indexing_start_time: Optional[float] = None
        self._progress_threshold_seconds = 10.0  # Show progress after 10s

    def index_files(self, file_collector: 'FileCollectorProtocol') -> None:
        """Index with timed progress reporting."""
        import time
        self._indexing_start_time = time.time()

        # ... existing batching logic ...

        for batch in file_collector.collect_files_batched(batch_size=20):
            # ... existing processing ...

            # Only notify if operation is taking long
            elapsed = time.time() - self._indexing_start_time
            if elapsed > self._progress_threshold_seconds:
                self._notify_progress(
                    f"Indexing: batch {batch_count} ({total_indexed} files)",
                    progress=progress
                )
```

### Testing Strategy

1. **Unit Test**: Verify PROGRESS events emitted during indexing
2. **Integration Test**: Verify status bar updates in TUI mode
3. **Timing Test**: Verify progress only shown after threshold
4. **Visual Test**: Manual inspection of status bar behavior

### Files Modified/Created
- `src/infrastructure/threading/protocols.py` (extend EventType)
- `src/context/semantic_manager.py`
- `src/cli/textual_interactive.py`
- `src/cli/textual_app.py`

---

## Implementation Order

Recommended order based on dependencies and risk:

### Phase 1: Quick Win (Issue 3.1)
- **Effort**: Low
- **Risk**: Low
- **Dependencies**: None
- **Files**: 4

Change default `db_dir_name` - simple, isolated change with clear tests.

### Phase 2: Theme Foundation (Issues 3.2/3.3)
- **Effort**: Medium
- **Risk**: Medium (visual changes)
- **Dependencies**: None
- **Files**: 8

Create theme system and apply to existing formatters. Visual testing required.

### Phase 3: Progress Integration (Issue 3.4)
- **Effort**: Medium
- **Risk**: Low (additive)
- **Dependencies**: Existing event system
- **Files**: 4

Connect progress reporting to status bar. No breaking changes.

---

## Success Criteria

### Issue 3.1
- [ ] `SemanticIndexConfig()` default is `.scrappy/lancedb`
- [ ] New projects don't create `.lancedb` at root
- [ ] All tests pass

### Issues 3.2/3.3
- [ ] `ThemeProtocol` defined and implemented
- [ ] Help table uses theme colors
- [ ] Cache stats use theme colors
- [ ] Banner uses theme colors
- [ ] CSS variables align with theme
- [ ] Visual consistency across CLI and TUI

### Issue 3.4
- [ ] Progress events emitted during indexing
- [ ] Status bar shows indexing progress in TUI
- [ ] Progress hidden for quick operations (<10s)
- [ ] Auto-hide after completion

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Visual regression | Medium | Manual visual testing, screenshot comparison |
| Theme not applied everywhere | Low | Grep for hardcoded colors, systematic update |
| Status bar flicker | Low | Threshold for showing, debouncing |
| Breaking existing tests | Medium | Run full test suite after each change |

---

## References

- `docs/TODO/ISSUES_PRIORITIZED.md` - Original issue documentation
- `CLAUDE.md` - Architecture guidelines
- `src/infrastructure/protocols.py` - Existing protocol patterns
- `src/cli/unified_io.py` - IO abstraction reference
