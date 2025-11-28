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
1. **Scattered Color Definitions**: Colors defined inline across 17 files

2. **Two Styling Systems**:
   - Rich markup for CLI mode
   - Textual CSS for TUI mode

3. **No Theme Protocol**: Components directly use color strings instead of theme abstraction

### Complete File Inventory

All files requiring theme integration (17 total):

#### Infrastructure Layer (3 files)
| File | Current Colors | Usage |
|------|----------------|-------|
| `src/infrastructure/formatters/stats_formatter.py` | cyan, green, yellow, red | Headers, percentages, boolean status |
| `src/infrastructure/formatters/cache_formatter.py` | cyan, green, yellow | Hit rates, toggle messages |
| `src/infrastructure/formatters/rate_limit_formatter.py` | cyan, green, yellow, red | Provider headers, quotas, warnings |

#### Progress/Status Layer (2 files)
| File | Current Colors | Usage |
|------|----------------|-------|
| `src/infrastructure/progress.py` | cyan, green, red | Status messages, spinner text |
| `src/infrastructure/textual_progress.py` | cyan, green, red | TUI progress states |

#### CLI Layer (9 files)
| File | Current Colors | Usage |
|------|----------------|-------|
| `src/cli/interactive_banner.py` | cyan, yellow, white | Title, commands, panel border |
| `src/cli/display_rich.py` | cyan, yellow | Panel borders, status messages |
| `src/cli/unified_io.py` | full color map, blue borders | Core I/O, panel defaults |
| `src/cli/output_bridge.py` | yellow, red, green | Warning/error/success messages |
| `src/cli/rich_dashboard.py` | yellow, green, cyan, blue, white, magenta | State indicators, panel borders |
| `src/cli/task_router_handler.py` | green, yellow, cyan, blue, white | Task type color mapping |
| `src/cli/context_commands.py` | bright_white | Path display |
| `src/cli/interactive.py` | bright_white | User input echo |
| `src/cli/textual_app.py` | red | Error text |

#### Agent Layer (2 files)
| File | Current Colors | Usage |
|------|----------------|-------|
| `src/agent/ui.py` | blue, cyan, yellow, red, green | Thinking/result/warning panels |
| `src/agent_tools/formatters/output_formatter.py` | cyan, yellow, green, red, magenta, white, bright_black | Git diffs, file listings |

#### Tools Layer (2 files)
| File | Current Colors | Usage |
|------|----------------|-------|
| `src/agent_tools/tools/base.py` | bold red | Error display |
| `src/agent_tools/tools/file_tools.py` | bright_black | File sizes |

#### CSS Layer (1 file)
| File | Current Variables | Usage |
|------|-------------------|-------|
| `src/cli/scrappy.tcss` | $surface, $text, $text-muted, $accent (#00ff00), $panel-bg, #ffcc00 | TUI styling |

### Design Approach

**Protocol-First**: Define `ThemeProtocol` that provides color values for semantic purposes (not literal colors).

**Dependency Injection**: Components receive theme via constructor, enabling testing and customization.

**User-Configurable**: Themes loaded from config file, with presets and custom overrides.

**Single Source of Truth**: One theme definition used by both formatters and CSS generation.

### Architecture

```
ThemeProtocol (Protocol)
    |
    +-- ScrappyTheme (Default dark theme)
    |
    +-- LightTheme (Light mode preset)
    |
    +-- SolarizedTheme (Solarized preset)
    |
    +-- TestTheme (For testing - no colors)

Theme Loading:
    Config File -> ThemeLoader -> ThemeProtocol instance

Core Theme Colors (Semantic):
    Foreground:
    - primary: Borders, headers, labels, info text (cyan)
    - accent: Commands, keywords, interactive elements (orange/yellow)
    - success: Enabled states, completions, positive values (green)
    - warning: Caution states, attention needed (yellow)
    - error: Errors, disabled, negative states (red)
    - text: Normal text (white)
    - text_muted: Dimmed/secondary text (bright_black/gray)
    - info: Informational panels, thinking states (blue)

    Background:
    - surface: Main background color (#1e1e1e)
    - surface_alt: Elevated surfaces, panels, status bar (#2d2d2d)

Git/Diff Colors (Fixed - not theme-customizable):
    - git_add: Added lines (green)
    - git_remove: Removed lines (red)
    - git_header: Diff headers, chunk markers (cyan)
    - git_commit: Commit hashes (yellow)

Syntax Colors (File type indicators):
    - syntax_python: Python files (green)
    - syntax_js: JavaScript/TypeScript files (yellow)
    - syntax_config: JSON/YAML/TOML files (magenta)
    - syntax_docs: Markdown/text files (white)
```

### Implementation Steps

#### Step 1: Define Theme Protocol
**New File**: `src/infrastructure/theme.py`

```python
"""
Theme system for consistent color styling.

Provides a protocol-based theme system that works across CLI and TUI modes.
Includes core semantic colors, background colors, git/diff colors, and syntax colors.
Themes are user-configurable via config file.
"""

from typing import Protocol, Optional, Dict, Any
from dataclasses import dataclass, field
from pathlib import Path


class ThemeProtocol(Protocol):
    """Protocol for application theming.

    Defines semantic color names that map to actual colors.
    Components should use semantic names (primary, success, error)
    instead of literal colors (cyan, green, red).
    """

    # Foreground colors
    @property
    def primary(self) -> str:
        """Primary color for borders, headers, labels, info text."""
        ...

    @property
    def accent(self) -> str:
        """Accent color for commands, keywords, interactive elements."""
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
    def info(self) -> str:
        """Informational panels, thinking states."""
        ...

    @property
    def text(self) -> str:
        """Normal text color."""
        ...

    @property
    def text_muted(self) -> str:
        """Dimmed/secondary text."""
        ...

    # Background colors
    @property
    def surface(self) -> str:
        """Main background color."""
        ...

    @property
    def surface_alt(self) -> str:
        """Elevated surface (panels, status bar)."""
        ...


@dataclass(frozen=True)
class GitColors:
    """Fixed colors for git/diff output. Not theme-customizable."""
    add: str = "green"
    remove: str = "red"
    header: str = "cyan"
    commit: str = "yellow"
    meta: str = "bright_white"


@dataclass(frozen=True)
class SyntaxColors:
    """Colors for file type indicators in listings."""
    python: str = "green"
    javascript: str = "yellow"
    config: str = "magenta"
    docs: str = "white"
    default: str = "white"


@dataclass(frozen=True)
class ScrappyTheme:
    """Default dark theme."""
    # Foreground
    primary: str = "cyan"
    accent: str = "yellow"
    success: str = "green"
    warning: str = "yellow"
    error: str = "red"
    info: str = "blue"
    text: str = "white"
    text_muted: str = "bright_black"
    # Background
    surface: str = "#1e1e1e"
    surface_alt: str = "#2d2d2d"
    # Fixed
    git: GitColors = field(default_factory=GitColors)
    syntax: SyntaxColors = field(default_factory=SyntaxColors)


@dataclass(frozen=True)
class LightTheme:
    """Light mode preset."""
    # Foreground
    primary: str = "blue"
    accent: str = "magenta"
    success: str = "green"
    warning: str = "yellow"
    error: str = "red"
    info: str = "cyan"
    text: str = "black"
    text_muted: str = "bright_black"
    # Background
    surface: str = "#ffffff"
    surface_alt: str = "#f0f0f0"
    # Fixed
    git: GitColors = field(default_factory=GitColors)
    syntax: SyntaxColors = field(default_factory=SyntaxColors)


@dataclass(frozen=True)
class TestTheme:
    """Theme for testing - no colors applied."""
    primary: str = ""
    accent: str = ""
    success: str = ""
    warning: str = ""
    error: str = ""
    info: str = ""
    text: str = ""
    text_muted: str = ""
    surface: str = ""
    surface_alt: str = ""
    git: GitColors = field(default_factory=GitColors)
    syntax: SyntaxColors = field(default_factory=SyntaxColors)


# Theme presets registry
THEME_PRESETS: Dict[str, type] = {
    "dark": ScrappyTheme,
    "light": LightTheme,
}

# Valid theme color keys (for validation)
THEME_COLOR_KEYS = {
    "primary", "accent", "success", "warning", "error",
    "info", "text", "text_muted", "surface", "surface_alt"
}


@dataclass(frozen=True)
class CustomTheme:
    """Theme with user-customized colors."""
    primary: str = "cyan"
    accent: str = "yellow"
    success: str = "green"
    warning: str = "yellow"
    error: str = "red"
    info: str = "blue"
    text: str = "white"
    text_muted: str = "bright_black"
    surface: str = "#1e1e1e"
    surface_alt: str = "#2d2d2d"
    git: GitColors = field(default_factory=GitColors)
    syntax: SyntaxColors = field(default_factory=SyntaxColors)


def load_theme_from_config(config: Dict[str, Any]) -> ThemeProtocol:
    """Load theme from config dict.

    Config format:
        theme:
            preset: dark  # or "light", or omit for default
            # Override individual colors:
            primary: cyan
            accent: orange
            surface: "#1a1a1a"

    Args:
        config: Config dict with optional 'theme' section

    Returns:
        Theme instance (preset, custom, or default)
    """
    theme_config = config.get("theme", {})

    if not theme_config:
        return DEFAULT_THEME

    # Get base preset
    preset_name = theme_config.get("preset", "dark")
    base_class = THEME_PRESETS.get(preset_name, ScrappyTheme)
    base = base_class()

    # Collect overrides (only valid color keys)
    overrides = {
        k: v for k, v in theme_config.items()
        if k in THEME_COLOR_KEYS and v is not None
    }

    if not overrides:
        return base

    # Build kwargs for CustomTheme, starting with base values
    kwargs = {
        "primary": overrides.get("primary", base.primary),
        "accent": overrides.get("accent", base.accent),
        "success": overrides.get("success", base.success),
        "warning": overrides.get("warning", base.warning),
        "error": overrides.get("error", base.error),
        "info": overrides.get("info", base.info),
        "text": overrides.get("text", base.text),
        "text_muted": overrides.get("text_muted", base.text_muted),
        "surface": overrides.get("surface", base.surface),
        "surface_alt": overrides.get("surface_alt", base.surface_alt),
    }

    return CustomTheme(**kwargs)


# Default theme instance
DEFAULT_THEME = ScrappyTheme()

# Standalone instances for non-theme-aware code
GIT_COLORS = GitColors()
SYNTAX_COLORS = SyntaxColors()
```

#### Step 2: Update StatsFormatter Base Class
**File**: `src/infrastructure/formatters/stats_formatter.py`

Changes:
- Add `theme` parameter to constructor
- Replace hardcoded `"cyan"` with `self._theme.primary`
- Replace hardcoded `"green"/"yellow"/"red"` with theme colors

```python
def __init__(
    self,
    use_color: bool = True,
    theme: Optional[ThemeProtocol] = None
):
    self._use_color = use_color
    self._theme = theme or DEFAULT_THEME

def format_header(self, title: str, width: int = 60) -> str:
    if self._use_color:
        header = click.style(f"\n{title}", fg=self._theme.primary, bold=True)
        separator = click.style("-" * width, fg=self._theme.primary)
    # ...

def _get_percentage_color(self, percentage: float) -> str:
    if percentage < 75:
        return self._theme.success
    elif percentage < 90:
        return self._theme.warning
    return self._theme.error
```

#### Step 3: Update CacheFormatter
**File**: `src/infrastructure/formatters/cache_formatter.py`

Changes:
- Pass theme to parent constructor
- Use `self._theme.success` / `self._theme.warning` for hit rates

```python
def __init__(
    self,
    use_color: bool = True,
    theme: Optional[ThemeProtocol] = None
):
    super().__init__(use_color=use_color, theme=theme)

def format_hit_rate(self, rate_str: str, label: str = "Hit Rate") -> str:
    # ...
    color = self._theme.success if rate_value > 50 else self._theme.warning
    return f"{label}: {click.style(rate_str, fg=color)}"
```

#### Step 4: Update RateLimitFormatter
**File**: `src/infrastructure/formatters/rate_limit_formatter.py`

Changes:
- Pass theme to parent constructor
- Replace `"green"` with `self._theme.success` for provider headers
- Replace `"red"` with `self._theme.error` for warnings
- Replace `"cyan"` with `self._theme.primary` for file location

```python
def format_provider_section(self, provider: str, data: Dict[str, Any]) -> str:
    parts = []
    parts.append(click.style(f"{provider.upper()}:", fg=self._theme.success, bold=True))
    # ...

def format_warnings(self, warnings: List[str]) -> str:
    parts = [click.style("WARNINGS:", fg=self._theme.error, bold=True)]
    for warning in warnings:
        parts.append(click.style(f"  {warning}", fg=self._theme.error))
    # ...

def format_tracker_file_location(self, file_path: str) -> str:
    return click.style(f"Tracking File: {file_path}", fg=self._theme.primary)
```

#### Step 5: Update Help Display with Theme
**File**: `src/cli/display_rich.py`

Changes:
- Add theme parameter to display functions
- Replace `"cyan"` with `theme.primary` for borders/headers
- Replace `"yellow"` with `theme.accent` for commands

```python
def show_help_table(
    io: UnifiedIO,
    category: Optional[str] = None,
    theme: Optional[ThemeProtocol] = None
) -> None:
    theme = theme or DEFAULT_THEME

    table = Table(
        title=f"[bold {theme.primary}]Available Commands[/bold {theme.primary}]",
        title_style=theme.primary,
        header_style=f"bold {theme.primary}",
        border_style=theme.primary
    )

    table.add_column("Command", style=theme.accent)
    table.add_column("Description", style=theme.text)
    # ...
```

#### Step 6: Update Banner with Theme
**File**: `src/cli/interactive_banner.py`

Changes:
- Add theme parameter
- Replace `"cyan"` with `theme.primary` for title and borders
- Replace `"yellow"` with `theme.accent` for commands

```python
def display_banner(
    io: "UnifiedIOProtocol",
    theme: Optional[ThemeProtocol] = None
) -> None:
    theme = theme or DEFAULT_THEME

    title_text = Text()
    title_text.append("SCRAPPY", style=f"bold {theme.primary}")
    title_text.append(" - ", style="dim")
    title_text.append("Interactive Mode", style=f"bold {theme.text}")

    # Commands use accent color
    commands_text.append("  /help", style=theme.accent)
    # ...

    panel = Panel(
        content,
        title=f"[bold {theme.primary}]Welcome[/bold {theme.primary}]",
        border_style=theme.primary,
        padding=(1, 2)
    )
```

#### Step 7: Synchronize Textual CSS with Theme
**File**: `src/cli/scrappy.tcss`

Update CSS variables to match default dark theme. Note: Textual CSS is static and compiled at app start, so runtime theme switching requires app restart. The CSS defines the dark theme; light theme would need a separate CSS file or Textual's built-in theme system.

```css
/* Theme-aligned color variables - must match ScrappyTheme defaults */
$surface: #1e1e1e;
$surface-alt: #2d2d2d;
$text: #d4d4d4;
$text-muted: #808080;
$primary: #00ffff;      /* cyan - borders, headers, info */
$accent: #ffcc00;       /* orange/yellow - commands, interactive */
$success: #00ff00;      /* green - positive states */
$warning: #ffcc00;      /* yellow - caution */
$error: #ff0000;        /* red - errors */
$info: #0080ff;         /* blue - informational */

/* Main screen uses surface background */
Screen {
    background: $surface;
}

/* Status bar uses elevated surface */
#status_bar {
    background: $surface-alt;
}

/* Update input prompt to use primary (cyan) instead of green */
#input_prompt {
    color: $primary;
}

/* Capture mode uses accent (orange) */
#input_container.capture-mode #input_prompt {
    color: $accent;
}
```

**Limitation**: Full runtime theme switching in TUI mode is out of scope. Users changing themes must restart the app. 

#### Step 8: Update Progress Indicators
**File**: `src/infrastructure/progress.py`

Changes:
- Add theme parameter
- Replace `"cyan"` with `theme.primary` for status
- Replace `"green"` with `theme.success` for completion
- Replace `"red"` with `theme.error` for errors

```python
class ConsoleProgressReporter:
    def __init__(self, theme: Optional[ThemeProtocol] = None):
        self._theme = theme or DEFAULT_THEME

    def update_status(self, message: str) -> None:
        # Use theme.primary instead of "cyan"
        styled = f"[{self._theme.primary}]{message}[/{self._theme.primary}]"
```

**File**: `src/infrastructure/textual_progress.py`

Same pattern - replace hardcoded colors with theme references.

#### Step 9: Update Agent UI
**File**: `src/agent/ui.py`

Changes:
- Add theme parameter to AgentUI class
- Replace panel border colors with theme colors:
  - Thinking: `theme.info` (blue)
  - Success: `theme.success` (green)
  - Error: `theme.error` (red)
  - Warning: `theme.warning` (yellow)
- Replace tool/command colors:
  - Tool names: `theme.primary` (cyan)
  - Shell commands: `theme.accent` (yellow)

```python
class AgentUI:
    def __init__(self, theme: Optional[ThemeProtocol] = None):
        self._theme = theme or DEFAULT_THEME

    def show_thinking(self, content: str) -> None:
        panel = Panel(content, border_style=self._theme.info)
        # ...

    def show_result(self, content: str, is_error: bool = False) -> None:
        color = self._theme.error if is_error else self._theme.success
        panel = Panel(content, border_style=color)
```

#### Step 10: Update Output Formatter (Git/Syntax Colors)
**File**: `src/agent_tools/formatters/output_formatter.py`

Changes:
- Import `GIT_COLORS` and `SYNTAX_COLORS` from theme module
- Replace hardcoded git colors:
  - `"green"` -> `GIT_COLORS.add`
  - `"red"` -> `GIT_COLORS.remove`
  - `"cyan"` -> `GIT_COLORS.header`
  - `"yellow"` -> `GIT_COLORS.commit`
- Replace file type colors with `SYNTAX_COLORS.*`

```python
from src.infrastructure.theme import GIT_COLORS, SYNTAX_COLORS

def format_diff_line(self, line: str) -> Text:
    if line.startswith('+'):
        return Text(line, style=GIT_COLORS.add)
    elif line.startswith('-'):
        return Text(line, style=GIT_COLORS.remove)
    # ...

def get_file_style(self, extension: str) -> str:
    mapping = {
        '.py': SYNTAX_COLORS.python,
        '.js': SYNTAX_COLORS.javascript,
        '.ts': SYNTAX_COLORS.javascript,
        '.json': SYNTAX_COLORS.config,
        '.yaml': SYNTAX_COLORS.config,
        '.md': SYNTAX_COLORS.docs,
    }
    return mapping.get(extension, SYNTAX_COLORS.default)
```

#### Step 11: Update Rich Dashboard
**File**: `src/cli/rich_dashboard.py`

Changes:
- Add theme parameter to `RichDashboard.__init__`
- Update state color mapping
- Update panel border colors

```python
class RichDashboard:
    def __init__(self, theme: Optional[ThemeProtocol] = None):
        self._theme = theme or DEFAULT_THEME
        self._state_styles = {
            "idle": "dim",
            "thinking": self._theme.accent,
            "executing": self._theme.success,
            "scanning": self._theme.primary,
        }

    def _create_thought_panel(self, content: str) -> Panel:
        return Panel(content, border_style=self._theme.info)

    def _create_terminal_panel(self, content: str) -> Panel:
        return Panel(content, border_style=self._theme.text)

    def _create_context_panel(self, content: str) -> Panel:
        return Panel(content, border_style=self._theme.accent)
```

#### Step 12: Update Task Router Handler
**File**: `src/cli/task_router_handler.py`

Changes:
- Add theme parameter
- Update task type color mapping

```python
class TaskRouterHandler:
    def __init__(self, theme: Optional[ThemeProtocol] = None):
        self._theme = theme or DEFAULT_THEME
        self._task_colors = {
            "direct_command": self._theme.success,
            "code_generation": self._theme.accent,
            "research": self._theme.primary,
            "conversation": self._theme.info,
        }

    def _get_task_color(self, task_type: str) -> str:
        return self._task_colors.get(task_type, self._theme.text)
```

#### Step 13: Update Output Bridge
**File**: `src/cli/output_bridge.py`

Changes:
- Add theme parameter to `OutputBridge.__init__`
- Update message styling methods

```python
class OutputBridge:
    def __init__(self, theme: Optional[ThemeProtocol] = None):
        self._theme = theme or DEFAULT_THEME

    def warning(self, message: str) -> None:
        styled = Text(message, style=self._theme.warning)
        self._console.print(styled)

    def error(self, message: str) -> None:
        styled = Text(message, style=f"{self._theme.error} bold")
        self._console.print(styled)

    def success(self, message: str) -> None:
        styled = Text(message, style=self._theme.success)
        self._console.print(styled)
```

#### Step 14: Update Unified IO
**File**: `src/cli/unified_io.py`

Changes:
- Add theme parameter to `UnifiedIO.__init__`
- Update default panel border color
- Update color map to use theme
- Keep security warnings as hardcoded red (intentional - safety critical)

```python
class UnifiedIO:
    def __init__(self, theme: Optional[ThemeProtocol] = None):
        self._theme = theme or DEFAULT_THEME
        self._color_map = {
            "primary": self._theme.primary,
            "accent": self._theme.accent,
            "success": self._theme.success,
            "warning": self._theme.warning,
            "error": self._theme.error,
            "info": self._theme.info,
        }

    def panel(self, content: str, title: str = "", border_style: str = None) -> None:
        style = border_style or self._theme.info
        panel = Panel(content, title=title, border_style=style)
        self._console.print(panel)

    def security_warning(self, message: str) -> None:
        # Hardcoded red - intentionally not theme-customizable for safety
        panel = Panel(
            message,
            title="[blink bold white on red]SECURITY WARNING[/]",
            border_style="red"
        )
        self._console.print(panel)
```

#### Step 15: Update Remaining CLI Files

**File**: `src/cli/context_commands.py`

```python
class ContextCommands:
    def __init__(self, theme: Optional[ThemeProtocol] = None):
        self._theme = theme or DEFAULT_THEME

    def show_project_path(self, path: str) -> None:
        # Replace "bright_white" with theme.text
        styled = click.style(path, fg=self._theme.text, bold=True)
        click.echo(styled)
```

**File**: `src/cli/interactive.py`

```python
def echo_user_input(self, text: str) -> None:
    # Replace "bright_white" with theme.text
    styled = click.style(text, fg=self._theme.text, bold=True)
    click.echo(styled)
```

**File**: `src/cli/textual_app.py`

```python
def show_error(self, message: str) -> None:
    # Replace "red" with theme.error
    self.query_one(RichLog).write(Text(message, style=self._theme.error))
```

#### Step 16: Update Agent Tools

**File**: `src/agent_tools/tools/base.py`

```python
class BaseTool:
    def __init__(self, theme: Optional[ThemeProtocol] = None):
        self._theme = theme or DEFAULT_THEME

    def display_error(self, message: str) -> None:
        # Replace "bold red" with theme.error
        styled = Text(message, style=f"bold {self._theme.error}")
        console.print(styled)
```

**File**: `src/agent_tools/tools/file_tools.py`

```python
def format_file_size(self, size: int) -> Text:
    # Replace "bright_black" with theme.text_muted
    return Text(f"{size:,} bytes", style=self._theme.text_muted)
```

#### Step 17: Integrate Theme Loading at App Startup
**File**: `src/cli/app.py` (or wherever app initialization occurs)

Changes:
- Load theme from config during app startup
- Pass theme to all components that need it

```python
from src.infrastructure.theme import load_theme_from_config, DEFAULT_THEME

class App:
    def __init__(self, config: Dict[str, Any]):
        # Load theme from config
        self._theme = load_theme_from_config(config)

        # Pass theme to components
        self._io = UnifiedIO(theme=self._theme)
        self._output_bridge = OutputBridge(theme=self._theme)
        self._dashboard = RichDashboard(theme=self._theme)
        # ... etc
```

### Testing Strategy

1. **Unit Tests**: Test theme module
   - Verify `ScrappyTheme` provides all 10 color properties
   - Verify `LightTheme` provides all 10 color properties
   - Verify `TestTheme` returns empty strings for all colors
   - Verify `GitColors` and `SyntaxColors` have correct defaults
   - Test `load_theme_from_config()`:
     - Empty config returns `DEFAULT_THEME`
     - `preset: dark` returns `ScrappyTheme`
     - `preset: light` returns `LightTheme`
     - Invalid preset falls back to `ScrappyTheme`
     - Individual color overrides work correctly
     - Invalid keys are ignored
     - Partial overrides inherit from base preset

2. **Integration Tests**: Verify theme injection
   - Test formatters accept and use theme parameter
   - Test theme propagates through component constructors
   - Test color output matches theme values

3. **Visual Tests**: Manual inspection
   - CLI mode: verify all colors match theme
   - TUI mode: verify CSS colors match theme defaults
   - Test both dark and light presets
   - Test custom color overrides

4. **Regression Tests**: Ensure existing functionality works
   - All existing tests pass
   - No broken color output
   - Components without explicit theme use `DEFAULT_THEME`

### Files Modified/Created

**New Files (1):**
- `src/infrastructure/theme.py`

**Infrastructure Layer (3):**
- `src/infrastructure/formatters/stats_formatter.py`
- `src/infrastructure/formatters/cache_formatter.py`
- `src/infrastructure/formatters/rate_limit_formatter.py`

**Progress Layer (2):**
- `src/infrastructure/progress.py`
- `src/infrastructure/textual_progress.py`

**CLI Layer (9):**
- `src/cli/interactive_banner.py`
- `src/cli/display_rich.py`
- `src/cli/unified_io.py`
- `src/cli/output_bridge.py`
- `src/cli/rich_dashboard.py`
- `src/cli/task_router_handler.py`
- `src/cli/context_commands.py`
- `src/cli/interactive.py`
- `src/cli/textual_app.py`

**Agent Layer (2):**
- `src/agent/ui.py`
- `src/agent_tools/formatters/output_formatter.py`

**Tools Layer (2):**
- `src/agent_tools/tools/base.py`
- `src/agent_tools/tools/file_tools.py`

**CSS Layer (1):**
- `src/cli/scrappy.tcss`

**Total: 20 files (1 new, 19 modified)**

---

## Implementation Order

Recommended order based on dependencies and risk:

### Phase 1: Theme Foundation (Step 1) - COMPLETED
- **Effort**: Low
- **Risk**: Low
- **Files**: 1 created, 1 test file
- **Steps**: 1

Created `src/infrastructure/theme.py` with:
- [x] `ThemeProtocol` (10 color properties)
- [x] `GitColors`, `SyntaxColors` (fixed color sets)
- [x] `ScrappyTheme` (default dark)
- [x] `LightTheme` (light preset)
- [x] `CustomTheme` (for user overrides)
- [x] `NoColorTheme` (empty strings for testing - renamed from TestTheme to avoid pytest collection warning)
- [x] `load_theme_from_config()` function
- [x] `THEME_PRESETS` registry
- [x] `THEME_COLOR_KEYS` validation set
- [x] `DEFAULT_THEME`, `GIT_COLORS`, `SYNTAX_COLORS` global instances

Created `tests/infrastructure/test_theme.py` with 83 unit tests.

### Phase 2: Infrastructure Formatters (Steps 2-4) - COMPLETED
- **Effort**: Medium
- **Risk**: Low
- **Files**: 3
- **Steps**: 2, 3, 4

Updated formatters to accept theme via constructor:
- [x] `stats_formatter.py` (Step 2) - Added `theme` parameter, uses `self._theme.primary`, `self._theme.success`, `self._theme.warning`, `self._theme.error`
- [x] `cache_formatter.py` (Step 3) - Passes theme to parent, uses theme colors for hit rates and toggle messages
- [x] `rate_limit_formatter.py` (Step 4) - Uses theme colors for provider headers, warnings, and file location

Added 24 theme integration tests in `tests/infrastructure/test_formatters.py`:
- [x] `TestStatsFormatterThemeIntegration` (9 tests)
- [x] `TestCacheFormatterThemeIntegration` (6 tests)
- [x] `TestRateLimitFormatterThemeIntegration` (6 tests)
- [x] `TestNoColorThemeIntegration` (3 tests)

### Phase 3: Progress Indicators (Step 8) - COMPLETED
- **Effort**: Low
- **Risk**: Low
- **Files**: 2
- **Steps**: 8

Updated progress reporters to accept theme via constructor:
- [x] `progress.py` (Step 8) - Added `theme` parameter to `RichProgressReporter`, `LiveProgressReporter`, `UnifiedIOProgressReporter`, and `create_progress_reporter` factory
- [x] `textual_progress.py` (Step 8) - Added `theme` parameter to `TextualProgressReporter`

Added 14 theme integration tests:
- [x] `TestRichProgressReporterTheme` (3 tests) in `tests/infrastructure/test_progress.py`
- [x] `TestUnifiedIOProgressReporterTheme` (5 tests) in `tests/infrastructure/test_progress.py`
- [x] `TestTextualProgressReporterTheme` (5 tests) in `tests/infrastructure/test_texual_progress.py`
- [x] Updated existing tests to use `DEFAULT_THEME` colors instead of hardcoded strings

### Phase 4: Core CLI Components (Steps 5, 6, 11-14) - COMPLETED
- **Effort**: Medium
- **Risk**: Medium (visual changes)
- **Files**: 6
- **Steps**: 5, 6, 11, 12, 13, 14

Updated CLI components to accept theme via constructor:
- [x] `display_rich.py` (Step 5) - Added `theme` parameter to `show_help_table`, `show_status_rich`, `show_rate_limits_rich`, `show_plan_tree`
- [x] `interactive_banner.py` (Step 6) - Added `theme` parameter to `display_banner`, `render_welcome_banner`
- [x] `rich_dashboard.py` (Step 11) - Added `theme` parameter to `RichDashboard.__init__`, updated `_state_styles` and panel border colors
- [x] `task_router_handler.py` (Step 12) - Added `theme` parameter to `CLITaskRouterHandler.__init__`, added `_task_colors` mapping
- [x] `output_bridge.py` (Step 13) - Added `theme` parameter to `OutputBridge`, `ConsoleOutputBridge`, `create_output_bridge`
- [x] `unified_io.py` (Step 14) - Added `theme` parameter to `UnifiedIO.__init__`, added `theme` property, updated `panel()` default border

Added 33 theme integration tests in `tests/cli/test_cli_theme_integration.py`:
- [x] `TestDisplayRichThemeIntegration` (6 tests)
- [x] `TestInteractiveBannerThemeIntegration` (2 tests)
- [x] `TestRichDashboardThemeIntegration` (4 tests)
- [x] `TestTaskRouterHandlerThemeIntegration` (4 tests)
- [x] `TestOutputBridgeThemeIntegration` (8 tests)
- [x] `TestUnifiedIOThemeIntegration` (5 tests)
- [x] `TestNoColorThemeIntegration` (3 tests)
- [x] `TestThemePropagation` (1 test)

### Phase 5: Agent Layer (Steps 9, 10) - COMPLETED
- **Effort**: Medium
- **Risk**: Low
- **Files**: 2
- **Steps**: 9, 10

Updated agent components to use theme:
- [x] `agent/ui.py` (Step 9) - Added `theme` parameter to `AgentUI.__init__`, updated all display methods to use theme colors:
  - `show_thinking`: uses `theme.info` for panel border
  - `show_tool_request`: uses `theme.primary` for tool name display
  - `show_command`: uses `theme.accent` for shell command display
  - `show_error`: uses `theme.error` for error panel border
  - `show_result`: uses `theme.success`/`theme.error` based on `is_error` flag
  - `show_warning`: uses `theme.warning` for warning panel border
  - `show_progress`: uses `theme.primary` for progress messages
  - `show_provider_status`: uses `theme.primary` as default color
- [x] `output_formatter.py` (Step 10) - Updated to use `GIT_COLORS` and `SYNTAX_COLORS` from theme module:
  - `GitOutputFormatter`: uses `GIT_COLORS.commit`, `GIT_COLORS.add`, `GIT_COLORS.remove`, `GIT_COLORS.header`, `GIT_COLORS.meta`
  - `RichDirectoryFormatter.format_file_name`: uses `SYNTAX_COLORS.python`, `SYNTAX_COLORS.javascript`, `SYNTAX_COLORS.docs`, `SYNTAX_COLORS.config`

Added 55 theme integration tests:
- [x] `tests/agent/test_agent_ui_theme.py` (20 tests) - Comprehensive tests for AgentUI theme usage
- [x] `tests/agent_tools/test_output_formatter.py` (35 new tests) - Tests for GIT_COLORS and SYNTAX_COLORS usage

### Phase 6: Remaining Files (Steps 15, 16) - COMPLETED
- **Effort**: Low
- **Risk**: Low
- **Files**: 5
- **Steps**: 15, 16

Updated remaining files to accept theme via constructor:
- [x] `context_commands.py` (Step 15) - Added `theme` parameter to `CLIContextCommands.__init__`, uses theme colors for:
  - Context Status header: `theme.primary`
  - Working Memory header: `theme.accent`
  - Explored/Context Aware status: `theme.success`/`theme.warning`/`theme.error`
  - Error messages: `theme.error`
  - Project path display: `theme.text`
  - Success messages: `theme.success`
- [x] `interactive.py` (Step 15) - Added `theme` parameter to `InteractiveMode.__init__`, uses theme colors for:
  - User input echo: `theme.text`
  - EOF warning: `theme.warning`
  - Session saved: `theme.success`
  - Goodbye message: `theme.primary`
  - Error messages: `theme.error`
- [x] `textual_app.py` (Step 15) - Added `theme` parameter to `ScrappyApp.__init__`, uses:
  - Error text styling: `theme.error`
- [x] `tools/base.py` (Step 16) - Updated `ToolResult.__rich__()` to use `DEFAULT_THEME.error` for error styling
- [x] `tools/file_tools.py` (Step 16) - Updated `ListDirectoryTool` to use:
  - Directory names: `DEFAULT_THEME.primary`
  - File sizes: `DEFAULT_THEME.text_muted`
  - Python files: `SYNTAX_COLORS.python`
  - JavaScript files: `SYNTAX_COLORS.javascript`
  - Docs files: `SYNTAX_COLORS.docs`
  - Config files: `SYNTAX_COLORS.config`

Added 22 theme integration tests in `tests/cli/test_phase6_theme_integration.py`:
- [x] `TestContextCommandsThemeIntegration` (7 tests)
- [x] `TestInteractiveModeThemeIntegration` (6 tests)
- [x] `TestTextualAppThemeIntegration` (2 tests)
- [x] `TestToolResultThemeIntegration` (1 test)
- [x] `TestFileToolsThemeIntegration` (3 tests)
- [x] `TestNoColorThemePhase6Integration` (3 tests)

### Phase 7: CSS Sync (Step 7) - COMPLETED
- **Effort**: Low
- **Risk**: Medium (TUI visual change)
- **Files**: 1
- **Steps**: 7

Updated `scrappy.tcss` to align CSS variables with theme defaults:
- [x] Added all semantic color variables from `ScrappyTheme`:
  - `$primary: #00ffff` (cyan - borders, headers, info text, input prompt)
  - `$accent: #ffcc00` (yellow/orange - commands, interactive elements, capture mode)
  - `$success: #00ff00` (green - positive states)
  - `$warning: #ffcc00` (yellow - caution states)
  - `$error: #ff0000` (red - errors)
  - `$info: #0080ff` (blue - informational panels, thinking state)
- [x] Renamed `$panel-bg` to `$surface-alt` for consistency with theme
- [x] Changed input prompt from green (`#00ff00`) to cyan (`$primary`) - intentional visual change for theme consistency
- [x] Updated capture mode to use `$accent` variable instead of hardcoded `#ffcc00`
- [x] Updated prompt display to use `$accent` variable instead of hardcoded `#ffcc00`
- [x] Added reference comment pointing to `src/infrastructure/theme.py` as authoritative source

**Note**: Runtime theme switching not supported in TUI mode (requires app restart).

### Phase 8: App Integration (Step 17) - COMPLETED
- **Effort**: Low
- **Risk**: Low
- **Files**: 5 modified
- **Steps**: 17

Integrated theme loading at app startup:
- [x] Added `theme_config` field and `theme` property to `CLIConfig` class
- [x] Added `from_dict` and `to_dict` methods to handle 'theme' <-> 'theme_config' mapping
- [x] Updated `cli_factory.py` functions to accept and pass theme:
  - `get_io_interface()` - accepts theme parameter
  - `initialize_cli_handlers()` - passes theme to CLIContextCommands and CLITaskRouterHandler
  - `create_cli_from_context()` - passes theme to CLI
  - `create_cli()` - passes theme to CLI
- [x] Updated `CLI` class in `core.py` to accept theme and pass to handlers
- [x] Updated `commands.py` to load theme from config and pass to CLI:
  - `cli()` main command - loads theme from `get_config().theme`
  - `interactive()` command - loads theme from `get_config().theme`

Added 27 theme integration tests in `tests/cli/test_phase8_theme_integration.py`:
- [x] `TestCLIConfigTheme` (9 tests)
- [x] `TestCLIConfigFromDict` (4 tests)
- [x] `TestCLIFactoryTheme` (3 tests)
- [x] `TestCLICoreTheme` (3 tests)
- [x] `TestCreateCliFromContext` (2 tests)
- [x] `TestCreateCli` (2 tests)
- [x] `TestThemeProtocolCompliance` (4 tests)

---

## Success Criteria

### Theme System (Phase 1) - COMPLETED
- [x] `ThemeProtocol` defined with 10 semantic colors (8 foreground + 2 background)
- [x] `ScrappyTheme` (dark) implements protocol with correct defaults
- [x] `LightTheme` preset implements protocol
- [x] `CustomTheme` supports user overrides
- [x] `NoColorTheme` provides empty strings for testing (renamed from TestTheme)
- [x] `GitColors` provides fixed diff/commit colors
- [x] `SyntaxColors` provides file type indicator colors
- [x] `load_theme_from_config()` loads themes from config dict
- [x] `THEME_PRESETS` registry contains dark and light
- [x] `THEME_COLOR_KEYS` validates config keys

### Config Integration (Phase 8) - COMPLETED
- [x] Theme section supported in config file
- [x] Preset selection works (`preset: dark` or `preset: light`)
- [x] Individual color overrides work
- [x] Invalid preset falls back to dark theme
- [x] Invalid keys are silently ignored
- [x] Theme loaded and passed to all components at startup

### Color Consistency (Phases 2-7)
- [x] All 19 files updated to use theme
- [x] No hardcoded color strings remain (except security warnings)
- [x] CSS variables match theme defaults
- [x] TUI uses `surface` and `surface_alt` for backgrounds
- [x] TUI input prompt uses `primary` (cyan) not green

### Visual Verification
- [ ] Banner displays with primary borders, accent commands
- [ ] Help table uses primary headers, accent command names
- [ ] Cache/rate limit stats use theme colors
- [ ] Progress indicators use theme colors
- [ ] Agent panels use theme colors (info thinking, success/error results)
- [ ] Git diffs use fixed colors (green add, red remove)
- [ ] File listings use syntax colors
- [ ] Background colors applied in TUI mode
- [ ] Light theme preset renders correctly

### Testing
- [x] All existing tests pass
- [x] Unit tests for all theme classes (83 tests in tests/infrastructure/test_theme.py)
- [x] Unit tests for `load_theme_from_config()` edge cases
- [x] Integration tests for theme injection (24 tests in tests/infrastructure/test_formatters.py)
- [x] Integration tests for Phase 6 components (22 tests in tests/cli/test_phase6_theme_integration.py)
- [x] Integration tests for Phase 8 app startup (27 tests in tests/cli/test_phase8_theme_integration.py)
- [ ] Manual visual inspection of dark theme
- [ ] Manual visual inspection of light theme
- [ ] Manual visual inspection of custom overrides

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Visual regression | Medium | Manual visual testing, screenshot comparison |
| Theme not applied everywhere | Low | Grep for hardcoded colors after implementation |
| TUI accent color change (green -> cyan) | Medium | Document as intentional change for consistency |
| Breaking existing tests | Medium | Run full test suite after each phase |
| Dependency injection complexity | Low | Use `Optional[ThemeProtocol]` with `DEFAULT_THEME` fallback |

---

## Color Reference Card

### Default Dark Theme

| Semantic | Color | Hex | Usage |
|----------|-------|-----|-------|
| `primary` | cyan | #00ffff | Borders, headers, labels, info text |
| `accent` | yellow | #ffcc00 | Commands, keywords, interactive elements |
| `success` | green | #00ff00 | Enabled, completed, positive values |
| `warning` | yellow | #ffcc00 | Caution states |
| `error` | red | #ff0000 | Errors, disabled, negative states |
| `info` | blue | #0080ff | Informational panels, thinking state |
| `text` | white | #ffffff | Normal text |
| `text_muted` | gray | #808080 | Dimmed, secondary text |
| `surface` | dark gray | #1e1e1e | Main background |
| `surface_alt` | lighter gray | #2d2d2d | Panels, status bar |

### Light Theme Preset

| Semantic | Color | Hex | Usage |
|----------|-------|-----|-------|
| `primary` | blue | #0000ff | Borders, headers |
| `accent` | magenta | #ff00ff | Commands, keywords |
| `text` | black | #000000 | Normal text |
| `surface` | white | #ffffff | Main background |
| `surface_alt` | light gray | #f0f0f0 | Panels |

### Git Colors (Fixed)

| Name | Color | Usage |
|------|-------|-------|
| `add` | green | Added lines (+) |
| `remove` | red | Removed lines (-) |
| `header` | cyan | Diff headers (+++/---) |
| `commit` | yellow | Commit hashes |

### Syntax Colors (Fixed)

| Name | Color | File Types |
|------|-------|------------|
| `python` | green | .py |
| `javascript` | yellow | .js, .ts, .jsx, .tsx |
| `config` | magenta | .json, .yaml, .yml, .toml |
| `docs` | white | .md, .txt, .rst |

---

## Config File Format

Users can customize themes in their config file:

```yaml
# .scrappy/config.yaml

theme:
  # Use a preset (dark, light)
  preset: dark

  # Or override individual colors:
  # primary: cyan
  # accent: orange
  # surface: "#1a1a1a"
```

**Full custom theme example:**

```yaml
theme:
  preset: dark
  primary: "#61afef"      # One Dark blue
  accent: "#e5c07b"       # One Dark yellow
  success: "#98c379"      # One Dark green
  error: "#e06c75"        # One Dark red
  info: "#56b6c2"         # One Dark cyan
  text: "#abb2bf"         # One Dark foreground
  text_muted: "#5c6370"   # One Dark comment
  surface: "#282c34"      # One Dark background
  surface_alt: "#3e4451"  # One Dark gutter
```

---

## References

- `docs/TODO/ISSUES_PRIORITIZED.md` - Original issue documentation
- `CLAUDE.md` - Architecture guidelines