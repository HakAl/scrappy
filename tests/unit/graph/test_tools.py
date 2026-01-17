"""
Unit tests for ToolAdapter.

Tests the LangGraph tool adapter that wraps ToolRegistry.
"""

from pathlib import Path

from scrappy.agent_tools.tools.base import (
    ToolBase,
    ToolContext,
    ToolParameter,
    ToolResult as BaseToolResult,
)
from scrappy.agent_tools.tools.registry import ToolRegistry
from scrappy.graph.state import ToolCall
from scrappy.graph.tools import ToolAdapter, ToolAdapterProtocol


def make_tool_call(id: str, name: str, arguments: str = "{}") -> ToolCall:
    """Create a ToolCall in OpenAI format for testing."""
    return {
        "type": "function",
        "id": id,
        "function": {
            "name": name,
            "arguments": arguments,
        },
    }


class MockTool(ToolBase):
    """A simple mock tool for testing."""

    def __init__(
        self,
        name: str = "mock_tool",
        description: str = "A mock tool for testing",
        return_value: str = "mock result",
        should_fail: bool = False,
    ):
        self._name = name
        self._description = description
        self._return_value = return_value
        self._should_fail = should_fail

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="input",
                param_type=str,
                description="Input to process",
                required=False,
            )
        ]

    def execute(self, context: ToolContext, **kwargs) -> BaseToolResult:
        if self._should_fail:
            return BaseToolResult(
                success=False,
                output="",
                error="Mock failure",
            )
        input_val = kwargs.get("input", "")
        return BaseToolResult(
            success=True,
            output=f"{self._return_value}: {input_val}" if input_val else self._return_value,
        )


def create_test_context() -> ToolContext:
    """Create a minimal ToolContext for testing."""
    return ToolContext(
        project_root=Path("."),
        dry_run=True,
    )


class TestToolAdapterProtocol:
    """Test that ToolAdapter implements the protocol."""

    def test_adapter_implements_protocol(self):
        """ToolAdapter should implement ToolAdapterProtocol."""
        registry = ToolRegistry()
        adapter = ToolAdapter(registry)
        assert isinstance(adapter, ToolAdapterProtocol)


class TestToolAdapterGetToolSchemas:
    """Tests for get_tool_schemas method."""

    def test_returns_empty_list_for_empty_registry(self):
        """Empty registry should return empty schema list."""
        registry = ToolRegistry()
        adapter = ToolAdapter(registry)

        schemas = adapter.get_tool_schemas()

        assert schemas == []

    def test_returns_openai_format_schema(self):
        """Schema should be in OpenAI function calling format."""
        registry = ToolRegistry()
        registry.register(MockTool(name="test_tool", description="Test description"))
        adapter = ToolAdapter(registry)

        schemas = adapter.get_tool_schemas()

        assert len(schemas) == 1
        schema = schemas[0]

        # Verify OpenAI format structure
        assert schema["type"] == "function"
        assert "function" in schema
        assert schema["function"]["name"] == "test_tool"
        assert schema["function"]["description"] == "Test description"
        assert "parameters" in schema["function"]

    def test_schema_includes_parameter_definitions(self):
        """Schema should include parameter definitions."""
        registry = ToolRegistry()
        registry.register(MockTool())
        adapter = ToolAdapter(registry)

        schemas = adapter.get_tool_schemas()

        params = schemas[0]["function"]["parameters"]
        assert params["type"] == "object"
        assert "input" in params["properties"]
        assert params["properties"]["input"]["type"] == "string"

    def test_multiple_tools_return_multiple_schemas(self):
        """Multiple tools should return multiple schemas."""
        registry = ToolRegistry()
        registry.register(MockTool(name="tool_a", description="Tool A"))
        registry.register(MockTool(name="tool_b", description="Tool B"))
        adapter = ToolAdapter(registry)

        schemas = adapter.get_tool_schemas()

        assert len(schemas) == 2
        names = {s["function"]["name"] for s in schemas}
        assert names == {"tool_a", "tool_b"}


class TestToolAdapterExecute:
    """Tests for execute method."""

    def test_execute_single_tool_call(self):
        """Should execute a single tool call and return result."""
        registry = ToolRegistry()
        registry.register(MockTool(name="echo", return_value="echoed"))
        adapter = ToolAdapter(registry)
        context = create_test_context()

        tool_calls: list[ToolCall] = [
            make_tool_call("call_1", "echo", '{"input": "hello"}')
        ]

        results = adapter.execute(tool_calls, context)

        assert len(results) == 1
        assert results[0]["name"] == "echo"
        assert "result" in results[0]
        assert "echoed: hello" in results[0]["result"]

    def test_execute_multiple_tool_calls(self):
        """Should execute multiple tool calls sequentially."""
        registry = ToolRegistry()
        registry.register(MockTool(name="tool_a", return_value="result_a"))
        registry.register(MockTool(name="tool_b", return_value="result_b"))
        adapter = ToolAdapter(registry)
        context = create_test_context()

        tool_calls: list[ToolCall] = [
            make_tool_call("call_1", "tool_a"),
            make_tool_call("call_2", "tool_b"),
        ]

        results = adapter.execute(tool_calls, context)

        assert len(results) == 2
        assert results[0]["name"] == "tool_a"
        assert results[1]["name"] == "tool_b"
        assert "result_a" in results[0]["result"]
        assert "result_b" in results[1]["result"]

    def test_execute_with_empty_arguments(self):
        """Should handle tool call with no arguments."""
        registry = ToolRegistry()
        registry.register(MockTool(name="no_args", return_value="no args result"))
        adapter = ToolAdapter(registry)
        context = create_test_context()

        tool_calls: list[ToolCall] = [
            make_tool_call("call_1", "no_args")
        ]

        results = adapter.execute(tool_calls, context)

        assert len(results) == 1
        assert "result" in results[0]
        assert "no args result" in results[0]["result"]

    def test_execute_tool_not_found(self):
        """Should return error for unknown tool."""
        registry = ToolRegistry()
        adapter = ToolAdapter(registry)
        context = create_test_context()

        tool_calls: list[ToolCall] = [
            make_tool_call("call_1", "nonexistent_tool")
        ]

        results = adapter.execute(tool_calls, context)

        assert len(results) == 1
        assert results[0]["name"] == "nonexistent_tool"
        assert "error" in results[0]
        assert "not found" in results[0]["error"]

    def test_execute_invalid_json_arguments(self):
        """Should return error for invalid JSON arguments."""
        registry = ToolRegistry()
        registry.register(MockTool(name="test"))
        adapter = ToolAdapter(registry)
        context = create_test_context()

        tool_calls: list[ToolCall] = [
            make_tool_call("call_1", "test", "not valid json")
        ]

        results = adapter.execute(tool_calls, context)

        assert len(results) == 1
        assert "error" in results[0]
        assert "Invalid arguments JSON" in results[0]["error"]

    def test_execute_continues_after_error(self):
        """Should continue executing remaining tools after one fails."""
        registry = ToolRegistry()
        registry.register(MockTool(name="will_fail", should_fail=True))
        registry.register(MockTool(name="will_succeed", return_value="success"))
        adapter = ToolAdapter(registry)
        context = create_test_context()

        tool_calls: list[ToolCall] = [
            make_tool_call("call_1", "will_fail"),
            make_tool_call("call_2", "will_succeed"),
        ]

        results = adapter.execute(tool_calls, context)

        assert len(results) == 2
        # First tool returned an error in its output (via ToolResult.error)
        # The registry.execute returns the string output, which includes "Error:"
        assert results[0]["name"] == "will_fail"
        # Second tool should still succeed
        assert results[1]["name"] == "will_succeed"
        assert "success" in results[1]["result"]

    def test_execute_empty_tool_calls(self):
        """Should return empty list for empty tool calls."""
        registry = ToolRegistry()
        adapter = ToolAdapter(registry)
        context = create_test_context()

        results = adapter.execute([], context)

        assert results == []


class TestToolAdapterGetToolNames:
    """Tests for get_tool_names method."""

    def test_returns_empty_list_for_empty_registry(self):
        """Empty registry should return empty names list."""
        registry = ToolRegistry()
        adapter = ToolAdapter(registry)

        names = adapter.get_tool_names()

        assert names == []

    def test_returns_registered_tool_names(self):
        """Should return names of all registered tools."""
        registry = ToolRegistry()
        registry.register(MockTool(name="alpha"))
        registry.register(MockTool(name="beta"))
        registry.register(MockTool(name="gamma"))
        adapter = ToolAdapter(registry)

        names = adapter.get_tool_names()

        assert set(names) == {"alpha", "beta", "gamma"}


class TestToolAdapterFactory:
    """Tests for factory methods."""

    def test_create_default_has_tools(self):
        """create_default should have default tools registered."""
        adapter = ToolAdapter.create_default()

        names = adapter.get_tool_names()

        # Should have some tools registered
        assert len(names) > 0
        # Should have common tools like read_file
        assert "read_file" in names


class TestToolResultFormat:
    """Tests for ToolResult format compatibility."""

    def test_result_has_name_field(self):
        """ToolResult should have name field."""
        registry = ToolRegistry()
        registry.register(MockTool(name="test"))
        adapter = ToolAdapter(registry)
        context = create_test_context()

        tool_calls: list[ToolCall] = [make_tool_call("1", "test")]
        results = adapter.execute(tool_calls, context)

        assert "name" in results[0]

    def test_success_result_has_result_field(self):
        """Successful execution should have result field."""
        registry = ToolRegistry()
        registry.register(MockTool(name="test", return_value="test output"))
        adapter = ToolAdapter(registry)
        context = create_test_context()

        tool_calls: list[ToolCall] = [make_tool_call("1", "test")]
        results = adapter.execute(tool_calls, context)

        assert "result" in results[0]
        assert "error" not in results[0]

    def test_error_result_has_error_field(self):
        """Failed execution should have error field."""
        registry = ToolRegistry()
        adapter = ToolAdapter(registry)
        context = create_test_context()

        tool_calls: list[ToolCall] = [make_tool_call("1", "nonexistent")]
        results = adapter.execute(tool_calls, context)

        assert "error" in results[0]

    def test_tool_returning_error_result_puts_error_in_error_field(self):
        """Tool returning ToolResult(success=False, error=...) should have error in error field.

        This is critical for error visibility - errors must be in the 'error' field,
        not hidden in the 'result' field as a string.
        """
        registry = ToolRegistry()
        registry.register(MockTool(name="failing_tool", should_fail=True))
        adapter = ToolAdapter(registry)
        context = create_test_context()

        tool_calls: list[ToolCall] = [make_tool_call("1", "failing_tool")]
        results = adapter.execute(tool_calls, context)

        # Error should be in 'error' field, not 'result' field
        assert "error" in results[0], "Error should be in error field"
        assert results[0]["error"] == "Mock failure"
        assert results[0].get("result") is None, "Error should not be in result field"


class TestToolAdapterEdgeCases:
    """Edge case tests for unusual or malformed inputs."""

    def test_empty_tool_name(self):
        """Empty tool name should return not found error."""
        registry = ToolRegistry()
        adapter = ToolAdapter(registry)
        context = create_test_context()

        tool_calls: list[ToolCall] = [make_tool_call("1", "")]
        results = adapter.execute(tool_calls, context)

        assert "error" in results[0]
        assert "not found" in results[0]["error"]

    def test_whitespace_only_tool_name(self):
        """Whitespace-only tool name should return not found error."""
        registry = ToolRegistry()
        adapter = ToolAdapter(registry)
        context = create_test_context()

        tool_calls: list[ToolCall] = [make_tool_call("1", "   ")]
        results = adapter.execute(tool_calls, context)

        assert "error" in results[0]

    def test_unicode_in_arguments(self):
        """Unicode characters in arguments should be handled."""
        registry = ToolRegistry()
        registry.register(MockTool(name="unicode_test"))
        adapter = ToolAdapter(registry)
        context = create_test_context()

        tool_calls: list[ToolCall] = [
            make_tool_call("1", "unicode_test", '{"input": "Hello world"}')
        ]
        results = adapter.execute(tool_calls, context)

        assert "result" in results[0]

    def test_empty_json_object_arguments(self):
        """Empty JSON object arguments should work."""
        registry = ToolRegistry()
        registry.register(MockTool(name="test"))
        adapter = ToolAdapter(registry)
        context = create_test_context()

        tool_calls: list[ToolCall] = [
            make_tool_call("1", "test", "{}")
        ]
        results = adapter.execute(tool_calls, context)

        assert "result" in results[0]

    def test_empty_string_arguments(self):
        """Empty string arguments should be treated as empty JSON object."""
        registry = ToolRegistry()
        registry.register(MockTool(name="test"))
        adapter = ToolAdapter(registry)
        context = create_test_context()

        tool_calls: list[ToolCall] = [
            make_tool_call("1", "test", "")
        ]
        results = adapter.execute(tool_calls, context)

        assert "result" in results[0]

    def test_null_in_json_arguments(self):
        """JSON with null value should be validated.

        When a tool expects string but receives null, validation should fail.
        """
        registry = ToolRegistry()
        registry.register(MockTool(name="test"))  # MockTool expects string input
        adapter = ToolAdapter(registry)
        context = create_test_context()

        tool_calls: list[ToolCall] = [
            make_tool_call("1", "test", '{"input": null}')
        ]
        results = adapter.execute(tool_calls, context)

        # Null is not a valid string, so validation should fail
        assert "error" in results[0]
        assert "must be string" in results[0]["error"]

    def test_nested_json_arguments(self):
        """Nested JSON in arguments should be validated.

        When a tool expects string but receives nested object, validation fails.
        """
        registry = ToolRegistry()
        registry.register(MockTool(name="test"))  # MockTool expects string input
        adapter = ToolAdapter(registry)
        context = create_test_context()

        tool_calls: list[ToolCall] = [
            make_tool_call("1", "test", '{"input": {"nested": "value"}}')
        ]
        results = adapter.execute(tool_calls, context)

        # Nested object is not a valid string, so validation should fail
        assert "error" in results[0]
        assert "must be string" in results[0]["error"]

    def test_very_long_arguments(self):
        """Very long argument strings should be handled."""
        registry = ToolRegistry()
        registry.register(MockTool(name="test"))
        adapter = ToolAdapter(registry)
        context = create_test_context()

        long_input = "x" * 10000
        tool_calls: list[ToolCall] = [
            make_tool_call("1", "test", f'{{"input": "{long_input}"}}')
        ]
        results = adapter.execute(tool_calls, context)

        assert "result" in results[0]

    def test_special_characters_in_arguments(self):
        """Special characters in arguments should be handled."""
        registry = ToolRegistry()
        registry.register(MockTool(name="test"))
        adapter = ToolAdapter(registry)
        context = create_test_context()

        tool_calls: list[ToolCall] = [
            make_tool_call("1", "test", '{"input": "line1\\nline2\\ttab"}')
        ]
        results = adapter.execute(tool_calls, context)

        assert "result" in results[0]

    def test_json_array_arguments_invalid(self):
        """JSON array as arguments should be handled (likely error)."""
        registry = ToolRegistry()
        registry.register(MockTool(name="test"))
        adapter = ToolAdapter(registry)
        context = create_test_context()

        tool_calls: list[ToolCall] = [
            make_tool_call("1", "test", "[1, 2, 3]")
        ]
        results = adapter.execute(tool_calls, context)

        # Arrays are not valid kwargs, but parsing should not crash
        # The execute method should handle this gracefully
        assert "name" in results[0]

    def test_duplicate_tool_calls(self):
        """Duplicate tool calls should all be executed."""
        registry = ToolRegistry()
        registry.register(MockTool(name="test", return_value="result"))
        adapter = ToolAdapter(registry)
        context = create_test_context()

        tool_calls: list[ToolCall] = [
            make_tool_call("1", "test"),
            make_tool_call("2", "test"),
            make_tool_call("3", "test"),
        ]
        results = adapter.execute(tool_calls, context)

        assert len(results) == 3
        assert all(r["name"] == "test" for r in results)

    def test_empty_id_in_tool_call(self):
        """Tool call with empty id should still execute."""
        registry = ToolRegistry()
        registry.register(MockTool(name="test"))
        adapter = ToolAdapter(registry)
        context = create_test_context()

        tool_calls: list[ToolCall] = [make_tool_call("", "test")]
        results = adapter.execute(tool_calls, context)

        assert "result" in results[0]
