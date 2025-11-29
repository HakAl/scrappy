"""
Theme system for consistent color styling.

Provides a protocol-based theme system that works across CLI and TUI modes.
Includes core semantic colors, background colors, git/diff colors, and syntax colors.
Themes are user-configurable via config file.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Protocol


class ThemeProtocol(Protocol):
    """Protocol for application theming.

    Defines semantic color names that map to actual colors.
    Components should use semantic names (primary, success, error)
    instead of literal colors (cyan, green, red).
    """

    # Theme metadata
    @property
    def preset(self) -> str:
        """Theme preset name ('dark', 'light', or 'custom')."""
        ...

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

    # Metadata
    preset: str = "dark"
    # Foreground
    primary: str = "#00ffff"
    accent: str = "#ff9900"
    success: str = "#00ff00"
    warning: str = "#ffff00"
    error: str = "#ff0000"
    info: str = "#0000ff"
    text: str = "#ffffff"
    text_muted: str = "#808080"
    # Background
    surface: str = "#1e1e1e"
    surface_alt: str = "#2d2d2d"
    # Fixed
    git: GitColors = field(default_factory=GitColors)
    syntax: SyntaxColors = field(default_factory=SyntaxColors)


@dataclass(frozen=True)
class LightTheme:
    """Light mode preset."""

    # Metadata
    preset: str = "light"
    # Foreground
    primary: str = "#0000ff"
    accent: str = "#ff00ff"
    success: str = "#00ff00"
    warning: str = "#ff9900"  # Amber - better contrast on white background
    error: str = "#ff0000"
    info: str = "#00ffff"
    text: str = "#000000"
    text_muted: str = "#808080"
    # Background
    surface: str = "#ffffff"
    surface_alt: str = "#f0f0f0"
    # Fixed
    git: GitColors = field(default_factory=GitColors)
    syntax: SyntaxColors = field(default_factory=SyntaxColors)


@dataclass(frozen=True)
class NoColorTheme:
    """Theme for testing - no colors applied."""

    preset: str = "dark"  # Default to dark for testing
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
    "primary",
    "accent",
    "success",
    "warning",
    "error",
    "info",
    "text",
    "text_muted",
    "surface",
    "surface_alt",
}


@dataclass(frozen=True)
class CustomTheme:
    """Theme with user-customized colors."""

    preset: str = "dark"  # Inherited from base theme (dark or light)
    primary: str = "#00ffff"
    accent: str = "#ff9900"
    success: str = "#00ff00"
    warning: str = "#ffff00"
    error: str = "#ff0000"
    info: str = "#0000ff"
    text: str = "#ffffff"
    text_muted: str = "#808080"
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
        k: v for k, v in theme_config.items() if k in THEME_COLOR_KEYS and v is not None
    }

    if not overrides:
        return base

    # Build kwargs for CustomTheme, starting with base values
    kwargs = {
        "preset": preset_name,  # Inherit preset from config (dark or light)
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
