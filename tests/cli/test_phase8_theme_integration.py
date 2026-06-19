"""
Tests for Phase 8: Theme integration at app startup.

Verifies that:
- CLIConfig loads and exposes theme from config files
- CLI factory functions pass theme to components
- Theme flows from config through to CLI components
"""

from unittest.mock import MagicMock, patch

from scrappy.cli.cli_config import CLIConfig
from scrappy.infrastructure.persistence import ConversationStoreProtocol
from scrappy.infrastructure.theme import (
    ScrappyTheme,
    LightTheme,
    CustomTheme,
    DEFAULT_THEME,
)


class TestCLIConfigTheme:
    """Tests for CLIConfig theme property."""

    def test_default_config_has_scrappy_theme(self):
        """Default CLIConfig should use ScrappyTheme."""
        config = CLIConfig()
        assert isinstance(config.theme, ScrappyTheme)

    def test_empty_theme_config_uses_default(self):
        """Empty theme_config dict should fall back to default theme."""
        config = CLIConfig(theme_config={})
        assert isinstance(config.theme, ScrappyTheme)

    def test_dark_preset_uses_scrappy_theme(self):
        """preset: dark should use ScrappyTheme."""
        config = CLIConfig(theme_config={"preset": "dark"})
        assert isinstance(config.theme, ScrappyTheme)

    def test_light_preset_uses_light_theme(self):
        """preset: light should use LightTheme."""
        config = CLIConfig(theme_config={"preset": "light"})
        assert isinstance(config.theme, LightTheme)

    def test_invalid_preset_falls_back_to_dark(self):
        """Invalid preset should fall back to ScrappyTheme."""
        config = CLIConfig(theme_config={"preset": "invalid"})
        assert isinstance(config.theme, ScrappyTheme)

    def test_color_override_creates_custom_theme(self):
        """Color overrides should create CustomTheme."""
        config = CLIConfig(theme_config={"primary": "magenta"})
        assert isinstance(config.theme, CustomTheme)
        assert config.theme.primary == "magenta"

    def test_theme_is_cached(self):
        """Theme property should be cached after first access."""
        config = CLIConfig(theme_config={"preset": "dark"})
        theme1 = config.theme
        theme2 = config.theme
        assert theme1 is theme2

    def test_theme_config_preserved_in_to_dict(self):
        """to_dict should preserve theme config under 'theme' key."""
        config = CLIConfig(theme_config={"preset": "light", "primary": "cyan"})
        d = config.to_dict()
        assert "theme" in d
        assert d["theme"]["preset"] == "light"
        assert d["theme"]["primary"] == "cyan"

    def test_theme_config_not_include_cached_theme(self):
        """to_dict should not include _theme field."""
        config = CLIConfig(theme_config={"preset": "dark"})
        _ = config.theme  # Access to populate cache
        d = config.to_dict()
        assert "_theme" not in d


class TestCLIConfigFromDict:
    """Tests for CLIConfig.from_dict with theme."""

    def test_from_dict_maps_theme_to_theme_config(self):
        """from_dict should map 'theme' key to theme_config field."""
        data = {"theme": {"preset": "light"}}
        config = CLIConfig.from_dict(data)
        assert config.theme_config == {"preset": "light"}
        assert isinstance(config.theme, LightTheme)

    def test_from_dict_with_theme_override(self):
        """from_dict should handle theme color overrides."""
        data = {"theme": {"preset": "dark", "accent": "orange"}}
        config = CLIConfig.from_dict(data)
        assert isinstance(config.theme, CustomTheme)
        assert config.theme.accent == "orange"

    def test_from_dict_without_theme(self):
        """from_dict without theme should use default."""
        data = {"temperature_default": 0.8}
        config = CLIConfig.from_dict(data)
        assert isinstance(config.theme, ScrappyTheme)

    def test_from_dict_preserves_theme_config_on_round_trip(self):
        """Theme config should survive to_dict -> from_dict round trip."""
        original = CLIConfig.from_dict({"theme": {"preset": "light", "error": "pink"}})
        restored = CLIConfig.from_dict(original.to_dict())
        assert restored.theme_config == {"preset": "light", "error": "pink"}


class TestCLIConfigMerge:
    """Tests for CLIConfig.merge with theme."""

    def test_merge_preserves_theme_when_other_has_empty_dict(self):
        """Merge should not overwrite theme with empty dict."""
        file_config = CLIConfig(theme_config={"preset": "light"})
        env_config = CLIConfig(theme_config={})
        merged = file_config.merge(env_config)
        assert merged.theme_config == {"preset": "light"}
        assert isinstance(merged.theme, LightTheme)

    def test_merge_overwrites_theme_when_other_has_value(self):
        """Merge should overwrite theme when other has a value."""
        file_config = CLIConfig(theme_config={"preset": "dark"})
        override_config = CLIConfig(theme_config={"preset": "light"})
        merged = file_config.merge(override_config)
        assert merged.theme_config == {"preset": "light"}
        assert isinstance(merged.theme, LightTheme)

    def test_merge_from_default_to_file_config(self):
        """Merge default config with file config should use file theme."""
        default = CLIConfig()
        file_config = CLIConfig(theme_config={"preset": "light", "primary": "blue"})
        merged = default.merge(file_config)
        assert merged.theme_config == {"preset": "light", "primary": "blue"}

    def test_merge_chain_preserves_theme(self):
        """Chained merges should preserve theme through empty configs."""
        base = CLIConfig(theme_config={"preset": "light"})
        empty1 = CLIConfig(theme_config={})
        empty2 = CLIConfig(theme_config={})
        result = base.merge(empty1).merge(empty2)
        assert result.theme_config == {"preset": "light"}


class TestCLIFactoryTheme:
    """Tests for CLI factory functions with theme."""

    def test_get_io_interface_returns_io_with_existing_io(self):
        """get_io_interface should return existing IO if provided."""
        from scrappy.cli.utils.cli_factory import get_io_interface

        existing_io = MagicMock()
        result = get_io_interface(io=existing_io, theme=CustomTheme())
        assert result is existing_io

    def test_get_io_interface_returns_test_io_in_test_mode(self):
        """get_io_interface in test_mode should return TestIO."""
        from scrappy.cli.utils.cli_factory import get_io_interface
        from scrappy.cli.io_interface import TestIO

        result = get_io_interface(test_mode=True)
        assert isinstance(result, TestIO)



class TestCLICoreTheme:
    """Tests for CLI core class with theme."""

    def _mock_handlers(self):
        """Create a dict of mock handlers for CLI initialization."""
        return {
            "display": MagicMock(),
            "session_mgr": MagicMock(),
            "codebase": MagicMock(),
            "tasks": MagicMock(),
            "multiprovider": MagicMock(),
            "smart": MagicMock(),
            "agent_mgr": MagicMock(),
        }

    def _mock_store(self):
        """Conversation store double that loads no history (no filesystem I/O)."""
        store = MagicMock(spec=ConversationStoreProtocol)
        store.get_recent.return_value = []
        return store

    def test_cli_stores_theme(self):
        """CLI should store the theme."""
        from scrappy.cli.core import CLI

        theme = CustomTheme(primary="magenta")

        with patch.object(CLI, "_create_default_orchestrator") as mock_orch:
            mock_orch.return_value = MagicMock()
            with patch.object(CLI, "_create_default_io") as mock_io:
                mock_io.return_value = MagicMock()
                with patch("scrappy.cli.core.initialize_cli_handlers", return_value=self._mock_handlers()):
                    cli = CLI(theme=theme, conversation_store=self._mock_store())
                    assert cli._theme is theme

    def test_cli_uses_default_theme(self):
        """CLI without theme should use DEFAULT_THEME."""
        from scrappy.cli.core import CLI

        with patch.object(CLI, "_create_default_orchestrator") as mock_orch:
            mock_orch.return_value = MagicMock()
            with patch.object(CLI, "_create_default_io") as mock_io:
                mock_io.return_value = MagicMock()
                with patch("scrappy.cli.core.initialize_cli_handlers", return_value=self._mock_handlers()):
                    cli = CLI(conversation_store=self._mock_store())
                    assert cli._theme is DEFAULT_THEME

    def test_injected_conversation_store_skips_default_io(self):
        """Injecting a store bypasses create_conversation_store, so __init__ does no
        filesystem I/O.

        Regression guard for scrappy-g5mx: with a mocked orchestrator and the default
        store path, the constructor wrote .scrappy/config.json to a Mock-derived path,
        leaking junk files into CWD. The injectable seam must short-circuit that.
        """
        from scrappy.cli.core import CLI

        with patch.object(CLI, "_create_default_orchestrator") as mock_orch:
            mock_orch.return_value = MagicMock()
            with patch.object(CLI, "_create_default_io") as mock_io:
                mock_io.return_value = MagicMock()
                with patch("scrappy.cli.core.initialize_cli_handlers", return_value=self._mock_handlers()):
                    with patch("scrappy.cli.core.create_conversation_store") as mock_create:
                        # Benign return so a regression (unconditional create) still
                        # constructs cleanly and fails at the assertion below, not via
                        # an incidental error in history loading.
                        mock_create.return_value = self._mock_store()
                        CLI(conversation_store=self._mock_store())
                        mock_create.assert_not_called()



class TestCreateCliFromContext:
    """Tests for create_cli_from_context with theme."""

    def test_passes_theme_to_cli(self):
        """create_cli_from_context should pass theme to CLI."""
        from scrappy.cli.utils.cli_factory import create_cli_from_context
        from scrappy.cli.core import CLI

        ctx = MagicMock()
        ctx.obj = {}
        theme = CustomTheme(primary="blue")

        with patch.object(CLI, "__init__", return_value=None) as mock_init:
            with patch.object(CLI, "initialize"):
                create_cli_from_context(ctx, theme=theme)
                mock_init.assert_called_once()
                call_kwargs = mock_init.call_args.kwargs
                assert call_kwargs.get("theme") is theme

    def test_uses_default_theme_when_not_provided(self):
        """create_cli_from_context without theme should use DEFAULT_THEME."""
        from scrappy.cli.utils.cli_factory import create_cli_from_context
        from scrappy.cli.core import CLI

        ctx = MagicMock()
        ctx.obj = {}

        with patch.object(CLI, "__init__", return_value=None) as mock_init:
            with patch.object(CLI, "initialize"):
                create_cli_from_context(ctx)
                mock_init.assert_called_once()
                call_kwargs = mock_init.call_args.kwargs
                assert call_kwargs.get("theme") is DEFAULT_THEME


class TestCreateCli:
    """Tests for create_cli helper with theme."""

    def test_passes_theme_to_cli(self):
        """create_cli should pass theme to CLI."""
        from scrappy.cli.utils.cli_factory import create_cli
        from scrappy.cli.core import CLI

        theme = LightTheme()

        with patch.object(CLI, "__init__", return_value=None) as mock_init:
            with patch.object(CLI, "initialize"):
                create_cli({}, theme=theme)
                mock_init.assert_called_once()
                call_kwargs = mock_init.call_args.kwargs
                assert call_kwargs.get("theme") is theme

    def test_uses_default_theme_when_not_provided(self):
        """create_cli without theme should use DEFAULT_THEME."""
        from scrappy.cli.utils.cli_factory import create_cli
        from scrappy.cli.core import CLI

        with patch.object(CLI, "__init__", return_value=None) as mock_init:
            with patch.object(CLI, "initialize"):
                create_cli({})
                mock_init.assert_called_once()
                call_kwargs = mock_init.call_args.kwargs
                assert call_kwargs.get("theme") is DEFAULT_THEME


class TestThemeProtocolCompliance:
    """Verify all theme implementations satisfy ThemeProtocol."""

