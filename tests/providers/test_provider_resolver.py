"""
Tests for ProviderResolver utility.

Tests provider hint resolution to actual provider names and models:
- Hint types: fast, quality, high_volume, general
- Provider priority: cerebras > groq > gemini
- Fallback behavior when providers unavailable
- ProviderSelector integration
"""

import pytest
from unittest.mock import Mock

from src.task_router.provider_resolver import ProviderResolver


class TestProviderResolverBasics:
    """Test basic provider resolution functionality."""

    def test_resolve_with_no_hint_returns_none(self):
        """Return None when no hint provided."""
        resolver = ProviderResolver(orchestrator=None)
        provider, model = resolver.resolve(None)

        assert provider is None
        assert model is None

    def test_resolve_with_empty_hint_returns_none(self):
        """Return None when empty string hint provided."""
        resolver = ProviderResolver(orchestrator=None)
        provider, model = resolver.resolve("")

        assert provider is None
        assert model is None

    def test_resolve_without_orchestrator_returns_none(self):
        """Return None when no orchestrator provided."""
        resolver = ProviderResolver(orchestrator=None)
        provider, model = resolver.resolve("fast")

        assert provider is None
        assert model is None

    def test_resolve_with_orchestrator_but_no_providers_attribute(self):
        """Handle orchestrator without providers attribute."""
        orch = Mock(spec=[])  # No providers attribute
        resolver = ProviderResolver(orchestrator=orch)
        provider, model = resolver.resolve("fast")

        assert provider is None
        assert model is None


class TestFastHintResolution:
    """Test resolution of 'fast' hint."""

    @pytest.fixture
    def mock_orchestrator(self):
        orch = Mock()
        orch.providers = Mock()
        return orch

    def test_fast_hint_prefers_cerebras(self, mock_orchestrator):
        """Fast hint should prefer cerebras when available."""
        mock_orchestrator.providers.list_available.return_value = ['groq', 'cerebras', 'gemini']

        resolver = ProviderResolver(orchestrator=mock_orchestrator, use_provider_selector=False)
        provider, model = resolver.resolve("fast")

        assert provider == 'cerebras'
        assert model is None

    def test_fast_hint_falls_back_to_groq(self, mock_orchestrator):
        """Fast hint should use groq when cerebras unavailable."""
        mock_orchestrator.providers.list_available.return_value = ['groq', 'gemini']

        resolver = ProviderResolver(orchestrator=mock_orchestrator, use_provider_selector=False)
        provider, model = resolver.resolve("fast")

        assert provider == 'groq'
        assert model is None

    def test_fast_hint_falls_back_to_gemini(self, mock_orchestrator):
        """Fast hint should use gemini when only option."""
        mock_orchestrator.providers.list_available.return_value = ['gemini']

        resolver = ProviderResolver(orchestrator=mock_orchestrator)
        provider, model = resolver.resolve("fast")

        assert provider == 'gemini'
        assert model is None

    def test_fast_hint_with_no_available_providers(self, mock_orchestrator):
        """Fast hint returns None when no providers available."""
        mock_orchestrator.providers.list_available.return_value = []

        resolver = ProviderResolver(orchestrator=mock_orchestrator)
        provider, model = resolver.resolve("fast")

        assert provider is None
        assert model is None

    def test_fast_hint_with_unknown_providers(self, mock_orchestrator):
        """Fast hint returns None when only unknown providers available."""
        mock_orchestrator.providers.list_available.return_value = ['unknown', 'other']

        resolver = ProviderResolver(orchestrator=mock_orchestrator, use_provider_selector=False)
        provider, model = resolver.resolve("fast")

        assert provider is None
        assert model is None


class TestQualityHintResolution:
    """Test resolution of 'quality' hint."""

    @pytest.fixture
    def mock_orchestrator(self):
        orch = Mock()
        orch.providers = Mock()
        return orch

    def test_quality_hint_falls_back_to_gemini(self, mock_orchestrator):
        """Quality hint should use gemini as last resort."""
        mock_orchestrator.providers.list_available.return_value = ['gemini']

        resolver = ProviderResolver(orchestrator=mock_orchestrator)
        provider, model = resolver.resolve("quality")

        assert provider == 'gemini'
        assert model is None

    def test_quality_hint_with_no_available_providers(self, mock_orchestrator):
        """Quality hint returns None when no providers available."""
        mock_orchestrator.providers.list_available.return_value = []

        resolver = ProviderResolver(orchestrator=mock_orchestrator)
        provider, model = resolver.resolve("quality")

        assert provider is None
        assert model is None

class TestUnknownHints:
    """Test behavior with unknown or invalid hints."""

    @pytest.fixture
    def mock_orchestrator(self):
        orch = Mock()
        orch.providers = Mock()
        orch.providers.list_available.return_value = ['cerebras', 'groq']
        return orch

    def test_unknown_hint_returns_none(self, mock_orchestrator):
        """Unknown hint should return None."""
        resolver = ProviderResolver(orchestrator=mock_orchestrator, use_provider_selector=False)
        provider, model = resolver.resolve("unknown_hint")

        assert provider is None
        assert model is None

    def test_invalid_hint_type_returns_none(self, mock_orchestrator):
        """Non-string hint should be handled gracefully."""
        resolver = ProviderResolver(orchestrator=mock_orchestrator)
        provider, model = resolver.resolve(123)  # Invalid type

        assert provider is None
        assert model is None


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_handles_list_available_exception(self):
        """Handle exception when listing available providers."""
        orch = Mock()
        orch.providers = Mock()
        orch.providers.list_available.side_effect = Exception("Provider error")

        resolver = ProviderResolver(orchestrator=orch)
        provider, model = resolver.resolve("fast")

        # Should handle exception gracefully
        assert provider is None
        assert model is None

    def test_handles_missing_providers_method(self):
        """Handle orchestrator without list_available method."""
        orch = Mock()
        orch.providers = Mock(spec=[])  # No list_available method

        resolver = ProviderResolver(orchestrator=orch)
        provider, model = resolver.resolve("fast")

        assert provider is None
        assert model is None


class TestResolverReusability:
    """Test that resolver can be reused for multiple resolutions."""

    @pytest.fixture
    def mock_orchestrator(self):
        orch = Mock()
        orch.providers = Mock()
        orch.providers.list_available.return_value = ['cerebras', 'groq', 'gemini']
        return orch

    def test_resolver_can_be_reused(self, mock_orchestrator):
        """Same resolver instance can resolve multiple hints."""
        resolver = ProviderResolver(orchestrator=mock_orchestrator)

        # Resolve multiple hints
        fast_provider, _ = resolver.resolve("fast")
        quality_provider, quality_model = resolver.resolve("quality")
        general_provider, _ = resolver.resolve("general")

        assert fast_provider == 'cerebras'
        assert quality_provider == 'cerebras'
        assert quality_model == 'llama-3.3-70b'
        assert general_provider == 'cerebras'

    def test_resolver_handles_changing_provider_availability(self, mock_orchestrator):
        """Resolver adapts to changing provider availability."""
        resolver = ProviderResolver(orchestrator=mock_orchestrator)

        # First resolution with cerebras available
        mock_orchestrator.providers.list_available.return_value = ['cerebras', 'groq']
        provider1, _ = resolver.resolve("fast")
        assert provider1 == 'cerebras'

        # Second resolution with only groq available
        mock_orchestrator.providers.list_available.return_value = ['groq']
        provider2, _ = resolver.resolve("fast")
        assert provider2 == 'groq'
