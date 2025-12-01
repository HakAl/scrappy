"""Provider protocol conformance tests.

Tests that LLM provider implementations correctly conform to LLMProviderProtocol.
"""

import pytest

from tests.protocol_conformance.conftest import (
    assert_implements_protocol,
    assert_has_method,
    assert_has_property,
)

from scrappy.providers.base import LLMProviderProtocol, LLMProviderBase


class TestLLMProviderProtocolDefinition:
    """Tests for the LLMProviderProtocol itself."""

    def test_protocol_has_name_property(self):
        """Protocol should define name property."""
        assert_has_property(LLMProviderProtocol, 'name')

    def test_protocol_has_available_models_property(self):
        """Protocol should define available_models property."""
        assert_has_property(LLMProviderProtocol, 'available_models')

    def test_protocol_has_default_model_property(self):
        """Protocol should define default_model property."""
        assert_has_property(LLMProviderProtocol, 'default_model')

    def test_protocol_has_chat_method(self):
        """Protocol should define chat method."""
        assert_has_method(LLMProviderProtocol, 'chat')

    def test_protocol_has_get_limits_method(self):
        """Protocol should define get_limits method."""
        assert_has_method(LLMProviderProtocol, 'get_limits')


class TestLLMProviderBaseConformance:
    """Tests for LLMProviderBase implementation."""

    def test_base_implements_protocol(self):
        """LLMProviderBase should implement LLMProviderProtocol."""
        assert_implements_protocol(LLMProviderBase, LLMProviderProtocol)

    def test_base_has_async_chat(self):
        """LLMProviderBase should have chat_async method (utility)."""
        assert_has_method(LLMProviderBase, 'chat_async')

    def test_base_has_is_available(self):
        """LLMProviderBase should have is_available method (utility)."""
        assert_has_method(LLMProviderBase, 'is_available')


class TestGroqProviderConformance:
    """Tests for GroqProvider implementation."""

    @pytest.fixture
    def provider_class(self):
        """Get GroqProvider class."""
        from scrappy.providers.groq_provider import GroqProvider
        return GroqProvider

    def test_groq_implements_protocol(self, provider_class):
        """GroqProvider should implement LLMProviderProtocol."""
        assert_implements_protocol(provider_class, LLMProviderProtocol)

    def test_groq_has_name(self, provider_class):
        """GroqProvider should have name property."""
        assert_has_property(provider_class, 'name')

    def test_groq_has_available_models(self, provider_class):
        """GroqProvider should have available_models property."""
        assert_has_property(provider_class, 'available_models')

    def test_groq_has_default_model(self, provider_class):
        """GroqProvider should have default_model property."""
        assert_has_property(provider_class, 'default_model')

    def test_groq_has_chat(self, provider_class):
        """GroqProvider should have chat method."""
        assert_has_method(provider_class, 'chat')

    def test_groq_has_get_limits(self, provider_class):
        """GroqProvider should have get_limits method."""
        assert_has_method(provider_class, 'get_limits')


class TestCerebrasProviderConformance:
    """Tests for CerebrasProvider implementation."""

    @pytest.fixture
    def provider_class(self):
        """Get CerebrasProvider class."""
        from scrappy.providers.cerebras_provider import CerebrasProvider
        return CerebrasProvider

    def test_cerebras_implements_protocol(self, provider_class):
        """CerebrasProvider should implement LLMProviderProtocol."""
        assert_implements_protocol(provider_class, LLMProviderProtocol)

    def test_cerebras_has_name(self, provider_class):
        """CerebrasProvider should have name property."""
        assert_has_property(provider_class, 'name')

    def test_cerebras_has_chat(self, provider_class):
        """CerebrasProvider should have chat method."""
        assert_has_method(provider_class, 'chat')


class TestCohereProviderConformance:
    """Tests for CohereProvider implementation."""

    @pytest.fixture
    def provider_class(self):
        """Get CohereProvider class."""
        from scrappy.providers.cohere_provider import CohereProvider
        return CohereProvider

    def test_cohere_implements_protocol(self, provider_class):
        """CohereProvider should implement LLMProviderProtocol."""
        assert_implements_protocol(provider_class, LLMProviderProtocol)

    def test_cohere_has_name(self, provider_class):
        """CohereProvider should have name property."""
        assert_has_property(provider_class, 'name')

    def test_cohere_has_chat(self, provider_class):
        """CohereProvider should have chat method."""
        assert_has_method(provider_class, 'chat')


class TestGeminiProviderConformance:
    """Tests for GeminiProvider implementation."""

    @pytest.fixture
    def provider_class(self):
        """Get GeminiProvider class."""
        from scrappy.providers.gemini_provider import GeminiProvider
        return GeminiProvider

    def test_gemini_implements_protocol(self, provider_class):
        """GeminiProvider should implement LLMProviderProtocol."""
        assert_implements_protocol(provider_class, LLMProviderProtocol)

    def test_gemini_has_name(self, provider_class):
        """GeminiProvider should have name property."""
        assert_has_property(provider_class, 'name')

    def test_gemini_has_chat(self, provider_class):
        """GeminiProvider should have chat method."""
        assert_has_method(provider_class, 'chat')


class TestGitHubModelsProviderConformance:
    """Tests for GitHubModelsProvider implementation."""

    @pytest.fixture
    def provider_class(self):
        """Get GitHubModelsProvider class."""
        from scrappy.providers.github_models_provider import GitHubModelsProvider
        return GitHubModelsProvider

    def test_github_implements_protocol(self, provider_class):
        """GitHubModelsProvider should implement LLMProviderProtocol."""
        assert_implements_protocol(provider_class, LLMProviderProtocol)

    def test_github_has_name(self, provider_class):
        """GitHubModelsProvider should have name property."""
        assert_has_property(provider_class, 'name')

    def test_github_has_chat(self, provider_class):
        """GitHubModelsProvider should have chat method."""
        assert_has_method(provider_class, 'chat')


@pytest.mark.skip(reason="ProviderRegistry doesn't exist as a separate module")
class TestProviderRegistryConformance:
    """Tests for ProviderRegistry conformance to ProviderRegistryProtocol."""

    def test_registry_has_register(self):
        """ProviderRegistry should have register method."""
        from scrappy.providers.registry import ProviderRegistry

        assert_has_method(ProviderRegistry, 'register')

    def test_registry_has_get(self):
        """ProviderRegistry should have get method."""
        from scrappy.providers.registry import ProviderRegistry

        assert_has_method(ProviderRegistry, 'get')

    def test_registry_has_list_all(self):
        """ProviderRegistry should have list_all method."""
        from scrappy.providers.registry import ProviderRegistry

        assert_has_method(ProviderRegistry, 'list_all')


class TestProviderSignatures:
    """Tests that verify provider method signatures match protocol."""

    def test_chat_accepts_messages(self):
        """chat() should accept messages list as first parameter."""
        from scrappy.providers.base import LLMProviderBase
        import inspect

        sig = inspect.signature(LLMProviderBase.chat)
        params = list(sig.parameters.keys())

        # First param is self, second should be messages
        assert 'messages' in params

    def test_chat_accepts_optional_model(self):
        """chat() should accept optional model parameter."""
        from scrappy.providers.base import LLMProviderBase
        import inspect

        sig = inspect.signature(LLMProviderBase.chat)
        params = sig.parameters

        assert 'model' in params
        # Model should have a default value (making it optional)
        assert params['model'].default is not inspect.Parameter.empty

    def test_chat_accepts_kwargs(self):
        """chat() should accept **kwargs for provider-specific params."""
        from scrappy.providers.base import LLMProviderBase
        import inspect

        sig = inspect.signature(LLMProviderBase.chat)
        params = sig.parameters

        # Should have a VAR_KEYWORD parameter
        has_kwargs = any(
            p.kind == inspect.Parameter.VAR_KEYWORD
            for p in params.values()
        )
        assert has_kwargs, "chat() should accept **kwargs"
