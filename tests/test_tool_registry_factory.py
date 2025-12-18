"""
Tests for ToolRegistryFactory - standalone registry creation.

These tests prepare for extracting _create_default_registry from CodeAgent
into a standalone factory function/class. This enables:
- Independent testing of registry configuration
- Dependency injection of different registries
- Separation of concerns (configuration vs orchestration)

TDD: These tests will FAIL until we create src/agent_tools/registry_factory.py
"""
import pytest
from unittest.mock import Mock, patch

from scrappy.agent_tools.tools import ToolRegistry

# These imports will FAIL until we create the factory module
# This is intentional TDD - tests fail first, then we implement
from scrappy.agent_tools.registry_factory import (
    create_default_registry,
    create_minimal_registry
)


class TestToolRegistryFactoryBehavior:
    """Tests for the factory behavior we want to extract."""

    @pytest.mark.unit

    @pytest.mark.unit
    def test_default_registry_has_file_tools(self):
        """Default registry should include file operation tools."""
        registry = create_default_registry()
        tool_names = [t.name for t in registry.list_all()]

        assert "read_file" in tool_names
        assert "write_file" in tool_names
        assert "list_files" in tool_names
        assert "list_directory" in tool_names

    @pytest.mark.unit
    def test_default_registry_has_git_tools(self):
        """Default registry should include git tools."""
        registry = create_default_registry()
        tool_names = [t.name for t in registry.list_all()]

        assert "git_log" in tool_names
        assert "git_status" in tool_names
        assert "git_diff" in tool_names
        assert "git_blame" in tool_names
        assert "git_show" in tool_names
        assert "git_recent_changes" in tool_names

    @pytest.mark.unit
    def test_default_registry_has_search_tools(self):
        """Default registry should include search tools."""
        registry = create_default_registry()
        tool_names = [t.name for t in registry.list_all()]

        assert "find_exact_text" in tool_names
        assert "codebase_search" in tool_names

    @pytest.mark.unit
    def test_default_registry_has_web_tools(self):
        """Default registry should include web tools."""
        registry = create_default_registry()
        tool_names = [t.name for t in registry.list_all()]

        assert "web_fetch" in tool_names
        assert "web_search" in tool_names

    @pytest.mark.unit
    def test_default_registry_has_python_tools(self):
        """Default registry should include Python analysis tools."""
        registry = create_default_registry()
        tool_names = [t.name for t in registry.list_all()]

        assert "analyze_python_dependencies" in tool_names

    @pytest.mark.unit
    def test_default_registry_tool_count(self):
        """Default registry should have expected number of tools."""
        registry = create_default_registry()

        # 4 file + 6 git + 2 search + 2 web + 1 python + 1 command + 1 complete + 1 task = 18 tools
        assert len(registry.list_all()) == 18

    @pytest.mark.unit
    def test_all_tools_are_callable(self):
        """All tools in registry should be callable."""
        registry = create_default_registry()

        for tool in registry.list_all():
            assert callable(tool), f"Tool {tool.name} is not callable"


    @pytest.mark.unit
    def test_all_tools_have_descriptions(self):
        """All tools should have descriptions for LLM context."""
        registry = create_default_registry()

        for tool in registry.list_all():
            assert hasattr(tool, 'description'), f"Tool {tool.name} missing description"
            assert tool.description, f"Tool {tool.name} has empty description"

    @pytest.mark.unit
    def test_no_duplicate_tool_names(self):
        """Registry should not have duplicate tool names."""
        registry = create_default_registry()
        tool_names = [t.name for t in registry.list_all()]

        assert len(tool_names) == len(set(tool_names)), "Duplicate tool names found"

    @pytest.mark.unit
    def test_factory_creates_fresh_instances(self):
        """Each factory call should create new tool instances."""
        registry1 = create_default_registry()
        registry2 = create_default_registry()

        # Different registry instances
        assert registry1 is not registry2

        # Tools should also be different instances
        tools1 = {t.name: t for t in registry1.list_all()}
        tools2 = {t.name: t for t in registry2.list_all()}

        for name in tools1:
            assert tools1[name] is not tools2[name], f"Tool {name} is same instance"


class TestToolRegistryFactoryCustomization:
    """Tests for customizing registry creation."""

    @pytest.mark.unit
    def test_can_inject_semantic_search_provider(self):
        """Should be able to inject semantic search provider to codebase_search tool."""
        mock_semantic_search = Mock()
        mock_semantic_search.is_indexed.return_value = True

        registry = create_default_registry(semantic_search=mock_semantic_search)

        # Find the codebase_search tool
        codebase_search_tool = None
        for tool in registry.list_all():
            if tool.name == "codebase_search":
                codebase_search_tool = tool
                break

        assert codebase_search_tool is not None, "codebase_search tool not found in registry"
        # Verify the tool received the semantic_search dependency
        assert hasattr(codebase_search_tool, '_semantic_search')
        assert codebase_search_tool._semantic_search is mock_semantic_search

    @pytest.mark.unit
    def test_codebase_search_without_semantic_provider(self):
        """codebase_search tool should handle None semantic_search gracefully."""
        registry = create_default_registry(semantic_search=None)

        # Find the codebase_search tool
        codebase_search_tool = None
        for tool in registry.list_all():
            if tool.name == "codebase_search":
                codebase_search_tool = tool
                break

        assert codebase_search_tool is not None, "codebase_search tool not found in registry"
        # Should have None semantic_search
        assert hasattr(codebase_search_tool, '_semantic_search')
        assert codebase_search_tool._semantic_search is None

    @pytest.mark.unit
    def test_can_create_minimal_registry(self):
        """Should be able to create registry with subset of tools."""
        registry = create_minimal_registry()
        tool_names = [t.name for t in registry.list_all()]

        # Minimal should have just core file operations
        assert "read_file" in tool_names
        assert "write_file" in tool_names
        # But not everything
        assert len(tool_names) < 14

    @pytest.mark.unit
    def test_can_create_registry_without_web_tools(self):
        """Should be able to exclude web tools for offline mode."""
        registry = create_default_registry(include_web=False)
        tool_names = [t.name for t in registry.list_all()]

        assert "web_fetch" not in tool_names
        assert "web_search" not in tool_names
        # But other tools present
        assert "read_file" in tool_names
        assert "git_status" in tool_names

    @pytest.mark.unit
    def test_can_create_registry_without_git_tools(self):
        """Should be able to exclude git tools for non-git projects."""
        registry = create_default_registry(include_git=False)
        tool_names = [t.name for t in registry.list_all()]

        assert "git_log" not in tool_names
        assert "git_status" not in tool_names
        # But other tools present
        assert "read_file" in tool_names
        assert "find_exact_text" in tool_names

    @pytest.mark.unit
    def test_can_add_custom_tools_to_registry(self):
        """Should be able to add custom tools to default registry."""
        registry = create_default_registry()

        # Create a mock custom tool
        custom_tool = Mock()
        custom_tool.name = "custom_analysis"
        custom_tool.description = "Custom analysis tool"

        registry.register(custom_tool)

        tool_names = [t.name for t in registry.list_all()]
        assert "custom_analysis" in tool_names
        assert len(tool_names) == 19  # 18 default + 1 custom


class TestToolRegistryFactoryIntegration:
    """Tests for factory integration with CodeAgent."""

    @pytest.mark.unit
    def test_code_agent_can_use_factory_registry(self, mock_orchestrator_adapter, tmp_path):
        """CodeAgent should accept registry from factory."""
        from scrappy.agent.core import CodeAgent
        from scrappy.agent_config import AgentConfig

        # Create registry using factory
        registry = create_default_registry()

        # Inject into CodeAgent
        agent = CodeAgent(
            orchestrator=mock_orchestrator_adapter,
            project_path=str(tmp_path),
            config=AgentConfig(),
            tool_registry=registry
        )

        # Should use the injected registry
        assert agent.tool_registry is registry

    @pytest.mark.unit
    def test_code_agent_tools_match_registry(self, mock_orchestrator_adapter, tmp_path):
        """CodeAgent.tools dict should include all registry tools."""
        from scrappy.agent.core import CodeAgent
        from scrappy.agent_config import AgentConfig

        registry = create_default_registry()

        agent = CodeAgent(
            orchestrator=mock_orchestrator_adapter,
            project_path=str(tmp_path),
            config=AgentConfig(),
            tool_registry=registry
        )

        # All registry tools should be in agent.tools
        for tool in registry.list_all():
            assert tool.name in agent.tools, f"Registry tool {tool.name} not in agent.tools"

    @pytest.mark.unit
    def test_agent_with_minimal_registry(self, mock_orchestrator_adapter, tmp_path):
        """CodeAgent should work with minimal registry."""
        from scrappy.agent.core import CodeAgent
        from scrappy.agent_config import AgentConfig

        # Create minimal registry
        registry = create_minimal_registry()

        agent = CodeAgent(
            orchestrator=mock_orchestrator_adapter,
            project_path=str(tmp_path),
            config=AgentConfig(),
            tool_registry=registry
        )

        # Should have fewer tools
        registry_tool_count = len(registry.list_all())
        # +1 for run_command which is always added
        assert len(agent.tools) == registry_tool_count + 1


# Fixtures

@pytest.fixture
def mock_orchestrator_adapter():
    """Create a minimal mock orchestrator adapter for testing."""
    from scrappy.orchestrator_adapter import OrchestratorAdapter

    adapter = Mock(spec=OrchestratorAdapter)
    adapter.list_providers.return_value = ["mock_provider"]
    adapter.context = Mock()
    adapter.context.format_for_prompt.return_value = "Mock context"
    adapter.delegate.return_value = Mock(content="test", provider="mock_provider")
    return adapter
