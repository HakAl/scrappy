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

from scrappy.task_router.provider_resolver import ProviderResolver
from scrappy.orchestrator.model_selection import ModelSelectionType


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
        provider, model = resolver.resolve(ModelSelectionType.FAST)

        assert provider is None
        assert model is None

    def test_resolve_with_orchestrator_but_no_providers_attribute(self):
        """Handle orchestrator without providers attribute."""
        orch = Mock(spec=[])  # No providers attribute
        resolver = ProviderResolver(orchestrator=orch)
        provider, model = resolver.resolve(ModelSelectionType.FAST)

        assert provider is None
        assert model is None


class TestFastHintResolution:
    """Test resolution of 'fast' hint."""

    @pytest.fixture
    def mock_orchestrator(self):
        orch = Mock()
        orch.provider_selector = Mock()
        orch.provider_selector.get_model = Mock(return_value=('cerebras', 'llama3.1-8b'))
        return orch

    def test_fast_hint_prefers_cerebras(self, mock_orchestrator):
        """Fast hint should prefer cerebras when available."""
        mock_orchestrator.provider_selector.get_model.return_value = ('cerebras', 'llama3.1-8b')

        resolver = ProviderResolver(orchestrator=mock_orchestrator)
        provider, model = resolver.resolve(ModelSelectionType.FAST)

        assert provider == 'cerebras'
        assert model == 'llama3.1-8b'

    def test_fast_hint_falls_back_to_groq(self, mock_orchestrator):
        """Fast hint should use groq when cerebras unavailable."""
        mock_orchestrator.provider_selector.get_model.return_value = ('groq', 'llama-3.3-70b')

        resolver = ProviderResolver(orchestrator=mock_orchestrator)
        provider, model = resolver.resolve(ModelSelectionType.FAST)

        assert provider == 'groq'
        assert model == 'llama-3.3-70b'

    def test_fast_hint_falls_back_to_gemini(self, mock_orchestrator):
        """Fast hint should use gemini when only option."""
        mock_orchestrator.provider_selector.get_model.return_value = ('gemini', 'gemini-2.0-flash-lite')

        resolver = ProviderResolver(orchestrator=mock_orchestrator)
        provider, model = resolver.resolve(ModelSelectionType.FAST)

        assert provider == 'gemini'
        assert model == 'gemini-2.0-flash-lite'

    def test_fast_hint_with_no_available_providers(self, mock_orchestrator):
        """Fast hint returns None when no providers available."""
        mock_orchestrator.provider_selector.get_model.side_effect = RuntimeError("No providers available")

        resolver = ProviderResolver(orchestrator=mock_orchestrator)
        provider, model = resolver.resolve(ModelSelectionType.FAST)

        assert provider is None
        assert model is None

    def test_fast_hint_with_unknown_providers(self, mock_orchestrator):
        """Fast hint returns None when only unknown providers available."""
        mock_orchestrator.provider_selector.get_model.return_value = (None, None)

        resolver = ProviderResolver(orchestrator=mock_orchestrator)
        provider, model = resolver.resolve(ModelSelectionType.FAST)

        assert provider is None
        assert model is None


class TestQualityHintResolution:
    """Test resolution of 'quality' hint."""

    @pytest.fixture
    def mock_orchestrator(self):
        orch = Mock()
        orch.provider_selector = Mock()
        orch.provider_selector.get_model = Mock(return_value=('cerebras', 'llama-3.3-70b'))
        return orch

    def test_quality_hint_falls_back_to_gemini(self, mock_orchestrator):
        """Quality hint should use gemini as last resort."""
        mock_orchestrator.provider_selector.get_model.return_value = ('gemini', 'gemini-2.5-flash')

        resolver = ProviderResolver(orchestrator=mock_orchestrator)
        provider, model = resolver.resolve(ModelSelectionType.QUALITY)

        assert provider == 'gemini'
        assert model == 'gemini-2.5-flash'

    def test_quality_hint_with_no_available_providers(self, mock_orchestrator):
        """Quality hint returns None when no providers available."""
        mock_orchestrator.provider_selector.get_model.side_effect = RuntimeError("No providers available")

        resolver = ProviderResolver(orchestrator=mock_orchestrator)
        provider, model = resolver.resolve(ModelSelectionType.QUALITY)

        assert provider is None
        assert model is None

class TestUnknownHints:
    """Test behavior with unknown or invalid hints."""

    @pytest.fixture
    def mock_orchestrator(self):
        orch = Mock()
        orch.provider_selector = Mock()
        orch.provider_selector.get_model = Mock(return_value=('cerebras', 'llama3.1-8b'))
        return orch

    def test_invalid_hint_type_returns_none(self, mock_orchestrator):
        """Non-enum hint should be handled gracefully."""
        # If we pass a string that's not an enum, it should fail gracefully
        mock_orchestrator.provider_selector.get_model.side_effect = AttributeError("not a valid ModelSelectionType")

        resolver = ProviderResolver(orchestrator=mock_orchestrator)
        provider, model = resolver.resolve("string_not_enum")  # Invalid type

        assert provider is None
        assert model is None


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_handles_list_available_exception(self):
        """Handle exception when getting model."""
        orch = Mock()
        orch.provider_selector = Mock()
        orch.provider_selector.get_model.side_effect = RuntimeError("Provider error")

        resolver = ProviderResolver(orchestrator=orch)
        provider, model = resolver.resolve(ModelSelectionType.FAST)

        # Should handle exception gracefully
        assert provider is None
        assert model is None

    def test_handles_missing_providers_method(self):
        """Handle orchestrator without provider_selector attribute."""
        orch = Mock(spec=[])  # No provider_selector attribute

        resolver = ProviderResolver(orchestrator=orch)
        provider, model = resolver.resolve(ModelSelectionType.FAST)

        assert provider is None
        assert model is None


class TestResolverReusability:
    """Test that resolver can be reused for multiple resolutions."""

    @pytest.fixture
    def mock_orchestrator(self):
        orch = Mock()
        orch.provider_selector = Mock()
        return orch

    def test_resolver_can_be_reused(self, mock_orchestrator):
        """Same resolver instance can resolve multiple hints."""
        # Set up different return values for different calls
        mock_orchestrator.provider_selector.get_model.side_effect = [
            ('cerebras', 'llama3.1-8b'),  # First call for FAST
            ('cerebras', 'llama-3.3-70b'),  # Second call for QUALITY
        ]

        resolver = ProviderResolver(orchestrator=mock_orchestrator)

        # Resolve multiple hints
        fast_provider, fast_model = resolver.resolve(ModelSelectionType.FAST)
        quality_provider, quality_model = resolver.resolve(ModelSelectionType.QUALITY)

        assert fast_provider == 'cerebras'
        assert quality_provider == 'cerebras'
        assert quality_model == 'llama-3.3-70b'

    def test_resolver_handles_changing_provider_availability(self, mock_orchestrator):
        """Resolver adapts to changing provider availability."""
        # Set up different return values for different calls
        mock_orchestrator.provider_selector.get_model.side_effect = [
            ('cerebras', 'llama3.1-8b'),  # First call
            ('groq', 'llama-3.3-70b-versatile'),  # Second call
        ]

        resolver = ProviderResolver(orchestrator=mock_orchestrator)

        # First resolution with cerebras available
        provider1, _ = resolver.resolve(ModelSelectionType.FAST)
        assert provider1 == 'cerebras'

        # Second resolution with only groq available
        provider2, _ = resolver.resolve(ModelSelectionType.FAST)
        assert provider2 == 'groq'
