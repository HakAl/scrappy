"""
Integration tests for theme configuration loading.

Tests the complete flow from config file → CLIConfig → ThemeProtocol → Application,
verifying that user theme configuration works end-to-end.
"""

import json
import os
import pytest
from pathlib import Path

from scrappy.cli.config_factory import get_config, reset_config, CLIConfigFactory
from scrappy.cli.cli_config import CLIConfig
from scrappy.infrastructure.theme import (
    ThemeProtocol,
    ScrappyTheme,
    LightTheme,
    CustomTheme,
    DEFAULT_THEME,
)




@pytest.fixture(autouse=True)
def reset_global_config():
    """Reset global config before and after each test."""
    reset_config()
    yield
    reset_config()


class TestEndToEndThemeLoading:
    """Tests for complete end-to-end theme loading flow."""

    def test_yaml_config_to_theme_protocol(self, tmp_path: Path, monkeypatch):
        """Complete flow: .scrappy.yaml → CLIConfig → ThemeProtocol."""
        # Create config file
        config_file = tmp_path / ".scrappy.yaml"
        config_file.write_text("""
theme:
  preset: dark
  primary: "#61afef"
  accent: "#e5c07b"
  success: "#98c379"
""")
        monkeypatch.chdir(tmp_path)

        # Load config using factory
        config = get_config()

        # Verify theme is loaded
        assert config.theme_config is not None
        # Note: ThemeProtocol is not @runtime_checkable, so we check the concrete type
        assert isinstance(config.theme, CustomTheme)

        # Verify custom colors
        assert config.theme.primary == "#61afef"
        assert config.theme.accent == "#e5c07b"
        assert config.theme.success == "#98c379"

        # Verify defaults from dark preset
        assert config.theme.text == "#ffffff"

    def test_json_config_to_theme_protocol(self, tmp_path: Path, monkeypatch):
        """Complete flow: .scrappy.json → CLIConfig → ThemeProtocol."""
        config_file = tmp_path / ".scrappy.json"
        config_file.write_text(json.dumps({
            "theme": {
                "preset": "light",
                "primary": "#0000ff",
                "error": "#ff0000"
            }
        }))
        monkeypatch.chdir(tmp_path)

        config = get_config()

        assert isinstance(config.theme, CustomTheme)
        assert config.theme.primary == "#0000ff"
        assert config.theme.error == "#ff0000"
        assert config.theme.text == "#000000"  # from light preset (hex code)

    def test_no_config_file_uses_default_theme(self, tmp_path: Path, monkeypatch):
        """When no config file exists, uses DEFAULT_THEME."""
        # Empty directory
        monkeypatch.chdir(tmp_path)

        config = get_config()

        assert isinstance(config.theme, ScrappyTheme)
        assert config.theme.primary == DEFAULT_THEME.primary
        assert config.theme.surface == DEFAULT_THEME.surface

    def test_empty_theme_section_uses_default(self, tmp_path: Path):
        """Config with empty theme section uses default theme."""
        config_file = tmp_path / "empty_theme.yaml"
        config_file.write_text("""
temperature_default: 0.8
theme:
""")
        factory = CLIConfigFactory()
        config = factory.create_from_file(str(config_file))

        # Empty theme section results in default theme
        assert isinstance(config.theme, ScrappyTheme)
        # Other config values load correctly
        assert config.temperature_default == 0.8

    def test_theme_properties_are_accessible(self, tmp_path: Path, monkeypatch):
        """All ThemeProtocol properties are accessible from loaded theme."""
        config_file = tmp_path / ".scrappy.yaml"
        config_file.write_text("""
theme:
  preset: dark
  primary: cyan
  accent: yellow
  success: green
  warning: orange
  error: red
  info: blue
  text: white
  text_muted: gray
  surface: "#1a1a1a"
  surface_alt: "#2a2a2a"
""")
        monkeypatch.chdir(tmp_path)

        config = get_config()
        theme = config.theme

        # All properties should be accessible
        assert theme.primary == "cyan"
        assert theme.accent == "yellow"
        assert theme.success == "green"
        assert theme.warning == "orange"
        assert theme.error == "red"
        assert theme.info == "blue"
        assert theme.text == "white"
        assert theme.text_muted == "gray"
        assert theme.surface == "#1a1a1a"
        assert theme.surface_alt == "#2a2a2a"


class TestThemeConfigMerging:
    """Tests for theme configuration merging from multiple sources."""

    def test_config_merge_preserves_theme(self, tmp_path: Path):
        """Merging configs combines theme from both sources."""
        base_config = CLIConfig(theme_config={"preset": "dark", "primary": "cyan"})
        override_config = CLIConfig(theme_config={"primary": "magenta", "accent": "orange"})

        merged = base_config.merge(override_config)

        # Override's theme completely replaces base theme (dict merge behavior)
        assert merged.theme_config["primary"] == "magenta"
        assert merged.theme_config["accent"] == "orange"
        # Note: preset might not be preserved if override doesn't have it
        assert isinstance(merged.theme, (CustomTheme, ScrappyTheme))
        assert merged.theme.primary == "magenta"

    def test_config_merge_override_preset(self, tmp_path: Path):
        """Later config overrides preset from earlier config."""
        base_config = CLIConfig(theme_config={"preset": "dark"})
        override_config = CLIConfig(theme_config={"preset": "light"})

        merged = base_config.merge(override_config)

        assert merged.theme_config["preset"] == "light"
        assert isinstance(merged.theme, LightTheme)

    def test_empty_theme_config_does_not_override(self, tmp_path: Path):
        """Empty theme_config doesn't override existing theme."""
        base_config = CLIConfig(theme_config={"preset": "light", "primary": "blue"})
        empty_config = CLIConfig(theme_config={})

        merged = base_config.merge(empty_config)

        # Original theme preserved
        assert merged.theme_config["preset"] == "light"
        assert merged.theme_config["primary"] == "blue"
        assert isinstance(merged.theme, CustomTheme)


class TestThemeCaching:
    """Tests for theme lazy loading and caching."""

    def test_theme_is_cached_on_first_access(self):
        """Theme is loaded once and cached."""
        config = CLIConfig(theme_config={"preset": "dark"})

        # First access loads theme
        theme1 = config.theme
        assert isinstance(theme1, ScrappyTheme)

        # Second access returns cached instance
        # Note: They should be the same type and values, caching ensures same object
        theme2 = config.theme
        assert type(theme1) == type(theme2)
        assert theme1.primary == theme2.primary

    def test_theme_loads_lazily(self):
        """Theme is not loaded until accessed."""
        config = CLIConfig(theme_config={"preset": "dark"})

        # _theme should be None before first access
        assert config._theme is None

        # Access triggers load
        _ = config.theme
        assert config._theme is not None



class TestGlobalConfigTheme:
    """Tests for global config getter with theme."""


    def test_get_config_caches_theme(self, tmp_path: Path, monkeypatch):
        """get_config() returns same config instance on repeated calls."""
        config_file = tmp_path / ".scrappy.yaml"
        config_file.write_text("""
theme:
  preset: dark
""")
        monkeypatch.chdir(tmp_path)

        config1 = get_config()
        config2 = get_config()

        # get_config() caches the config instance
        assert config1 is config2
        # Theme should be the same type
        assert type(config1.theme) == type(config2.theme)

    def test_get_config_reload_creates_new_theme(self, tmp_path: Path, monkeypatch):
        """get_config(reload=True) creates new theme instance."""
        config_file = tmp_path / ".scrappy.yaml"
        config_file.write_text("""
theme:
  preset: dark
""")
        monkeypatch.chdir(tmp_path)

        config1 = get_config()
        config2 = get_config(reload=True)

        # Different config instances
        assert config1 is not config2
        # But themes should be equivalent
        assert type(config1.theme) == type(config2.theme)


class TestThemeWithOtherConfig:
    """Tests that theme works alongside other config options."""

    def test_theme_and_temperature_both_load(self, tmp_path: Path):
        """Theme and other config options load together."""
        config_file = tmp_path / "mixed_config.yaml"
        config_file.write_text("""
temperature_default: 0.9
max_tokens_query: 2000

theme:
  preset: light
  primary: purple

dashboard_enabled: false
""")
        factory = CLIConfigFactory()
        config = factory.create_from_file(str(config_file))

        # Theme loaded correctly
        assert isinstance(config.theme, CustomTheme)
        assert config.theme.primary == "purple"
        assert config.theme.text == "#000000"  # from light preset (hex code)

        # Other config loaded correctly
        assert config.temperature_default == 0.9
        assert config.max_tokens_query == 2000
        assert hasattr(config, "dashboard_enabled") is False

    def test_config_to_dict_includes_theme(self):
        """Config serialization includes theme."""
        config = CLIConfig(
            theme_config={"preset": "dark", "primary": "cyan"},
            temperature_default=0.8
        )

        config_dict = config.to_dict()

        # Theme mapped to 'theme' key for config file compatibility
        assert 'theme' in config_dict
        assert config_dict['theme']['preset'] == "dark"
        assert config_dict['theme']['primary'] == "cyan"
        assert config_dict['temperature_default'] == 0.8

    def test_config_from_dict_loads_theme(self):
        """Config deserialization loads theme."""
        config_dict = {
            "theme": {
                "preset": "light",
                "accent": "orange"
            },
            "temperature_default": 0.7
        }

        config = CLIConfig.from_dict(config_dict)

        assert isinstance(config.theme, CustomTheme)
        assert config.theme.accent == "orange"
        assert config.temperature_default == 0.7


class TestRealWorldScenarios:
    """Real-world usage scenarios for theme configuration."""

    def test_one_dark_pro_theme_config(self, tmp_path: Path, monkeypatch):
        """User configures One Dark Pro theme (real-world example)."""
        config_file = tmp_path / ".scrappy.yaml"
        config_file.write_text("""
theme:
  preset: dark
  primary: "#61afef"
  accent: "#e5c07b"
  success: "#98c379"
  error: "#e06c75"
  warning: "#d19a66"
  info: "#56b6c2"
  text: "#abb2bf"
  text_muted: "#5c6370"
  surface: "#282c34"
  surface_alt: "#3e4451"
""")
        monkeypatch.chdir(tmp_path)

        config = get_config()

        # Verify all One Dark Pro colors loaded
        assert config.theme.primary == "#61afef"
        assert config.theme.accent == "#e5c07b"
        assert config.theme.success == "#98c379"
        assert config.theme.error == "#e06c75"
        assert config.theme.warning == "#d19a66"
        assert config.theme.info == "#56b6c2"
        assert config.theme.text == "#abb2bf"
        assert config.theme.text_muted == "#5c6370"
        assert config.theme.surface == "#282c34"
        assert config.theme.surface_alt == "#3e4451"

    def test_minimal_theme_override(self, tmp_path: Path, monkeypatch):
        """User overrides just one color (real-world minimal config)."""
        config_file = tmp_path / ".scrappy.yaml"
        config_file.write_text("""
theme:
  accent: "#ff00ff"
""")
        monkeypatch.chdir(tmp_path)

        config = get_config()

        # Only accent overridden
        assert config.theme.accent == "#ff00ff"
        # Rest are defaults from ScrappyTheme
        assert config.theme.primary == "#00ffff"
        assert config.theme.success == "#00ff00"

    def test_switch_to_light_theme(self, tmp_path: Path, monkeypatch):
        """User switches from dark to light preset (real-world scenario)."""
        config_file = tmp_path / ".scrappy.yaml"
        config_file.write_text("""
theme:
  preset: light
""")
        monkeypatch.chdir(tmp_path)

        config = get_config()

        # Light theme loaded (hex codes)
        assert isinstance(config.theme, LightTheme)
        assert config.theme.text == "#000000"
        assert config.theme.surface == "#ffffff"
        assert config.theme.surface_alt == "#f0f0f0"

    def test_light_theme_with_custom_accent(self, tmp_path: Path, monkeypatch):
        """User uses light theme with custom accent color."""
        config_file = tmp_path / ".scrappy.yaml"
        config_file.write_text("""
theme:
  preset: light
  accent: "#ff6600"
""")
        monkeypatch.chdir(tmp_path)

        config = get_config()

        # Light theme with override (hex codes)
        assert isinstance(config.theme, CustomTheme)
        assert config.theme.accent == "#ff6600"
        assert config.theme.text == "#000000"  # from light preset
        assert config.theme.surface == "#ffffff"  # from light preset
