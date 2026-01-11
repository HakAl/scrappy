"""
Integration test for LangGraphBridge data flow.

This test exercises the full path from LangGraphBridge.run_agent()
through the graph to verify data actually reaches the LLM service.
"""

import pytest
from unittest.mock import Mock, MagicMock
from typing import Any

from scrappy.graph.state import AgentState


class MockToolCall:
    """Mock tool call object."""
    def __init__(self, id: str, name: str, arguments: str) -> None:
        self.id = id
        self.name = name
        self.arguments = arguments


class MockLLMResponse:
    """Mock LLM response."""
    def __init__(
        self,
        content: str = "",
        tool_calls: list = None,
        model: str = "mock-model",
        provider: str = "mock",
    ) -> None:
        self.content = content
        self.tool_calls = tool_calls or []
        self.model = model
        self.provider = provider


class TracingLLMService:
    """LLM service that traces all calls for debugging."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.configured = True

    def is_configured(self) -> bool:
        return self.configured

    def completion_sync(
        self,
        model: str,
        messages: list[dict],
        **kwargs: Any,
    ) -> tuple[MockLLMResponse, dict]:
        """Record the call and return a simple response."""
        self.calls.append({
            "model": model,
            "messages": messages,
            "messages_count": len(messages),
            "kwargs": kwargs,
        })

        # Return a "done" response (no tool calls)
        return MockLLMResponse(content="Task completed successfully."), {}


@pytest.mark.integration
class TestBridgeDataFlow:
    """Test that data flows correctly through the bridge to LLM."""

    def test_llm_service_receives_messages(self):
        """Verify that completion_sync is called with proper messages."""
        from scrappy.graph.agent import run_agent

        # Create tracing LLM service
        llm_service = TracingLLMService()

        # Run agent with a simple task
        result = run_agent(
            task="Say hello",
            working_dir=".",
            llm_service=llm_service,
        )

        # Verify LLM was called
        assert len(llm_service.calls) >= 1, "LLM service was never called!"

        # Check first call has messages
        first_call = llm_service.calls[0]
        assert first_call["messages_count"] >= 2, (
            f"Expected at least 2 messages (system + user), got {first_call['messages_count']}"
        )

        # Verify message structure
        messages = first_call["messages"]
        assert messages[0]["role"] == "system", "First message should be system"
        assert "Say hello" in str(messages), "User task should be in messages"

    def test_bridge_run_agent_calls_llm(self):
        """Test LangGraphBridge.run_agent() actually calls LLM."""
        from scrappy.cli.textual.langgraph_bridge import LangGraphBridge, AgentResult

        # Create mocks for Textual components
        mock_app = Mock()
        mock_bridge = Mock()
        mock_bridge.blocking_confirm = Mock(return_value=True)
        mock_output_adapter = Mock()
        mock_output_adapter.post_output = Mock()

        # Create tracing LLM service
        llm_service = TracingLLMService()

        # Create the bridge
        bridge = LangGraphBridge(
            app=mock_app,
            bridge=mock_bridge,
            output_adapter=mock_output_adapter,
            llm_service=llm_service,
        )

        # Run agent directly (not in worker)
        result = bridge.run_agent(
            task="Say hello",
            working_dir=".",
        )

        # Check result
        assert isinstance(result, AgentResult), f"Expected AgentResult, got {type(result)}"

        # Verify LLM was called
        assert len(llm_service.calls) >= 1, (
            f"LLM service was never called! "
            f"Result: success={result.success}, error={result.error}"
        )

        print(f"LLM calls: {len(llm_service.calls)}")
        for i, call in enumerate(llm_service.calls):
            print(f"Call {i}: model={call['model']}, messages={call['messages_count']}")


@pytest.mark.integration
class TestRealLLMService:
    """Test with real LiteLLMService to find the actual failure."""


@pytest.mark.integration
class TestOrchestratorLLMService:
    """Test that orchestrator's llm_service works through the graph."""

    def test_orchestrator_llm_service_through_graph(self):
        """Test using orchestrator.llm_service like the TUI does."""
        from scrappy.orchestrator.core import AgentOrchestrator
        from scrappy.graph.agent import run_agent

        # Create orchestrator (like CLI does)
        orchestrator = AgentOrchestrator()

        # Get llm_service like textual_interactive.py does
        llm_service = getattr(orchestrator, 'llm_service', None)
        print(f"orchestrator.llm_service exists: {llm_service is not None}")
        print(f"llm_service type: {type(llm_service)}")

        if llm_service is None:
            pytest.fail("orchestrator.llm_service is None!")

        # Check if configured
        is_configured = llm_service.is_configured()
        print(f"llm_service.is_configured() = {is_configured}")

        if not is_configured:
            pytest.skip("LLM service not configured (no API keys)")

        # Run through graph
        result = run_agent(
            task="Say hello in exactly 3 words",
            working_dir=".",
            llm_service=llm_service,
        )

        print(f"Result: done={result.done}, iterations={result.iteration}")
        print(f"Messages: {len(result.messages)}")

        assert result.done, f"Agent didn't complete: last_error={result.last_error}"
        assert len(result.messages) >= 1, "No messages generated"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
