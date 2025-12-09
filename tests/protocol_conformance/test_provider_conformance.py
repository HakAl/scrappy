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







class TestLLMProviderBaseConformance:
    """Tests for LLMProviderBase implementation."""





class TestGroqProviderConformance:
    """Tests for GroqProvider implementation."""

    @pytest.fixture
    def provider_class(self):
        """Get GroqProvider class."""
        from scrappy.providers.groq_provider import GroqProvider
        return GroqProvider








class TestCerebrasProviderConformance:
    """Tests for CerebrasProvider implementation."""

    @pytest.fixture
    def provider_class(self):
        """Get CerebrasProvider class."""
        from scrappy.providers.cerebras_provider import CerebrasProvider
        return CerebrasProvider





class TestCohereProviderConformance:
    """Tests for CohereProvider implementation."""

    @pytest.fixture
    def provider_class(self):
        """Get CohereProvider class."""
        from scrappy.providers.cohere_provider import CohereProvider
        return CohereProvider





class TestGeminiProviderConformance:
    """Tests for GeminiProvider implementation."""

    @pytest.fixture
    def provider_class(self):
        """Get GeminiProvider class."""
        from scrappy.providers.gemini_provider import GeminiProvider
        return GeminiProvider





class TestGitHubModelsProviderConformance:
    """Tests for GitHubModelsProvider implementation."""

    @pytest.fixture
    def provider_class(self):
        """Get GitHubModelsProvider class."""
        from scrappy.providers.github_models_provider import GitHubModelsProvider
        return GitHubModelsProvider





@pytest.mark.skip(reason="ProviderRegistry doesn't exist as a separate module")
class TestProviderRegistryConformance:
    """Tests for ProviderRegistry conformance to ProviderRegistryProtocol."""





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
