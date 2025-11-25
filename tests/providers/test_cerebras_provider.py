import pytest
import os
import json
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from types import SimpleNamespace

# Assumes the class is in src/providers/cerebras_provider.py
from src.providers.cerebras_provider import CerebrasProvider
from src.providers.base import LLMResponse, ToolCall, ProviderLimits


# -----------------------------------------------------------------------------
# Fixtures & Helpers
# -----------------------------------------------------------------------------

@pytest.fixture
def mock_env():
    """Sets up environment variables."""
    with patch.dict(os.environ, {"CEREBRAS_API_KEY": "sk-test-key"}):
        yield


@pytest.fixture
def mock_openai_client():
    """Mocks the OpenAI class and the returned client instance."""
    with patch("src.providers.cerebras_provider.OpenAI") as MockClass:
        mock_client = Mock()
        MockClass.return_value = mock_client
        yield MockClass, mock_client


@pytest.fixture
def provider(mock_env, mock_openai_client):
    """Returns a CerebrasProvider instance with mocked dependencies."""
    return CerebrasProvider()


def create_mock_completion(content="Hello", tokens_in=10, tokens_out=20,
                           finish_reason="stop", tool_calls=None,
                           latency=0.5, speed=100.0):
    """
    Creates a mock object mimicking the OpenAI API response structure,
    including Cerebras-specific attributes on the usage object.
    """
    # Mock Usage object with standard and dynamic attributes
    usage = SimpleNamespace(
        prompt_tokens=tokens_in,
        completion_tokens=tokens_out,
        total_tokens=tokens_in + tokens_out,
        completion_tokens_per_sec=speed,
        total_latency=latency
    )

    # Mock Message object
    message = SimpleNamespace(content=content, tool_calls=tool_calls)

    # Mock Choice object
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)

    # Root response object
    response = SimpleNamespace(choices=[choice], usage=usage)
    return response


# -----------------------------------------------------------------------------
# Initialization Tests
# -----------------------------------------------------------------------------

def test_init_success(mock_env, mock_openai_client):
    """Test successful initialization with env var."""
    provider = CerebrasProvider()
    assert provider.name == "cerebras"
    assert provider.is_available()
    mock_openai_client[0].assert_called_once()  # Class was instantiated


def test_init_with_explicit_key(mock_openai_client):
    """Test initialization passing key directly."""
    with patch.dict(os.environ, {}, clear=True):
        provider = CerebrasProvider(api_key="direct-key")
        assert provider._api_key == "direct-key"


def test_init_raises_missing_key():
    """Test initialization fails if no key provided."""
    with patch.dict(os.environ, {}, clear=True):
        # We also need to mock safe_import or OPENAI_AVAILABLE so it doesn't fail on that first
        with patch("src.providers.cerebras_provider.OPENAI_AVAILABLE", True):
            with pytest.raises(ValueError) as exc:  # raises raise_env_var_not_found
                CerebrasProvider()
            assert "CEREBRAS_API_KEY" in str(exc.value)


def test_init_raises_missing_package():
    """Test initialization fails if openai package is missing."""
    with patch("src.providers.cerebras_provider.OPENAI_AVAILABLE", False):
        with pytest.raises(ImportError) as exc:
            CerebrasProvider(api_key="test")
        assert "openai" in str(exc.value)


# -----------------------------------------------------------------------------
# Sync Chat Tests
# -----------------------------------------------------------------------------

def test_chat_basic_flow(provider, mock_openai_client):
    """Test standard synchronous chat."""
    _, client_instance = mock_openai_client

    # Setup mock response
    mock_response = create_mock_completion(content="Test Response")
    client_instance.chat.completions.create.return_value = mock_response

    messages = [{"role": "user", "content": "Hi"}]
    response = provider.chat(messages)

    assert isinstance(response, LLMResponse)
    assert response.content == "Test Response"
    assert response.provider == "cerebras"
    assert response.metadata['tokens_per_sec'] == 100.0  # From create_mock_completion default
    assert response.metadata['cerebras_latency'] == 0.5


def test_chat_invalid_model(provider):
    """Test that invalid models raise an error."""
    with pytest.raises(ValueError) as exc:
        provider.chat([{"role": "user", "content": "Hi"}], model="gpt-4-fake")
    assert "not supported" in str(exc.value)


def test_chat_with_tools(provider, mock_openai_client):
    """Test native tool calling support."""
    _, client_instance = mock_openai_client

    # Create a mock tool call
    tool_call_obj = SimpleNamespace(
        id="call_123",
        function=SimpleNamespace(name="get_weather", arguments='{"city": "Paris"}')
    )

    mock_response = create_mock_completion(
        content=None,
        tool_calls=[tool_call_obj],
        finish_reason="tool_calls"
    )
    client_instance.chat.completions.create.return_value = mock_response

    tools = [{"type": "function", "function": {"name": "get_weather"}}]
    response = provider.chat_with_tools([], tools=tools)

    assert response.tool_calls is not None
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "get_weather"
    assert response.tool_calls[0].arguments == {"city": "Paris"}
    assert response.metadata['finish_reason'] == "tool_calls"


# -----------------------------------------------------------------------------
# Async Chat Tests (Custom Implementation)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_async_success(provider):
    """Test async chat using httpx mock."""

    # Prepare mock response data
    mock_json = {
        "choices": [{"message": {"content": "Async Hello"}, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": 5,
            "completion_tokens": 5,
            "completion_tokens_per_sec": 500.0,
            "total_latency": 0.1
        }
    }

    # Mock httpx.AsyncClient
    with patch("src.providers.cerebras_provider.httpx.AsyncClient") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.__aenter__.return_value = mock_instance

        # Configure post response
        mock_post_resp = Mock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = mock_json
        mock_instance.post = AsyncMock(return_value=mock_post_resp)

        response = await provider.chat_async([{"role": "user", "content": "Hi"}])

        assert response.content == "Async Hello"
        assert response.metadata['async'] is True
        assert response.metadata['tokens_per_sec'] == 500.0


@pytest.mark.asyncio
async def test_chat_async_rate_limit_retry(provider):
    """
    Test that chat_async retries on 429 errors.

    Sequence:
    1. 429 Error (Rate Limit)
    2. 200 OK (Success)
    """
    success_json = {
        "choices": [{"message": {"content": "Finally"}, "finish_reason": "stop"}],
        "usage": {}
    }

    with patch("src.providers.cerebras_provider.httpx.AsyncClient") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.__aenter__.return_value = mock_instance

        # Setup responses: First 429, Then 200
        bad_resp = Mock()
        bad_resp.status_code = 429

        good_resp = Mock()
        good_resp.status_code = 200
        good_resp.json.return_value = success_json

        # Mock the post method to return bad_resp first, then good_resp
        mock_instance.post = AsyncMock(side_effect=[bad_resp, good_resp])

        # Mock asyncio.sleep to skip waiting in tests
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            response = await provider.chat_async([{"role": "user", "content": "Hi"}])

            assert response.content == "Finally"
            assert response.metadata['retry_attempts'] == 1  # 0-indexed, so 1 means 2nd try

            # Ensure we waited
            mock_sleep.assert_called_once()
            assert mock_instance.post.call_count == 2


@pytest.mark.asyncio
async def test_chat_async_exhausted_retries(provider):
    """Test that exception is raised after max retries."""
    with patch("src.providers.cerebras_provider.httpx.AsyncClient") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.__aenter__.return_value = mock_instance

        bad_resp = Mock()
        bad_resp.status_code = 429
        mock_instance.post = AsyncMock(return_value=bad_resp)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(Exception) as exc:
                await provider.chat_async(
                    [{"role": "user", "content": "Hi"}],
                    max_retries=2
                )
            assert "Rate limit" in str(exc.value)


@pytest.mark.asyncio
async def test_chat_async_fallback_if_no_httpx(provider):
    """Test fallback to parent method if httpx is missing."""

    # Simulate HTTPX_AVAILABLE = False
    with patch("src.providers.cerebras_provider.HTTPX_AVAILABLE", False):
        # Mock the super().chat_async behavior (which calls synchronous chat in a thread usually)
        # Since we can't easily patch super(), we rely on the fact that base.chat_async calls self.chat

        # We just mock self.chat to return a result
        with patch.object(provider, 'chat') as mock_chat:
            mock_chat.return_value = LLMResponse("Fallback Content", "model", "cerebras")

            result = await provider.chat_async([{"role": "user", "content": "test"}])

            assert result.content == "Fallback Content"
            # Verify we didn't try to use httpx
            # (implied by reaching here without httpx errors)


# -----------------------------------------------------------------------------
# Utility & Config Tests
# -----------------------------------------------------------------------------

def test_get_limits(provider):
    """Verify hardcoded limit retrieval."""
    limits = provider.get_limits()
    assert isinstance(limits, ProviderLimits)
    # Check Llama 3.1 8B defaults
    assert limits.requests_per_day == 14400
    assert limits.tokens_per_minute == 60000


def test_get_model_for_task(provider):
    """Verify model selection logic."""
    assert provider.get_model_for_task("fast") == "llama3.1-8b"
    assert provider.get_model_for_task("high_volume") == "llama3.1-8b"
    assert provider.get_model_for_task("quality") == "llama-3.3-70b"
    # Unknown tasks use the default model (qwen instruct for better tool-calling)
    assert provider.get_model_for_task("unknown_task") == "qwen-3-235b-a22b-instruct-2507"

def test_get_model_info(provider):
    """Verify detailed model info retrieval."""
    from src.providers.base import ModelInfo

    # Known model
    info = provider.get_model_info("llama3.1-8b")
    assert isinstance(info, ModelInfo)
    assert info.id == "llama3.1-8b"
    assert info.context_length == 8192
    assert info.rpd == 14400
    assert info.tpm == 60000
    assert info.quality == "good"
    assert info.speed == "ultra_fast"

    # Unknown model (should fall back to generic via parent class)
    info_generic = provider.get_model_info("unknown-model")
    assert info_generic.id == "unknown-model"