# Customization Guide

This guide explains how to customize Scrappy CLI settings including themes, display options, and behavior parameters.

## Quick Start

1. Copy the example config to your project directory:
   ```bash
   # Choose JSON or YAML format
   cp .scrappy.example.json .scrappy.json
   # OR
   cp .scrappy.example.yaml .scrappy.yaml
   ```

2. Edit the file to customize settings

3. Run Scrappy - it will automatically load your config

## Configuration File Locations

Config is loaded from these locations (in order of priority):

1. **Environment variable**: File path specified in `CLI_CONFIG_PATH`
2. **Current directory**: `.scrappy.json`, `.scrappy.yaml`, or `.scrappy.toml`
3. **Environment variables**: Individual settings with `CLI_` prefix
4. **Defaults**: Built-in default values

## Supported Formats

- **JSON**: `.scrappy.json`
- **YAML**: `.scrappy.yaml`
- **TOML**: `.scrappy.toml`

---

## Theme Configuration

Themes control the colors used throughout the CLI and TUI interfaces.

### Using Presets

Two built-in presets are available:

```yaml
theme:
  preset: dark   # Default - optimized for dark terminals
```

```yaml
theme:
  preset: light  # For light terminal backgrounds
```

### Custom Colors

Override individual colors while keeping a preset as the base:

```yaml
theme:
  preset: dark
  primary: "#61afef"      # Borders, headers, labels
  accent: "#e5c07b"       # Commands, keywords, interactive elements
  success: "#98c379"      # Enabled states, completions
  warning: "#d19a66"      # Caution states
  error: "#e06c75"        # Errors, disabled states
  info: "#56b6c2"         # Informational panels
  text: "#abb2bf"         # Normal text
  text_muted: "#5c6370"   # Dimmed/secondary text
  surface: "#282c34"      # Main background (TUI only)
  surface_alt: "#3e4451"  # Panels, status bar (TUI only)
```

### Color Formats

Colors can be specified as:
- **Hex codes**: `"#ff9900"`, `"#abc"` (short form)
- **Named colors**: `"cyan"`, `"red"`, `"bright_white"`
- **RGB**: Supported by the underlying Rich library

### Named Colors Reference

Standard terminal colors:
- `black`, `red`, `green`, `yellow`, `blue`, `magenta`, `cyan`, `white`

Bright variants:
- `bright_black`, `bright_red`, `bright_green`, `bright_yellow`
- `bright_blue`, `bright_magenta`, `bright_cyan`, `bright_white`

### Example Themes

**One Dark**
```yaml
theme:
  preset: dark
  primary: "#61afef"
  accent: "#e5c07b"
  success: "#98c379"
  error: "#e06c75"
  info: "#56b6c2"
  text: "#abb2bf"
  text_muted: "#5c6370"
  surface: "#282c34"
  surface_alt: "#3e4451"
```

**Dracula**
```yaml
theme:
  preset: dark
  primary: "#8be9fd"
  accent: "#ffb86c"
  success: "#50fa7b"
  warning: "#ffb86c"
  error: "#ff5555"
  info: "#bd93f9"
  text: "#f8f8f2"
  text_muted: "#6272a4"
  surface: "#282a36"
  surface_alt: "#44475a"
```

**Solarized Dark**
```yaml
theme:
  preset: dark
  primary: "#268bd2"
  accent: "#b58900"
  success: "#859900"
  warning: "#cb4b16"
  error: "#dc322f"
  info: "#2aa198"
  text: "#839496"
  text_muted: "#586e75"
  surface: "#002b36"
  surface_alt: "#073642"
```

**Nord**
```yaml
theme:
  preset: dark
  primary: "#88c0d0"
  accent: "#ebcb8b"
  success: "#a3be8c"
  warning: "#d08770"
  error: "#bf616a"
  info: "#81a1c1"
  text: "#eceff4"
  text_muted: "#4c566a"
  surface: "#2e3440"
  surface_alt: "#3b4252"
```

---

## Display Settings

```yaml
max_display_messages: 4      # Messages shown in compact status displays
progress_bar_width: 20       # Width of progress indicators
```

Legacy `dashboard_enabled` and `dashboard_refresh_rate` settings are ignored.

### Separators

Control the width of visual separators in console output:

```yaml
separator_width_narrow: 40
separator_width_standard: 50
separator_width_wide: 60
```

---

## LLM Settings

### Temperature

Temperature controls response randomness (0.0 = deterministic, 2.0 = maximum creativity):

```yaml
temperature_low: 0.3        # For precise, deterministic responses
temperature_default: 0.7    # Standard temperature
```

### Token Limits

```yaml
max_tokens_query: 1000      # Max tokens for queries
max_tokens_summary: 2000    # Max tokens for summaries
```

---

## Content Limits

### Line Limits

```yaml
max_lines_config: 100       # Lines when reading config files
max_lines_dependency: 50    # Lines when reading dependency files
max_test_results: 20        # Test files to display
```

### Truncation Thresholds

Control how much content is shown before truncating:

```yaml
truncate_error_message: 500      # Error messages
truncate_research_medium: 1000   # Medium research content
truncate_research_large: 1500    # Large research content
truncate_file_content: 2000      # General file content
truncate_priority_file: 3000     # Important files (more content shown)
```

### Preview Lengths

```yaml
preview_short: 40           # Short previews (filenames)
preview_standard: 50        # Standard preview length
preview_conclusion: 200     # Conclusion/summary previews
```

---

## Rate Limiting

Thresholds for rate limit warnings (as percentages, 0.0-1.0):

```yaml
cache_hit_good: 0.50        # Good cache hit rate (50%)
rate_limit_warning: 0.75    # Warning threshold (75%)
rate_limit_critical: 0.90   # Critical threshold (90%)
```

---

## Iteration Limits

```yaml
max_iterations: 10          # Max iterations for iterative commands
```

---

## Clarification Settings

Controls when user clarification is requested for ambiguous tasks:

```yaml
clarification:
  confidence_threshold: 0.7      # Below this, always ask for clarification
  high_confidence_bypass: 0.9    # Above this, skip conflicting signal checks
```

---

## Environment Variables

Any setting can be overridden via environment variables using the `CLI_` prefix:

```bash
# Override temperature
export CLI_TEMPERATURE_DEFAULT=0.8

# Override token limit
export CLI_MAX_TOKENS_QUERY=2000
```

Nested settings use underscores:

```bash
# Override theme preset
export CLI_THEME_PRESET=light

# Override clarification threshold
export CLI_CLARIFICATION_CONFIDENCE_THRESHOLD=0.8
```

---

## Complete Example

`.scrappy.yaml`:

```yaml
# LLM settings
temperature_low: 0.3
temperature_default: 0.7
max_tokens_query: 1000
max_tokens_summary: 2000

# Content limits
max_lines_config: 100
max_lines_dependency: 50
truncate_error_message: 500
truncate_file_content: 2000

# Display
max_display_messages: 4
progress_bar_width: 20

# Rate limits
rate_limit_warning: 0.75
rate_limit_critical: 0.90

# Iterations
max_iterations: 10

# Clarification
clarification:
  confidence_threshold: 0.7
  high_confidence_bypass: 0.9

# Theme - One Dark
theme:
  preset: dark
  primary: "#61afef"
  accent: "#e5c07b"
  success: "#98c379"
  error: "#e06c75"
  info: "#56b6c2"
  text: "#abb2bf"
  text_muted: "#5c6370"
  surface: "#282c34"
  surface_alt: "#3e4451"
```

`.scrappy.json`:

```json
{
  "temperature_low": 0.3,
  "temperature_default": 0.7,
  "max_tokens_query": 1000,
  "max_tokens_summary": 2000,
  "max_iterations": 10,
  "clarification": {
    "confidence_threshold": 0.7,
    "high_confidence_bypass": 0.9
  },
  "theme": {
    "preset": "dark",
    "primary": "#61afef",
    "accent": "#e5c07b",
    "success": "#98c379",
    "error": "#e06c75"
  }
}
```

---

## Tips

1. **Start with a preset** - Use `dark` or `light` as a base, then override specific colors

2. **Test your theme** - Run any Scrappy command to see your theme in action

3. **Use hex codes for precision** - Named colors work but hex gives more control

4. **Keep config in version control** - Share your team's preferred settings

5. **Use environment variables for overrides** - Useful for CI/CD or temporary changes
