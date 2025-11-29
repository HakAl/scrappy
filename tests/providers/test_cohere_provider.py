"""
Test suite for Cohere LLM Provider implementation.

This module contains comprehensive tests for the CohereProvider class,
including initialization, API interactions, error handling, rate limiting,
and embedding functionality.
"""

import os
import time
import pytest
from unittest.mock import Mock, patch, MagicMock, call
from typing import List, Dict, Any, Optional

from src.providers.cohere_provider import CohereProvider, LLMResponse, ProviderLimits


class TestCohereProvider:
    """Test suite for CohereProvider class."""

    @pytest.fixture
    def mock_cohere_client_v2(self):
        """Create a mock Cohere V2 client for chat operations."""
        mock_client = Mock()

        # Mock response structure
        mock_response = Mock()
        mock_response.message = Mock()
        mock_response.message.content = [Mock()]
        mock_response.message.content[0].text = "Test response from Cohere"

        mock_meta = Mock()
        mock_meta.tokens = Mock()
        mock_meta.tokens.input_tokens = 15
        mock_meta.tokens.output_tokens = 8
        mock_response.meta = mock_meta

        mock_client.chat.return_value = mock_response
        return mock_client

    @pytest.fixture
    def mock_cohere_client_v1(self):
        """Create a mock Cohere V1 client for embeddings."""
        mock_client = Mock()

        # Mock embedding response
        mock_embed_response = Mock()
        mock_embed_response.embeddings = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        mock_client.embed.return_value = mock_embed_response

        return mock_client

    @pytest.fixture
    def provider_with_mock_clients(self, mock_cohere_client_v2, mock_cohere_client_v1):
        """Create provider with mock clients."""
        with patch('src.providers.cohere_provider.cohere') as mock_cohere:
            mock_cohere.ClientV2.return_value = mock_cohere_client_v2
            mock_cohere.Client.return_value = mock_cohere_client_v1

            provider = CohereProvider(api_key="test-key")
            return provider

    @pytest.fixture
    def provider_with_env_key(self, monkeypatch):
        """Create provider with environment variable key."""
        monkeypatch.setenv("COHERE_API_KEY", "env-test-key")

        with patch('src.providers.cohere_provider.cohere') as mock_cohere:
            mock_cohere.ClientV2.return_value = Mock()
            mock_cohere.Client.return_value = Mock()

            return CohereProvider()

    def test_initialization_with_api_key(self, mock_cohere_client_v2, mock_cohere_client_v1):
        """Test provider initialization with explicit API key."""
        with patch('src.providers.cohere_provider.cohere') as mock_cohere:
            mock_cohere.ClientV2.return_value = mock_cohere_client_v2
            mock_cohere.Client.return_value = mock_cohere_client_v1

            provider = CohereProvider(api_key="test-key")

            assert provider._api_key == "test-key"
            assert provider.name == "cohere"
            assert provider.default_model == "command-r7b-12-2024"
            assert provider._calls_made == 0


    def test_available_models(self, provider_with_mock_clients):
        """Test that available models are correctly listed."""
        models = provider_with_mock_clients.available_models
        expected_models = [
            'command-r-08-2024', 'command-r7b-12-2024', 'command-a-03-2025',
            'command-a-reasoning-08-2025', 'c4ai-aya-expanse-8b', 'c4ai-aya-expanse-32b'
        ]

        assert isinstance(models, list)
        assert len(models) == len(expected_models)
        for model in expected_models:
            assert model in models

    def test_model_configurations(self, provider_with_mock_clients):
        """Test that model configurations are properly defined."""
        from src.providers.base import ModelType, SpeedRank, QualityRank
        configs = provider_with_mock_clients.MODELS

        # Test Command R7B configuration (default)
        r7b_config = configs['command-r7b-12-2024']
        assert r7b_config['type'] == ModelType.CHAT or r7b_config['type'] == 'chat'
        assert r7b_config['quality'] == QualityRank.MODERATE or r7b_config['quality'] == 'moderate'
        assert r7b_config['speed'] == SpeedRank.VERY_FAST or r7b_config['speed'] == 'very_fast'
        assert r7b_config['context'] == 128000

        # Test Command A configuration
        command_a_config = configs['command-a-03-2025']
        assert command_a_config['type'] == ModelType.CHAT or command_a_config['type'] == 'chat'
        assert command_a_config['quality'] == QualityRank.EXCELLENT or command_a_config['quality'] == 'excellent'
        assert command_a_config['speed'] == SpeedRank.MODERATE or command_a_config['speed'] == 'moderate'
        assert command_a_config['context'] == 256000

        # Test reasoning model
        reasoning_config = configs['command-a-reasoning-08-2025']
        assert reasoning_config['type'] == ModelType.REASONING or reasoning_config['type'] == 'reasoning'
        assert reasoning_config['quality'] == QualityRank.EXCELLENT or reasoning_config['quality'] == 'excellent'
        assert reasoning_config['speed'] == SpeedRank.SLOW or reasoning_config['speed'] == 'slow'

    def test_chat_basic(self, provider_with_mock_clients):
        """Test basic chat functionality."""
        messages = [{"role": "user", "content": "Hello, how are you?"}]

        response = provider_with_mock_clients.chat(messages)

        assert isinstance(response, LLMResponse)
        assert response.content == "Test response from Cohere"
        assert response.model == "command-r7b-12-2024"
        assert response.provider == "cohere"
        assert response.tokens_used == 23  # 15 input + 8 output
        assert response.input_tokens == 15
        assert response.output_tokens == 8
        assert response.latency_ms > 0
        assert 'model_config' in response.metadata
        assert 'session_calls' in response.metadata
        assert response.metadata['session_calls'] == 1

    def test_chat_with_custom_model(self, provider_with_mock_clients):
        """Test chat with custom model selection."""
        messages = [{"role": "user", "content": "Test message"}]

        response = provider_with_mock_clients.chat(messages, model="command-a-03-2025")

        assert response.model == "command-a-03-2025"
        assert response.content == "Test response from Cohere"

    def test_chat_with_custom_parameters(self, provider_with_mock_clients):
        """Test chat with custom parameters."""
        messages = [{"role": "user", "content": "Test message"}]

        response = provider_with_mock_clients.chat(
            messages,
            max_tokens=500,
            temperature=0.5,
            top_p=0.9
        )

        assert response.content == "Test response from Cohere"
        # Verify the client was called with correct parameters
        call_args = provider_with_mock_clients._client.chat.call_args
        assert call_args[1]['max_tokens'] == 500
        assert call_args[1]['temperature'] == 0.5
        assert call_args[1]['top_p'] == 0.9

    def test_chat_without_usage_info(self, provider_with_mock_clients, mock_cohere_client_v2):
        """Test chat when usage info is not available."""
        # Mock response without meta info
        mock_response = Mock()
        mock_response.message = Mock()
        mock_response.message.content = [Mock()]
        mock_response.message.content[0].text = "Response without usage"
        mock_response.meta = None

        mock_cohere_client_v2.chat.return_value = mock_response

        messages = [{"role": "user", "content": "Test"}]
        response = provider_with_mock_clients.chat(messages)

        assert response.content == "Response without usage"
        assert response.tokens_used == 0
        assert response.input_tokens == 0
        assert response.output_tokens == 0

    def test_chat_warning_10_calls(self, provider_with_mock_clients, caplog):
        """Test warning is logged every 10 calls."""
        import logging
        messages = [{"role": "user", "content": "Test"}]

        with caplog.at_level(logging.WARNING):
            # Make 10 calls
            for _ in range(10):
                provider_with_mock_clients.chat(messages)

            # Should log warning after 10 calls
            assert "Cohere calls this session: 10" in caplog.text
            assert "1000 calls/month limit" in caplog.text

    def test_chat_empty_content(self, provider_with_mock_clients, mock_cohere_client_v2):
        """Test chat with empty content in response."""
        # Mock response with empty content
        mock_response = Mock()
        mock_response.message = Mock()
        mock_response.message.content = []  # Empty content
        mock_response.meta = Mock()
        mock_response.meta.tokens = Mock()
        mock_response.meta.tokens.input_tokens = 5
        mock_response.meta.tokens.output_tokens = 0

        mock_cohere_client_v2.chat.return_value = mock_response

        messages = [{"role": "user", "content": "Test"}]
        response = provider_with_mock_clients.chat(messages)

        assert response.content == ""
        assert response.tokens_used == 5

    def test_get_limits(self, provider_with_mock_clients):
        """Test rate limit information."""
        limits = provider_with_mock_clients.get_limits()

        assert isinstance(limits, ProviderLimits)
        assert limits.requests_per_minute == 20
        assert limits.requests_per_month == 1000



    def test_embed_custom_model(self, mock_cohere_client_v2, mock_cohere_client_v1):
        """Test embedding with custom model."""
        with patch('src.providers.cohere_provider.cohere') as mock_cohere:
            mock_cohere.ClientV2.return_value = mock_cohere_client_v2
            mock_cohere.Client.return_value = mock_cohere_client_v1

            provider = CohereProvider(api_key="test-key")
            texts = ["Test text"]

            embeddings = provider.embed(texts, model="embed-multilingual-v3.0")

            # Verify correct model was used
            mock_cohere_client_v1.embed.assert_called_once_with(
                texts=texts,
                model="embed-multilingual-v3.0",
                input_type='search_document'
            )
            # Mock returns [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
            assert embeddings == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]

    def test_embed_counts_toward_limit(self, provider_with_mock_clients):
        """Test that embed calls count toward session limit."""
        texts = ["Test"]

        initial_calls = provider_with_mock_clients._calls_made
        provider_with_mock_clients.embed(texts)

        assert provider_with_mock_clients._calls_made == initial_calls + 1

    def test_is_available(self, provider_with_mock_clients):
        """Test provider availability check."""
        assert provider_with_mock_clients.is_available() is True

        # Test with no API key
        provider_with_mock_clients._api_key = None
        assert provider_with_mock_clients.is_available() is False

        # Test with Cohere not available
        provider_with_mock_clients._api_key = "test-key"
        with patch('src.providers.cohere_provider.COHERE_AVAILABLE', False):
            assert provider_with_mock_clients.is_available() is False

    def test_get_remaining_budget(self, provider_with_mock_clients):
        """Test remaining budget calculation."""
        # Make some calls first
        provider_with_mock_clients._calls_made = 15

        budget = provider_with_mock_clients.get_remaining_budget()

        assert isinstance(budget, dict)
        assert budget['session_calls'] == 15
        assert budget['estimated_monthly_remaining'] == 985  # 1000 - 15
        assert 'warning' in budget
        assert 'session-only tracking' in budget['warning']

    def test_latency_measurement(self, provider_with_mock_clients):
        """Test that latency is properly measured."""
        messages = [{"role": "user", "content": "Test latency"}]

        response = provider_with_mock_clients.chat(messages)

        assert response.latency_ms > 0
        assert response.latency_ms < 1000  # Should be fast for mock

    def test_multiple_chat_calls_tracking(self, provider_with_mock_clients):
        """Test that multiple chat calls are properly tracked."""
        messages = [{"role": "user", "content": "Test"}]

        # Make multiple calls
        for i in range(5):
            response = provider_with_mock_clients.chat(messages)
            assert response.metadata['session_calls'] == i + 1

        assert provider_with_mock_clients._calls_made == 5

    def test_client_initialization(self, mock_cohere_client_v2, mock_cohere_client_v1):
        """Test that both V1 and V2 clients are properly initialized."""
        with patch('src.providers.cohere_provider.cohere') as mock_cohere:
            mock_cohere.ClientV2.return_value = mock_cohere_client_v2
            mock_cohere.Client.return_value = mock_cohere_client_v1

            provider = CohereProvider(api_key="test-key")

            # Verify both clients were created
            mock_cohere.ClientV2.assert_called_once_with(api_key="test-key")
            mock_cohere.Client.assert_called_once_with(api_key="test-key")

            assert provider._client == mock_cohere_client_v2
            assert provider._client_v1 == mock_cohere_client_v1

    @pytest.mark.parametrize("model_name", [
        "command-r-08-2024", "command-r7b-12-2024", "command-a-03-2025",
        "command-a-reasoning-08-2025", "c4ai-aya-expanse-8b", "c4ai-aya-expanse-32b"
    ])
    def test_all_supported_models(self, provider_with_mock_clients, model_name):
        """Test that all supported models can be used."""
        messages = [{"role": "user", "content": "Test"}]

        response = provider_with_mock_clients.chat(messages, model=model_name)

        assert response.model == model_name
        assert response.content == "Test response from Cohere"


    def test_metadata_inclusion(self, provider_with_mock_clients):
        """Test that metadata is properly included in response."""
        messages = [{"role": "user", "content": "Test"}]

        response = provider_with_mock_clients.chat(messages)

        assert 'model_config' in response.metadata
        assert 'session_calls' in response.metadata
        assert response.metadata['session_calls'] == 1
        assert isinstance(response.metadata['model_config'], dict)

    def test_model_config_variations(self, provider_with_mock_clients):
        """Test that different models have correct configurations."""
        from src.providers.base import ModelType, SpeedRank
        configs = provider_with_mock_clients.MODELS

        # Test multilingual models
        assert configs['c4ai-aya-expanse-8b']['type'] == ModelType.CHAT or configs['c4ai-aya-expanse-8b']['type'] == 'chat'
        assert configs['c4ai-aya-expanse-32b']['type'] == ModelType.CHAT or configs['c4ai-aya-expanse-32b']['type'] == 'chat'
        assert configs['c4ai-aya-expanse-8b']['context'] == 8192
        assert configs['c4ai-aya-expanse-32b']['context'] == 8192

        # Test reasoning model
        assert configs['command-a-reasoning-08-2025']['type'] == ModelType.REASONING or configs['command-a-reasoning-08-2025']['type'] == 'reasoning'
        assert configs['command-a-reasoning-08-2025']['speed'] == SpeedRank.SLOW or configs['command-a-reasoning-08-2025']['speed'] == 'slow'


class TestCohereProviderIntegration:
    """Integration tests for CohereProvider (requires real API key)."""

# todo
    # @pytest.mark.integration
    # @pytest.mark.skipif(not os.environ.get("COHERE_API_KEY"), reason="COHERE_API_KEY not set")
    # def test_real_api_call(self):
    #     """Test with real Cohere API (requires valid API key)."""
    #     provider = CohereProvider()
    #
    #     messages = [{"role": "user", "content": "Say 'Hello from Cohere!' and nothing else."}]
    #
    #     response = provider.chat(messages, max_tokens=50)
    #
    #     assert isinstance(response, LLMResponse)
    #     assert response.provider == "cohere"
    #     assert response.model == "command-r7b-12-2024"
    #     assert "hello" in response.content.lower() or "hi" in response.content.lower()

    # DELETED: test_real_rate_limits
    # Tests should NEVER make real API calls.
    # Rate limit logic is tested with mocked providers throughout the test suite.


if __name__ == "__main__":
    pytest.main([__file__, "-v"])