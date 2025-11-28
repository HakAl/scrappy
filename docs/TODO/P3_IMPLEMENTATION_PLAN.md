# P3 Issues Implementation Plan

This document outlines the implementation plan for all Priority 3 (Medium Impact) issues from `ISSUES_PRIORITIZED.md`.

---

## Overview

| Issue | Description | Complexity | Dependencies |
|-------|-------------|------------|--------------|
| 3.2/3.3 | Color Theme Inconsistency / Help Table All White | Medium | Theme system first |

---


## Issues 3.2/3.3: Color Theme Inconsistency / White Tables

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