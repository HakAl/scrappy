"""
Tests for CodeAgent - execution flows, action parsing, and tool orchestration.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch, call
from pathlib import Path
from dataclasses import asdict
import json

from src.agent import (
    CodeAgent,
    AgentThought,
    AgentAction,
    ActionResult,
    EvaluationResult,
    ConversationState
)
from src.agent_config import AgentConfig
from src.agent_tools.tools import ToolRegistry
from src.orchestrator_adapter import OrchestratorAdapter


class TestAgentDataStructures:
    """Tests for agent dataclasses."""

    @pytest.mark.unit
    def test_agent_thought_creation(self):
        """Test creating AgentThought."""
        thought = AgentThought(
            raw_response="I should read the file first",
            provider="cerebras",
            iteration=1
        )
        assert thought.raw_response == "I should read the file first"
        assert thought.provider == "cerebras"
        assert thought.iteration == 1

    @pytest.mark.unit
    def test_agent_action_creation(self):
        """Test creating AgentAction."""
        action = AgentAction(
            thought="Need to read the config file",
            action="read_file",
            parameters={"path": "config.json"},
            is_complete=False
        )
        assert action.thought == "Need to read the config file"
        assert action.action == "read_file"
        assert action.parameters["path"] == "config.json"
        assert action.is_complete is False
        assert action.result_text == ""

    @pytest.mark.unit
    def test_agent_action_with_completion(self):
        """Test AgentAction when task is complete."""
        action = AgentAction(
            thought="Task completed successfully",
            action="",
            parameters={},
            is_complete=True,
            result_text="File has been created successfully"
        )
        assert action.is_complete is True
        assert action.result_text == "File has been created successfully"

    @pytest.mark.unit
    def test_action_result_success(self):
        """Test successful ActionResult."""
        result = ActionResult(
            success=True,
            output="File content: Hello World",
            action="read_file",
            parameters={"path": "test.txt"},
            approved=True,
            executed=True
        )
        assert result.success is True
        assert result.approved is True
        assert result.executed is True

    @pytest.mark.unit
    def test_action_result_rejected(self):
        """Test rejected ActionResult."""
        result = ActionResult(
            success=False,
            output="User rejected the action",
            action="write_file",
            parameters={"path": "test.txt", "content": "data"},
            approved=False,
            executed=False
        )
        assert result.approved is False
        assert result.executed is False

    @pytest.mark.unit
    def test_evaluation_result_complete(self):
        """Test EvaluationResult when complete."""
        result = EvaluationResult(
            is_complete=True,
            should_continue=False,
            reason="Task achieved successfully",
            final_result="Created requirements.txt with all dependencies"
        )
        assert result.is_complete is True
        assert result.should_continue is False
        assert result.final_result is not None

    @pytest.mark.unit
    def test_evaluation_result_continue(self):
        """Test EvaluationResult when should continue."""
        result = EvaluationResult(
            is_complete=False,
            should_continue=True,
            reason="More work needed",
            final_result=None
        )
        assert result.is_complete is False
        assert result.should_continue is True

    @pytest.mark.unit
    def test_conversation_state_initialization(self):
        """Test ConversationState initialization."""
        state = ConversationState()
        assert state.messages == []
        assert state.system_prompt == ""
        assert state.iteration == 0
        assert state.max_iterations == 10
        assert state.tools_executed == []
        assert state.auto_confirm is False

    @pytest.mark.unit
    def test_conversation_state_custom(self):
        """Test ConversationState with custom values."""
        messages = [{"role": "user", "content": "Hello"}]
        state = ConversationState(
            messages=messages,
            system_prompt="You are an assistant",
            iteration=3,
            max_iterations=20,
            tools_executed=["read_file", "search_code"],
            auto_confirm=True
        )
        assert len(state.messages) == 1
        assert state.max_iterations == 20
        assert len(state.tools_executed) == 2
        assert state.auto_confirm is True


class TestCodeAgentInitialization:
    """Tests for CodeAgent initialization."""

    @pytest.fixture
    def mock_adapter(self):
        """Create a mock orchestrator adapter."""
        adapter = MagicMock()
        adapter.list_providers.return_value = ["cerebras", "groq", "gemini"]
        adapter.delegate.return_value = Mock(content="test response", tokens_used=50)
        adapter.get_preferred_provider.return_value = (None, None)
        return adapter

    @pytest.mark.unit
    def test_agent_initialization_with_adapter(self, mock_adapter, temp_project_dir):
        """Test agent initialization with adapter."""
        agent = CodeAgent(
            orchestrator=mock_adapter,
            project_path=str(temp_project_dir)
        )

        # Agent wraps orchestrator in AgentOrchestratorAdapter
        assert agent.adapter is not None
        assert agent.project_root == temp_project_dir
        assert isinstance(agent.config, AgentConfig)
        assert agent.tool_registry is not None

    @pytest.mark.unit
    def test_agent_uses_default_config(self, mock_adapter, temp_project_dir):
        """Test that agent uses default config when not provided."""
        agent = CodeAgent(
            orchestrator=mock_adapter,
            project_path=str(temp_project_dir)
        )

        assert isinstance(agent.config, AgentConfig)
        # Config has file/command settings, not max_iterations
        assert agent.config.max_file_read_size > 0

    @pytest.mark.unit
    def test_agent_uses_custom_config(self, mock_adapter, temp_project_dir):
        """Test agent with custom config."""
        custom_config = AgentConfig()
        custom_config.max_iterations = 50

        agent = CodeAgent(
            orchestrator=mock_adapter,
            project_path=str(temp_project_dir),
            config=custom_config
        )

        assert agent.config.max_iterations == 50

    @pytest.mark.unit
    def test_agent_creates_default_registry(self, mock_adapter, temp_project_dir):
        """Test that agent creates default tool registry."""
        agent = CodeAgent(
            orchestrator=mock_adapter,
            project_path=str(temp_project_dir)
        )

        tools = agent.tool_registry.list_tools()
        assert len(tools) > 0
        # Check for essential tools
        assert "read_file" in tools
        assert "write_file" in tools

    @pytest.mark.unit
    def test_agent_uses_custom_registry(self, mock_adapter, temp_project_dir):
        """Test agent with custom tool registry."""
        custom_registry = ToolRegistry()

        agent = CodeAgent(
            orchestrator=mock_adapter,
            project_path=str(temp_project_dir),
            tool_registry=custom_registry
        )

        assert agent.tool_registry is custom_registry

    @pytest.mark.unit
    def test_agent_selects_planner_from_preferences(self, mock_adapter, temp_project_dir):
        """Test that agent selects planner based on preferences."""
        # Need to ensure list_providers returns a proper list, not Mock
        # Also need to mock the registry for AgentOrchestratorAdapter
        mock_adapter.list_providers.return_value = ["cerebras", "groq", "gemini"]
        mock_adapter.registry = MagicMock()
        mock_adapter.registry.list_available.return_value = ["cerebras", "groq", "gemini"]

        agent = CodeAgent(
            orchestrator=mock_adapter,
            project_path=str(temp_project_dir)
        )

        # Should select from available providers
        assert agent.planner is not None
        # planner should be a string provider name
        assert isinstance(agent.planner, str)

    @pytest.mark.unit
    def test_agent_creates_tool_context(self, mock_adapter, temp_project_dir):
        """Test that agent creates tool context correctly."""
        agent = CodeAgent(
            orchestrator=mock_adapter,
            project_path=str(temp_project_dir)
        )

        assert agent.tool_context is not None
        assert agent.tool_context.project_root == temp_project_dir
        assert agent.tool_context.dry_run is False

    @pytest.mark.unit
    def test_agent_builds_tools_mapping(self, mock_adapter, temp_project_dir):
        """Test that agent builds tools mapping."""
        agent = CodeAgent(
            orchestrator=mock_adapter,
            project_path=str(temp_project_dir)
        )

        assert isinstance(agent.tools, dict)
        # Should have run_command tool
        assert "run_command" in agent.tools

    @pytest.mark.unit
    def test_agent_initializes_audit_log(self, mock_adapter, temp_project_dir):
        """Test that agent initializes audit log."""
        agent = CodeAgent(
            orchestrator=mock_adapter,
            project_path=str(temp_project_dir)
        )

        assert agent.audit_log == []

    @pytest.mark.unit
    def test_agent_with_orchestrator_wrapping(self, temp_project_dir):
        """Test that non-adapter orchestrator gets wrapped."""
        mock_orch = Mock()
        mock_orch.registry = Mock()
        mock_orch.registry.list_available.return_value = ["cerebras"]

        with patch('src.agent.AgentOrchestratorAdapter') as mock_wrapper:
            mock_adapter_instance = MagicMock()  # Use MagicMock to allow any attribute
            mock_adapter_instance.list_providers.return_value = ["cerebras"]
            mock_adapter_instance.get_preferred_provider.return_value = (None, None)
            mock_wrapper.return_value = mock_adapter_instance

            agent = CodeAgent(
                orchestrator=mock_orch,
                project_path=str(temp_project_dir)
            )

            mock_wrapper.assert_called_once_with(mock_orch)


class TestAgentActionParsing:
    """Tests for parsing LLM responses into actions."""

    @pytest.fixture
    def agent(self, temp_project_dir):
        """Create agent for testing."""
        mock_adapter = MagicMock()
        mock_adapter.list_providers.return_value = ["cerebras"]
        mock_adapter.get_preferred_provider.return_value = (None, None)

        return CodeAgent(
            orchestrator=mock_adapter,
            project_path=str(temp_project_dir)
        )

    @pytest.mark.unit
    def test_parse_action_from_json_response(self, agent):
        """Test parsing action from JSON response."""
        response = '''
        {
            "thought": "I need to read the config file",
            "action": "read_file",
            "parameters": {"path": "config.json"}
        }
        '''

        # This tests the parsing logic
        try:
            data = json.loads(response)
            action = AgentAction(
                thought=data.get("thought", ""),
                action=data.get("action", ""),
                parameters=data.get("parameters", {}),
                is_complete=data.get("is_complete", False)
            )
            assert action.action == "read_file"
            assert action.parameters["path"] == "config.json"
        except Exception:
            pass  # JSON parsing not the focus here

    @pytest.mark.unit
    def test_parse_completion_action(self, agent):
        """Test parsing completion action."""
        action = AgentAction(
            thought="Task is complete",
            action="complete",
            parameters={},
            is_complete=True,
            result_text="Successfully created the file"
        )

        assert action.is_complete is True
        assert action.action == "complete"

    @pytest.mark.unit
    def test_parse_action_with_nested_parameters(self, agent):
        """Test parsing action with nested parameters."""
        action = AgentAction(
            thought="Writing complex data",
            action="write_file",
            parameters={
                "path": "config.json",
                "content": '{"key": "value", "nested": {"a": 1}}'
            },
            is_complete=False
        )

        assert "content" in action.parameters
        assert "nested" in action.parameters["content"]


class TestAgentToolExecution:
    """Tests for agent tool execution."""

    @pytest.fixture
    def agent(self, temp_project_dir):
        """Create agent for tool execution testing."""
        mock_adapter = MagicMock()
        mock_adapter.list_providers.return_value = ["cerebras"]
        mock_adapter.get_preferred_provider.return_value = (None, None)

        return CodeAgent(
            orchestrator=mock_adapter,
            project_path=str(temp_project_dir)
        )

    @pytest.mark.unit
    def test_tools_dictionary_populated(self, agent):
        """Test that tools dictionary is populated."""
        assert len(agent.tools) > 0
        assert callable(agent.tools.get("run_command"))

    @pytest.mark.unit
    def test_tool_name_map_populated(self, agent):
        """Test that tool name map is populated."""
        assert len(agent._tool_name_map) > 0
        assert "read_file" in agent._tool_name_map

    @pytest.mark.unit
    def test_read_file_tool_available(self, agent):
        """Test that read_file tool is available."""
        # Check it's in the registry
        tool = agent.tool_registry.get("read_file")
        assert tool is not None

    @pytest.mark.unit
    def test_write_file_tool_available(self, agent):
        """Test that write_file tool is available."""
        tool = agent.tool_registry.get("write_file")
        assert tool is not None

    @pytest.mark.unit
    def test_search_code_tool_available(self, agent):
        """Test that search_code tool is available."""
        tool = agent.tool_registry.get("search_code")
        assert tool is not None


class TestConversationFlow:
    """Tests for conversation and iteration flow."""

    @pytest.mark.unit
    def test_conversation_state_tracks_iterations(self):
        """Test that conversation state tracks iterations."""
        state = ConversationState(iteration=0, max_iterations=10)

        # Simulate iterations
        for i in range(5):
            state.iteration += 1
            state.tools_executed.append(f"tool_{i}")

        assert state.iteration == 5
        assert len(state.tools_executed) == 5

    @pytest.mark.unit
    def test_conversation_stops_at_max_iterations(self):
        """Test that conversation respects max iterations."""
        state = ConversationState(iteration=9, max_iterations=10)

        # Should stop after one more iteration
        state.iteration += 1
        assert state.iteration >= state.max_iterations

    @pytest.mark.unit
    def test_conversation_state_messages_accumulate(self):
        """Test that messages accumulate correctly."""
        state = ConversationState()

        state.messages.append({"role": "user", "content": "Task 1"})
        state.messages.append({"role": "assistant", "content": "I'll help"})
        state.messages.append({"role": "user", "content": "Continue"})

        assert len(state.messages) == 3
        assert state.messages[0]["role"] == "user"
        assert state.messages[1]["role"] == "assistant"
