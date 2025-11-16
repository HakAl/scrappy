"""
Tests for provider-specific implementations - Cerebras, Groq, Gemini, Cohere.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from src.providers.base import LLMResponse, ProviderLimits


class TestCerebrasProvider:
    """Tests for Cerebras provider implementation."""

    @pytest.mark.unit
    @patch('src.providers.cerebras_provider.OpenAI')
    def test_cerebras_provider_initialization(self, mock_openai):
        """Test Cerebras provider can be initialized."""
        from src.providers.cerebras_provider import CerebrasProvider

        with patch.dict('os.environ', {'CEREBRAS_API_KEY': 'test-key'}):
            provider = CerebrasProvider()

            assert provider.name == "cerebras"
            assert len(provider.available_models) > 0
            assert provider.default_model is not None

    @pytest.mark.unit
    @patch('src.providers.cerebras_provider.OpenAI')
    def test_cerebras_chat_call(self, mock_openai):
        """Test Cerebras chat method."""
        from src.providers.cerebras_provider import CerebrasProvider

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Test response"))]
        mock_response.usage = MagicMock(total_tokens=100, prompt_tokens=30, completion_tokens=70)
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        with patch.dict('os.environ', {'CEREBRAS_API_KEY': 'test-key'}):
            provider = CerebrasProvider()
            response = provider.chat(
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=100
            )

            assert isinstance(response, LLMResponse)
            assert response.content == "Test response"
            assert response.provider == "cerebras"
            assert response.tokens_used == 100

    @pytest.mark.unit
    @patch('src.providers.cerebras_provider.OpenAI')
    def test_cerebras_get_limits(self, mock_openai):
        """Test Cerebras provider limits."""
        from src.providers.cerebras_provider import CerebrasProvider

        with patch.dict('os.environ', {'CEREBRAS_API_KEY': 'test-key'}):
            provider = CerebrasProvider()
            limits = provider.get_limits()

            assert isinstance(limits, ProviderLimits)
            assert limits.requests_per_day is not None or limits.requests_per_minute is not None

    @pytest.mark.unit
    @patch('src.providers.cerebras_provider.OpenAI')
    def test_cerebras_available_models(self, mock_openai):
        """Test Cerebras available models list."""
        from src.providers.cerebras_provider import CerebrasProvider

        with patch.dict('os.environ', {'CEREBRAS_API_KEY': 'test-key'}):
            provider = CerebrasProvider()
            models = provider.available_models

            assert isinstance(models, list)
            assert len(models) > 0


class TestGroqProvider:
    """Tests for Groq provider implementation."""

    @pytest.mark.unit
    @patch('src.providers.groq_provider.Groq')
    def test_groq_provider_initialization(self, mock_groq):
        """Test Groq provider can be initialized."""
        from src.providers.groq_provider import GroqProvider

        with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
            provider = GroqProvider()

            assert provider.name == "groq"
            assert len(provider.available_models) > 0

    @pytest.mark.unit
    @patch('src.providers.groq_provider.Groq')
    def test_groq_chat_call(self, mock_groq):
        """Test Groq chat method."""
        from src.providers.groq_provider import GroqProvider

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Groq response"))]
        mock_response.usage = MagicMock(total_tokens=80, prompt_tokens=20, completion_tokens=60)
        mock_client.chat.completions.create.return_value = mock_response
        mock_groq.return_value = mock_client

        with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
            provider = GroqProvider()
            response = provider.chat(
                messages=[{"role": "user", "content": "Test"}]
            )

            assert isinstance(response, LLMResponse)
            assert response.content == "Groq response"
            assert response.provider == "groq"

    @pytest.mark.unit
    @patch('src.providers.groq_provider.Groq')
    def test_groq_get_limits(self, mock_groq):
        """Test Groq provider limits."""
        from src.providers.groq_provider import GroqProvider

        with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
            provider = GroqProvider()
            limits = provider.get_limits()

            assert isinstance(limits, ProviderLimits)


class TestGeminiProvider:
    """Tests for Gemini provider implementation."""

    @pytest.mark.unit
    @patch('src.providers.gemini_provider.genai')
    def test_gemini_provider_initialization(self, mock_genai):
        """Test Gemini provider can be initialized."""
        from src.providers.gemini_provider import GeminiProvider

        with patch.dict('os.environ', {'GOOGLE_API_KEY': 'test-key'}):
            provider = GeminiProvider()

            assert provider.name == "gemini"
            assert len(provider.available_models) > 0

    @pytest.mark.unit
    @patch('src.providers.gemini_provider.genai')
    def test_gemini_chat_call(self, mock_genai):
        """Test Gemini chat method."""
        from src.providers.gemini_provider import GeminiProvider

        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Gemini response"
        mock_response.usage_metadata = MagicMock(
            total_token_count=90,
            prompt_token_count=25,
            candidates_token_count=65
        )
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model

        with patch.dict('os.environ', {'GOOGLE_API_KEY': 'test-key'}):
            provider = GeminiProvider()
            response = provider.chat(
                messages=[{"role": "user", "content": "Hello Gemini"}]
            )

            assert isinstance(response, LLMResponse)
            assert response.content == "Gemini response"
            assert response.provider == "gemini"

    @pytest.mark.unit
    @patch('src.providers.gemini_provider.genai')
    def test_gemini_handles_system_message(self, mock_genai):
        """Test Gemini handles system messages correctly."""
        from src.providers.gemini_provider import GeminiProvider

        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Response with system context"
        mock_response.usage_metadata = MagicMock(
            total_token_count=50,
            prompt_token_count=20,
            candidates_token_count=30
        )
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model

        with patch.dict('os.environ', {'GOOGLE_API_KEY': 'test-key'}):
            provider = GeminiProvider()
            response = provider.chat(
                messages=[
                    {"role": "system", "content": "You are helpful"},
                    {"role": "user", "content": "Hello"}
                ]
            )

            assert response.content == "Response with system context"

    @pytest.mark.unit
    @patch('src.providers.gemini_provider.genai')
    def test_gemini_get_limits(self, mock_genai):
        """Test Gemini provider limits."""
        from src.providers.gemini_provider import GeminiProvider

        with patch.dict('os.environ', {'GOOGLE_API_KEY': 'test-key'}):
            provider = GeminiProvider()
            limits = provider.get_limits()

            assert isinstance(limits, ProviderLimits)


class TestCohereProvider:
    """Tests for Cohere provider implementation."""

    @pytest.mark.unit
    @patch('src.providers.cohere_provider.cohere')
    def test_cohere_provider_initialization(self, mock_cohere):
        """Test Cohere provider can be initialized."""
        from src.providers.cohere_provider import CohereProvider

        mock_client = MagicMock()
        mock_cohere.Client.return_value = mock_client

        with patch.dict('os.environ', {'COHERE_API_KEY': 'test-key'}):
            provider = CohereProvider()

            assert provider.name == "cohere"
            assert len(provider.available_models) > 0

    @pytest.mark.unit
    @patch('src.providers.cohere_provider.cohere')
    def test_cohere_chat_call(self, mock_cohere):
        """Test Cohere chat method."""
        from src.providers.cohere_provider import CohereProvider

        # Mock V2 client (used for chat)
        mock_client_v2 = MagicMock()
        mock_response = MagicMock()
        # Cohere V2 response structure
        mock_content_block = MagicMock()
        mock_content_block.text = "Cohere response"
        mock_response.message = MagicMock()
        mock_response.message.content = [mock_content_block]
        mock_response.usage = MagicMock(
            billed_units=MagicMock(input_tokens=15, output_tokens=25)
        )
        mock_client_v2.chat.return_value = mock_response
        mock_cohere.ClientV2.return_value = mock_client_v2
        mock_cohere.Client.return_value = MagicMock()  # V1 client

        with patch.dict('os.environ', {'COHERE_API_KEY': 'test-key'}):
            provider = CohereProvider()
            response = provider.chat(
                messages=[{"role": "user", "content": "Hello Cohere"}]
            )

            assert isinstance(response, LLMResponse)
            assert response.content == "Cohere response"
            assert response.provider == "cohere"

    @pytest.mark.unit
    @patch('src.providers.cohere_provider.cohere')
    def test_cohere_get_limits(self, mock_cohere):
        """Test Cohere provider limits."""
        from src.providers.cohere_provider import CohereProvider

        mock_client = MagicMock()
        mock_cohere.Client.return_value = mock_client

        with patch.dict('os.environ', {'COHERE_API_KEY': 'test-key'}):
            provider = CohereProvider()
            limits = provider.get_limits()

            assert isinstance(limits, ProviderLimits)


class TestProviderErrorHandling:
    """Tests for provider error handling."""

    @pytest.mark.unit
    @patch('src.providers.cerebras_provider.OpenAI')
    def test_cerebras_handles_api_error(self, mock_openai):
        """Test Cerebras handles API errors gracefully."""
        from src.providers.cerebras_provider import CerebrasProvider

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API Error")
        mock_openai.return_value = mock_client

        with patch.dict('os.environ', {'CEREBRAS_API_KEY': 'test-key'}):
            provider = CerebrasProvider()

            with pytest.raises(Exception):
                provider.chat(messages=[{"role": "user", "content": "Test"}])

    @pytest.mark.unit
    @patch('src.providers.groq_provider.Groq')
    def test_groq_handles_rate_limit(self, mock_groq):
        """Test Groq handles rate limit errors."""
        from src.providers.groq_provider import GroqProvider

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Rate limit exceeded")
        mock_groq.return_value = mock_client

        with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
            provider = GroqProvider()

            with pytest.raises(Exception):
                provider.chat(messages=[{"role": "user", "content": "Test"}])

    @pytest.mark.unit
    def test_provider_missing_api_key(self):
        """Test that providers handle missing API keys."""
        # Clear environment
        with patch.dict('os.environ', {}, clear=True):
            # Providers should raise or return unavailable
            try:
                from src.providers.cerebras_provider import CerebrasProvider
                provider = CerebrasProvider()
                # Either raises exception or is_available returns False
            except Exception:
                pass  # Expected behavior

    @pytest.mark.unit
    @patch('src.providers.gemini_provider.genai')
    def test_gemini_handles_empty_response(self, mock_genai):
        """Test Gemini handles empty response."""
        from src.providers.gemini_provider import GeminiProvider

        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = ""
        mock_response.usage_metadata = MagicMock(
            total_token_count=10,
            prompt_token_count=10,
            candidates_token_count=0
        )
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model

        with patch.dict('os.environ', {'GOOGLE_API_KEY': 'test-key'}):
            provider = GeminiProvider()
            response = provider.chat(
                messages=[{"role": "user", "content": "Test"}]
            )

            assert response.content == ""


class TestProviderResponseParsing:
    """Tests for parsing provider responses into LLMResponse."""

    @pytest.mark.unit
    def test_llm_response_preserves_metadata(self):
        """Test that metadata is preserved in response."""
        response = LLMResponse(
            content="Test",
            model="test-model",
            provider="test",
            tokens_used=100,
            metadata={"custom": "data", "retry": 2}
        )

        assert response.metadata["custom"] == "data"
        assert response.metadata["retry"] == 2

    @pytest.mark.unit
    def test_llm_response_tracks_latency(self):
        """Test that latency can be tracked."""
        response = LLMResponse(
            content="Test",
            model="model",
            provider="provider",
            latency_ms=150.5
        )

        assert response.latency_ms == 150.5

    @pytest.mark.unit
    def test_llm_response_timestamp(self):
        """Test that response has timestamp."""
        response = LLMResponse(
            content="Test",
            model="model",
            provider="provider"
        )

        assert isinstance(response.timestamp, datetime)

    @pytest.mark.unit
    def test_llm_response_raw_response_storage(self):
        """Test that raw response can be stored."""
        raw = {"id": "123", "choices": [], "usage": {}}
        response = LLMResponse(
            content="Test",
            model="model",
            provider="provider",
            raw_response=raw
        )

        assert response.raw_response == raw
