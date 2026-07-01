"""Tests for control tools (CompleteTool)."""

from pathlib import Path


from scrappy.agent_tools.tools.control_tools import CompleteTool
from scrappy.agent_tools.tools.base import ToolContext
from scrappy.agent_config import AgentConfig


class TestCompleteTool:
    """Test CompleteTool behavior."""

    def test_name(self):
        """Verify tool has correct name."""
        tool = CompleteTool()
        assert tool.name == "complete"

    def test_description(self):
        """Verify tool has description."""
        tool = CompleteTool()
        assert tool.description
        assert "complete" in tool.description.lower()

    def test_parameters(self):
        """Verify tool has correct parameters."""
        tool = CompleteTool()
        params = tool.parameters
        assert len(params) == 1
        assert params[0].name == "result"
        assert params[0].param_type is str

    def test_execute_returns_success(self):
        """Verify execute returns successful ToolResult."""
        tool = CompleteTool()
        context = ToolContext(project_root=Path("."), config=AgentConfig())

        result = tool.execute(context, result="Task completed successfully")

        assert result.success is True
        assert result.output == "Task completed successfully"
        assert result.error is None

    def test_execute_sets_stop_loop_metadata(self):
        """Verify execute sets stop_loop metadata to trigger loop termination."""
        tool = CompleteTool()
        context = ToolContext(project_root=Path("."), config=AgentConfig())

        result = tool.execute(context, result="All done")

        assert result.metadata.get("stop_loop") is True

    def test_execute_with_empty_result(self):
        """Verify execute handles empty result string."""
        tool = CompleteTool()
        context = ToolContext(project_root=Path("."), config=AgentConfig())

        result = tool.execute(context, result="")

        assert result.success is True
        assert result.output == ""
        assert result.metadata.get("stop_loop") is True

    def test_execute_with_multiline_result(self):
        """Verify execute handles multiline result."""
        tool = CompleteTool()
        context = ToolContext(project_root=Path("."), config=AgentConfig())

        multiline_result = """Task completed:
- Created 3 files
- Ran tests
- All passing"""

        result = tool.execute(context, result=multiline_result)

        assert result.success is True
        assert result.output == multiline_result
        assert result.metadata.get("stop_loop") is True


class TestCompleteToolInRegistry:
    """Test CompleteTool integration with registry."""

    def test_registered_in_default_registry(self):
        """Verify CompleteTool is registered in default registry."""
        from scrappy.agent_tools.registry_factory import create_default_registry

        registry = create_default_registry()

        assert registry.exists("complete")

    def test_schema_in_openai_format(self):
        """Verify CompleteTool schema is in OpenAI format."""
        from scrappy.agent_tools.registry_factory import create_default_registry

        registry = create_default_registry()
        schemas = registry.to_openai_schema()

        # Find complete tool schema
        complete_schema = None
        for schema in schemas:
            if schema["function"]["name"] == "complete":
                complete_schema = schema
                break

        assert complete_schema is not None
        assert complete_schema["type"] == "function"
        assert "result" in complete_schema["function"]["parameters"]["properties"]

    def test_can_execute_via_registry(self):
        """Verify CompleteTool can be executed via registry."""
        from scrappy.agent_tools.registry_factory import create_default_registry

        registry = create_default_registry()
        context = ToolContext(project_root=Path("."), config=AgentConfig())

        tool = registry.get("complete")
        result = tool.execute(context, result="Done via registry")

        assert result.success is True
        assert result.output == "Done via registry"
        assert result.metadata.get("stop_loop") is True
