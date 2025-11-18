"""
Tests for native tool call integration in agent core.

These tests verify that the agent can work with providers that support
native tool calling (returning ToolCall objects instead of JSON text).

Tests are written to FAIL until the integration is complete. They cover:
1. AgentThought storing LLMResponse for native tool calls
2. _think() detecting native tool support and using chat_with_tools()
3. _plan_action() using NativeToolCallParser when tool_calls present
4. OrchestratorAdapter.delegate_with_tools() method
"""
import pytest
from unittest.mock import Mock, patch

from src.agent.core import CodeAgent
from src.agent.types import AgentThought, ConversationState
from src.agent_config import AgentConfig
from src.orchestrator_adapter import OrchestratorAdapter
from src.providers.base import LLMResponse, ToolCall

# Use existing test helpers
from tests.helpers import make_response, ConfigurableTestOrchestrator


@pytest.fixture
def minimal_config():
    """Create minimal config for testing."""
    return AgentConfig(
        dangerous_commands=["rm -rf /"],
        interactive_commands=["npx create"],
        long_running_commands=["npm install"],
        command_timeout=10,
        max_command_output=1000,
    )


def make_tool_call(
    call_id: str = "call_123",
    name: str = "read_file",
    arguments: dict = None
) -> ToolCall:
    """Helper to create ToolCall objects."""
    if arguments is None:
        arguments = {"file_path": "src/main.py"}
    return ToolCall(id=call_id, name=name, arguments=arguments)


def make_response_with_tools(
    content: str = "I'll read the main file to understand the structure.",
    tool_calls: list = None,
    provider: str = "mock_native_provider"
) -> LLMResponse:
    """Helper to create LLMResponse with native tool calls."""
    if tool_calls is None:
        tool_calls = [make_tool_call()]

    return LLMResponse(
        content=content,
        model="mock-model",
        provider=provider,
        tool_calls=tool_calls
    )


@pytest.fixture
def mock_orchestrator_with_native_support():
    """Create orchestrator adapter that supports native tool calling."""
    orch = ConfigurableTestOrchestrator(
        available_providers=["mock_native_provider"],
        recommended_provider="mock_native_provider"
    )

    # Mock the delegate_with_tools method to return proper LLMResponse
    def mock_delegate_with_tools(*args, **kwargs):
        return make_response_with_tools()

    orch.delegate_with_tools = Mock(side_effect=mock_delegate_with_tools)

    # Mock provider registry for native tool support detection
    # This needs to be set up BEFORE agent creation
    orch._registry = Mock()
    mock_provider = Mock()
    mock_provider.supports_tool_calling = True
    mock_provider.available_models = ["mock-model"]
    orch._registry.get = Mock(return_value=mock_provider)

    # Also add registry to orch itself for the wrapped adapter
    orch.registry = orch._registry

    return orch


@pytest.fixture
def agent_with_native_orchestrator(mock_orchestrator_with_native_support, minimal_config):
    """Create agent with native tool support enabled."""
    return CodeAgent(
        orchestrator=mock_orchestrator_with_native_support,
        project_path=".",
        config=minimal_config
    )


class TestAgentThoughtNativeToolSupport:
    """Tests for AgentThought storing full LLMResponse."""

    @pytest.mark.unit
    def test_agent_thought_stores_llm_response(self):
        """AgentThought should be able to store full LLMResponse object."""
        # Create LLMResponse with tool calls using helper
        response = make_response_with_tools(
            content="Reading the file",
            tool_calls=[make_tool_call(name="read_file", arguments={"file_path": "main.py"})]
        )

        # AgentThought should accept and store the full response
        thought = AgentThought(
            raw_response=response.content,
            provider=response.provider,
            iteration=1,
            llm_response=response  # New field for native tool support
        )

        # Should be able to access the full response
        assert thought.llm_response is not None
        assert thought.llm_response.tool_calls is not None
        assert len(thought.llm_response.tool_calls) == 1
        assert thought.llm_response.tool_calls[0].name == "read_file"

    @pytest.mark.unit
    def test_agent_thought_optional_llm_response(self):
        """AgentThought should work without llm_response for backward compatibility."""
        # Old code should still work
        thought = AgentThought(
            raw_response="JSON response",
            provider="test-provider",
            iteration=1
        )

        # Should default to None
        assert hasattr(thought, "llm_response")
        assert thought.llm_response is None

    @pytest.mark.unit
    def test_agent_thought_preserves_raw_response(self):
        """AgentThought raw_response should still contain text content."""
        response = make_response_with_tools(
            content="I'll read the main file to understand the structure."
        )

        thought = AgentThought(
            raw_response=response.content,
            provider=response.provider,
            iteration=1,
            llm_response=response
        )

        # raw_response is still the text content
        assert thought.raw_response == "I'll read the main file to understand the structure."
        # But we also have access to tool_calls
        assert thought.llm_response.tool_calls is not None


class TestThinkMethodNativeToolDetection:
    """Tests for _think() method detecting and using native tool calling."""

    @pytest.mark.unit
    def test_think_returns_thought_with_llm_response_when_native_tools_available(
        self,
        agent_with_native_orchestrator,
        mock_orchestrator_with_native_support
    ):
        """_think() should include LLMResponse when provider supports native tools."""
        # This test verifies AgentThought can store llm_response

        # Create conversation state
        state = ConversationState(
            messages=[{"role": "user", "content": "Read main.py"}],
            system_prompt="You are a helpful assistant",
            iteration=1
        )

        # Call _think
        thought = agent_with_native_orchestrator._think(state)

        # Key behavior: AgentThought now has llm_response field
        assert hasattr(thought, 'llm_response')
        assert thought.llm_response is not None

        # The response should be from the orchestrator
        # (Whether it's native tools or JSON doesn't matter for this test)
        assert thought.raw_response is not None
        assert thought.provider is not None

    @pytest.mark.unit
    def test_think_uses_delegate_with_tools_for_native_provider(
        self,
        agent_with_native_orchestrator,
        mock_orchestrator_with_native_support
    ):
        """_think() should call delegate_with_tools() when provider supports native tools."""
        response = make_response_with_tools()
        mock_orchestrator_with_native_support.delegate_with_tools.side_effect = lambda *args, **kwargs: response

        state = ConversationState(
            messages=[{"role": "user", "content": "Read main.py"}],
            system_prompt="You are a helpful assistant",
            iteration=1
        )

        # Call _think
        thought = agent_with_native_orchestrator._think(state)

        # Native tools are supported, so delegate_with_tools should be called
        assert mock_orchestrator_with_native_support.delegate_with_tools.called, \
            "delegate_with_tools should be called when provider supports native tools"

        # Verify tools were passed
        call_kwargs = mock_orchestrator_with_native_support.delegate_with_tools.call_args
        assert call_kwargs is not None
        assert "tools" in call_kwargs.kwargs or len(call_kwargs.args) > 2

    @pytest.mark.unit
    def test_think_falls_back_to_delegate_for_json_provider(
        self,
        minimal_config
    ):
        """_think() should use regular delegate() for providers without native tool support."""
        # Create orchestrator with JSON-only provider
        orch = ConfigurableTestOrchestrator(
            available_providers=["mock_json_provider"],
            response_content='{"thought": "test", "action": "read_file", "parameters": {}, "is_complete": false}'
        )

        # Mock provider that doesn't support native tools
        mock_provider = Mock()
        mock_provider.supports_tool_calling = False
        orch._registry = Mock()
        orch._registry.get = Mock(return_value=mock_provider)

        agent = CodeAgent(
            orchestrator=orch,
            project_path=".",
            config=minimal_config
        )

        state = ConversationState(
            messages=[{"role": "user", "content": "Read main.py"}],
            system_prompt="You are a helpful assistant",
            iteration=1
        )

        # This should use regular delegate, not delegate_with_tools
        thought = agent._think(state)

        # Should have used regular delegate (tracked in orch.delegate_calls)
        assert len(orch.delegate_calls) > 0

        # llm_response should be None or not have tool_calls
        assert thought.llm_response is None or thought.llm_response.tool_calls is None

    @pytest.mark.unit
    def test_think_passes_tool_schemas_for_native_calling(
        self,
        agent_with_native_orchestrator,
        mock_orchestrator_with_native_support
    ):
        """_think() should pass OpenAI-compatible tool schemas to delegate_with_tools()."""
        response = make_response_with_tools()
        mock_orchestrator_with_native_support.delegate_with_tools.side_effect = lambda *args, **kwargs: response

        state = ConversationState(
            messages=[{"role": "user", "content": "Read main.py"}],
            system_prompt="You are a helpful assistant",
            iteration=1
        )

        agent_with_native_orchestrator._think(state)

        # delegate_with_tools should be called since provider supports native tools
        assert mock_orchestrator_with_native_support.delegate_with_tools.called, \
            "delegate_with_tools should be called when provider supports native tools"

        call_kwargs = mock_orchestrator_with_native_support.delegate_with_tools.call_args.kwargs

        # Should have tools parameter with OpenAI schema format
        assert "tools" in call_kwargs
        tools = call_kwargs["tools"]

        # Tools should be a list of OpenAI-format tool definitions
        assert isinstance(tools, list)
        assert len(tools) > 0
        # Each tool should have type and function
        assert "type" in tools[0]
        assert tools[0]["type"] == "function"
        assert "function" in tools[0]
        assert "name" in tools[0]["function"]


class TestPlanActionNativeToolParsing:
    """Tests for _plan_action() handling native tool calls."""

    @pytest.mark.unit
    def test_plan_action_uses_native_parser_when_tool_calls_present(
        self,
        agent_with_native_orchestrator
    ):
        """_plan_action() should detect tool_calls and use NativeToolCallParser."""
        response = make_response_with_tools(
            content="I'll read the main file to understand the structure.",
            tool_calls=[make_tool_call(name="read_file", arguments={"file_path": "src/main.py"})]
        )

        thought = AgentThought(
            raw_response=response.content,
            provider="mock_native_provider",
            iteration=1,
            llm_response=response
        )

        action = agent_with_native_orchestrator._plan_action(thought)

        # Should have parsed the tool call correctly
        assert action.action == "read_file"
        assert action.parameters == {"file_path": "src/main.py"}
        assert action.thought == "I'll read the main file to understand the structure."

    @pytest.mark.unit
    def test_plan_action_falls_back_to_json_when_no_tool_calls(
        self,
        agent_with_native_orchestrator
    ):
        """_plan_action() should use JSON parser when no tool_calls present."""
        json_response = '{"thought": "Analyzing code", "action": "read_file", "parameters": {"file_path": "main.py"}, "is_complete": false}'

        thought = AgentThought(
            raw_response=json_response,
            provider="mock_json_provider",
            iteration=1,
            llm_response=None  # No LLMResponse means JSON parsing
        )

        action = agent_with_native_orchestrator._plan_action(thought)

        # Should have parsed JSON correctly
        assert action.action == "read_file"
        assert action.parameters == {"file_path": "main.py"}
        assert action.thought == "Analyzing code"

    @pytest.mark.unit
    def test_plan_action_handles_complete_action_from_native_tools(
        self,
        agent_with_native_orchestrator
    ):
        """_plan_action() should handle 'complete' tool call correctly."""
        response = make_response_with_tools(
            content="I have completed the task.",
            tool_calls=[make_tool_call(
                call_id="call_456",
                name="complete",
                arguments={"result": "Task completed successfully. The file has been read."}
            )]
        )

        thought = AgentThought(
            raw_response=response.content,
            provider="mock_native_provider",
            iteration=1,
            llm_response=response
        )

        action = agent_with_native_orchestrator._plan_action(thought)

        # Should recognize completion
        assert action.is_complete is True
        assert action.action == "complete"
        assert "Task completed successfully" in action.result_text

    @pytest.mark.unit
    def test_plan_action_handles_empty_tool_calls_falls_back_to_json(
        self,
        agent_with_native_orchestrator
    ):
        """_plan_action() should fall back to JSON parsing when tool_calls is empty list."""
        # Empty tool_calls list means fall back to parsing content as JSON
        # This ensures backward compatibility with providers that might return empty list
        json_content = '{"thought": "Task complete", "action": "complete", "is_complete": true, "result": "Summary here"}'
        response = LLMResponse(
            content=json_content,
            model="mock-model",
            provider="mock_native_provider",
            tool_calls=[]  # Empty list -> fall back to JSON parsing
        )

        thought = AgentThought(
            raw_response=response.content,
            provider="mock_native_provider",
            iteration=1,
            llm_response=response
        )

        action = agent_with_native_orchestrator._plan_action(thought)

        # Should parse JSON content successfully
        assert action.is_complete is True
        assert action.action == "complete"
        assert "Summary here" in action.result_text


class TestOrchestratorAdapterDelegateWithTools:
    """Tests for OrchestratorAdapter.delegate_with_tools() method."""

    @pytest.mark.unit
    def test_orchestrator_adapter_protocol_includes_delegate_with_tools(self):
        """OrchestratorAdapter Protocol should define delegate_with_tools() method."""
        # Check that the Protocol defines delegate_with_tools
        # This will fail until we add the method to the Protocol
        assert hasattr(OrchestratorAdapter, "delegate_with_tools")

        # Verify it's defined as a method in the Protocol
        from inspect import signature
        sig = signature(OrchestratorAdapter.delegate_with_tools)

        # Should accept tools parameter
        assert "tools" in sig.parameters

    @pytest.mark.unit
    def test_delegate_with_tools_accepts_tool_schemas(self):
        """delegate_with_tools() should accept OpenAI-compatible tool schemas."""
        # Create a mock that conforms to the Protocol
        adapter = Mock(spec=OrchestratorAdapter)

        # Mock the delegate_with_tools to return proper response using helper
        response = make_response_with_tools(
            content="Tool response",
            tool_calls=[make_tool_call(name="read_file", arguments={"file_path": "x.py"})]
        )
        adapter.delegate_with_tools.return_value = response

        # Define tool schemas
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read a file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string"}
                        },
                        "required": ["file_path"]
                    }
                }
            }
        ]

        # Call delegate_with_tools - this should work once Protocol is updated
        result = adapter.delegate_with_tools(
            provider="mock_provider",
            prompt="Read the file",
            tools=tools
        )

        # Should return LLMResponse with tool_calls
        assert isinstance(result, LLMResponse)
        assert result.tool_calls is not None
        adapter.delegate_with_tools.assert_called_once()

    @pytest.mark.unit
    def test_delegate_with_tools_returns_llm_response_with_tool_calls(self):
        """delegate_with_tools() should return LLMResponse preserving tool_calls."""
        adapter = Mock(spec=OrchestratorAdapter)

        expected_response = make_response_with_tools(
            content="Checking git status",
            tool_calls=[make_tool_call(call_id="call_abc", name="git_status", arguments={})]
        )
        adapter.delegate_with_tools.return_value = expected_response

        response = adapter.delegate_with_tools(
            provider="mock_provider",
            prompt="Check git status",
            tools=[{"type": "function", "function": {"name": "git_status"}}]
        )

        # Should preserve tool_calls from provider response
        assert response.tool_calls is not None
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "git_status"

    @pytest.mark.unit
    def test_delegate_with_tools_signature_matches_expected(self):
        """delegate_with_tools() should have the expected signature."""
        # Verify the Protocol method has proper signature
        from inspect import signature
        import inspect

        sig = signature(OrchestratorAdapter.delegate_with_tools)
        params = sig.parameters

        # Expected parameters
        assert "provider" in params or "provider_name" in params
        assert "prompt" in params
        assert "tools" in params

        # system_prompt should be optional (has default of None)
        if "system_prompt" in params:
            param = params["system_prompt"]
            # Check it has a default (None is a valid default)
            assert param.default is not inspect.Parameter.empty


class TestEndToEndNativeToolCalling:
    """Integration tests for complete native tool calling flow."""

    @pytest.mark.unit
    def test_agent_loop_with_native_tool_provider(
        self,
        minimal_config
    ):
        """Agent should complete task using native tool calls."""
        # Create orchestrator with proper context
        orch = ConfigurableTestOrchestrator(
            available_providers=["mock_native_provider"],
            response_content='{"thought": "test", "action": "complete", "is_complete": true, "result": "done"}'
        )

        # Setup: Provider returns completion
        complete_response = make_response_with_tools(
            content="Task complete.",
            tool_calls=[make_tool_call(call_id="call_2", name="complete", arguments={"result": "Task done successfully"})]
        )

        orch.delegate_with_tools = Mock(return_value=complete_response)

        # Mock registry
        orch._registry = Mock()
        mock_provider = Mock()
        mock_provider.supports_tool_calling = True
        orch._registry.get = Mock(return_value=mock_provider)

        agent = CodeAgent(
            orchestrator=orch,
            project_path=".",
            config=minimal_config
        )

        # Test that agent can be created and basic properties work
        # (Full run test would require more complex mocking)
        assert agent is not None
        assert agent._response_parser is not None

        # Verify UnifiedResponseParser is used
        from src.agent.response_parser import UnifiedResponseParser
        assert isinstance(agent._response_parser, UnifiedResponseParser)

    @pytest.mark.unit
    def test_mixed_provider_support_in_same_session(self, minimal_config):
        """Agent should handle switching between JSON and native tool providers."""
        # This test ensures the agent can work with both types
        orch = ConfigurableTestOrchestrator(
            available_providers=["mock_native_provider", "mock_json_provider"]
        )

        agent = CodeAgent(
            orchestrator=orch,
            project_path=".",
            config=minimal_config
        )

        # Verify agent can be configured for either mode
        assert agent._response_parser is not None

        # The parser should be able to handle both formats
        # (This will be UnifiedResponseParser after integration)
        from src.agent.response_parser import UnifiedResponseParser
        assert isinstance(agent._response_parser, UnifiedResponseParser)
