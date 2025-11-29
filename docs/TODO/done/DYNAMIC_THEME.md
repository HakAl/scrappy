[//]: # (Dynamic Theme Integration Plan)

## Task Overview

Theme is organized well enough to surface to users with some fast refactors.
The TUI integration must be completed in the on_mount lifecycle method.

**User config mapping pseudocode:**
```
config = userconfig ? userconfig+default : default
```

---

## Plan: Dynamic Theme Loading for TUI

### Step 0: Wire user config theme to ScrappyApp

**File:** `src/cli/textual_interactive.py`

**Goal:** Pass the theme from CLIConfig to ScrappyApp so user config is respected.

**Current state:**
- Line 127 creates ScrappyApp without passing theme parameter
- CLIConfig already loads theme from `.scrappy.yaml`/`.scrappy.json`
- ScrappyApp already accepts optional `theme` parameter

**Changes required:**

1. **Add CLIConfig import** (top of file):
```python
from .config_factory import get_config
```

2. **Update `__init__` to accept CLIConfig** (line 44):
```python
def __init__(
    self,
    orchestrator: "Orchestrator",
    session_context: "SessionContextProtocol",
    # ... other params ...
    io: UnifiedIO,
    cli: "CLI" = None,
    config: "CLIConfig" = None,  # NEW: optional config
):
```

3. **Store config with fallback** (after line 86):
```python
    self._cli = cli
    # NEW: Load config if not provided
    from .config_factory import get_config
    self._config = config or get_config()
```

4. **Pass theme to ScrappyApp** (line 127):
```python
    # Create ScrappyApp with InteractiveMode, output adapter, and user theme
    app = ScrappyApp(interactive_mode, output_adapter, theme=self._config.theme)
```

**Flow:**
```
.scrappy.yaml (user config)
    ↓
CLIConfigFactory.create() loads file
    ↓
CLIConfig.theme property returns ThemeProtocol
    ↓
TextualInteractiveMode receives CLIConfig
    ↓
ScrappyApp gets theme from config
    ↓
Theme registered in on_mount()
```

**Note:** The caller (CLI factory) should pass CLIConfig to TextualInteractiveMode. If not passed, fallback to `get_config()` to load from default locations.

---

### Step 1: Convert theme defaults to hex values

**File:** `src/infrastructure/theme.py`

**Goal:** Convert all color names to hex values for Textual compatibility.

**Standard color mappings (using Rich/ANSI standard palette):**
- `cyan` → `#00ffff`
- `yellow` → `#ffff00`
- `green` → `#00ff00`
- `red` → `#ff0000`
- `blue` → `#0000ff`
- `magenta` → `#ff00ff`
- `white` → `#ffffff`
- `black` → `#000000`
- `bright_black` → `#808080` (gray)

**Changes required:**

1. **ScrappyTheme** (dark theme):
   - `primary: "cyan"` → `primary: "#00ffff"`
   - `accent: "yellow"` → `accent: "#ffff00"`
   - `success: "green"` → `success: "#00ff00"`
   - `warning: "yellow"` → `warning: "#ffff00"`
   - `error: "red"` → `error: "#ff0000"`
   - `info: "blue"` → `info: "#0000ff"`
   - `text: "white"` → `text: "#ffffff"`
   - `text_muted: "bright_black"` → `text_muted: "#808080"`
   - surface/surface_alt already hex

2. **LightTheme**:
   - `primary: "blue"` → `primary: "#0000ff"`
   - `accent: "magenta"` → `accent: "#ff00ff"`
   - `success: "green"` → `success: "#00ff00"`
   - `warning: "yellow"` → `warning: "#ffff00"`
   - `error: "red"` → `error: "#ff0000"`
   - `info: "cyan"` → `info: "#00ffff"`
   - `text: "black"` → `text: "#000000"`
   - `text_muted: "bright_black"` → `text_muted: "#808080"`
   - surface/surface_alt already hex

3. **CustomTheme**: Apply same conversions as ScrappyTheme defaults

**Note:** GitColors and SyntaxColors can remain as color names since they're used with Rich markup, not Textual CSS.

**Caveat:** Some Click-based commands may need updates if they reference theme colors directly. Check CLI command rendering.

---

### Step 2: Remove static variable definitions from TCSS

**File:** `src/cli/scrappy.tcss`

**Goal:** Remove hardcoded TCSS variables so they can be injected dynamically from user config.

**Changes:**
1. Remove lines 6-21 (all `$variable: value;` definitions):
   - `$surface`
   - `$surface-alt`
   - `$text`
   - `$text-muted`
   - `$primary`
   - `$accent`
   - `$success`
   - `$warning`
   - `$error`
   - `$info`

2. Keep all usage of these variables (lines 22+) unchanged - Textual will resolve them from the registered theme

**Validation:** After removal, TCSS should only contain:
- Comments explaining theme integration
- CSS rules that reference `$variables`
- No `$variable: value;` assignments

---

### Step 3: Create and register Textual Theme in ScrappyApp

**File:** `src/cli/textual_app.py`

**Goal:** Convert ThemeProtocol to Textual Theme and register it dynamically.

**Implementation in `on_mount()` method (after line 698):**

```python
def on_mount(self) -> None:
    """Called when app starts."""
    # Register dynamic theme from ThemeProtocol
    self._register_user_theme()

    # Set TUI mode context...
    OutputModeContext.set_tui_mode(True, self.output_adapter)
    # ... rest of existing code
```

**New method to add:**

```python
def _register_user_theme(self) -> None:
    """Register theme from ThemeProtocol with Textual.

    Maps our ThemeProtocol colors to Textual's Theme system.
    Textual requires hex values and uses different naming conventions.
    """
    from textual.theme import Theme

    # Map ThemeProtocol to Textual Theme parameters
    # Textual uses: primary, secondary, accent, foreground, background,
    #               surface, panel, boost, warning, error, success
    textual_theme = Theme(
        name="scrappy_user",
        primary=self._theme.primary,
        secondary=self._theme.info,  # Map info -> secondary
        accent=self._theme.accent,
        foreground=self._theme.text,  # Map text -> foreground
        background=self._theme.surface,
        surface=self._theme.surface_alt,  # Map surface_alt -> surface
        warning=self._theme.warning,
        error=self._theme.error,
        success=self._theme.success,
        dark=True,  # TODO: detect from theme or make configurable
        variables={
            # Custom CSS variables for our specific use cases
            "text-muted": self._theme.text_muted,
        }
    )

    self.register_theme(textual_theme)
    self.theme = "scrappy_user"
```

**Import addition needed:**
```python
from textual.theme import Theme
```

**Edge cases to handle:**
- If `self._theme` colors are still color names (shouldn't happen after Step 1), validation/conversion
- Dark vs light theme detection (currently hardcoded `dark=True`)
- User customizations that override only some colors

---

### Step 4: Update and verify tests

**Files to update/verify:**

1. **tests/infrastructure/test_theme.py**
   - Update assertions to expect hex values instead of color names
   - Add test: `test_theme_colors_are_hex_format()`
   - Verify: `test_load_theme_from_config_*` still pass

2. **tests/cli/test_phase8_theme_integration.py**
   - Verify: `TestThemeProtocolCompliance` still passes
   - Add test: `test_textual_theme_creation_from_protocol()`
   - Add test: `test_theme_registration_in_on_mount()`

3. **New test to add:**

```python
def test_textual_theme_creation_from_protocol():
    """Verify ThemeProtocol can be converted to Textual Theme."""
    from textual.theme import Theme
    from src.infrastructure.theme import ScrappyTheme

    theme = ScrappyTheme()

    # Should be able to create Textual theme
    textual_theme = Theme(
        name="test",
        primary=theme.primary,
        accent=theme.accent,
        foreground=theme.text,
        background=theme.surface,
        # ... etc
    )

    assert textual_theme.name == "test"
    # Verify colors are hex format
    assert theme.primary.startswith("#")
    assert theme.accent.startswith("#")
```

4. **Validation checks:**
   - All theme colors must start with `#` (hex format)
   - TCSS file has no static variable definitions
   - Theme registration happens in `on_mount()` not `__init__()`
   - User config overrides properly merge with defaults

---

## Acceptance Criteria

- [ ] **Step 0**: TextualInteractiveMode loads and passes theme from CLIConfig
- [ ] **Step 0**: User config from `.scrappy.yaml`/`.scrappy.json` is loaded
- [ ] **Step 0**: Theme from config is passed to ScrappyApp
- [ ] **Step 1**: All theme classes use hex color values
- [ ] **Step 1**: Color name to hex mappings are correct
- [ ] **Step 2**: TCSS has no static `$variable:` definitions
- [ ] **Step 2**: TCSS still references variables (usage remains)
- [ ] **Step 3**: Theme is registered dynamically in `on_mount()`
- [ ] **Step 3**: Textual Theme is created from ThemeProtocol
- [ ] **Step 3**: Theme mapping (ThemeProtocol → Textual) is correct
- [ ] **Step 4**: All existing tests pass with hex values
- [ ] **Step 4**: New tests verify hex format validation
- [ ] **Step 4**: New tests verify Textual theme creation
- [ ] **Integration**: User can customize theme via config file
- [ ] **Integration**: TUI respects all user theme overrides
- [ ] **Integration**: CLI commands still render colors correctly (Rich markup)
- [ ] **Integration**: Both CLI and TUI use the same theme from config

---

## User Configuration Examples

After implementation, users can customize themes in their `.scrappy.yaml`:

**Example 1: Use light theme preset**
```yaml
theme:
  preset: light
```

**Example 2: Dark theme with custom accent color**
```yaml
theme:
  preset: dark
  accent: "#e5c07b"  # Golden accent
```

**Example 3: Fully custom One Dark Pro theme**
```yaml
theme:
  preset: dark
  primary: "#61afef"      # Blue
  accent: "#e5c07b"       # Gold
  success: "#98c379"      # Green
  error: "#e06c75"        # Red
  warning: "#d19a66"      # Orange
  info: "#56b6c2"         # Cyan
  text: "#abb2bf"         # Light gray
  text_muted: "#5c6370"   # Dark gray
  surface: "#282c34"      # Dark background
  surface_alt: "#3e4451"  # Lighter background
```

**Example 4: Override just one color**
```yaml
theme:
  preset: dark
  primary: "#ff00ff"  # Magenta primary, everything else default dark
```

**Validation:**
- Colors can be hex (`#ff0000`) or names (`red`) for now
- After Step 1, themes will use hex internally but config can accept either
- Invalid colors fall back to preset defaults
- Missing preset defaults to `dark`
