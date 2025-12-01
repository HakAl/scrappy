import pytest
import os
from unittest.mock import MagicMock, patch, AsyncMock
from scrappy.providers.gemini_provider import GeminiProvider


# --- Fixtures ---

@pytest.fixture
def mock_env_setup(monkeypatch):
    """Ensure environment variables are set."""
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-123")


@pytest.fixture
def mock_genai():
    """Mock the google.generativeai module."""
    with patch("scrappy.providers.gemini_provider.genai") as mock:
        # Setup default response structure
        mock_response = MagicMock()
        mock_response.text = "Gemini response"
        mock_response.usage_metadata.prompt_token_count = 10
        mock_response.usage_metadata.candidates_token_count = 20

        # Setup the model instance
        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response

        mock.GenerativeModel.return_value = mock_model
        yield mock


@pytest.fixture
def provider(mock_env_setup, mock_genai):
    """Return an initialized provider with mocked dependencies."""
    # We must patch GEMINI_AVAILABLE to True to bypass the safe_import check
    with patch("scrappy.providers.gemini_provider.GEMINI_AVAILABLE", True):
        return GeminiProvider()


# --- Initialization Tests ---





# --- Message Formatting Tests ---

def test_message_conversion_standard(provider):
    """Should map roles correctly."""
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"}
    ]
    converted = provider._convert_messages(messages)

    assert len(converted) == 2
    assert converted[0]["role"] == "user"
    assert converted[1]["role"] == "model"  # Mapped from assistant


def test_message_conversion_system_role(provider):
    """Should convert system role to user prompt + acknowledgment."""
    messages = [
        {"role": "system", "content": "Be helpful."},
        {"role": "user", "content": "Question?"}
    ]
    converted = provider._convert_messages(messages)

    # System -> User Msg + Model Acknowledgment + Actual User Msg
    assert len(converted) == 3
    assert converted[0]["role"] == "user"
    assert "System instruction: Be helpful." in converted[0]["parts"][0]

    assert converted[1]["role"] == "model"
    assert "Understood" in converted[1]["parts"][0]

    assert converted[2]["role"] == "user"
    assert converted[2]["parts"][0] == "Question?"


def test_message_conversion_single_user(provider):
    """Optimization: Single user message returns raw string (supported by Gemini SDK)."""
    messages = [{"role": "user", "content": "Just this"}]
    converted = provider._convert_messages(messages)

    # Should return just the string content, not the list structure
    assert converted == "Just this"


# --- Synchronous Chat Tests ---

def test_chat_success(provider, mock_genai):
    """Should return a formatted LLMResponse on success."""
    messages = [{"role": "user", "content": "Hi"}]

    response = provider.chat(messages)

    assert response.content == "Gemini response"
    assert response.provider == "gemini"
    assert response.tokens_used == 30  # 10 + 20 from fixture
    assert response.metadata['fallback_used'] is False

    # Verify call
    mock_genai.GenerativeModel.assert_called()
    mock_genai.GenerativeModel.return_value.generate_content.assert_called_once()


def test_chat_fallback_logic(provider, mock_genai):
    """
    CRITICAL TEST: Should try next model if first hits rate limit.
    """
    # Setup: First call raises 429 (Rate limit), Second call succeeds

    # We need to mock the GenerativeModel constructor to return different mocks
    # or the same mock that behaves differently on subsequent calls.
    mock_model = mock_genai.GenerativeModel.return_value

    # Create an exception that looks like a rate limit
    rate_limit_error = Exception("429 Resource has been exhausted (e.g. check quota)")

    # Side effect: First call fails, second succeeds
    mock_model.generate_content.side_effect = [
        rate_limit_error,
        MagicMock(text="Fallback Success", usage_metadata=None)
    ]

    messages = [{"role": "user", "content": "Hi"}]

    # Use a specific preferred model
    response = provider.chat(messages, model="gemini-2.5-flash-lite", auto_fallback=True)

    assert response.content == "Fallback Success"
    assert response.metadata['fallback_used'] is True
    assert response.metadata['original_model'] == "gemini-2.5-flash-lite"

    # Ensure we tried at least two models
    assert len(response.metadata['attempted_models']) >= 2
    # Ensure the failed model was added to internal limit tracking
    assert "gemini-2.5-flash-lite" in provider._limited_models


def test_chat_fallback_exhaustion(provider, mock_genai):
    """Should raise RuntimeError if ALL models fail."""
    mock_model = mock_genai.GenerativeModel.return_value
    mock_model.generate_content.side_effect = Exception("429 Quota exceeded")

    messages = [{"role": "user", "content": "Hi"}]

    with pytest.raises(RuntimeError) as exc:
        provider.chat(messages, auto_fallback=True)

    assert "All providers rate limited" in str(exc.value)




# --- Asynchronous Chat Tests ---

@pytest.mark.asyncio
async def test_chat_async_success(provider):
    """Should use httpx for async calls."""
    messages = [{"role": "user", "content": "Hi"}]

    # Mock httpx response data
    mock_json = {
        "candidates": [{"content": {"parts": [{"text": "Async Response"}]}}],
        "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 5}
    }

    with patch("scrappy.providers.gemini_provider.HTTPX_AVAILABLE", True):
        with patch("httpx.AsyncClient") as MockClient:
            # Setup mock client context manager
            mock_client_instance = AsyncMock()
            MockClient.return_value.__aenter__.return_value = mock_client_instance

            # Setup post response
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_json
            mock_client_instance.post.return_value = mock_response

            response = await provider.chat_async(messages)

            assert response.content == "Async Response"
            assert response.metadata['async'] is True
            mock_client_instance.post.assert_called_once()


@pytest.mark.asyncio
async def test_chat_async_fallback(provider):
    """Should handle fallback in async mode via HTTP 429 codes."""
    messages = [{"role": "user", "content": "Hi"}]

    with patch("scrappy.providers.gemini_provider.HTTPX_AVAILABLE", True):
        with patch("httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            MockClient.return_value.__aenter__.return_value = mock_client_instance

            # Response 1: 429 Too Many Requests
            resp_fail = MagicMock()
            resp_fail.status_code = 429

            # Response 2: 200 OK
            resp_success = MagicMock()
            resp_success.status_code = 200
            resp_success.json.return_value = {
                "candidates": [{"content": {"parts": [{"text": "Async Fallback"}]}}]
            }

            # Side effect for post()
            mock_client_instance.post.side_effect = [resp_fail, resp_success]

            response = await provider.chat_async(
                messages,
                model="gemini-2.5-flash-lite",
                auto_fallback=True
            )

            assert response.content == "Async Fallback"
            assert response.metadata['fallback_used'] is True
            # Should have been called twice (once for fail, once for success)
            assert mock_client_instance.post.call_count == 2


# --- Utility Tests ---

def test_limits_tracking(provider):
    """Should track and reset limited models."""
    provider._limited_models.add("gemini-2.0-flash")

    summary = provider.get_usage_summary()
    assert "gemini-2.0-flash" in summary["limited_models"]
    assert "gemini-2.0-flash" not in summary["available_models"]

    provider.reset_limited_models()
    assert len(provider._limited_models) == 0


# --- Null Content Handling Tests (Issue: NO_OUTPUT.md Issue 3) ---

def test_chat_returns_empty_string_when_response_text_is_none(provider, mock_genai):
    """
    ISSUE: _single_model_chat() does not handle None response.text from API.

    When the Gemini API returns None for response.text, the LLMResponse
    should contain an empty string, not None.

    EXPECTED: LLMResponse.content should be "" (empty string), not None.
    """
    # Setup mock to return None for text
    mock_model = mock_genai.GenerativeModel.return_value
    mock_response = MagicMock()
    mock_response.text = None  # API returns None
    mock_response.usage_metadata = None
    mock_model.generate_content.return_value = mock_response

    messages = [{"role": "user", "content": "Hi"}]

    response = provider.chat(messages)

    # LLMResponse.content is typed as `str`, not `Optional[str]`
    # So we should get empty string, not None
    assert response.content is not None, "content should not be None"
    assert isinstance(response.content, str), "content should be a string"
    assert response.content == "", "content should be empty string when API returns None"