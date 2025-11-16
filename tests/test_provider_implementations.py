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

    @pytest.mark.unit
    def test_groq_missing_api_key_raises_error(self):
        """Test Groq raises error when API key missing."""
        from src.providers.groq_provider import GroqProvider

        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ValueError, match="GROQ_API_KEY"):
                GroqProvider()

    @pytest.mark.unit
    @patch('src.providers.groq_provider.Groq')
    def test_groq_invalid_model_raises_error(self, mock_groq):
        """Test Groq raises error for invalid model."""
        from src.providers.groq_provider import GroqProvider

        with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
            provider = GroqProvider()

            with pytest.raises(ValueError, match="not supported"):
                provider.chat([{"role": "user", "content": "test"}], model="invalid-model")

    @pytest.mark.unit
    @patch('src.providers.groq_provider.Groq')
    def test_groq_get_model_for_task_fast(self, mock_groq):
        """Test Groq recommends fast model."""
        from src.providers.groq_provider import GroqProvider

        with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
            provider = GroqProvider()
            model = provider.get_model_for_task('fast')

            assert model == 'llama-3.1-8b-instant'

    @pytest.mark.unit
    @patch('src.providers.groq_provider.Groq')
    def test_groq_get_model_for_task_quality(self, mock_groq):
        """Test Groq recommends quality model."""
        from src.providers.groq_provider import GroqProvider

        with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
            provider = GroqProvider()
            model = provider.get_model_for_task('quality')

            assert model == 'llama-3.3-70b-versatile'

    @pytest.mark.unit
    @patch('src.providers.groq_provider.Groq')
    def test_groq_get_model_for_task_high_volume(self, mock_groq):
        """Test Groq recommends high volume model."""
        from src.providers.groq_provider import GroqProvider

        with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
            provider = GroqProvider()
            model = provider.get_model_for_task('high_volume')

            assert model == 'mixtral-8x7b-32768'

    @pytest.mark.unit
    @patch('src.providers.groq_provider.Groq')
    def test_groq_get_model_for_task_unknown(self, mock_groq):
        """Test Groq returns default for unknown task type."""
        from src.providers.groq_provider import GroqProvider

        with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
            provider = GroqProvider()
            model = provider.get_model_for_task('unknown_task')

            assert model == provider.default_model

    @pytest.mark.unit
    @patch('src.providers.groq_provider.Groq')
    def test_groq_is_available(self, mock_groq):
        """Test Groq is_available returns True when configured."""
        from src.providers.groq_provider import GroqProvider

        with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
            provider = GroqProvider()
            assert provider.is_available() is True

    @pytest.mark.unit
    @patch('src.providers.groq_provider.Groq')
    def test_groq_default_model(self, mock_groq):
        """Test Groq default model is set correctly."""
        from src.providers.groq_provider import GroqProvider

        with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
            provider = GroqProvider()
            assert provider.default_model == 'llama-3.1-8b-instant'

    @pytest.mark.unit
    @patch('src.providers.groq_provider.Groq')
    def test_groq_chat_with_specific_model(self, mock_groq):
        """Test Groq chat with specific model."""
        from src.providers.groq_provider import GroqProvider

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(
            message=MagicMock(content="Response"),
            finish_reason="stop"
        )]
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=20)
        mock_client.chat.completions.create.return_value = mock_response
        mock_groq.return_value = mock_client

        with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
            provider = GroqProvider()
            response = provider.chat(
                [{"role": "user", "content": "test"}],
                model='llama-3.3-70b-versatile'
            )

            assert response.model == 'llama-3.3-70b-versatile'
            # Verify call args
            mock_client.chat.completions.create.assert_called_once()

    @pytest.mark.unit
    @patch('src.providers.groq_provider.Groq')
    def test_groq_chat_with_custom_temperature(self, mock_groq):
        """Test Groq chat with custom temperature."""
        from src.providers.groq_provider import GroqProvider

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(
            message=MagicMock(content="Response"),
            finish_reason="stop"
        )]
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=20)
        mock_client.chat.completions.create.return_value = mock_response
        mock_groq.return_value = mock_client

        with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
            provider = GroqProvider()
            provider.chat(
                [{"role": "user", "content": "test"}],
                temperature=0.9
            )

            call_args = mock_client.chat.completions.create.call_args
            assert call_args[1]['temperature'] == 0.9

    @pytest.mark.unit
    @patch('src.providers.groq_provider.Groq')
    def test_groq_chat_response_metadata(self, mock_groq):
        """Test Groq chat response includes metadata."""
        from src.providers.groq_provider import GroqProvider

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(
            message=MagicMock(content="Response"),
            finish_reason="length"
        )]
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=20)
        mock_client.chat.completions.create.return_value = mock_response
        mock_groq.return_value = mock_client

        with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
            provider = GroqProvider()
            response = provider.chat([{"role": "user", "content": "test"}])

            assert 'finish_reason' in response.metadata
            assert response.metadata['finish_reason'] == 'length'
            assert 'model_config' in response.metadata

    @pytest.mark.unit
    @patch('src.providers.groq_provider.Groq')
    def test_groq_chat_no_usage_info(self, mock_groq):
        """Test Groq chat handles missing usage info."""
        from src.providers.groq_provider import GroqProvider

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(
            message=MagicMock(content="Response"),
            finish_reason="stop"
        )]
        mock_response.usage = None  # No usage info
        mock_client.chat.completions.create.return_value = mock_response
        mock_groq.return_value = mock_client

        with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
            provider = GroqProvider()
            response = provider.chat([{"role": "user", "content": "test"}])

            assert response.input_tokens == 0
            assert response.output_tokens == 0
            assert response.tokens_used == 0

    @pytest.mark.unit
    @patch('src.providers.groq_provider.Groq')
    def test_groq_limits_match_default_model(self, mock_groq):
        """Test that limits match the default model configuration."""
        from src.providers.groq_provider import GroqProvider

        with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
            provider = GroqProvider()
            limits = provider.get_limits()

            # Default model is llama-3.1-8b-instant
            assert limits.requests_per_minute == 30
            assert limits.requests_per_day == 7000
            assert limits.tokens_per_minute == 20000
            assert limits.tokens_per_day == 200000

    @pytest.mark.unit
    @patch('src.providers.groq_provider.Groq')
    def test_groq_available_models_list(self, mock_groq):
        """Test Groq available models list."""
        from src.providers.groq_provider import GroqProvider

        with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
            provider = GroqProvider()
            models = provider.available_models

            assert 'llama-3.1-8b-instant' in models
            assert 'llama-3.3-70b-versatile' in models
            assert 'mixtral-8x7b-32768' in models
            assert len(models) >= 5

    @pytest.mark.unit
    @patch('src.providers.groq_provider.Groq')
    def test_groq_chat_latency_measured(self, mock_groq):
        """Test Groq chat measures latency."""
        from src.providers.groq_provider import GroqProvider

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(
            message=MagicMock(content="Response"),
            finish_reason="stop"
        )]
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=20)
        mock_client.chat.completions.create.return_value = mock_response
        mock_groq.return_value = mock_client

        with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
            provider = GroqProvider()
            response = provider.chat([{"role": "user", "content": "test"}])

            assert response.latency_ms >= 0
            assert isinstance(response.latency_ms, float)

    @pytest.mark.asyncio
    @pytest.mark.unit
    @patch('src.providers.groq_provider.Groq')
    async def test_groq_chat_async_fallback(self, mock_groq):
        """Test Groq async chat fallback when httpx not available."""
        from src.providers.groq_provider import GroqProvider
        import src.providers.groq_provider as groq_module

        # Temporarily disable httpx
        original_httpx = groq_module.HTTPX_AVAILABLE
        groq_module.HTTPX_AVAILABLE = False

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(
            message=MagicMock(content="Async response"),
            finish_reason="stop"
        )]
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=20)
        mock_client.chat.completions.create.return_value = mock_response
        mock_groq.return_value = mock_client

        try:
            with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
                provider = GroqProvider()
                response = await provider.chat_async([{"role": "user", "content": "test"}])

                assert response.content == "Async response"
        finally:
            groq_module.HTTPX_AVAILABLE = original_httpx

    @pytest.mark.asyncio
    @pytest.mark.unit
    @patch('src.providers.groq_provider.Groq')
    @patch('src.providers.groq_provider.httpx')
    async def test_groq_chat_async_with_httpx(self, mock_httpx, mock_groq):
        """Test Groq async chat with httpx."""
        from src.providers.groq_provider import GroqProvider
        import src.providers.groq_provider as groq_module
        from unittest.mock import AsyncMock

        # Ensure httpx is available
        original_httpx = groq_module.HTTPX_AVAILABLE
        groq_module.HTTPX_AVAILABLE = True

        # Create async mock for httpx client
        mock_async_client = AsyncMock()
        mock_response = MagicMock()  # Not AsyncMock - json() is sync
        mock_response.json.return_value = {
            'choices': [{
                'message': {'content': 'Async HTTPX response'},
                'finish_reason': 'stop'
            }],
            'usage': {
                'prompt_tokens': 15,
                'completion_tokens': 25
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_async_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
        mock_httpx.AsyncClient.return_value = mock_async_client

        try:
            with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
                provider = GroqProvider()
                response = await provider.chat_async([{"role": "user", "content": "test"}])

                assert response.content == "Async HTTPX response"
                assert response.input_tokens == 15
                assert response.output_tokens == 25
                assert response.tokens_used == 40
                assert response.metadata.get('async') is True
        finally:
            groq_module.HTTPX_AVAILABLE = original_httpx

    @pytest.mark.asyncio
    @pytest.mark.unit
    @patch('src.providers.groq_provider.Groq')
    @patch('src.providers.groq_provider.httpx')
    async def test_groq_chat_async_invalid_model(self, mock_httpx, mock_groq):
        """Test Groq async chat with invalid model."""
        from src.providers.groq_provider import GroqProvider
        import src.providers.groq_provider as groq_module

        original_httpx = groq_module.HTTPX_AVAILABLE
        groq_module.HTTPX_AVAILABLE = True

        try:
            with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
                provider = GroqProvider()

                with pytest.raises(ValueError, match="not supported"):
                    await provider.chat_async(
                        [{"role": "user", "content": "test"}],
                        model="invalid-model"
                    )
        finally:
            groq_module.HTTPX_AVAILABLE = original_httpx

    @pytest.mark.unit
    @patch('src.providers.groq_provider.Groq')
    def test_groq_with_explicit_api_key(self, mock_groq):
        """Test Groq initialization with explicit API key."""
        from src.providers.groq_provider import GroqProvider

        provider = GroqProvider(api_key="explicit-key")

        assert provider._api_key == "explicit-key"
        mock_groq.assert_called_once_with(api_key="explicit-key")


class TestGeminiProvider:
    """Tests for Gemini provider implementation."""

    @pytest.mark.unit
    @patch('src.providers.gemini_provider.GEMINI_AVAILABLE', True)
    @patch('src.providers.gemini_provider.genai')
    def test_gemini_provider_initialization(self, mock_genai):
        """Test Gemini provider can be initialized."""
        from src.providers.gemini_provider import GeminiProvider

        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key'}):
            provider = GeminiProvider()

            assert provider.name == "gemini"
            assert len(provider.available_models) > 0

    @pytest.mark.unit
    @patch('src.providers.gemini_provider.GEMINI_AVAILABLE', True)
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

        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key'}):
            provider = GeminiProvider()
            response = provider.chat(
                messages=[{"role": "user", "content": "Hello Gemini"}]
            )

            assert isinstance(response, LLMResponse)
            assert response.content == "Gemini response"
            assert response.provider == "gemini"

    @pytest.mark.unit
    @patch('src.providers.gemini_provider.GEMINI_AVAILABLE', True)
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

        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key'}):
            provider = GeminiProvider()
            response = provider.chat(
                messages=[
                    {"role": "system", "content": "You are helpful"},
                    {"role": "user", "content": "Hello"}
                ]
            )

            assert response.content == "Response with system context"

    @pytest.mark.unit
    @patch('src.providers.gemini_provider.GEMINI_AVAILABLE', True)
    @patch('src.providers.gemini_provider.genai')
    def test_gemini_get_limits(self, mock_genai):
        """Test Gemini provider limits."""
        from src.providers.gemini_provider import GeminiProvider

        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key'}):
            provider = GeminiProvider()
            limits = provider.get_limits()

            assert isinstance(limits, ProviderLimits)


class TestCohereProvider:
    """Tests for Cohere provider implementation."""

    @pytest.mark.unit
    @patch('src.providers.cohere_provider.COHERE_AVAILABLE', True)
    @patch('src.providers.cohere_provider.cohere')
    def test_cohere_provider_initialization(self, mock_cohere):
        """Test Cohere provider can be initialized."""
        from src.providers.cohere_provider import CohereProvider

        mock_cohere.ClientV2.return_value = MagicMock()
        mock_cohere.Client.return_value = MagicMock()

        with patch.dict('os.environ', {'COHERE_API_KEY': 'test-key'}):
            provider = CohereProvider()

            assert provider.name == "cohere"
            assert len(provider.available_models) > 0

    @pytest.mark.unit
    @patch('src.providers.cohere_provider.COHERE_AVAILABLE', True)
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
        mock_response.meta = MagicMock()
        mock_response.meta.tokens = MagicMock(input_tokens=15, output_tokens=25)
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
    @patch('src.providers.cohere_provider.COHERE_AVAILABLE', True)
    @patch('src.providers.cohere_provider.cohere')
    def test_cohere_get_limits(self, mock_cohere):
        """Test Cohere provider limits."""
        from src.providers.cohere_provider import CohereProvider

        mock_cohere.ClientV2.return_value = MagicMock()
        mock_cohere.Client.return_value = MagicMock()

        with patch.dict('os.environ', {'COHERE_API_KEY': 'test-key'}):
            provider = CohereProvider()
            limits = provider.get_limits()

            assert isinstance(limits, ProviderLimits)
            assert limits.requests_per_minute == 20
            assert limits.requests_per_month == 1000

    @pytest.mark.unit
    def test_cohere_missing_api_key_raises_error(self):
        """Test Cohere raises error when API key missing."""
        from src.providers.cohere_provider import CohereProvider
        import src.providers.cohere_provider as cohere_module

        original = cohere_module.COHERE_AVAILABLE
        cohere_module.COHERE_AVAILABLE = True

        try:
            with patch.dict('os.environ', {}, clear=True):
                with pytest.raises(ValueError, match="COHERE_API_KEY"):
                    CohereProvider()
        finally:
            cohere_module.COHERE_AVAILABLE = original

    @pytest.mark.unit
    @patch('src.providers.cohere_provider.COHERE_AVAILABLE', True)
    @patch('src.providers.cohere_provider.cohere')
    def test_cohere_invalid_model_raises_error(self, mock_cohere):
        """Test Cohere raises error for invalid model."""
        from src.providers.cohere_provider import CohereProvider

        mock_cohere.ClientV2.return_value = MagicMock()
        mock_cohere.Client.return_value = MagicMock()

        with patch.dict('os.environ', {'COHERE_API_KEY': 'test-key'}):
            provider = CohereProvider()

            with pytest.raises(ValueError, match="not supported"):
                provider.chat([{"role": "user", "content": "test"}], model="invalid-model")

    @pytest.mark.unit
    @patch('src.providers.cohere_provider.COHERE_AVAILABLE', True)
    @patch('src.providers.cohere_provider.cohere')
    def test_cohere_get_model_for_task_fast(self, mock_cohere):
        """Test Cohere recommends fast model."""
        from src.providers.cohere_provider import CohereProvider

        mock_cohere.ClientV2.return_value = MagicMock()
        mock_cohere.Client.return_value = MagicMock()

        with patch.dict('os.environ', {'COHERE_API_KEY': 'test-key'}):
            provider = CohereProvider()
            model = provider.get_model_for_task('fast')
            assert model == 'command-r7b-12-2024'

    @pytest.mark.unit
    @patch('src.providers.cohere_provider.COHERE_AVAILABLE', True)
    @patch('src.providers.cohere_provider.cohere')
    def test_cohere_get_model_for_task_quality(self, mock_cohere):
        """Test Cohere recommends quality model."""
        from src.providers.cohere_provider import CohereProvider

        mock_cohere.ClientV2.return_value = MagicMock()
        mock_cohere.Client.return_value = MagicMock()

        with patch.dict('os.environ', {'COHERE_API_KEY': 'test-key'}):
            provider = CohereProvider()
            model = provider.get_model_for_task('quality')
            assert model == 'command-a-03-2025'

    @pytest.mark.unit
    @patch('src.providers.cohere_provider.COHERE_AVAILABLE', True)
    @patch('src.providers.cohere_provider.cohere')
    def test_cohere_get_model_for_task_reasoning(self, mock_cohere):
        """Test Cohere recommends reasoning model."""
        from src.providers.cohere_provider import CohereProvider

        mock_cohere.ClientV2.return_value = MagicMock()
        mock_cohere.Client.return_value = MagicMock()

        with patch.dict('os.environ', {'COHERE_API_KEY': 'test-key'}):
            provider = CohereProvider()
            model = provider.get_model_for_task('reasoning')
            assert model == 'command-a-reasoning-08-2025'

    @pytest.mark.unit
    @patch('src.providers.cohere_provider.COHERE_AVAILABLE', True)
    @patch('src.providers.cohere_provider.cohere')
    def test_cohere_get_model_for_task_multilingual(self, mock_cohere):
        """Test Cohere recommends multilingual model."""
        from src.providers.cohere_provider import CohereProvider

        mock_cohere.ClientV2.return_value = MagicMock()
        mock_cohere.Client.return_value = MagicMock()

        with patch.dict('os.environ', {'COHERE_API_KEY': 'test-key'}):
            provider = CohereProvider()
            model = provider.get_model_for_task('multilingual')
            assert model == 'c4ai-aya-expanse-32b'

    @pytest.mark.unit
    @patch('src.providers.cohere_provider.COHERE_AVAILABLE', True)
    @patch('src.providers.cohere_provider.cohere')
    def test_cohere_get_model_for_task_unknown(self, mock_cohere):
        """Test Cohere returns default for unknown task."""
        from src.providers.cohere_provider import CohereProvider

        mock_cohere.ClientV2.return_value = MagicMock()
        mock_cohere.Client.return_value = MagicMock()

        with patch.dict('os.environ', {'COHERE_API_KEY': 'test-key'}):
            provider = CohereProvider()
            model = provider.get_model_for_task('unknown')
            assert model == provider.default_model

    @pytest.mark.unit
    @patch('src.providers.cohere_provider.COHERE_AVAILABLE', True)
    @patch('src.providers.cohere_provider.cohere')
    def test_cohere_is_available(self, mock_cohere):
        """Test Cohere is_available returns True when configured."""
        from src.providers.cohere_provider import CohereProvider

        mock_cohere.ClientV2.return_value = MagicMock()
        mock_cohere.Client.return_value = MagicMock()

        with patch.dict('os.environ', {'COHERE_API_KEY': 'test-key'}):
            provider = CohereProvider()
            assert provider.is_available() is True

    @pytest.mark.unit
    @patch('src.providers.cohere_provider.COHERE_AVAILABLE', True)
    @patch('src.providers.cohere_provider.cohere')
    def test_cohere_embed(self, mock_cohere):
        """Test Cohere embed method."""
        from src.providers.cohere_provider import CohereProvider

        mock_client_v1 = MagicMock()
        mock_response = MagicMock()
        mock_response.embeddings = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        mock_client_v1.embed.return_value = mock_response
        mock_cohere.ClientV2.return_value = MagicMock()
        mock_cohere.Client.return_value = mock_client_v1

        with patch.dict('os.environ', {'COHERE_API_KEY': 'test-key'}):
            provider = CohereProvider()
            embeddings = provider.embed(["text1", "text2"])

            assert len(embeddings) == 2
            assert embeddings[0] == [0.1, 0.2, 0.3]

    @pytest.mark.unit
    @patch('src.providers.cohere_provider.COHERE_AVAILABLE', True)
    @patch('src.providers.cohere_provider.cohere')
    def test_cohere_get_remaining_budget(self, mock_cohere):
        """Test Cohere get_remaining_budget method."""
        from src.providers.cohere_provider import CohereProvider

        mock_cohere.ClientV2.return_value = MagicMock()
        mock_cohere.Client.return_value = MagicMock()

        with patch.dict('os.environ', {'COHERE_API_KEY': 'test-key'}):
            provider = CohereProvider()
            budget = provider.get_remaining_budget()

            assert 'session_calls' in budget
            assert 'estimated_monthly_remaining' in budget
            assert 'warning' in budget
            assert budget['session_calls'] == 0
            assert budget['estimated_monthly_remaining'] == 1000

    @pytest.mark.unit
    @patch('src.providers.cohere_provider.COHERE_AVAILABLE', True)
    @patch('src.providers.cohere_provider.cohere')
    def test_cohere_chat_tracks_calls(self, mock_cohere):
        """Test Cohere chat tracks call count."""
        from src.providers.cohere_provider import CohereProvider

        mock_client_v2 = MagicMock()
        mock_response = MagicMock()
        mock_content_block = MagicMock()
        mock_content_block.text = "Response"
        mock_response.message = MagicMock()
        mock_response.message.content = [mock_content_block]
        mock_response.meta = None
        mock_client_v2.chat.return_value = mock_response
        mock_cohere.ClientV2.return_value = mock_client_v2
        mock_cohere.Client.return_value = MagicMock()

        with patch.dict('os.environ', {'COHERE_API_KEY': 'test-key'}):
            provider = CohereProvider()

            provider.chat([{"role": "user", "content": "test"}])
            assert provider._calls_made == 1

            provider.chat([{"role": "user", "content": "test"}])
            assert provider._calls_made == 2

            budget = provider.get_remaining_budget()
            assert budget['session_calls'] == 2
            assert budget['estimated_monthly_remaining'] == 998

    @pytest.mark.unit
    @patch('src.providers.cohere_provider.COHERE_AVAILABLE', True)
    @patch('src.providers.cohere_provider.cohere')
    def test_cohere_chat_warns_on_milestone(self, mock_cohere, capsys):
        """Test Cohere chat warns every 10 calls."""
        from src.providers.cohere_provider import CohereProvider

        mock_client_v2 = MagicMock()
        mock_response = MagicMock()
        mock_content_block = MagicMock()
        mock_content_block.text = "Response"
        mock_response.message = MagicMock()
        mock_response.message.content = [mock_content_block]
        mock_response.meta = None
        mock_client_v2.chat.return_value = mock_response
        mock_cohere.ClientV2.return_value = mock_client_v2
        mock_cohere.Client.return_value = MagicMock()

        with patch.dict('os.environ', {'COHERE_API_KEY': 'test-key'}):
            provider = CohereProvider()

            # Make 10 calls to trigger warning
            for _ in range(10):
                provider.chat([{"role": "user", "content": "test"}])

            captured = capsys.readouterr()
            assert "WARNING: Cohere calls this session" in captured.out
            assert "10" in captured.out

    @pytest.mark.unit
    @patch('src.providers.cohere_provider.COHERE_AVAILABLE', True)
    @patch('src.providers.cohere_provider.cohere')
    def test_cohere_chat_with_no_meta(self, mock_cohere):
        """Test Cohere chat handles missing meta info."""
        from src.providers.cohere_provider import CohereProvider

        mock_client_v2 = MagicMock()
        mock_response = MagicMock()
        mock_content_block = MagicMock()
        mock_content_block.text = "Response"
        mock_response.message = MagicMock()
        mock_response.message.content = [mock_content_block]
        mock_response.meta = None  # No meta info
        mock_client_v2.chat.return_value = mock_response
        mock_cohere.ClientV2.return_value = mock_client_v2
        mock_cohere.Client.return_value = MagicMock()

        with patch.dict('os.environ', {'COHERE_API_KEY': 'test-key'}):
            provider = CohereProvider()
            response = provider.chat([{"role": "user", "content": "test"}])

            assert response.input_tokens == 0
            assert response.output_tokens == 0
            assert response.tokens_used == 0

    @pytest.mark.unit
    @patch('src.providers.cohere_provider.COHERE_AVAILABLE', True)
    @patch('src.providers.cohere_provider.cohere')
    def test_cohere_default_model(self, mock_cohere):
        """Test Cohere default model is set correctly."""
        from src.providers.cohere_provider import CohereProvider

        mock_cohere.ClientV2.return_value = MagicMock()
        mock_cohere.Client.return_value = MagicMock()

        with patch.dict('os.environ', {'COHERE_API_KEY': 'test-key'}):
            provider = CohereProvider()
            assert provider.default_model == 'command-r7b-12-2024'

    @pytest.mark.unit
    @patch('src.providers.cohere_provider.COHERE_AVAILABLE', True)
    @patch('src.providers.cohere_provider.cohere')
    def test_cohere_with_explicit_api_key(self, mock_cohere):
        """Test Cohere initialization with explicit API key."""
        from src.providers.cohere_provider import CohereProvider

        mock_cohere.ClientV2.return_value = MagicMock()
        mock_cohere.Client.return_value = MagicMock()

        provider = CohereProvider(api_key="explicit-key")

        assert provider._api_key == "explicit-key"
        mock_cohere.ClientV2.assert_called_once_with(api_key="explicit-key")
        mock_cohere.Client.assert_called_once_with(api_key="explicit-key")


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
    @patch('src.providers.gemini_provider.GEMINI_AVAILABLE', True)
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

        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key'}):
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
