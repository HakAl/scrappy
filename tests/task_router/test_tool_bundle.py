"""
Tests for ToolBundle.

Tests the behavior of tool management for research tasks,
including tool registry, execution, and validation.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock
from scrappy.task_router.strategies.tool_bundle import ToolBundle


class FakeTool:
    """Test double for tool instances."""

    def __init__(self, name: str, description: str, result: str = "success", should_fail: bool = False):
        self.name = name
        self.description = description
        self.result = result
        self.should_fail = should_fail
        self.calls = []

    def get_full_description(self) -> str:
        """Return tool description."""
        return f"{self.name}: {self.description}"

    def __call__(self, context, **params):
        """Execute tool and record call."""
        self.calls.append({'context': context, 'params': params})
        if self.should_fail:
            raise ValueError(f"Tool {self.name} failed")
        return self.result


class FakeToolRegistry:
    """Test double for tool registry."""

    def __init__(self):
        self.tools = {}

    def register(self, tool):
        """Register a tool."""
        self.tools[tool.name] = tool

    def get(self, name: str):
        """Get a tool by name."""
        return self.tools.get(name)


class TestToolBundleInitialization:
    """Test ToolBundle initialization."""

    def test_creates_with_provided_registry_and_context(self):
        """Initializes with provided registry and context."""
        registry = FakeToolRegistry()
        context = Mock()

        bundle = ToolBundle(
            tool_registry=registry,
            tool_context=context,
            project_root=Path("/test")
        )

        assert bundle._tool_registry is registry
        assert bundle._tool_context is context
        assert bundle._project_root == Path("/test")

    def test_has_tools_returns_true_when_registry_exists(self):
        """has_tools returns True when registry is available."""
        registry = FakeToolRegistry()
        bundle = ToolBundle(tool_registry=registry)

        assert bundle.has_tools() is True

    def test_has_tools_returns_false_when_no_registry(self):
        """has_tools returns False when registry is None."""
        bundle = ToolBundle(tool_registry=None)

        assert bundle.has_tools() is False

    def test_uses_default_project_root_when_not_provided(self):
        """Uses current working directory as default project root."""
        bundle = ToolBundle()

        assert bundle._project_root == Path.cwd()


class TestToolBundleDescriptions:
    """Test tool description generation."""

    def test_returns_empty_string_when_no_registry(self):
        """Returns empty string when registry is not available."""
        bundle = ToolBundle(tool_registry=None)

        result = bundle.get_tool_descriptions()

        assert result == ""

    def test_returns_descriptions_for_available_tools(self):
        """Returns formatted descriptions for research tools."""
        registry = FakeToolRegistry()
        registry.register(FakeTool("web_fetch", "Fetch web content"))
        registry.register(FakeTool("read_file", "Read a file"))

        bundle = ToolBundle(tool_registry=registry)

        result = bundle.get_tool_descriptions()

        assert "- web_fetch: Fetch web content" in result
        assert "- read_file: Read a file" in result

    def test_ignores_tools_not_in_research_tools_list(self):
        """Only includes tools that are in RESEARCH_TOOLS list."""
        registry = FakeToolRegistry()
        registry.register(FakeTool("web_fetch", "Fetch web content"))
        registry.register(FakeTool("write_file", "Write to file"))  # Not in RESEARCH_TOOLS

        bundle = ToolBundle(tool_registry=registry)

        result = bundle.get_tool_descriptions()

        assert "web_fetch" in result
        assert "write_file" not in result

    def test_handles_missing_tools_gracefully(self):
        """Handles case where RESEARCH_TOOLS has tools not in registry."""
        registry = FakeToolRegistry()
        # Only register one tool, but RESEARCH_TOOLS has many

        bundle = ToolBundle(tool_registry=registry)

        result = bundle.get_tool_descriptions()

        # Should not crash, just return empty or partial results
        assert isinstance(result, str)


class TestToolBundleValidation:
    """Test tool validation."""

    def test_allows_tools_in_research_tools_list(self):
        """Returns True for tools in RESEARCH_TOOLS."""
        bundle = ToolBundle()

        assert bundle.is_allowed_tool("web_fetch") is True
        assert bundle.is_allowed_tool("read_file") is True
        assert bundle.is_allowed_tool("search_code") is True
        assert bundle.is_allowed_tool("git_log") is True

    def test_rejects_tools_not_in_research_tools_list(self):
        """Returns False for tools not in RESEARCH_TOOLS."""
        bundle = ToolBundle()

        assert bundle.is_allowed_tool("write_file") is False
        assert bundle.is_allowed_tool("execute_shell") is False
        assert bundle.is_allowed_tool("delete_file") is False

    def test_rejects_empty_tool_name(self):
        """Returns False for empty string."""
        bundle = ToolBundle()

        assert bundle.is_allowed_tool("") is False

    def test_is_case_sensitive(self):
        """Tool name validation is case-sensitive."""
        bundle = ToolBundle()

        assert bundle.is_allowed_tool("WEB_FETCH") is False
        assert bundle.is_allowed_tool("Web_Fetch") is False


class TestToolBundleExecution:
    """Test tool execution."""

    def test_executes_tool_with_parameters(self):
        """Executes tool with provided parameters."""
        registry = FakeToolRegistry()
        tool = FakeTool("read_file", "Read a file", result="file content")
        registry.register(tool)

        context = Mock()
        bundle = ToolBundle(tool_registry=registry, tool_context=context)

        result = bundle.execute_tool({
            "tool": "read_file",
            "parameters": {"path": "test.txt"}
        })

        assert result == "file content"
        assert len(tool.calls) == 1
        assert tool.calls[0]['params'] == {"path": "test.txt"}
        assert tool.calls[0]['context'] is context

    def test_handles_missing_tool_name(self):
        """Returns error message when tool name is missing."""
        bundle = ToolBundle(tool_registry=FakeToolRegistry())

        result = bundle.execute_tool({"parameters": {}})

        assert "Error: No tool name specified" in result

    def test_handles_disallowed_tool(self):
        """Returns error when tool is not in RESEARCH_TOOLS."""
        registry = FakeToolRegistry()
        bundle = ToolBundle(tool_registry=registry)

        result = bundle.execute_tool({
            "tool": "write_file",
            "parameters": {}
        })

        assert "not available for research tasks" in result

    def test_handles_tool_not_found_in_registry(self):
        """Returns error when tool is not registered."""
        registry = FakeToolRegistry()
        bundle = ToolBundle(tool_registry=registry)

        result = bundle.execute_tool({
            "tool": "web_fetch",  # In RESEARCH_TOOLS but not registered
            "parameters": {}
        })

        assert "Tool 'web_fetch' not found" in result

    def test_handles_tool_execution_error(self):
        """Returns error message when tool execution fails."""
        registry = FakeToolRegistry()
        tool = FakeTool("read_file", "Read file", should_fail=True)
        registry.register(tool)

        bundle = ToolBundle(tool_registry=registry, tool_context=Mock())

        result = bundle.execute_tool({
            "tool": "read_file",
            "parameters": {"path": "test.txt"}
        })

        assert "Error executing read_file" in result
        assert "Tool read_file failed" in result

    def test_handles_missing_parameters(self):
        """Handles tool call with no parameters key."""
        registry = FakeToolRegistry()
        tool = FakeTool("web_fetch", "Fetch", result="fetched")
        registry.register(tool)

        bundle = ToolBundle(tool_registry=registry, tool_context=Mock())

        result = bundle.execute_tool({"tool": "web_fetch"})

        # Should pass empty dict as params
        assert result == "fetched"
        assert tool.calls[0]['params'] == {}

    def test_truncates_long_results(self):
        """Truncates results longer than 10000 characters."""
        registry = FakeToolRegistry()
        long_result = "A" * 15000
        tool = FakeTool("read_file", "Read", result=long_result)
        registry.register(tool)

        bundle = ToolBundle(tool_registry=registry, tool_context=Mock())

        result = bundle.execute_tool({
            "tool": "read_file",
            "parameters": {}
        })

        assert len(result) < len(long_result)
        assert "... [truncated]" in result
        assert len(result) <= 10000 + len("\n... [truncated]")

    def test_does_not_truncate_short_results(self):
        """Does not truncate results under 10000 characters."""
        registry = FakeToolRegistry()
        short_result = "A" * 5000
        tool = FakeTool("read_file", "Read", result=short_result)
        registry.register(tool)

        bundle = ToolBundle(tool_registry=registry, tool_context=Mock())

        result = bundle.execute_tool({
            "tool": "read_file",
            "parameters": {}
        })

        assert result == short_result
        assert "[truncated]" not in result

    def test_handles_no_registry_during_execution(self):
        """Returns error when trying to execute without registry."""
        bundle = ToolBundle(tool_registry=None)

        result = bundle.execute_tool({
            "tool": "read_file",
            "parameters": {}
        })

        assert "Tool registry not available" in result


class TestToolBundleFactoryMethod:
    """Test create_with_orchestrator factory method."""

    def test_creates_bundle_with_orchestrator_aware_context(self):
        """Factory creates bundle with orchestrator in context."""
        orchestrator = Mock()
        orchestrator.remember_file_read = Mock()

        bundle = ToolBundle.create_with_orchestrator(
            orchestrator=orchestrator,
            project_root=Path("/test")
        )

        assert bundle._project_root == Path("/test")
        # Context should be created with orchestrator

    def test_handles_orchestrator_without_remember_file_read(self):
        """Handles orchestrator that doesn't have remember_file_read."""
        orchestrator = Mock(spec=[])  # No attributes

        bundle = ToolBundle.create_with_orchestrator(orchestrator)

        # Should not crash, creates bundle anyway
        assert bundle is not None

    def test_uses_default_project_root_in_factory(self):
        """Factory uses cwd as default project root."""
        orchestrator = Mock()

        bundle = ToolBundle.create_with_orchestrator(orchestrator)

        assert bundle._project_root == Path.cwd()


class TestToolBundleEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_handles_tool_returning_none(self):
        """Handles tool that returns None instead of string."""
        registry = FakeToolRegistry()
        tool = FakeTool("read_file", "Read", result=None)
        registry.register(tool)

        bundle = ToolBundle(tool_registry=registry, tool_context=Mock())

        # Should not crash when checking length
        result = bundle.execute_tool({
            "tool": "read_file",
            "parameters": {}
        })

        assert result is None

    def test_handles_tool_call_with_extra_keys(self):
        """Handles tool call dict with extra unexpected keys."""
        registry = FakeToolRegistry()
        tool = FakeTool("read_file", "Read", result="ok")
        registry.register(tool)

        bundle = ToolBundle(tool_registry=registry, tool_context=Mock())

        result = bundle.execute_tool({
            "tool": "read_file",
            "parameters": {},
            "extra_key": "ignored",
            "another": 123
        })

        assert result == "ok"

    def test_all_research_tools_are_valid_strings(self):
        """RESEARCH_TOOLS constant contains only valid strings."""
        bundle = ToolBundle()

        for tool_name in bundle.RESEARCH_TOOLS:
            assert isinstance(tool_name, str)
            assert len(tool_name) > 0
            assert tool_name == tool_name.lower().replace(" ", "_")
