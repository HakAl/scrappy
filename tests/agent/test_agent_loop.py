"""
Tests for AgentLoop component.

Tests the AgentLoop class extracted from CodeAgent.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from scrappy.agent.agent_loop import AgentLoop
from scrappy.agent.types import (
    AgentThought,
    AgentAction,
    ActionResult,
    EvaluationResult,
    ConversationState,
    AgentContext,
)
from scrappy.agent_config import AgentConfig


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
def mock_context_factory():
    """Create a mock context factory."""
    mock = Mock()
    mock.build_context.return_value = AgentContext(
        system_prompt="Test system prompt",
        active_tools=["read_file", "write_file"],
        passive_rag_context="",
    )
    return mock


@pytest.fixture
def agent_loop(
    mock_orchestrator,
    mock_action_executor,
    mock_response_parser,
    mock_ui,
    mock_tool_registry,
    mock_provider_strategy,
    mock_context_factory,
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
        context_factory=mock_context_factory,
        tools={"read_file": Mock(), "write_file": Mock()},
    )


class TestAgentLoopThink:
    """Tests for AgentLoop.think()."""



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
        context = AgentContext(
            system_prompt="system prompt",
            active_tools=["read_file", "write_file"],
        )

        agent_loop.think(state, context)

        mock_ui.show_provider_status.assert_called()
        # First call should mention "Analyzing"
        first_call = mock_ui.show_provider_status.call_args_list[0]
        assert "Analyzing" in first_call[0][1] or "Response" in first_call[0][1]


class TestAgentLoopPlan:
    """Tests for AgentLoop.plan()."""




class TestAgentLoopExecute:
    """Tests for AgentLoop.execute()."""



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

        mock_context_factory = Mock()
        mock_context_factory.build_context.return_value = AgentContext(
            system_prompt="system",
            active_tools=["write_file"],
            passive_rag_context="",
        )

        agent_loop = AgentLoop(
            orchestrator=mock_orchestrator,
            action_executor=mock_action_executor,
            response_parser=mock_response_parser,
            ui=mock_ui,
            tool_registry=mock_tool_registry,
            provider_strategy=mock_provider_strategy,
            config=config,
            context_factory=mock_context_factory,
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

        mock_context_factory = Mock()
        mock_context_factory.build_context.return_value = AgentContext(
            system_prompt="system",
            active_tools=["read_file"],
            passive_rag_context="",
        )

        agent_loop = AgentLoop(
            orchestrator=mock_orchestrator,
            action_executor=mock_action_executor,
            response_parser=mock_response_parser,
            ui=mock_ui,
            tool_registry=mock_tool_registry,
            provider_strategy=mock_provider_strategy,
            config=config,
            context_factory=mock_context_factory,
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


class TestAgentLoopContextRebuild:
    """Tests for per-iteration context rebuild behavior."""

    def test_context_rebuilt_every_iteration(
        self,
        mock_action_executor,
        mock_response_parser,
        mock_ui,
        mock_tool_registry,
        mock_provider_strategy,
    ):
        """run() should rebuild context on each iteration."""
        mock_orchestrator = Mock(spec=['delegate', 'list_providers'])
        response = Mock()
        response.content = '{"thought": "test", "action": "read_file", "parameters": {}}'
        response.provider = "openai"
        response.tool_calls = None
        mock_orchestrator.delegate.return_value = response

        mock_response_parser.parse.return_value = Mock(
            thought="working",
            action="read_file",
            parameters={"path": "test.py"},
            is_complete=False,
            result_text="",
        )

        config = AgentConfig()

        # Track context factory calls
        mock_context_factory = Mock()
        mock_context_factory.build_context.return_value = AgentContext(
            system_prompt="system",
            active_tools=["read_file"],
            passive_rag_context="",
        )

        agent_loop = AgentLoop(
            orchestrator=mock_orchestrator,
            action_executor=mock_action_executor,
            response_parser=mock_response_parser,
            ui=mock_ui,
            tool_registry=mock_tool_registry,
            provider_strategy=mock_provider_strategy,
            config=config,
            context_factory=mock_context_factory,
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

        agent_loop.run("test task", state)

        # Context factory should be called once per iteration
        assert mock_context_factory.build_context.call_count == 3
        # Each call should receive task and system_prompt
        for call in mock_context_factory.build_context.call_args_list:
            assert call[0][0] == "test task"
            assert call[0][1] == "system"


    def test_index_readiness_changes_mid_conversation(
        self,
        mock_action_executor,
        mock_response_parser,
        mock_ui,
        mock_tool_registry,
        mock_provider_strategy,
    ):
        """run() should immediately use new tools when index becomes ready."""
        mock_orchestrator = Mock(spec=['delegate', 'list_providers'])
        response = Mock()
        response.content = '{"thought": "test", "action": "read_file", "parameters": {}}'
        response.provider = "openai"
        response.tool_calls = None
        mock_orchestrator.delegate.return_value = response

        mock_response_parser.parse.return_value = Mock(
            thought="working",
            action="read_file",
            parameters={"path": "test.py"},
            is_complete=False,
            result_text="",
        )

        config = AgentConfig()

        # Simulate index becoming ready after iteration 2
        iteration_count = [0]

        def build_context_side_effect(task, system_prompt):
            iteration_count[0] += 1
            if iteration_count[0] <= 2:
                # Iterations 1-2: Index not ready
                return AgentContext(
                    system_prompt="basic system prompt",
                    active_tools=["read_file", "write_file"],
                    passive_rag_context="",
                )
            else:
                # Iteration 3+: Index ready, semantic search available
                return AgentContext(
                    system_prompt="system prompt with semantic search",
                    active_tools=["read_file", "write_file", "semantic_search"],
                    passive_rag_context="Semantic index ready",
                )

        mock_context_factory = Mock()
        mock_context_factory.build_context.side_effect = build_context_side_effect

        agent_loop = AgentLoop(
            orchestrator=mock_orchestrator,
            action_executor=mock_action_executor,
            response_parser=mock_response_parser,
            ui=mock_ui,
            tool_registry=mock_tool_registry,
            provider_strategy=mock_provider_strategy,
            config=config,
            context_factory=mock_context_factory,
            tools={
                "read_file": Mock(),
                "write_file": Mock(),
                "semantic_search": Mock(),
            },
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

        agent_loop.run("test task", state)

        # Verify context was rebuilt 3 times
        assert mock_context_factory.build_context.call_count == 3

        # Verify each call passed correct parameters
        for call in mock_context_factory.build_context.call_args_list:
            assert call[0][0] == "test task"
            assert call[0][1] == "system"

    def test_context_passed_to_think_on_each_iteration(
        self,
        mock_action_executor,
        mock_response_parser,
        mock_ui,
        mock_tool_registry,
        mock_provider_strategy,
    ):
        """run() should pass fresh context to think() on each iteration."""
        mock_orchestrator = Mock(spec=['delegate', 'list_providers'])
        response = Mock()
        response.content = '{"thought": "test", "action": "read_file", "parameters": {}}'
        response.provider = "openai"
        response.tool_calls = None
        mock_orchestrator.delegate.return_value = response

        mock_response_parser.parse.return_value = Mock(
            thought="working",
            action="read_file",
            parameters={"path": "test.py"},
            is_complete=False,
            result_text="",
        )

        config = AgentConfig()

        # Track what contexts are generated
        contexts_generated = []

        def build_context_side_effect(task, system_prompt):
            context = AgentContext(
                system_prompt=f"system {len(contexts_generated) + 1}",
                active_tools=["read_file"],
                passive_rag_context=f"iteration {len(contexts_generated) + 1}",
            )
            contexts_generated.append(context)
            return context

        mock_context_factory = Mock()
        mock_context_factory.build_context.side_effect = build_context_side_effect

        agent_loop = AgentLoop(
            orchestrator=mock_orchestrator,
            action_executor=mock_action_executor,
            response_parser=mock_response_parser,
            ui=mock_ui,
            tool_registry=mock_tool_registry,
            provider_strategy=mock_provider_strategy,
            config=config,
            context_factory=mock_context_factory,
            tools={"read_file": Mock()},
        )

        state = ConversationState(
            messages=[
                {"role": "system", "content": "system"},
                {"role": "user", "content": "task"},
            ],
            system_prompt="system",
            iteration=0,
            max_iterations=2,
        )

        agent_loop.run("test task", state)

        # Should generate unique context for each iteration
        assert len(contexts_generated) == 2
        assert contexts_generated[0].system_prompt == "system 1"
        assert contexts_generated[1].system_prompt == "system 2"
        assert contexts_generated[0].passive_rag_context == "iteration 1"
        assert contexts_generated[1].passive_rag_context == "iteration 2"
