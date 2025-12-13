"""
Tests for theme configuration loading from files.

Verifies that theme settings load correctly from YAML and JSON config files,
including all 10 color properties and preset selection.
"""

import json
import os
import pytest
from pathlib import Path

from scrappy.cli.config_factory import CLIConfigFactory
from scrappy.cli.cli_config import CLIConfig
from scrappy.infrastructure.theme import (
    ScrappyTheme,
    LightTheme,
    CustomTheme,
)

  # Ignore if directory still locked or not empty


class TestThemeLoadingFromYAML:
    """Tests for loading theme from YAML config files."""

    def test_load_dark_preset_from_yaml(self, tmp_path: Path):
        """Dark preset loads correctly from YAML."""
        config_file = tmp_path / "dark.yaml"
        config_file.write_text("""
theme:
  preset: dark
""")
        factory = CLIConfigFactory()
        config = factory.create_from_file(str(config_file))

        assert config.theme_config == {"preset": "dark"}
        assert isinstance(config.theme, ScrappyTheme)

    def test_load_light_preset_from_yaml(self, tmp_path: Path):
        """Light preset loads correctly from YAML."""
        config_file = tmp_path / "light.yaml"
        config_file.write_text("""
theme:
  preset: light
""")
        factory = CLIConfigFactory()
        config = factory.create_from_file(str(config_file))

        assert config.theme_config == {"preset": "light"}
        assert isinstance(config.theme, LightTheme)
        assert config.theme.primary == "#0000ff"
        assert config.theme.text == "#000000"
        assert config.theme.surface == "#ffffff"

    def test_load_all_color_overrides_from_yaml(self, tmp_path: Path):
        """All 10 color properties load correctly from YAML."""
        config_file = tmp_path / "all_colors.yaml"
        config_file.write_text("""
theme:
  preset: dark
  primary: "#61afef"
  accent: "#e5c07b"
  success: "#98c379"
  warning: "#d19a66"
  error: "#e06c75"
  info: "#56b6c2"
  text: "#abb2bf"
  text_muted: "#5c6370"
  surface: "#282c34"
  surface_alt: "#3e4451"
""")
        factory = CLIConfigFactory()
        config = factory.create_from_file(str(config_file))

        assert isinstance(config.theme, CustomTheme)
        assert config.theme.primary == "#61afef"
        assert config.theme.accent == "#e5c07b"
        assert config.theme.success == "#98c379"
        assert config.theme.warning == "#d19a66"
        assert config.theme.error == "#e06c75"
        assert config.theme.info == "#56b6c2"
        assert config.theme.text == "#abb2bf"
        assert config.theme.text_muted == "#5c6370"
        assert config.theme.surface == "#282c34"
        assert config.theme.surface_alt == "#3e4451"

    def test_load_partial_overrides_from_yaml(self, tmp_path: Path):
        """Partial color overrides work, rest use preset defaults."""
        config_file = tmp_path / "partial.yaml"
        config_file.write_text("""
theme:
  preset: dark
  primary: "#ff00ff"
  error: "#ffc0cb"
""")
        factory = CLIConfigFactory()
        config = factory.create_from_file(str(config_file))

        assert isinstance(config.theme, CustomTheme)
        assert config.theme.primary == "#ff00ff"
        assert config.theme.error == "#ffc0cb"
        # Defaults from dark preset
        assert config.theme.accent == "#ff9900"
        assert config.theme.success == "#00ff00"

    def test_load_overrides_on_light_preset_from_yaml(self, tmp_path: Path):
        """Color overrides on light preset use light defaults for non-overridden."""
        config_file = tmp_path / "light_override.yaml"
        config_file.write_text("""
theme:
  preset: light
  primary: purple
""")
        factory = CLIConfigFactory()
        config = factory.create_from_file(str(config_file))

        assert isinstance(config.theme, CustomTheme)
        assert config.theme.primary == "purple"
        # Defaults from light preset
        assert config.theme.text == "#000000"
        assert config.theme.surface == "#ffffff"


class TestThemeLoadingFromJSON:
    """Tests for loading theme from JSON config files."""

    def test_load_dark_preset_from_json(self, tmp_path: Path):
        """Dark preset loads correctly from JSON."""
        config_file = tmp_path / "dark.json"
        config_file.write_text(json.dumps({
            "theme": {
                "preset": "dark"
            }
        }))
        factory = CLIConfigFactory()
        config = factory.create_from_file(str(config_file))

        assert config.theme_config == {"preset": "dark"}
        assert isinstance(config.theme, ScrappyTheme)

    def test_load_light_preset_from_json(self, tmp_path: Path):
        """Light preset loads correctly from JSON."""
        config_file = tmp_path / "light.json"
        config_file.write_text(json.dumps({
            "theme": {
                "preset": "light"
            }
        }))
        factory = CLIConfigFactory()
        config = factory.create_from_file(str(config_file))

        assert config.theme_config == {"preset": "light"}
        assert isinstance(config.theme, LightTheme)

    def test_load_all_color_overrides_from_json(self, tmp_path: Path):
        """All 10 color properties load correctly from JSON."""
        config_file = tmp_path / "all_colors.json"
        config_file.write_text(json.dumps({
            "theme": {
                "preset": "dark",
                "primary": "#61afef",
                "accent": "#e5c07b",
                "success": "#98c379",
                "warning": "#d19a66",
                "error": "#e06c75",
                "info": "#56b6c2",
                "text": "#abb2bf",
                "text_muted": "#5c6370",
                "surface": "#282c34",
                "surface_alt": "#3e4451"
            }
        }))
        factory = CLIConfigFactory()
        config = factory.create_from_file(str(config_file))

        assert isinstance(config.theme, CustomTheme)
        assert config.theme.primary == "#61afef"
        assert config.theme.accent == "#e5c07b"
        assert config.theme.success == "#98c379"
        assert config.theme.warning == "#d19a66"
        assert config.theme.error == "#e06c75"
        assert config.theme.info == "#56b6c2"
        assert config.theme.text == "#abb2bf"
        assert config.theme.text_muted == "#5c6370"
        assert config.theme.surface == "#282c34"
        assert config.theme.surface_alt == "#3e4451"


class TestThemeLoadingEdgeCases:
    """Tests for edge cases in theme loading."""

    def test_missing_theme_section_uses_default(self, tmp_path: Path):
        """Config without theme section uses default dark theme."""
        config_file = tmp_path / "no_theme.yaml"
        config_file.write_text("""
temperature_default: 0.8
""")
        factory = CLIConfigFactory()
        config = factory.create_from_file(str(config_file))

        assert config.theme_config == {}
        assert isinstance(config.theme, ScrappyTheme)



    def test_invalid_color_keys_are_ignored(self, tmp_path: Path):
        """Invalid color keys are silently ignored."""
        config_file = tmp_path / "invalid_keys.yaml"
        config_file.write_text("""
theme:
  preset: dark
  primary: cyan
  invalid_key: value
  not_a_color: "#ffffff"
""")
        factory = CLIConfigFactory()
        config = factory.create_from_file(str(config_file))

        assert isinstance(config.theme, CustomTheme)
        assert config.theme.primary == "cyan"
        # No error raised, invalid keys ignored

    def test_theme_with_other_config_options(self, tmp_path: Path):
        """Theme loads correctly alongside other config options."""
        config_file = tmp_path / "mixed.yaml"
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
        assert config.theme.text == "#000000"  # from light preset

        # Other options loaded correctly
        assert config.temperature_default == 0.9
        assert config.max_tokens_query == 2000
        assert config.dashboard_enabled is False


class TestThemeConfigFactoryCreate:
    """Tests for CLIConfigFactory.create() with theme."""



    def test_create_with_explicit_path_loads_theme(self, tmp_path: Path):
        """create() with explicit path loads theme."""
        config_file = tmp_path / "custom_config.yaml"
        config_file.write_text("""
theme:
  preset: light
  accent: orange
""")
        factory = CLIConfigFactory()
        config = factory.create(config_path=str(config_file))

        assert isinstance(config.theme, CustomTheme)
        assert config.theme.accent == "orange"
        assert config.theme.text == "#000000"  # from light preset
