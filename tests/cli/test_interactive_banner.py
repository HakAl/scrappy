"""
Tests for interactive banner display.

Tests the ASCII art banner with provider status and workspace display.
"""

from pathlib import Path
from unittest.mock import Mock

from scrappy.cli.interactive_banner import (
    BANNER_ART,
    _get_configured_provider_names,
    display_banner,
)
from scrappy.infrastructure.paths import TempPathProvider


class MockApiKeyService:
    """Mock API key service for testing."""

    def __init__(self, configured_keys: dict[str, str] | None = None):
        self._keys = configured_keys or {}

    def get_key(self, key_name: str) -> str | None:
        return self._keys.get(key_name)


class MockOutputSink:
    """Mock OutputSink for testing banner output in TUI mode."""

    def __init__(self):
        self.renderables: list[str] = []

    def post_output(self, content: str) -> None:
        self.renderables.append(content)

    def post_renderable(self, obj) -> None:
        # Convert renderable to string for testing
        self.renderables.append(str(obj))


class MockIO:
    """Mock IO for testing banner output."""

    def __init__(self, use_output_sink: bool = True):
        self.console_prints: list[str] = []
        self.echo_calls: list[str] = []
        self._console = Mock()
        self._console.print = lambda text: self.console_prints.append(str(text))
        self._output_sink = MockOutputSink() if use_output_sink else None

    @property
    def console(self):
        return self._console

    @property
    def output_sink(self):
        return self._output_sink

    def echo(self, text: str = "") -> None:
        self.echo_calls.append(text)

    def get_all_output(self) -> str:
        """Get all output as a single string."""
        if self._output_sink:
            return " ".join(self._output_sink.renderables)
        return " ".join(self.console_prints)


class TestBannerArt:
    """Tests for banner art constant."""

    def test_banner_contains_version_placeholder(self):
        """Banner art should contain {version} placeholder."""
        assert "{version}" in BANNER_ART

    def test_banner_contains_welcome_text(self):
        """Banner art should contain 'Welcome to' text."""
        assert "Welcome to" in BANNER_ART

    def test_banner_contains_scrappy_letters(self):
        """Banner art should contain SCRAPPY in block letters."""
        # Check for distinctive characters from the ASCII art
        assert "███████" in BANNER_ART
        assert "╚══════" in BANNER_ART


class TestGetConfiguredProviderNames:
    """Tests for _get_configured_provider_names helper."""

    def test_returns_empty_list_when_no_keys(self):
        """Should return empty list when no API keys configured."""
        service = MockApiKeyService()
        providers = _get_configured_provider_names(service)
        assert providers == []

    def test_returns_groq_when_groq_key_set(self):
        """Should return Groq when GROQ_API_KEY is set."""
        service = MockApiKeyService({"GROQ_API_KEY": "test-key"})
        providers = _get_configured_provider_names(service)
        assert "Groq" in providers

    def test_returns_cerebras_when_cerebras_key_set(self):
        """Should return Cerebras when CEREBRAS_API_KEY is set."""
        service = MockApiKeyService({"CEREBRAS_API_KEY": "test-key"})
        providers = _get_configured_provider_names(service)
        assert "Cerebras" in providers

    def test_returns_multiple_providers(self):
        """Should return multiple providers when multiple keys set."""
        service = MockApiKeyService({
            "GROQ_API_KEY": "key1",
            "CEREBRAS_API_KEY": "key2",
        })
        providers = _get_configured_provider_names(service)
        assert len(providers) >= 2
        assert "Groq" in providers
        assert "Cerebras" in providers

    def test_capitalizes_provider_names(self):
        """Should capitalize provider names."""
        service = MockApiKeyService({"GROQ_API_KEY": "test-key"})
        providers = _get_configured_provider_names(service)
        # Provider names should be capitalized
        for provider in providers:
            assert provider[0].isupper()


class TestDisplayBanner:
    """Tests for display_banner function."""

    def test_displays_ascii_art(self, tmp_path: Path):
        """Banner should display ASCII art."""
        io = MockIO()
        path_provider = TempPathProvider(tmp_path)
        api_service = MockApiKeyService()

        display_banner(io, api_key_service=api_service, path_provider=path_provider)

        all_output = io.get_all_output()
        assert "Welcome to" in all_output

    def test_displays_version(self, tmp_path: Path):
        """Banner should display version number."""
        from scrappy import __version__

        io = MockIO()
        path_provider = TempPathProvider(tmp_path)
        api_service = MockApiKeyService()

        display_banner(io, api_key_service=api_service, path_provider=path_provider)

        all_output = io.get_all_output()
        assert __version__ in all_output

    def test_displays_workspace(self, tmp_path: Path):
        """Banner should display workspace path."""
        io = MockIO()
        path_provider = TempPathProvider(tmp_path)
        api_service = MockApiKeyService()

        display_banner(io, api_key_service=api_service, path_provider=path_provider)

        all_output = io.get_all_output()
        assert "Workspace" in all_output

    def test_displays_no_providers_message_when_none_configured(self, tmp_path: Path):
        """Banner should show setup message when no providers configured."""
        io = MockIO()
        path_provider = TempPathProvider(tmp_path)
        api_service = MockApiKeyService()  # No keys

        display_banner(io, api_key_service=api_service, path_provider=path_provider)

        all_output = io.get_all_output()
        assert "No providers configured" in all_output
        assert "/setup" in all_output

    def test_displays_provider_list_when_configured(self, tmp_path: Path):
        """Banner should show provider names when keys are configured."""
        io = MockIO()
        path_provider = TempPathProvider(tmp_path)
        api_service = MockApiKeyService({"GROQ_API_KEY": "test-key"})

        display_banner(io, api_key_service=api_service, path_provider=path_provider)

        all_output = io.get_all_output()
        assert "Providers" in all_output
        assert "Groq" in all_output

    def test_displays_help_hint(self, tmp_path: Path):
        """Banner should show /help hint."""
        io = MockIO()
        path_provider = TempPathProvider(tmp_path)
        api_service = MockApiKeyService()

        display_banner(io, api_key_service=api_service, path_provider=path_provider)

        all_output = io.get_all_output()
        assert "/help" in all_output

    def test_uses_default_dependencies_when_none_provided(self):
        """Banner should create default dependencies when none provided."""
        io = MockIO()

        # Should not raise - will use defaults
        # Note: This may show real configured providers from environment
        display_banner(io)

        # At minimum, workspace should be shown
        all_output = io.get_all_output()
        assert "Workspace" in all_output

    def test_works_in_cli_mode_without_output_sink(self, tmp_path: Path):
        """Banner should work when no output_sink (CLI mode)."""
        io = MockIO(use_output_sink=False)
        path_provider = TempPathProvider(tmp_path)
        api_service = MockApiKeyService()

        display_banner(io, api_key_service=api_service, path_provider=path_provider)

        # In CLI mode, output goes to console.print
        all_output = io.get_all_output()
        assert "Welcome to" in all_output
