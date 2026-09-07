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
    ScrappyTheme,
    LightTheme,
    CustomTheme,
    DEFAULT_THEME,
)




# ---------------------------------------------------------------------------
# CWD-DISCOVERY tests (scrappy-psjw).
#
# CLIConfigFactory.create_with_detection() resolves a config file in three ordered
# branches (cli/config_factory.py:146-159): an explicit path, then CLI_CONFIG_PATH from
# the environment, then a scan of Path.cwd() for DEFAULT_CONFIG_FILES. The tests in this
# file whose PURPOSE is the third branch write .scrappy.yaml/.json into a tmp_path and
# chdir there.
#
# scripts/contained-pytest.sh ALWAYS assigns CLI_CONFIG_PATH (deliberately: an ambient
# value outranks the CWD scan and reaches a real parser, and absence is not inheritable
# state, so unsetting a parent copy would leave a hostile value intact in an
# independently-based child). Branch 2 then wins unconditionally and branch 3 becomes
# unreachable, so these tests silently received defaults.
#
# The fix is an EXPLICIT, OPT-IN fixture requested by name in each CWD-discovery test.
# It is NOT autouse and NOT global: removing the variable for the whole session would
# hand the rest of the suite back the real-profile config discovery that PR-1 exists to
# displace. Containment is preserved because monkeypatch restores the launcher's value at
# teardown, and because the only directory this fixture exposes to the scan is a
# disposable tmp_path whose discovery inputs it verifies are empty first.
# ---------------------------------------------------------------------------


@pytest.fixture
def cwd_discovery_root(tmp_path: Path, monkeypatch):
    """A disposable CWD with controlled discovery inputs and no CLI_CONFIG_PATH.

    Yields the directory the test should write its config file into. Guarantees, in order:
      1. CLI_CONFIG_PATH is EXPLICITLY removed for this test only (branch 2 cannot win).
      2. The disposable directory contains NONE of DEFAULT_CONFIG_FILES, so whatever the
         test writes is the ONLY discovery input and a stale file cannot fake a pass.
      3. The process CWD is that disposable directory, so the branch-3 scan can only ever
         see controlled inputs and never the developer's real working tree.
    """
    monkeypatch.delenv('CLI_CONFIG_PATH', raising=False)
    assert 'CLI_CONFIG_PATH' not in os.environ, (
        "CLI_CONFIG_PATH must be absent for a CWD-discovery test, otherwise "
        "config_factory branch 2 wins and branch 3 is never exercised"
    )

    preexisting = [name for name in CLIConfigFactory.DEFAULT_CONFIG_FILES
                   if (tmp_path / name).exists()]
    assert not preexisting, f"disposable CWD must start with no discovery inputs, found {preexisting}"

    monkeypatch.chdir(tmp_path)
    assert Path.cwd().resolve() == tmp_path.resolve()
    return tmp_path


@pytest.fixture(autouse=True)
def reset_global_config():
    """Reset global config before and after each test."""
    reset_config()
    yield
    reset_config()


class TestEndToEndThemeLoading:
    """Tests for complete end-to-end theme loading flow."""

    def test_yaml_config_to_theme_protocol(self, cwd_discovery_root: Path):
        """Complete flow: .scrappy.yaml → CLIConfig → ThemeProtocol."""
        # Create config file
        config_file = cwd_discovery_root / ".scrappy.yaml"
        config_file.write_text("""
theme:
  preset: dark
  primary: "#61afef"
  accent: "#e5c07b"
  success: "#98c379"
""")
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

    def test_json_config_to_theme_protocol(self, cwd_discovery_root: Path):
        """Complete flow: .scrappy.json → CLIConfig → ThemeProtocol."""
        config_file = cwd_discovery_root / ".scrappy.json"
        config_file.write_text(json.dumps({
            "theme": {
                "preset": "light",
                "primary": "#0000ff",
                "error": "#ff0000"
            }
        }))
        config = get_config()

        assert isinstance(config.theme, CustomTheme)
        assert config.theme.primary == "#0000ff"
        assert config.theme.error == "#ff0000"
        assert config.theme.text == "#000000"  # from light preset (hex code)

    def test_no_config_file_uses_default_theme(self, cwd_discovery_root: Path):
        """When no config file exists, uses DEFAULT_THEME."""
        # Empty directory
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

    def test_theme_properties_are_accessible(self, cwd_discovery_root: Path):
        """All ThemeProtocol properties are accessible from loaded theme."""
        config_file = cwd_discovery_root / ".scrappy.yaml"
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
        assert type(theme1) is type(theme2)
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


    def test_get_config_caches_theme(self, cwd_discovery_root: Path):
        """get_config() returns same config instance on repeated calls."""
        config_file = cwd_discovery_root / ".scrappy.yaml"
        config_file.write_text("""
theme:
  preset: dark
""")
        config1 = get_config()
        config2 = get_config()

        # get_config() caches the config instance
        assert config1 is config2
        # Theme should be the same type
        assert type(config1.theme) is type(config2.theme)

    def test_get_config_reload_creates_new_theme(self, cwd_discovery_root: Path):
        """get_config(reload=True) creates new theme instance."""
        config_file = cwd_discovery_root / ".scrappy.yaml"
        config_file.write_text("""
theme:
  preset: dark
""")
        config1 = get_config()
        config2 = get_config(reload=True)

        # Different config instances
        assert config1 is not config2
        # But themes should be equivalent
        assert type(config1.theme) is type(config2.theme)


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

    def test_one_dark_pro_theme_config(self, cwd_discovery_root: Path):
        """User configures One Dark Pro theme (real-world example)."""
        config_file = cwd_discovery_root / ".scrappy.yaml"
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

    def test_minimal_theme_override(self, cwd_discovery_root: Path):
        """User overrides just one color (real-world minimal config)."""
        config_file = cwd_discovery_root / ".scrappy.yaml"
        config_file.write_text("""
theme:
  accent: "#ff00ff"
""")
        config = get_config()

        # Only accent overridden
        assert config.theme.accent == "#ff00ff"
        # Rest are defaults from ScrappyTheme
        assert config.theme.primary == "#00ffff"
        assert config.theme.success == "#00ff00"

    def test_switch_to_light_theme(self, cwd_discovery_root: Path):
        """User switches from dark to light preset (real-world scenario)."""
        config_file = cwd_discovery_root / ".scrappy.yaml"
        config_file.write_text("""
theme:
  preset: light
""")
        config = get_config()

        # Light theme loaded (hex codes)
        assert isinstance(config.theme, LightTheme)
        assert config.theme.text == "#000000"
        assert config.theme.surface == "#ffffff"
        assert config.theme.surface_alt == "#f0f0f0"

    def test_light_theme_with_custom_accent(self, cwd_discovery_root: Path):
        """User uses light theme with custom accent color."""
        config_file = cwd_discovery_root / ".scrappy.yaml"
        config_file.write_text("""
theme:
  preset: light
  accent: "#ff6600"
""")
        config = get_config()

        # Light theme with override (hex codes)
        assert isinstance(config.theme, CustomTheme)
        assert config.theme.accent == "#ff6600"
        assert config.theme.text == "#000000"  # from light preset
        assert config.theme.surface == "#ffffff"  # from light preset


class TestConfigDiscoveryPrecedence:
    """The scrappy-psjw mechanism, asserted directly rather than left implicit.

    Every test above named ``cwd_discovery_root`` depends on branch 3 of
    CLIConfigFactory.create_with_detection() being reachable. These four tests pin the
    precedence rule itself, in BOTH directions, so a future change to the launcher's
    CLI_CONFIG_PATH assignment or to config_factory's branch order fails loudly here
    rather than silently converting ten discovery tests into defaults-only tests.
    """

    SENTINEL_ACCENT = "#123456"

    def _write_cwd_config(self, directory: Path, accent: str) -> Path:
        config_file = directory / ".scrappy.yaml"
        config_file.write_text(f"theme:\n  accent: \"{accent}\"\n")
        return config_file

    def test_cwd_scan_is_reached_when_the_config_path_var_is_absent(self, cwd_discovery_root: Path):
        """Branch 3 (the Path.cwd() scan) genuinely runs. DISCOVERY COVERAGE IS PRESERVED.

        If this fails, the ten CWD-discovery tests above are no longer testing discovery.
        """
        self._write_cwd_config(cwd_discovery_root, self.SENTINEL_ACCENT)

        config = get_config()

        assert config.theme.accent == self.SENTINEL_ACCENT

    def test_config_path_var_outranks_the_cwd_scan(self, tmp_path: Path, monkeypatch):
        """Branch 2 beats branch 3. THIS IS THE CONTAINMENT PROPERTY the launcher relies on.

        The launcher assigns CLI_CONFIG_PATH precisely so a contained run cannot pick up a
        real config file the CWD scan would have found.
        """
        cwd_dir = tmp_path / "cwd"
        cwd_dir.mkdir()
        self._write_cwd_config(cwd_dir, self.SENTINEL_ACCENT)

        env_config = tmp_path / "from_env.yaml"
        env_config.write_text("theme:\n  accent: \"#abcdef\"\n")
        monkeypatch.setenv('CLI_CONFIG_PATH', str(env_config))
        monkeypatch.chdir(cwd_dir)

        config = get_config()

        assert config.theme.accent == "#abcdef"

    def test_absent_config_path_var_still_suppresses_the_cwd_scan(self, tmp_path: Path, monkeypatch):
        """The exact scrappy-psjw regression, reproduced as a permanent test.

        The launcher assigns a contained path that DOES NOT EXIST. config_factory.py:163
        gates the load on ``file_to_load.exists()``, so the load is skipped and defaults
        are returned, while branch 3 remains unreachable because branch 2 already matched.
        A caller that wants the CWD scan must remove the variable explicitly; it cannot
        rely on the assigned path being absent.
        """
        cwd_dir = tmp_path / "cwd"
        cwd_dir.mkdir()
        self._write_cwd_config(cwd_dir, self.SENTINEL_ACCENT)

        contained_absent = tmp_path / "contained-cli-config.absent.json"
        assert not contained_absent.exists()
        monkeypatch.setenv('CLI_CONFIG_PATH', str(contained_absent))
        monkeypatch.chdir(cwd_dir)

        config = get_config()

        assert config.theme.accent != self.SENTINEL_ACCENT
        assert config.theme.accent == DEFAULT_THEME.accent

    @pytest.mark.skipif(
        ".pytest_profile" not in Path.home().parts,
        reason="the launcher's assignment only exists inside scripts/contained-pytest.sh",
    )
    def test_tests_not_requesting_the_fixture_keep_the_launcher_assignment(self):
        """THE REMOVAL IS NOT GLOBAL. CONTAINMENT IS PRESERVED FOR EVERYONE ELSE.

        This test deliberately does NOT request cwd_discovery_root. Under the launcher it
        must still see the assigned CLI_CONFIG_PATH, pointing inside the contained
        profile. If the fixture were autouse, or if its teardown failed to restore, this
        fails: every other test in the suite would have regained the real-profile config
        discovery that PR-1 exists to displace.

        Asserted from the ambient environment rather than by inspecting the fixture, so it
        measures the effect rather than the intent.
        """
        assigned = os.environ.get('CLI_CONFIG_PATH')
        assert assigned, "the launcher must assign CLI_CONFIG_PATH for non-discovery tests"
        assert ".pytest_profile" in Path(assigned).parts
