"""
Tests for CodeAgent - execution flows, action parsing, and tool orchestration.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch, call
from pathlib import Path
from dataclasses import dataclass
import json

from scrappy.agent.core import CodeAgent
from scrappy.agent.types import (
    AgentThought,
    AgentAction,
    ActionResult,
    ConversationState
)
from scrappy.agent_config import AgentConfig
from scrappy.agent_tools.tools import ToolRegistry
from scrappy.orchestrator_adapter import OrchestratorAdapter


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
        # Configure get_recommended_provider to return proper provider strings
        mock_adapter.get_recommended_provider.return_value = "cerebras"

        agent = CodeAgent(
            orchestrator=mock_adapter,
            project_path=str(temp_project_dir)
        )

        # Should select from available providers using orchestrator's recommendation
        assert agent.planner is not None
        # planner should be a string provider name
        assert isinstance(agent.planner, str)
        # Agent should use orchestrator's recommendation
        assert agent.planner == "cerebras"

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
  # JSON parsing not the focus here

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
