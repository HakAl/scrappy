"""
Comprehensive tests for orchestrator adapter classes.

Tests LLMResponse, NullContext, AgentOrchestratorAdapter,
SimpleLLMAdapter, and MockOrchestratorAdapter.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from src.orchestrator_adapter import (
    LLMResponse,
    NullContext,
    AgentOrchestratorAdapter,
    SimpleLLMAdapter,
    MockOrchestratorAdapter,
    ContextProvider,
    OrchestratorAdapter
)


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    @pytest.mark.unit
    def test_creation_with_minimal_args(self):
        """Test creating response with minimal arguments."""
        response = LLMResponse(
            content="Hello world",
            provider="groq"
        )

        assert response.content == "Hello world"
        assert response.provider == "groq"
        assert response.model == ""
        assert response.tokens_used == 0
        assert response.cached is False

    @pytest.mark.unit
    def test_creation_with_all_args(self):
        """Test creating response with all arguments."""
        response = LLMResponse(
            content="Full response",
            provider="cerebras",
            model="llama-3.3-70b",
            tokens_used=500,
            cached=True
        )

        assert response.content == "Full response"
        assert response.provider == "cerebras"
        assert response.model == "llama-3.3-70b"
        assert response.tokens_used == 500
        assert response.cached is True

    @pytest.mark.unit
    def test_empty_content(self):
        """Test response with empty content."""
        response = LLMResponse(content="", provider="test")
        assert response.content == ""

    @pytest.mark.unit
    def test_large_token_count(self):
        """Test response with large token count."""
        response = LLMResponse(
            content="x" * 100000,
            provider="test",
            tokens_used=100000
        )
        assert response.tokens_used == 100000


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

    @pytest.mark.unit
    def test_implements_context_provider(self):
        """Test that NullContext implements ContextProvider protocol."""
        context = NullContext()
        assert isinstance(context, ContextProvider)


class TestAgentOrchestratorAdapter:
    """Tests for AgentOrchestratorAdapter."""

    @pytest.fixture
    def mock_orchestrator(self):
        """Create mock orchestrator."""
        orch = Mock()
        orch.context = Mock()
        orch.context.is_explored.return_value = True
        orch.context.get_summary.return_value = "Test codebase"
        orch.registry = Mock()
        orch.registry.list_available.return_value = ['groq', 'cerebras']
        return orch

    @pytest.mark.unit
    def test_initialization(self, mock_orchestrator):
        """Test adapter initialization."""
        adapter = AgentOrchestratorAdapter(mock_orchestrator)

        assert adapter._orch is mock_orchestrator
        assert adapter._preferred_provider is None
        assert adapter._preferred_model is None

    @pytest.mark.unit
    def test_set_preferred_provider(self, mock_orchestrator):
        """Test setting preferred provider."""
        adapter = AgentOrchestratorAdapter(mock_orchestrator)

        adapter.set_preferred_provider("cerebras", "llama-3.3-70b")

        assert adapter._preferred_provider == "cerebras"
        assert adapter._preferred_model == "llama-3.3-70b"

    @pytest.mark.unit
    def test_set_preferred_provider_without_model(self, mock_orchestrator):
        """Test setting preferred provider without model."""
        adapter = AgentOrchestratorAdapter(mock_orchestrator)

        adapter.set_preferred_provider("groq")

        assert adapter._preferred_provider == "groq"
        assert adapter._preferred_model is None

    @pytest.mark.unit
    def test_get_preferred_provider(self, mock_orchestrator):
        """Test getting preferred provider."""
        adapter = AgentOrchestratorAdapter(mock_orchestrator)
        adapter.set_preferred_provider("gemini", "gemini-pro")

        provider, model = adapter.get_preferred_provider()

        assert provider == "gemini"
        assert model == "gemini-pro"

    @pytest.mark.unit
    def test_get_preferred_provider_not_set(self, mock_orchestrator):
        """Test getting preferred provider when not set."""
        adapter = AgentOrchestratorAdapter(mock_orchestrator)

        provider, model = adapter.get_preferred_provider()

        assert provider is None
        assert model is None

    @pytest.mark.unit
    def test_context_property(self, mock_orchestrator):
        """Test context property returns orchestrator context."""
        adapter = AgentOrchestratorAdapter(mock_orchestrator)

        context = adapter.context

        assert context is mock_orchestrator.context

    @pytest.mark.unit
    def test_list_providers(self, mock_orchestrator):
        """Test list_providers delegates to registry."""
        adapter = AgentOrchestratorAdapter(mock_orchestrator)

        providers = adapter.list_providers()

        assert providers == ['groq', 'cerebras']
        mock_orchestrator.registry.list_available.assert_called_once()

    @pytest.mark.unit
    def test_delegate_returns_llm_response(self, mock_orchestrator):
        """Test delegate wraps response correctly."""
        mock_orchestrator.delegate.return_value = LLMResponse(
            content="Test response",
            provider="groq",
            model="llama-3.1-8b",
            tokens_used=100
        )

        adapter = AgentOrchestratorAdapter(mock_orchestrator)

        response = adapter.delegate(
            "groq",
            "Test prompt",
            system_prompt="System",
            max_tokens=2000,
            temperature=0.5
        )

        assert isinstance(response, LLMResponse)
        assert response.content == "Test response"
        assert response.provider == "groq"
        mock_orchestrator.delegate.assert_called_once_with(
            "groq",
            "Test prompt",
            system_prompt="System",
            max_tokens=2000,
            temperature=0.5,
            use_context=False
        )

    @pytest.mark.unit
    def test_delegate_adapts_non_llmresponse(self, mock_orchestrator):
        """Test delegate adapts non-LLMResponse objects."""
        # Return a mock object that's not LLMResponse
        mock_response = Mock()
        mock_response.content = "Adapted response"
        mock_response.model = "test-model"
        mock_response.tokens_used = 200
        mock_response.cached = True
        mock_orchestrator.delegate.return_value = mock_response

        adapter = AgentOrchestratorAdapter(mock_orchestrator)

        response = adapter.delegate("groq", "prompt")

        assert isinstance(response, LLMResponse)
        assert response.content == "Adapted response"
        assert response.provider == "groq"
        assert response.model == "test-model"
        assert response.tokens_used == 200
        assert response.cached is True

    @pytest.mark.unit
    def test_delegate_handles_missing_attributes(self, mock_orchestrator):
        """Test delegate handles response without expected attributes."""
        mock_response = Mock(spec=[])  # No attributes
        # Make it not an instance of LLMResponse
        mock_orchestrator.delegate.return_value = "plain string response"

        adapter = AgentOrchestratorAdapter(mock_orchestrator)

        response = adapter.delegate("groq", "prompt")

        assert isinstance(response, LLMResponse)
        assert response.content == "plain string response"
        assert response.provider == "groq"

    @pytest.mark.unit
    def test_remember_file_read(self, mock_orchestrator):
        """Test remember_file_read proxy method."""
        mock_orchestrator.remember_file_read = Mock()

        adapter = AgentOrchestratorAdapter(mock_orchestrator)
        adapter.remember_file_read("/path/to/file.py", "file content", 100)

        mock_orchestrator.remember_file_read.assert_called_once_with(
            "/path/to/file.py", "file content", 100
        )

    @pytest.mark.unit
    def test_remember_file_read_no_method(self, mock_orchestrator):
        """Test remember_file_read when orchestrator doesn't have method."""
        del mock_orchestrator.remember_file_read

        adapter = AgentOrchestratorAdapter(mock_orchestrator)

        # Should not raise error
        adapter.remember_file_read("/path", "content", 10)

    @pytest.mark.unit
    def test_remember_search(self, mock_orchestrator):
        """Test remember_search proxy method."""
        mock_orchestrator.remember_search = Mock()

        adapter = AgentOrchestratorAdapter(mock_orchestrator)
        adapter.remember_search("test query", ["result1", "result2"])

        mock_orchestrator.remember_search.assert_called_once_with(
            "test query", ["result1", "result2"]
        )

    @pytest.mark.unit
    def test_remember_search_no_method(self, mock_orchestrator):
        """Test remember_search when orchestrator doesn't have method."""
        del mock_orchestrator.remember_search

        adapter = AgentOrchestratorAdapter(mock_orchestrator)

        # Should not raise error
        adapter.remember_search("query", [])

    @pytest.mark.unit
    def test_remember_git_operation(self, mock_orchestrator):
        """Test remember_git_operation proxy method."""
        mock_orchestrator.remember_git_operation = Mock()

        adapter = AgentOrchestratorAdapter(mock_orchestrator)
        adapter.remember_git_operation("commit", "Successfully committed")

        mock_orchestrator.remember_git_operation.assert_called_once_with(
            "commit", "Successfully committed"
        )

    @pytest.mark.unit
    def test_remember_git_operation_no_method(self, mock_orchestrator):
        """Test remember_git_operation when orchestrator doesn't have method."""
        del mock_orchestrator.remember_git_operation

        adapter = AgentOrchestratorAdapter(mock_orchestrator)

        # Should not raise error
        adapter.remember_git_operation("status", "clean")


class TestSimpleLLMAdapter:
    """Tests for SimpleLLMAdapter."""

    @pytest.mark.unit
    def test_initialization_minimal(self):
        """Test minimal initialization."""
        def simple_llm(prompt, **kwargs):
            return "response"

        adapter = SimpleLLMAdapter(simple_llm)

        assert adapter._provider_name == "default"
        assert isinstance(adapter._context, NullContext)

    @pytest.mark.unit
    def test_initialization_with_provider_name(self):
        """Test initialization with custom provider name."""
        def simple_llm(prompt, **kwargs):
            return "response"

        adapter = SimpleLLMAdapter(simple_llm, provider_name="custom")

        assert adapter._provider_name == "custom"

    @pytest.mark.unit
    def test_initialization_with_context(self):
        """Test initialization with custom context."""
        def simple_llm(prompt, **kwargs):
            return "response"

        custom_context = Mock()
        custom_context.is_explored.return_value = True

        adapter = SimpleLLMAdapter(simple_llm, context_provider=custom_context)

        assert adapter._context is custom_context

    @pytest.mark.unit
    def test_context_property(self):
        """Test context property returns context provider."""
        def simple_llm(prompt, **kwargs):
            return "response"

        adapter = SimpleLLMAdapter(simple_llm)

        context = adapter.context
        assert isinstance(context, NullContext)

    @pytest.mark.unit
    def test_list_providers_returns_single_provider(self):
        """Test list_providers returns single provider name."""
        def simple_llm(prompt, **kwargs):
            return "response"

        adapter = SimpleLLMAdapter(simple_llm, provider_name="my_llm")

        providers = adapter.list_providers()

        assert providers == ["my_llm"]

    @pytest.mark.unit
    def test_delegate_calls_llm_function(self):
        """Test delegate calls the LLM function."""
        def simple_llm(prompt, system_prompt=None, max_tokens=1500, temperature=0.3):
            return f"Response to: {prompt}"

        adapter = SimpleLLMAdapter(simple_llm, provider_name="test_llm")

        response = adapter.delegate(
            "ignored",  # Provider name is ignored
            "Hello",
            system_prompt="Be helpful",
            max_tokens=1000,
            temperature=0.7
        )

        assert isinstance(response, LLMResponse)
        assert response.content == "Response to: Hello"
        assert response.provider == "test_llm"

    @pytest.mark.unit
    def test_delegate_ignores_provider_param(self):
        """Test that delegate ignores provider parameter."""
        call_args = {}

        def simple_llm(prompt, **kwargs):
            call_args.update(kwargs)
            call_args['prompt'] = prompt
            return "response"

        adapter = SimpleLLMAdapter(simple_llm, provider_name="actual")

        response = adapter.delegate("different_provider", "test")

        # Should use actual provider name, not passed one
        assert response.provider == "actual"

    @pytest.mark.unit
    def test_delegate_passes_all_parameters(self):
        """Test that delegate passes all parameters to LLM function."""
        received_args = {}

        def simple_llm(prompt, system_prompt=None, max_tokens=1500, temperature=0.3):
            received_args['prompt'] = prompt
            received_args['system_prompt'] = system_prompt
            received_args['max_tokens'] = max_tokens
            received_args['temperature'] = temperature
            return "ok"

        adapter = SimpleLLMAdapter(simple_llm)

        adapter.delegate(
            "provider",
            "user prompt",
            system_prompt="system prompt",
            max_tokens=2500,
            temperature=0.9
        )

        assert received_args['prompt'] == "user prompt"
        assert received_args['system_prompt'] == "system prompt"
        assert received_args['max_tokens'] == 2500
        assert received_args['temperature'] == 0.9

    @pytest.mark.unit
    def test_implements_orchestrator_adapter_protocol(self):
        """Test SimpleLLMAdapter implements OrchestratorAdapter protocol."""
        def simple_llm(prompt, **kwargs):
            return "response"

        adapter = SimpleLLMAdapter(simple_llm)

        # Check it has required methods
        assert hasattr(adapter, 'context')
        assert hasattr(adapter, 'list_providers')
        assert hasattr(adapter, 'delegate')


class TestMockOrchestratorAdapter:
    """Tests for MockOrchestratorAdapter."""

    @pytest.mark.unit
    def test_initialization_empty(self):
        """Test initialization without responses."""
        adapter = MockOrchestratorAdapter()

        assert adapter._responses == []
        assert adapter._call_index == 0
        assert adapter._calls == []
        assert isinstance(adapter._context, NullContext)

    @pytest.mark.unit
    def test_initialization_with_responses(self):
        """Test initialization with predefined responses."""
        responses = ["response1", "response2"]
        adapter = MockOrchestratorAdapter(responses=responses)

        assert adapter._responses == ["response1", "response2"]

    @pytest.mark.unit
    def test_context_property(self):
        """Test context property returns NullContext."""
        adapter = MockOrchestratorAdapter()

        context = adapter.context
        assert isinstance(context, NullContext)

    @pytest.mark.unit
    def test_list_providers_returns_mock(self):
        """Test list_providers returns mock provider."""
        adapter = MockOrchestratorAdapter()

        providers = adapter.list_providers()

        assert providers == ["mock"]

    @pytest.mark.unit
    def test_add_response(self):
        """Test adding responses to queue."""
        adapter = MockOrchestratorAdapter()

        adapter.add_response("new response")

        assert "new response" in adapter._responses

    @pytest.mark.unit
    def test_add_multiple_responses(self):
        """Test adding multiple responses."""
        adapter = MockOrchestratorAdapter()

        adapter.add_response("first")
        adapter.add_response("second")
        adapter.add_response("third")

        assert len(adapter._responses) == 3

    @pytest.mark.unit
    def test_delegate_returns_responses_in_order(self):
        """Test delegate returns responses in FIFO order."""
        adapter = MockOrchestratorAdapter(responses=["first", "second", "third"])

        r1 = adapter.delegate("mock", "prompt1")
        r2 = adapter.delegate("mock", "prompt2")
        r3 = adapter.delegate("mock", "prompt3")

        assert r1.content == "first"
        assert r2.content == "second"
        assert r3.content == "third"

    @pytest.mark.unit
    def test_delegate_returns_default_when_exhausted(self):
        """Test delegate returns default response when queue exhausted."""
        adapter = MockOrchestratorAdapter(responses=["only one"])

        r1 = adapter.delegate("mock", "prompt1")
        r2 = adapter.delegate("mock", "prompt2")

        assert r1.content == "only one"
        assert "No more responses" in r2.content
        assert "complete" in r2.content

    @pytest.mark.unit
    def test_delegate_tracks_calls(self):
        """Test that delegate tracks all calls."""
        adapter = MockOrchestratorAdapter(responses=["response"])

        adapter.delegate(
            "provider",
            "test prompt",
            system_prompt="system",
            max_tokens=1000,
            temperature=0.5,
            use_context=True
        )

        calls = adapter.get_calls()
        assert len(calls) == 1
        assert calls[0]['provider'] == "provider"
        assert calls[0]['prompt'] == "test prompt"
        assert calls[0]['system_prompt'] == "system"
        assert calls[0]['max_tokens'] == 1000
        assert calls[0]['temperature'] == 0.5
        assert calls[0]['use_context'] is True

    @pytest.mark.unit
    def test_get_calls_returns_all_calls(self):
        """Test get_calls returns all delegate calls."""
        adapter = MockOrchestratorAdapter(responses=["a", "b", "c"])

        adapter.delegate("mock", "prompt1")
        adapter.delegate("mock", "prompt2")
        adapter.delegate("mock", "prompt3")

        calls = adapter.get_calls()
        assert len(calls) == 3

    @pytest.mark.unit
    def test_reset_clears_call_index(self):
        """Test reset clears call index."""
        adapter = MockOrchestratorAdapter(responses=["first", "second"])

        adapter.delegate("mock", "prompt")
        adapter.reset()

        # Should start from beginning again
        response = adapter.delegate("mock", "prompt")
        assert response.content == "first"

    @pytest.mark.unit
    def test_reset_clears_calls_history(self):
        """Test reset clears calls history."""
        adapter = MockOrchestratorAdapter(responses=["response"])

        adapter.delegate("mock", "prompt1")
        adapter.delegate("mock", "prompt2")

        adapter.reset()

        calls = adapter.get_calls()
        assert len(calls) == 0

    @pytest.mark.unit
    def test_delegate_returns_llm_response(self):
        """Test delegate returns LLMResponse object."""
        adapter = MockOrchestratorAdapter(responses=["test"])

        response = adapter.delegate("mock", "prompt")

        assert isinstance(response, LLMResponse)
        assert response.provider == "mock"

    @pytest.mark.unit
    def test_delegate_with_empty_queue(self):
        """Test delegate with empty response queue."""
        adapter = MockOrchestratorAdapter()

        response = adapter.delegate("mock", "prompt")

        # Should return default completion response
        assert "complete" in response.content
        assert isinstance(response, LLMResponse)


class TestProtocolImplementation:
    """Tests for protocol implementation checking."""

    @pytest.mark.unit
    def test_null_context_is_context_provider(self):
        """Test NullContext implements ContextProvider."""
        context = NullContext()
        assert isinstance(context, ContextProvider)

    @pytest.mark.unit
    def test_simple_adapter_has_orchestrator_methods(self):
        """Test SimpleLLMAdapter has OrchestratorAdapter methods."""
        def llm(prompt, **kwargs):
            return "test"

        adapter = SimpleLLMAdapter(llm)

        # Check it can be used as an orchestrator adapter
        assert callable(adapter.delegate)
        assert callable(adapter.list_providers)
        assert hasattr(adapter, 'context')

    @pytest.mark.unit
    def test_mock_adapter_has_orchestrator_methods(self):
        """Test MockOrchestratorAdapter has OrchestratorAdapter methods."""
        adapter = MockOrchestratorAdapter()

        assert callable(adapter.delegate)
        assert callable(adapter.list_providers)
        assert hasattr(adapter, 'context')


class TestIntegrationScenarios:
    """Integration tests for adapter usage patterns."""

    @pytest.mark.unit
    def test_simple_adapter_conversation_flow(self):
        """Test SimpleLLMAdapter in conversation scenario."""
        responses = iter([
            "First response",
            "Second response",
            "Final response"
        ])

        def llm_func(prompt, **kwargs):
            return next(responses)

        adapter = SimpleLLMAdapter(llm_func, provider_name="test")

        r1 = adapter.delegate("test", "Hello")
        r2 = adapter.delegate("test", "Continue")
        r3 = adapter.delegate("test", "Finish")

        assert r1.content == "First response"
        assert r2.content == "Second response"
        assert r3.content == "Final response"

    @pytest.mark.unit
    def test_mock_adapter_assertion_pattern(self):
        """Test MockOrchestratorAdapter for test assertions."""
        adapter = MockOrchestratorAdapter(responses=[
            '{"action": "read_file", "path": "/test.py"}',
            '{"action": "complete", "result": "Done"}'
        ])

        # Simulate agent calls
        adapter.delegate("mock", "Read the file")
        adapter.delegate("mock", "Process results")

        # Assert on calls
        calls = adapter.get_calls()
        assert len(calls) == 2
        assert "Read the file" in calls[0]['prompt']
        assert "Process results" in calls[1]['prompt']

    @pytest.mark.unit
    def test_agent_orchestrator_adapter_with_llm_response(self):
        """Test AgentOrchestratorAdapter with proper LLMResponse."""
        mock_orch = Mock()
        mock_orch.context = NullContext()
        mock_orch.registry.list_available.return_value = ['groq']
        mock_orch.delegate.return_value = LLMResponse(
            content="AI response",
            provider="groq",
            model="llama-3.1-8b",
            tokens_used=150
        )

        adapter = AgentOrchestratorAdapter(mock_orch)
        response = adapter.delegate("groq", "Test")

        # Should pass through LLMResponse unchanged
        assert response.content == "AI response"
        assert response.tokens_used == 150
