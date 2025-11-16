"""
Tests for LLM provider base classes and registry.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from src.providers.base import LLMResponse, ProviderLimits, LLMProvider, ProviderRegistry


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    @pytest.mark.unit
    def test_response_creation(self):
        """Test creating a basic LLMResponse."""
        response = LLMResponse(
            content="Test content",
            model="test-model",
            provider="test-provider"
        )

        assert response.content == "Test content"
        assert response.model == "test-model"
        assert response.provider == "test-provider"
        assert response.tokens_used == 0
        assert response.input_tokens == 0
        assert response.output_tokens == 0
        assert response.latency_ms == 0.0
        assert response.raw_response is None
        assert isinstance(response.metadata, dict)
        assert isinstance(response.timestamp, datetime)

    @pytest.mark.unit
    def test_response_with_tokens(self):
        """Test response with token counts."""
        response = LLMResponse(
            content="Response",
            model="model",
            provider="provider",
            tokens_used=150,
            input_tokens=50,
            output_tokens=100
        )

        assert response.tokens_used == 150
        assert response.input_tokens == 50
        assert response.output_tokens == 100

    @pytest.mark.unit
    def test_response_with_metadata(self):
        """Test response with custom metadata."""
        metadata = {"cached": True, "retry_count": 2}
        response = LLMResponse(
            content="Test",
            model="model",
            provider="provider",
            metadata=metadata
        )

        assert response.metadata == metadata
        assert response.metadata["cached"] is True


class TestProviderLimits:
    """Tests for ProviderLimits dataclass."""

    @pytest.mark.unit
    def test_limits_creation(self):
        """Test creating provider limits."""
        limits = ProviderLimits(
            requests_per_minute=60,
            requests_per_day=10000,
            tokens_per_minute=100000
        )

        assert limits.requests_per_minute == 60
        assert limits.requests_per_day == 10000
        assert limits.tokens_per_minute == 100000
        assert limits.requests_per_month is None
        assert limits.remaining_requests is None

    @pytest.mark.unit
    def test_limits_defaults(self):
        """Test that limits default to None."""
        limits = ProviderLimits()

        assert limits.requests_per_minute is None
        assert limits.requests_per_day is None
        assert limits.requests_per_month is None
        assert limits.tokens_per_minute is None
        assert limits.tokens_per_day is None
        assert limits.remaining_requests is None
        assert limits.remaining_tokens is None


class TestProviderRegistry:
    """Tests for ProviderRegistry."""

    @pytest.fixture
    def registry(self):
        """Create an empty registry."""
        return ProviderRegistry()

    @pytest.fixture
    def mock_provider_class(self):
        """Create a mock provider class."""
        class MockProvider(LLMProvider):
            @property
            def name(self):
                return "mock"

            @property
            def available_models(self):
                return ["mock-model-1", "mock-model-2"]

            @property
            def default_model(self):
                return "mock-model-1"

            def chat(self, messages, model=None, max_tokens=1000, temperature=0.7, **kwargs):
                return LLMResponse(
                    content="Mock response",
                    model=model or self.default_model,
                    provider=self.name,
                    tokens_used=100
                )

            def get_limits(self):
                return ProviderLimits(
                    requests_per_minute=100,
                    requests_per_day=10000
                )

        return MockProvider

    @pytest.mark.unit
    def test_register_provider(self, registry, mock_provider_class):
        """Test registering a provider."""
        provider = mock_provider_class()
        registry.register(provider)

        assert "mock" in registry.list_available()
        assert registry.get("mock") is provider

    @pytest.mark.unit
    def test_get_nonexistent_provider(self, registry):
        """Test getting a provider that doesn't exist raises KeyError."""
        with pytest.raises(KeyError):
            registry.get("nonexistent")

    @pytest.mark.unit
    def test_list_available_empty(self, registry):
        """Test listing available providers when empty."""
        available = registry.list_available()
        assert isinstance(available, list)
        assert len(available) == 0

    @pytest.mark.unit
    def test_list_available_multiple(self, registry, mock_provider_class):
        """Test listing multiple providers."""
        provider1 = mock_provider_class()
        registry.register(provider1)

        # Create second mock provider with different name
        class SecondProvider(mock_provider_class):
            @property
            def name(self):
                return "second"

        provider2 = SecondProvider()
        registry.register(provider2)

        available = registry.list_available()
        assert len(available) == 2
        assert "mock" in available
        assert "second" in available

    @pytest.mark.unit
    def test_registry_stores_by_name(self, registry, mock_provider_class):
        """Test that registry uses provider name as key."""
        provider = mock_provider_class()
        registry.register(provider)

        # Verify internal storage
        assert hasattr(registry, '_providers') or hasattr(registry, 'providers')
        retrieved = registry.get("mock")
        assert retrieved.name == "mock"

    @pytest.mark.unit
    def test_provider_is_available(self, mock_provider_class):
        """Test provider availability check."""
        provider = mock_provider_class()
        assert provider.is_available() is True

    @pytest.mark.unit
    def test_provider_estimate_cost_default(self, mock_provider_class):
        """Test default cost estimation returns 0."""
        provider = mock_provider_class()
        cost = provider.estimate_cost(100, 200)
        assert cost == 0.0


class TestProviderInterface:
    """Tests for LLMProvider abstract interface compliance."""

    @pytest.mark.unit
    def test_chat_returns_llm_response(self, mock_provider):
        """Test that chat returns proper LLMResponse."""
        messages = [{"role": "user", "content": "Hello"}]
        response = mock_provider.chat(messages)

        # Mock provider returns what we configured in conftest
        assert hasattr(response, 'content')
        assert hasattr(response, 'tokens_used')

    @pytest.mark.unit
    def test_get_limits_returns_provider_limits(self, mock_provider):
        """Test that get_limits returns proper ProviderLimits."""
        limits = mock_provider.get_limits()

        assert hasattr(limits, 'requests_per_minute')
        assert hasattr(limits, 'requests_per_day')

    @pytest.mark.unit
    def test_provider_has_required_properties(self, mock_provider):
        """Test that provider has all required properties."""
        assert hasattr(mock_provider, 'name')
        assert hasattr(mock_provider, 'chat')
        assert hasattr(mock_provider, 'get_limits')
        assert hasattr(mock_provider, 'is_available')
