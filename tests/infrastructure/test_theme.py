"""
Tests for theme system.

Tests verify that:
1. ThemeProtocol defines all required semantic colors
2. Theme classes provide correct default values
3. load_theme_from_config() handles all cases correctly
4. GitColors and SyntaxColors provide consistent values
"""

import pytest

from scrappy.infrastructure.theme import (
    CustomTheme,
    DEFAULT_THEME,
    GitColors,
    LightTheme,
    NoColorTheme,
    ScrappyTheme,
    SyntaxColors,
    THEME_COLOR_KEYS,
    THEME_PRESETS,
    load_theme_from_config,
)


class TestScrappyTheme:
    """Tests for ScrappyTheme (default dark theme)."""

    def test_provides_all_foreground_colors(self):
        """ScrappyTheme provides all 8 foreground color properties."""
        theme = ScrappyTheme()

        assert theme.primary == "#00ffff"
        assert theme.accent == "#ff9900"
        assert theme.success == "#00ff00"
        assert theme.warning == "#ffff00"
        assert theme.error == "#ff0000"
        assert theme.info == "#0077ff"
        assert theme.text == "#ffffff"
        assert theme.text_muted == "#808080"

    def test_provides_background_colors(self):
        """ScrappyTheme provides 2 background color properties."""
        theme = ScrappyTheme()

        assert theme.surface  # has surface property
        assert theme.surface_alt  # has surface_alt property

    def test_provides_git_colors(self):
        """ScrappyTheme includes GitColors instance."""
        theme = ScrappyTheme()

        assert isinstance(theme.git, GitColors)
        assert theme.git.add == "green"
        assert theme.git.remove == "red"

    def test_provides_syntax_colors(self):
        """ScrappyTheme includes SyntaxColors instance."""
        theme = ScrappyTheme()

        assert isinstance(theme.syntax, SyntaxColors)
        assert theme.syntax.python == "green"
        assert theme.syntax.javascript == "yellow"



class TestLightTheme:
    """Tests for LightTheme preset."""

    def test_provides_all_foreground_colors(self):
        """LightTheme provides all 8 foreground color properties."""
        theme = LightTheme()

        assert theme.primary == "#0000ff"
        assert theme.accent == "#ff00ff"
        assert theme.success == "#00ff00"
        assert theme.warning == "#ff9900"  # Amber - better contrast on white
        assert theme.error == "#ff0000"
        assert theme.info == "#00ffff"
        assert theme.text == "#000000"
        assert theme.text_muted == "#808080"

    def test_provides_background_colors(self):
        """LightTheme uses light backgrounds."""
        theme = LightTheme()

        assert theme.surface == "#ffffff"
        assert theme.surface_alt == "#f0f0f0"

    def test_provides_git_colors(self):
        """LightTheme includes GitColors instance."""
        theme = LightTheme()

        assert isinstance(theme.git, GitColors)

    def test_provides_syntax_colors(self):
        """LightTheme includes SyntaxColors instance."""
        theme = LightTheme()

        assert isinstance(theme.syntax, SyntaxColors)


class TestNoColorTheme:
    """Tests for NoColorTheme (no colors applied)."""

    def test_all_foreground_colors_are_empty(self):
        """NoColorTheme returns empty strings for all foreground colors."""
        theme = NoColorTheme()

        assert theme.primary == ""
        assert theme.accent == ""
        assert theme.success == ""
        assert theme.warning == ""
        assert theme.error == ""
        assert theme.info == ""
        assert theme.text == ""
        assert theme.text_muted == ""

    def test_background_colors_are_empty(self):
        """NoColorTheme returns empty strings for background colors."""
        theme = NoColorTheme()

        assert theme.surface == ""
        assert theme.surface_alt == ""

    def test_still_provides_git_colors(self):
        """NoColorTheme still includes GitColors for diff formatting."""
        theme = NoColorTheme()

        assert isinstance(theme.git, GitColors)
        assert theme.git.add == "green"

    def test_still_provides_syntax_colors(self):
        """NoColorTheme still includes SyntaxColors for file listings."""
        theme = NoColorTheme()

        assert isinstance(theme.syntax, SyntaxColors)
        assert theme.syntax.python == "green"


class TestGitColors:
    """Tests for GitColors (fixed diff colors)."""

    def test_provides_all_git_colors(self):
        """GitColors provides all diff-related colors."""
        git = GitColors()

        assert git.add == "green"
        assert git.remove == "red"
        assert git.header == "cyan"
        assert git.commit == "yellow"
        assert git.meta == "bright_white"



class TestSyntaxColors:
    """Tests for SyntaxColors (file type indicators)."""

    def test_provides_all_syntax_colors(self):
        """SyntaxColors provides colors for file types."""
        syntax = SyntaxColors()

        assert syntax.python == "green"
        assert syntax.javascript == "yellow"
        assert syntax.config == "magenta"
        assert syntax.docs == "white"
        assert syntax.default == "white"



class TestThemePresets:
    """Tests for theme preset registry."""

    def test_contains_dark_preset(self):
        """THEME_PRESETS contains 'dark' preset."""
        assert "dark" in THEME_PRESETS
        assert THEME_PRESETS["dark"] is ScrappyTheme

    def test_contains_light_preset(self):
        """THEME_PRESETS contains 'light' preset."""
        assert "light" in THEME_PRESETS
        assert THEME_PRESETS["light"] is LightTheme


class TestThemeColorKeys:
    """Tests for valid color key validation."""

    def test_contains_all_foreground_keys(self):
        """THEME_COLOR_KEYS contains all foreground color names."""
        expected = {
            "primary",
            "accent",
            "success",
            "warning",
            "error",
            "info",
            "text",
            "text_muted",
        }
        assert expected.issubset(THEME_COLOR_KEYS)

    def test_contains_background_keys(self):
        """THEME_COLOR_KEYS contains background color names."""
        assert "surface" in THEME_COLOR_KEYS
        assert "surface_alt" in THEME_COLOR_KEYS



class TestLoadThemeFromConfig:
    """Tests for load_theme_from_config() function."""

    def test_empty_config_returns_default_theme(self):
        """Empty config returns DEFAULT_THEME."""
        config = {}

        theme = load_theme_from_config(config)

        assert isinstance(theme, ScrappyTheme)
        assert theme.primary == "#00ffff"

    def test_missing_theme_section_returns_default(self):
        """Config without 'theme' section returns DEFAULT_THEME."""
        config = {"other_key": "value"}

        theme = load_theme_from_config(config)

        assert isinstance(theme, ScrappyTheme)

    def test_empty_theme_section_returns_default(self):
        """Empty 'theme' section returns DEFAULT_THEME."""
        config = {"theme": {}}

        theme = load_theme_from_config(config)

        assert isinstance(theme, ScrappyTheme)

    def test_dark_preset_returns_scrappy_theme(self):
        """preset: dark returns ScrappyTheme."""
        config = {"theme": {"preset": "dark"}}

        theme = load_theme_from_config(config)

        assert isinstance(theme, ScrappyTheme)
        assert theme.primary == "#00ffff"

    def test_light_preset_returns_light_theme(self):
        """preset: light returns LightTheme."""
        config = {"theme": {"preset": "light"}}

        theme = load_theme_from_config(config)

        assert isinstance(theme, LightTheme)
        assert theme.primary == "#0000ff"
        assert theme.text == "#000000"

    def test_invalid_preset_falls_back_to_dark(self):
        """Invalid preset falls back to ScrappyTheme (dark)."""
        config = {"theme": {"preset": "nonexistent"}}

        theme = load_theme_from_config(config)

        assert isinstance(theme, ScrappyTheme)

    def test_single_color_override(self):
        """Single color override creates CustomTheme."""
        config = {"theme": {"primary": "magenta"}}

        theme = load_theme_from_config(config)

        assert isinstance(theme, CustomTheme)
        assert theme.primary == "magenta"
        # Other colors inherit from base (ScrappyTheme)
        assert theme.accent == "#ff9900"
        assert theme.success == "#00ff00"

    def test_multiple_color_overrides(self):
        """Multiple color overrides work correctly."""
        config = {
            "theme": {
                "primary": "#61afef",
                "accent": "#e5c07b",
                "surface": "#282c34",
            }
        }

        theme = load_theme_from_config(config)

        assert isinstance(theme, CustomTheme)
        assert theme.primary == "#61afef"
        assert theme.accent == "#e5c07b"
        assert theme.surface == "#282c34"
        # Non-overridden retain defaults
        assert theme.success == "#00ff00"
        assert theme.error == "#ff0000"

    def test_overrides_on_light_preset(self):
        """Color overrides work with light preset base."""
        config = {
            "theme": {
                "preset": "light",
                "primary": "purple",
            }
        }

        theme = load_theme_from_config(config)

        assert isinstance(theme, CustomTheme)
        assert theme.primary == "purple"
        # Other values from light preset
        assert theme.text == "#000000"
        assert theme.surface == "#ffffff"

    def test_invalid_keys_are_ignored(self):
        """Invalid color keys are silently ignored."""
        config = {
            "theme": {
                "primary": "cyan",
                "invalid_key": "value",
                "another_bad": "bad",
            }
        }

        theme = load_theme_from_config(config)

        assert isinstance(theme, CustomTheme)
        assert theme.primary == "cyan"
        # No error raised for invalid keys

    def test_none_values_are_ignored(self):
        """None values in config are ignored."""
        config = {
            "theme": {
                "primary": None,
                "accent": "orange",
            }
        }

        theme = load_theme_from_config(config)

        assert isinstance(theme, CustomTheme)
        assert theme.primary == "#00ffff"  # Default, not None
        assert theme.accent == "orange"

    def test_preset_key_itself_is_not_a_color(self):
        """'preset' key is not treated as a color override."""
        config = {
            "theme": {
                "preset": "dark",
            }
        }

        theme = load_theme_from_config(config)

        # Should return base ScrappyTheme, not CustomTheme
        assert isinstance(theme, ScrappyTheme)

    def test_full_custom_theme(self):
        """All colors can be customized."""
        config = {
            "theme": {
                "primary": "#61afef",
                "accent": "#e5c07b",
                "success": "#98c379",
                "warning": "#d19a66",
                "error": "#e06c75",
                "info": "#56b6c2",
                "text": "#abb2bf",
                "text_muted": "#5c6370",
                "surface": "#282c34",
                "surface_alt": "#3e4451",
            }
        }

        theme = load_theme_from_config(config)

        assert theme.primary == "#61afef"
        assert theme.accent == "#e5c07b"
        assert theme.success == "#98c379"
        assert theme.warning == "#d19a66"
        assert theme.error == "#e06c75"
        assert theme.info == "#56b6c2"
        assert theme.text == "#abb2bf"
        assert theme.text_muted == "#5c6370"
        assert theme.surface == "#282c34"
        assert theme.surface_alt == "#3e4451"


class TestCustomTheme:
    """Tests for CustomTheme class."""

    def test_default_values_match_scrappy_theme(self):
        """CustomTheme defaults match ScrappyTheme."""
        custom = CustomTheme()
        scrappy = ScrappyTheme()

        assert custom.primary == scrappy.primary
        assert custom.accent == scrappy.accent
        assert custom.success == scrappy.success
        assert custom.warning == scrappy.warning
        assert custom.error == scrappy.error
        assert custom.info == scrappy.info
        assert custom.text == scrappy.text
        assert custom.text_muted == scrappy.text_muted
        assert custom.surface == scrappy.surface
        assert custom.surface_alt == scrappy.surface_alt

    def test_custom_values_override_defaults(self):
        """Custom values override defaults."""
        custom = CustomTheme(primary="purple", accent="orange")

        assert custom.primary == "purple"
        assert custom.accent == "orange"
        assert custom.success == "#00ff00"  # Default retained

    def test_provides_git_colors(self):
        """CustomTheme includes GitColors."""
        custom = CustomTheme()

        assert isinstance(custom.git, GitColors)

    def test_provides_syntax_colors(self):
        """CustomTheme includes SyntaxColors."""
        custom = CustomTheme()

        assert isinstance(custom.syntax, SyntaxColors)


class TestDefaultTheme:
    """Tests for DEFAULT_THEME constant."""


    def test_has_expected_primary(self):
        """DEFAULT_THEME has cyan primary color."""
        assert DEFAULT_THEME.primary == "#00ffff"


class TestGlobalColorConstants:
    """Tests for GIT_COLORS and SYNTAX_COLORS constants."""




class TestThemeProtocolCompliance:
    """Tests that verify theme classes satisfy ThemeProtocol."""

    @pytest.fixture(params=[ScrappyTheme, LightTheme, CustomTheme, NoColorTheme])
    def theme(self, request):
        """Parametrized fixture providing all theme implementations."""
        return request.param()










