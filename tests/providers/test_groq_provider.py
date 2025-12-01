"""
Tests for Groq LLM Provider implementation.

Focuses on null content handling (Issue: NO_OUTPUT.md Issue 3).
"""

import pytest
import os
from unittest.mock import Mock, patch
from types import SimpleNamespace

from scrappy.providers.groq_provider import GroqProvider
from scrappy.providers.base import LLMResponse


# --- Fixtures ---

@pytest.fixture
def mock_env():
    """Sets up environment variables."""
    with patch.dict(os.environ, {"GROQ_API_KEY": "sk-test-key"}):
        yield


@pytest.fixture
def mock_groq_client():
    """Mocks the Groq class and the returned client instance."""
    with patch("scrappy.providers.groq_provider.Groq") as MockClass:
        mock_client = Mock()
        MockClass.return_value = mock_client
        yield MockClass, mock_client


@pytest.fixture
def provider(mock_env, mock_groq_client):
    """Returns a GroqProvider instance with mocked dependencies."""
    return GroqProvider()


def create_mock_completion(content="Hello", tokens_in=10, tokens_out=20, finish_reason="stop"):
    """Creates a mock object mimicking the Groq API response structure."""
    usage = SimpleNamespace(
        prompt_tokens=tokens_in,
        completion_tokens=tokens_out,
        total_tokens=tokens_in + tokens_out,
    )
    message = SimpleNamespace(content=content, tool_calls=None)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    response = SimpleNamespace(choices=[choice], usage=usage)
    return response


# --- Basic Tests ---

def test_init_success(mock_env, mock_groq_client):
    """Test successful initialization with env var."""
    provider = GroqProvider()
    assert provider.name == "groq"
    assert provider.is_available()
    mock_groq_client[0].assert_called_once()


def test_chat_basic_flow(provider, mock_groq_client):
    """Test standard synchronous chat."""
    _, client_instance = mock_groq_client

    mock_response = create_mock_completion(content="Test Response")
    client_instance.chat.completions.create.return_value = mock_response

    messages = [{"role": "user", "content": "Hi"}]
    response = provider.chat(messages)

    assert isinstance(response, LLMResponse)
    assert response.content == "Test Response"
    assert response.provider == "groq"


# --- Null Content Handling Tests (Issue: NO_OUTPUT.md Issue 3) ---

def test_chat_returns_empty_string_when_api_returns_none_content(provider, mock_groq_client):
    """
    ISSUE: chat() does not handle None content from API.
    chat_with_tools() has `content=message.content or ""` but chat() does not.

    When the Groq API returns None for message.content, the LLMResponse
    should contain an empty string, not None.

    EXPECTED: LLMResponse.content should be "" (empty string), not None.
    """
    _, client_instance = mock_groq_client

    # API returns None for content (can happen with some API responses)
    mock_response = create_mock_completion(content=None)
    client_instance.chat.completions.create.return_value = mock_response

    messages = [{"role": "user", "content": "Hi"}]
    response = provider.chat(messages)

    # LLMResponse.content is typed as `str`, not `Optional[str]`
    # So we should get empty string, not None
    assert response.content is not None, "content should not be None"
    assert isinstance(response.content, str), "content should be a string"
    assert response.content == "", "content should be empty string when API returns None"
