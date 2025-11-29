"""
Comprehensive tests for orchestrator adapter classes.

Tests LLMResponse, NullContext, AgentOrchestratorAdapter, and SimpleLLMAdapter.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from src.orchestrator_adapter import (
    LLMResponse,
    NullContext,
    ContextProvider,
    AgentOrchestratorAdapter
)


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    @pytest.mark.unit
    def test_creation_with_minimal_args(self):
        """Test creating response with minimal arguments."""
        response = LLMResponse(
            content="Hello world",
            provider="groq",
            model=""
        )

        assert response.content == "Hello world"
        assert response.provider == "groq"
        assert response.model == ""
        assert response.tokens_used == 0

    @pytest.mark.unit
    def test_creation_with_all_args(self):
        """Test creating response with all arguments."""
        response = LLMResponse(
            content="Full response",
            provider="cerebras",
            model="llama-3.3-70b",
            tokens_used=500
        )

        assert response.content == "Full response"
        assert response.provider == "cerebras"
        assert response.model == "llama-3.3-70b"
        assert response.tokens_used == 500

    @pytest.mark.unit
    def test_empty_content(self):
        """Test response with empty content."""
        response = LLMResponse(content="", provider="test", model="")
        assert response.content == ""

    @pytest.mark.unit
    def test_large_token_count(self):
        """Test response with large token count."""
        response = LLMResponse(
            content="x" * 100000,
            provider="test",
            model="",
            tokens_used=100000
        )
        assert response.tokens_used == 100000

    @pytest.mark.unit
    def test_tool_calls_field_exists(self):
        """Test that LLMResponse has tool_calls field for native tool calling."""
        response = LLMResponse(
            content="I'll help with that",
            provider="groq",
            model="llama-3.1-8b"
        )
        # tool_calls should default to None
        assert response.tool_calls is None

    @pytest.mark.unit
    def test_tool_calls_can_be_set(self):
        """Test that tool_calls can be populated with ToolCall objects."""
        from src.providers.base import ToolCall

        tool_calls = [
            ToolCall(id="call_1", name="read_file", arguments={"path": "/test.py"}),
            ToolCall(id="call_2", name="search_code", arguments={"pattern": "def main"})
        ]

        response = LLMResponse(
            content="Let me read that file",
            provider="groq",
            model="llama-3.1-8b",
            tool_calls=tool_calls
        )

        assert response.tool_calls is not None
        assert len(response.tool_calls) == 2
        assert response.tool_calls[0].name == "read_file"
        assert response.tool_calls[0].arguments == {"path": "/test.py"}
        assert response.tool_calls[1].name == "search_code"

    @pytest.mark.unit
    def test_response_with_metadata(self):
        """Test that LLMResponse includes metadata field."""
        response = LLMResponse(
            content="Response",
            provider="groq",
            model="llama-3.1-8b",
            metadata={"finish_reason": "tool_calls", "model_config": {"speed": "fast"}}
        )

        assert response.metadata["finish_reason"] == "tool_calls"
        assert response.metadata["model_config"]["speed"] == "fast"


class TestNullContext:
    """Tests for NullContext provider."""

    @pytest.mark.unit
    def test_is_explored_returns_false(self):
        """Test that NullContext is never explored."""
        context = NullContext()
        assert context.is_explored() is False

    @pytest.mark.unit
    def test_get_summary_returns_empty_string(self):
        """Test that NullContext returns empty summary."""
        context = NullContext()
        assert context.get_summary() == ""


class TestAgentOrchestratorAdapterSelectionType:
    """Tests for AgentOrchestratorAdapter selection_type handling."""

    @pytest.mark.unit
    def test_adapter_does_not_pass_none_selection_type(self):
        """Adapter should not pass selection_type=None, letting orchestrator use its default."""
        # Create mock orchestrator that tracks calls
        mock_orch = Mock()
        mock_response = Mock()
        mock_response.content = "test response"
        mock_response.model = "test-model"
        mock_response.provider = "test-provider"
        mock_response.tokens_used = 10
        mock_response.tool_calls = None
        mock_orch.delegate.return_value = mock_response

        # Create adapter with mock orchestrator
        adapter = AgentOrchestratorAdapter(mock_orch)

        # Call delegate WITHOUT selection_type (defaults to None)
        adapter.delegate(prompt="test prompt")

        # Verify orchestrator.delegate was called
        assert mock_orch.delegate.called

        # Get the kwargs that were passed to orchestrator
        call_kwargs = mock_orch.delegate.call_args[1]

        # selection_type should NOT be in kwargs (so orchestrator can use its default)
        assert 'selection_type' not in call_kwargs, (
            "Adapter should not pass selection_type=None, "
            "this overrides orchestrator's default value"
        )

    @pytest.mark.unit
    def test_adapter_passes_explicit_selection_type(self):
        """Adapter should pass selection_type when explicitly provided."""
        from src.orchestrator.model_selection import ModelSelectionType

        # Create mock orchestrator
        mock_orch = Mock()
        mock_response = Mock()
        mock_response.content = "test response"
        mock_response.model = "test-model"
        mock_response.provider = "test-provider"
        mock_response.tokens_used = 10
        mock_response.tool_calls = None
        mock_orch.delegate.return_value = mock_response

        # Create adapter
        adapter = AgentOrchestratorAdapter(mock_orch)

        # Call delegate WITH explicit selection_type
        adapter.delegate(
            prompt="test prompt",
            selection_type=ModelSelectionType.QUALITY
        )

        # Get the kwargs that were passed to orchestrator
        call_kwargs = mock_orch.delegate.call_args[1]

        # selection_type SHOULD be in kwargs when explicitly provided
        assert 'selection_type' in call_kwargs
        assert call_kwargs['selection_type'] == ModelSelectionType.QUALITY
