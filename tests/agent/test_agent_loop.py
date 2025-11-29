"""
Tests for AgentLoop component.

Tests the AgentLoop class extracted from CodeAgent.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from src.agent.agent_loop import AgentLoop
from src.agent.types import (
    AgentThought,
    AgentAction,
    ActionResult,
    EvaluationResult,
    ConversationState,
)
from src.agent_config import AgentConfig


@pytest.fixture
def mock_orchestrator():
    """Create a mock orchestrator adapter.

    Uses spec to ensure hasattr checks work correctly (e.g., no delegate_with_tools).
    """
    mock = Mock(spec=['delegate', 'list_providers'])
    response = Mock()
    response.content = '{"thought": "test", "action": "read_file", "parameters": {"path": "test.py"}}'
    response.provider = "openai"
    response.tool_calls = None  # Explicitly None, not Mock
    mock.delegate.return_value = response
    return mock


@pytest.fixture
def mock_action_executor():
    """Create a mock action executor."""
    mock = Mock()
    mock.execute.return_value = ActionResult(
        success=True,
        output="File content here",
        action="read_file",
        parameters={"path": "test.py"},
        approved=True,
        executed=True,
    )
    return mock


@pytest.fixture
def mock_response_parser():
    """Create a mock response parser."""
    mock = Mock()
    mock.parse.return_value = Mock(
        thought="test thought",
        action="read_file",
        parameters={"path": "test.py"},
        is_complete=False,
        result_text="",
    )
    return mock


@pytest.fixture
def mock_ui():
    """Create a mock UI."""
    mock = Mock()
    return mock


@pytest.fixture
def mock_tool_registry():
    """Create a mock tool registry."""
    mock = Mock()
    mock.to_openai_schema.return_value = []
    return mock


@pytest.fixture
def mock_provider_strategy():
    """Create a mock provider strategy."""
    mock = Mock()
    mock.get_planner.return_value = "openai"
    mock.get_executor.return_value = "openai"
    mock.supports_dynamic_selection.return_value = True
    return mock


@pytest.fixture
def agent_loop(
    mock_orchestrator,
    mock_action_executor,
    mock_response_parser,
    mock_ui,
    mock_tool_registry,
    mock_provider_strategy,
):
    """Create an AgentLoop instance with all mocked dependencies."""
    config = AgentConfig()
    return AgentLoop(
        orchestrator=mock_orchestrator,
        action_executor=mock_action_executor,
        response_parser=mock_response_parser,
        ui=mock_ui,
        tool_registry=mock_tool_registry,
        provider_strategy=mock_provider_strategy,
        config=config,
        tools={"read_file": Mock(), "write_file": Mock()},
    )


class TestAgentLoopThink:
    """Tests for AgentLoop.think()."""

    def test_think_delegates_to_orchestrator(
        self, agent_loop, mock_orchestrator, mock_provider_strategy
    ):
        """think() should delegate to orchestrator.delegate()."""
        # Provider strategy says dynamic selection, so orchestrator.delegate is called
        mock_provider_strategy.supports_dynamic_selection.return_value = True

        state = ConversationState(
            messages=[
                {"role": "system", "content": "system prompt"},
                {"role": "user", "content": "test task"},
            ],
            system_prompt="system prompt",
            iteration=1,
        )

        result = agent_loop.think(state)

        # With dynamic selection, delegate is called with provider_name=None
        mock_orchestrator.delegate.assert_called_once()
        assert isinstance(result, AgentThought)

    def test_think_uses_provider_from_strategy(
        self, agent_loop, mock_provider_strategy
    ):
        """think() should get provider from strategy."""
        state = ConversationState(
            messages=[
                {"role": "system", "content": "system prompt"},
                {"role": "user", "content": "test task"},
            ],
            system_prompt="system prompt",
            iteration=1,
        )

        agent_loop.think(state)

        mock_provider_strategy.get_planner.assert_called()

    def test_think_shows_progress_on_first_iteration(
        self, agent_loop, mock_ui
    ):
        """think() should show 'Analyzing' message on first iteration."""
        state = ConversationState(
            messages=[
                {"role": "system", "content": "system prompt"},
                {"role": "user", "content": "test task"},
            ],
            system_prompt="system prompt",
            iteration=1,
        )

        agent_loop.think(state)

        mock_ui.show_provider_status.assert_called()
        # First call should mention "Analyzing"
        first_call = mock_ui.show_provider_status.call_args_list[0]
        assert "Analyzing" in first_call[0][1] or "Response" in first_call[0][1]


class TestAgentLoopPlan:
    """Tests for AgentLoop.plan()."""

    def test_plan_parses_thought_response(
        self, agent_loop, mock_response_parser
    ):
        """plan() should parse thought.raw_response."""
        thought = AgentThought(
            raw_response='{"action": "read_file"}',
            provider="openai",
            iteration=1,
        )

        result = agent_loop.plan(thought)

        mock_response_parser.parse.assert_called_once()
        assert isinstance(result, AgentAction)

    def test_plan_uses_llm_response_for_native_tools(
        self, agent_loop, mock_response_parser
    ):
        """plan() should use llm_response when tool_calls present."""
        llm_response = Mock()
        llm_response.tool_calls = [{"name": "read_file", "arguments": {}}]

        thought = AgentThought(
            raw_response='{"action": "read_file"}',
            provider="openai",
            iteration=1,
            llm_response=llm_response,
        )

        agent_loop.plan(thought)

        # Should parse llm_response, not raw_response
        mock_response_parser.parse.assert_called_once_with(llm_response)


class TestAgentLoopExecute:
    """Tests for AgentLoop.execute()."""

    def test_execute_delegates_to_action_executor(
        self, agent_loop, mock_action_executor
    ):
        """execute() should delegate to action_executor.execute()."""
        action = AgentAction(
            thought="test",
            action="read_file",
            parameters={"path": "test.py"},
            is_complete=False,
        )
        state = ConversationState()

        result = agent_loop.execute(action, state)

        mock_action_executor.execute.assert_called_once()
        assert isinstance(result, ActionResult)


class TestAgentLoopEvaluate:
    """Tests for AgentLoop.evaluate()."""

    def test_evaluate_returns_complete_when_action_is_complete(
        self, agent_loop, mock_ui
    ):
        """evaluate() should return complete when action.is_complete is True."""
        action = AgentAction(
            thought="done",
            action="complete",
            parameters={},
            is_complete=True,
            result_text="Task finished",
        )
        result = ActionResult(
            success=True,
            output="",
            action="complete",
            parameters={},
            approved=True,
            executed=True,
            metadata={"stop_loop": True},
        )
        state = ConversationState(
            tools_executed=["write_file"],  # Meaningful action performed
        )
        # Set meaningful_actions in config
        agent_loop._config.meaningful_actions = ["write_file"]

        evaluation = agent_loop.evaluate(action, result, state)

        assert evaluation.is_complete is True
        assert evaluation.should_continue is False

    def test_evaluate_rejects_completion_without_meaningful_work(
        self, agent_loop, mock_ui
    ):
        """evaluate() should reject completion if no meaningful actions done."""
        action = AgentAction(
            thought="done",
            action="complete",
            parameters={},
            is_complete=True,
        )
        result = ActionResult(
            success=True,
            output="",
            action="complete",
            parameters={},
            approved=True,
            executed=False,
        )
        state = ConversationState(
            tools_executed=["read_file"],  # Not meaningful
        )
        agent_loop._config.meaningful_actions = ["write_file"]

        evaluation = agent_loop.evaluate(action, result, state)

        assert evaluation.is_complete is False
        assert evaluation.should_continue is True

    def test_evaluate_returns_stop_at_max_iterations(self, agent_loop):
        """evaluate() should stop at max iterations."""
        action = AgentAction(
            thought="still working",
            action="read_file",
            parameters={},
            is_complete=False,
        )
        result = ActionResult(
            success=True,
            output="",
            action="read_file",
            parameters={},
            approved=True,
            executed=True,
        )
        state = ConversationState(
            iteration=10,
            max_iterations=10,
        )

        evaluation = agent_loop.evaluate(action, result, state)

        assert evaluation.is_complete is False
        assert evaluation.should_continue is False
        assert "Max iterations" in evaluation.reason


class TestAgentLoopUpdateConversation:
    """Tests for AgentLoop.update_conversation()."""

    def test_update_conversation_adds_messages_on_execution(self, agent_loop):
        """update_conversation() should add messages when action executed."""
        state = ConversationState(messages=[], tools_executed=[])
        thought = AgentThought(
            raw_response="test response",
            provider="openai",
            iteration=1,
        )
        action = AgentAction(
            thought="test",
            action="read_file",
            parameters={"path": "test.py"},
            is_complete=False,
        )
        result = ActionResult(
            success=True,
            output="file content",
            action="read_file",
            parameters={"path": "test.py"},
            approved=True,
            executed=True,
        )

        agent_loop.update_conversation(state, thought, action, result)

        assert len(state.messages) == 2  # assistant + user
        assert state.messages[0]["role"] == "assistant"
        assert state.messages[1]["role"] == "user"
        assert "read_file" in state.tools_executed

    def test_update_conversation_tracks_failed_commands(self, agent_loop):
        """update_conversation() should track failed commands for retry detection."""
        state = ConversationState(
            messages=[],
            tools_executed=[],
            failed_commands=[],
            iteration=1,
        )
        thought = AgentThought(
            raw_response="test response",
            provider="openai",
            iteration=1,
        )
        action = AgentAction(
            thought="test",
            action="run_command",
            parameters={"command": "npm install"},
            is_complete=False,
        )
        result = ActionResult(
            success=False,
            output="npm ERR! network error",
            action="run_command",
            parameters={"command": "npm install"},
            approved=True,
            executed=True,
        )

        agent_loop.update_conversation(state, thought, action, result)

        assert len(state.failed_commands) == 1
        assert state.failed_commands[0]["approach"] == "npm"


class TestAgentLoopRun:
    """Tests for AgentLoop.run()."""

    def test_run_completes_on_successful_task(
        self,
        mock_response_parser,
        mock_ui,
        mock_tool_registry,
        mock_provider_strategy,
    ):
        """run() should complete when task is marked complete."""
        # Create orchestrator with proper response (spec prevents delegate_with_tools)
        mock_orchestrator = Mock(spec=['delegate', 'list_providers'])
        response = Mock()
        response.content = '{"thought": "test", "action": "write_file", "parameters": {}}'
        response.provider = "openai"
        response.tool_calls = None  # Must be None, not Mock
        mock_orchestrator.delegate.return_value = response

        # Create action executor that returns appropriate results
        mock_action_executor = Mock()
        def execute_side_effect(action, state, dry_run=False):
            if action.action == "complete":
                return ActionResult(
                    success=True,
                    output="Task completed",
                    action="complete",
                    parameters={},
                    approved=True,
                    executed=True,
                    metadata={"stop_loop": True},
                )
            return ActionResult(
                success=True,
                output="File written",
                action="write_file",
                parameters={"path": "test.py", "content": "test"},
                approved=True,
                executed=True,
            )
        mock_action_executor.execute.side_effect = execute_side_effect

        # Setup parser to return complete on second iteration
        call_count = [0]

        def parse_side_effect(response):
            call_count[0] += 1
            if call_count[0] == 1:
                return Mock(
                    thought="working",
                    action="write_file",
                    parameters={"path": "test.py", "content": "test"},
                    is_complete=False,
                    result_text="",
                )
            return Mock(
                thought="done",
                action="complete",
                parameters={},
                is_complete=True,
                result_text="Task completed",
            )

        mock_response_parser.parse.side_effect = parse_side_effect

        config = AgentConfig()
        config.meaningful_actions = ["write_file"]

        agent_loop = AgentLoop(
            orchestrator=mock_orchestrator,
            action_executor=mock_action_executor,
            response_parser=mock_response_parser,
            ui=mock_ui,
            tool_registry=mock_tool_registry,
            provider_strategy=mock_provider_strategy,
            config=config,
            tools={"write_file": Mock()},
        )

        state = ConversationState(
            messages=[
                {"role": "system", "content": "system"},
                {"role": "user", "content": "task"},
            ],
            system_prompt="system",
            iteration=0,
            max_iterations=10,
        )

        result = agent_loop.run("test task", state)

        assert result["success"] is True
        assert result["iterations"] == 2

    def test_run_stops_at_max_iterations(
        self,
        mock_action_executor,
        mock_response_parser,
        mock_ui,
        mock_tool_registry,
        mock_provider_strategy,
    ):
        """run() should stop at max iterations."""
        # Create orchestrator with proper response (spec prevents delegate_with_tools)
        mock_orchestrator = Mock(spec=['delegate', 'list_providers'])
        response = Mock()
        response.content = '{"thought": "test", "action": "read_file", "parameters": {}}'
        response.provider = "openai"
        response.tool_calls = None  # Must be None, not Mock
        mock_orchestrator.delegate.return_value = response

        # Parser always returns non-complete action
        mock_response_parser.parse.return_value = Mock(
            thought="working",
            action="read_file",
            parameters={"path": "test.py"},
            is_complete=False,
            result_text="",
        )

        config = AgentConfig()
        agent_loop = AgentLoop(
            orchestrator=mock_orchestrator,
            action_executor=mock_action_executor,
            response_parser=mock_response_parser,
            ui=mock_ui,
            tool_registry=mock_tool_registry,
            provider_strategy=mock_provider_strategy,
            config=config,
            tools={"read_file": Mock()},
        )

        state = ConversationState(
            messages=[
                {"role": "system", "content": "system"},
                {"role": "user", "content": "task"},
            ],
            system_prompt="system",
            iteration=0,
            max_iterations=3,
        )

        result = agent_loop.run("test task", state)

        assert result["success"] is False
        assert "Max iterations" in result["result"]
        assert result["iterations"] == 3
