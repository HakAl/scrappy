"""
Test suite for GitHub Models LLM Provider implementation.

This module contains comprehensive tests for the GitHubModelsProvider class,
including initialization, API interactions, error handling, and rate limiting.
"""

import os
import json
import time
import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from typing import Dict, Any, Optional

from src.providers.github_models_provider import GitHubModelsProvider, LLMResponse, ProviderLimits


class TestGitHubModelsProvider:
    """Test suite for GitHubModelsProvider class."""

    @pytest.fixture
    def mock_openai_client(self):
        """Create a mock OpenAI client."""
        mock_client = Mock()
        mock_completion = Mock()
        mock_completion.choices = [Mock()]
        mock_completion.choices[0].message.content = "Test response"
        mock_completion.choices[0].finish_reason = "stop"
        mock_completion.usage = Mock()
        mock_completion.usage.prompt_tokens = 10
        mock_completion.usage.completion_tokens = 5

        mock_response = Mock()
        mock_response.parse.return_value = mock_completion
        mock_response.headers = {
            'x-ratelimit-limit-requests': '10000',
            'x-ratelimit-remaining-requests': '9999',
            'x-ratelimit-limit-tokens': '10000000',
            'x-ratelimit-remaining-tokens': '9999995',
            'x-ms-region': 'eastus'
        }

        mock_client.chat.completions.with_raw_response.create.return_value = mock_response
        return mock_client

    @pytest.fixture
    def mock_httpx_response(self):
        """Create a mock httpx response for async tests."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {
            'x-ratelimit-limit-requests': '10000',
            'x-ratelimit-remaining-requests': '9999',
            'x-ratelimit-limit-tokens': '10000000',
            'x-ratelimit-remaining-tokens': '9999995',
            'x-ms-region': 'westus'
        }
        mock_response.json.return_value = {
            'choices': [{
                'message': {'content': 'Async test response'},
                'finish_reason': 'stop'
            }],
            'usage': {
                'prompt_tokens': 15,
                'completion_tokens': 8
            }
        }
        return mock_response

    @pytest.fixture
    def provider_with_mock_client(self, mock_openai_client):
        """Create provider with mock client."""
        return GitHubModelsProvider(client=mock_openai_client, api_key="test-key")

    @pytest.fixture
    def provider_with_env_key(self, monkeypatch):
        """Create provider with environment variable key."""
        monkeypatch.setenv("GITHUB_API_KEY", "env-test-key")
        return GitHubModelsProvider()

    def test_initialization_with_api_key(self, mock_openai_client):
        """Test provider initialization with explicit API key."""
        provider = GitHubModelsProvider(api_key="test-key", client=mock_openai_client)

        assert provider._api_key == "test-key"
        assert provider._client == mock_openai_client
        assert provider.name == "github"
        assert provider.default_model == "gpt-4o"

    def test_initialization_with_env_var(self, monkeypatch):
        """Test provider initialization with environment variable."""
        monkeypatch.setenv("GITHUB_API_KEY", "env-test-key")

        with patch('src.providers.github_models_provider.OpenAI') as mock_openai_class:
            mock_openai_class.return_value = Mock()
            provider = GitHubModelsProvider()

            assert provider._api_key == "env-test-key"

    def test_available_models(self, provider_with_mock_client):
        """Test that available models are correctly listed."""
        models = provider_with_mock_client.available_models
        expected_models = [
            'gpt-4o', 'gpt-4o-mini', 'deepseek-r1', 'grok-3-mini',
            'meta-llama-3.1-8b-instruct', 'llama-4-scout-17b-16e-instruct',
            'phi-4', 'mistral-small-2503', 'cohere-command-a'
        ]

        assert isinstance(models, list)
        assert len(models) == len(expected_models)
        for model in expected_models:
            assert model in models

    def test_model_configurations(self, provider_with_mock_client):
        """Test that model configurations are properly defined."""
        from src.providers.base import SpeedRank, QualityRank
        configs = provider_with_mock_client.MODELS

        # Test GPT-4o configuration
        gpt4o_config = configs['gpt-4o']
        assert gpt4o_config['rpd'] == 10000
        assert gpt4o_config['tpd'] == 10000000
        assert gpt4o_config['context'] == 128000
        assert gpt4o_config['speed'] == SpeedRank.MODERATE
        assert gpt4o_config['quality'] == QualityRank.EXCELLENT

        # Test DeepSeek R1 configuration
        deepseek_config = configs['deepseek-r1']
        assert deepseek_config['context'] == 64000
        assert deepseek_config['speed'] == SpeedRank.MODERATE
        assert deepseek_config['quality'] == QualityRank.EXCELLENT
        assert deepseek_config['reasoning'] is True

    def test_chat_basic(self, provider_with_mock_client):
        """Test basic chat functionality."""
        messages = [{"role": "user", "content": "Hello, how are you?"}]

        # Mock time.time to ensure measurable latency
        with patch('time.time', side_effect=[1000.0, 1000.1]):  # 100ms difference
            response = provider_with_mock_client.chat(messages)

        assert isinstance(response, LLMResponse)
        assert response.content == "Test response"
        assert response.model == "gpt-4o"
        assert response.provider == "github"
        assert response.tokens_used == 15
        assert response.input_tokens == 10
        assert response.output_tokens == 5
        assert response.latency_ms > 0
        assert response.metadata['finish_reason'] == "stop"
        assert 'rate_limits' in response.metadata

    def test_chat_with_custom_model(self, provider_with_mock_client):
        """Test chat with custom model selection."""
        messages = [{"role": "user", "content": "Test message"}]

        response = provider_with_mock_client.chat(messages, model="gpt-4o-mini")

        assert response.model == "gpt-4o-mini"
        assert response.content == "Test response"

    def test_chat_with_custom_parameters(self, provider_with_mock_client):
        """Test chat with custom parameters."""
        messages = [{"role": "user", "content": "Test message"}]

        response = provider_with_mock_client.chat(
            messages,
            max_tokens=500,
            temperature=0.5,
            top_p=0.9
        )

        assert response.content == "Test response"
        # Verify the client was called with correct parameters
        call_args = provider_with_mock_client._client.chat.completions.with_raw_response.create.call_args
        assert call_args[1]['max_tokens'] == 500
        assert call_args[1]['temperature'] == 0.5
        assert call_args[1]['top_p'] == 0.9

    def test_rate_limit_headers_parsing(self, provider_with_mock_client):
        """Test that rate limit headers are correctly parsed."""
        messages = [{"role": "user", "content": "Test"}]

        response = provider_with_mock_client.chat(messages)

        rate_limits = response.metadata['rate_limits']
        assert rate_limits['limit_requests'] == '10000'
        assert rate_limits['remaining_requests'] == '9999'
        assert rate_limits['limit_tokens'] == '10000000'
        assert rate_limits['remaining_tokens'] == '9999995'

    def test_get_limits_cached(self, provider_with_mock_client):
        """Test get_limits returns cached values after API call."""
        messages = [{"role": "user", "content": "Test"}]

        # Make an API call to populate cached limits
        provider_with_mock_client.chat(messages)

        limits = provider_with_mock_client.get_limits()

        assert isinstance(limits, ProviderLimits)
        assert limits.requests_per_day == 10000
        assert limits.tokens_per_day == 10000000
        assert limits.remaining_requests == 9999
        assert limits.remaining_tokens == 9999995

    def test_get_limits_default(self, provider_with_mock_client):
        """Test get_limits returns model defaults when no cache available."""
        # Before any API call, cached limits have no remaining_requests set
        # So get_limits() falls back to model defaults
        limits = provider_with_mock_client.get_limits()

        assert isinstance(limits, ProviderLimits)
        # Falls back to default model (gpt-4o) limits from MODELS config
        assert limits.requests_per_day == 10000  # gpt-4o rpd
        assert limits.tokens_per_day == 10000000  # gpt-4o tpd
        # remaining_* are None since we haven't made an API call yet
        assert limits.remaining_requests is None
        assert limits.remaining_tokens is None


    @pytest.mark.asyncio
    async def test_chat_async_basic(self, provider_with_mock_client, mock_httpx_response):
        """Test basic async chat functionality."""
        messages = [{"role": "user", "content": "Hello async"}]

        with patch('src.providers.github_models_provider.HTTPX_AVAILABLE', True):
            with patch('httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value.__aenter__.return_value = mock_client
                mock_client.post = AsyncMock(return_value=mock_httpx_response)

                response = await provider_with_mock_client.chat_async(messages)

                assert isinstance(response, LLMResponse)
                assert response.content == "Async test response"
                assert response.model == "gpt-4o"
                assert response.provider == "github"
                assert response.metadata['async'] is True

    @pytest.mark.asyncio
    async def test_chat_async_rate_limit_retry(self, provider_with_mock_client):
        """Test async chat with rate limit retry."""
        messages = [{"role": "user", "content": "Test"}]

        # Mock rate limit response followed by success
        rate_limit_response = Mock()
        rate_limit_response.status_code = 429

        success_response = Mock()
        success_response.status_code = 200
        success_response.headers = {
            'x-ratelimit-limit-requests': '10000',
            'x-ratelimit-remaining-requests': '9998',
            'x-ms-region': 'eastus'
        }
        success_response.json.return_value = {
            'choices': [{'message': {'content': 'Success after retry'}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 5, 'completion_tokens': 3}
        }

        with patch('src.providers.github_models_provider.HTTPX_AVAILABLE', True):
            with patch('httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value.__aenter__.return_value = mock_client
                mock_client.post = AsyncMock(side_effect=[rate_limit_response, success_response])

                with patch('asyncio.sleep', new_callable=AsyncMock):
                    response = await provider_with_mock_client.chat_async(messages)

                    assert response.content == "Success after retry"
                    assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_chat_async_httpx_not_available(self, provider_with_mock_client):
        """Test async chat falls back when httpx not available."""
        messages = [{"role": "user", "content": "Test"}]

        with patch('src.providers.github_models_provider.HTTPX_AVAILABLE', False):
            with patch.object(provider_with_mock_client, 'chat') as mock_chat:
                mock_chat.return_value = LLMResponse(
                    content="Fallback response",
                    model="gpt-4o",
                    provider="github",
                    tokens_used=10,
                    input_tokens=6,
                    output_tokens=4,
                    latency_ms=100.0,
                    raw_response={},
                    metadata={}
                )

                response = await provider_with_mock_client.chat_async(messages)

                assert response.content == "Fallback response"
                mock_chat.assert_called_once()

    def test_is_available(self, provider_with_mock_client):
        """Test provider availability check."""
        assert provider_with_mock_client.is_available() is True

        # Test with no API key
        provider_with_mock_client._api_key = None
        assert provider_with_mock_client.is_available() is False

        # Test with OpenAI not available
        provider_with_mock_client._api_key = "test-key"
        with patch('src.providers.github_models_provider.OPENAI_AVAILABLE', False):
            assert provider_with_mock_client.is_available() is False



    def test_metadata_inclusion(self, provider_with_mock_client):
        """Test that metadata is properly included in response."""
        messages = [{"role": "user", "content": "Test"}]

        response = provider_with_mock_client.chat(messages)

        assert 'model_config' in response.metadata
        assert 'rate_limits' in response.metadata
        assert 'region' in response.metadata
        assert response.metadata['region'] == 'eastus'

    @pytest.mark.parametrize("model_name", [
        "gpt-4o", "gpt-4o-mini", "deepseek-r1", "grok-3-mini",
        "meta-llama-3.1-8b-instruct", "llama-4-scout-17b-16e-instruct",
        "phi-4", "mistral-small-2503", "cohere-command-a"
    ])
    def test_all_supported_models(self, provider_with_mock_client, model_name):
        """Test that all supported models can be used."""
        messages = [{"role": "user", "content": "Test"}]

        response = provider_with_mock_client.chat(messages, model=model_name)

        assert response.model == model_name
        assert response.content == "Test response"

    def test_latency_measurement(self, provider_with_mock_client):
        """Test that latency is properly measured."""
        messages = [{"role": "user", "content": "Test"}]

        # Mock time.time to return predictable values for latency measurement
        with patch('time.time', side_effect=[1000.0, 1000.05]):  # 50ms difference
            response = provider_with_mock_client.chat(messages)

        # Latency should be reasonable (less than 1 second for mock)
        assert response.latency_ms < 1000
        assert response.latency_ms > 0

    def test_token_counting(self, provider_with_mock_client):
        """Test that token usage is correctly calculated."""
        messages = [{"role": "user", "content": "Test"}]

        response = provider_with_mock_client.chat(messages)

        assert response.tokens_used == response.input_tokens + response.output_tokens
        assert response.input_tokens == 10
        assert response.output_tokens == 5

    def test_response_without_usage(self, provider_with_mock_client):
        """Test handling of responses without usage information."""
        messages = [{"role": "user", "content": "Test"}]

        # Mock response without usage
        mock_completion = Mock()
        mock_completion.choices = [Mock()]
        mock_completion.choices[0].message.content = "No usage response"
        mock_completion.choices[0].finish_reason = "stop"
        mock_completion.usage = None

        mock_response = Mock()
        mock_response.parse.return_value = mock_completion
        mock_response.headers = {}

        provider_with_mock_client._client.chat.completions.with_raw_response.create.return_value = mock_response

        response = provider_with_mock_client.chat(messages)

        assert response.content == "No usage response"
        assert response.tokens_used == 0
        assert response.input_tokens == 0
        assert response.output_tokens == 0


class TestGitHubModelsProviderNullHandling:
    """
    Tests for null content handling (Issue: NO_OUTPUT.md Issue 3).

    GitHub Models Provider should return empty string when API returns None for content.
    """

    @pytest.fixture
    def mock_client_with_null_content(self):
        """Create a mock OpenAI client that returns None for message content."""
        mock_client = Mock()
        mock_completion = Mock()
        mock_completion.choices = [Mock()]
        mock_completion.choices[0].message.content = None  # API returns None
        mock_completion.choices[0].finish_reason = "stop"
        mock_completion.usage = Mock()
        mock_completion.usage.prompt_tokens = 10
        mock_completion.usage.completion_tokens = 0

        mock_response = Mock()
        mock_response.parse.return_value = mock_completion
        mock_response.headers = {}

        mock_client.chat.completions.with_raw_response.create.return_value = mock_response
        return mock_client

    def test_chat_returns_empty_string_when_api_returns_none_content(self, mock_client_with_null_content):
        """
        ISSUE: chat() does not handle None content from API.

        When the GitHub Models API returns None for message.content, the LLMResponse
        should contain an empty string, not None.

        EXPECTED: LLMResponse.content should be "" (empty string), not None.
        """
        provider = GitHubModelsProvider(client=mock_client_with_null_content, api_key="test-key")

        messages = [{"role": "user", "content": "Hi"}]
        response = provider.chat(messages)

        # LLMResponse.content is typed as `str`, not `Optional[str]`
        # So we should get empty string, not None
        assert response.content is not None, "content should not be None"
        assert isinstance(response.content, str), "content should be a string"
        assert response.content == "", "content should be empty string when API returns None"


class TestGitHubModelsProviderIntegration:
    """Integration tests for GitHubModelsProvider (requires real API key)."""
# todo
    # @pytest.mark.integration
    # @pytest.mark.skipif(not os.environ.get("GITHUB_API_KEY"), reason="GITHUB_API_KEY not set")
    # def test_real_api_call(self):
    #     """Test with real GitHub Models API (requires valid API key)."""
    #     provider = GitHubModelsProvider()
    #
    #     messages = [{"role": "user", "content": "Say 'Hello, World!' and nothing else."}]
    #
    #     response = provider.chat(messages, max_tokens=50)
    #
    #     assert isinstance(response, LLMResponse)
    #     assert response.provider == "github"
    #     assert response.model == "gpt-4o"
    #     assert "Hello" in response.content or "hello" in response.content.lower()
# todo
    # @pytest.mark.integration
    # @pytest.mark.skipif(not os.environ.get("GITHUB_API_KEY"), reason="GITHUB_API_KEY not set")
    # @pytest.mark.asyncio
    # async def test_real_async_api_call(self):
    #     """Test async call with real GitHub Models API."""
    #     provider = GitHubModelsProvider()
    #
    #     messages = [{"role": "user", "content": "Say 'Async works!' and nothing else."}]
    #
    #     response = await provider.chat_async(messages, max_tokens=50)
    #
    #     assert isinstance(response, LLMResponse)
    #     assert response.provider == "github"
    #     assert "async" in response.content.lower() or "works" in response.content.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])