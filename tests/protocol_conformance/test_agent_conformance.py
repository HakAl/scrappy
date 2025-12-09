"""Agent protocol conformance tests.

Tests that agent component implementations correctly conform to their protocols:
- ResponseParserProtocol
- ToolRegistryProtocol
"""

import pytest

from tests.protocol_conformance.conftest import (
    assert_implements_protocol,
    assert_has_method,
)

from scrappy.agent.protocols import (
    ResponseParserProtocol,
    ToolRegistryProtocol,
)


class TestResponseParserProtocolConformance:
    """Tests for ResponseParserProtocol implementations."""








class TestResponseParserBehavior:
    """Tests that verify actual parser behavior matches protocol contract."""

    def test_json_parser_returns_parse_result(self):
        """JSONResponseParser.parse() should return ParseResult."""
        from scrappy.agent.response_parser import JSONResponseParser, ParseResult

        parser = JSONResponseParser()
        result = parser.parse('{"thought": "test", "action": "test_action", "parameters": {}}')

        assert isinstance(result, ParseResult)

    def test_json_parser_handles_empty_input(self):
        """JSONResponseParser.parse() should handle empty input gracefully."""
        from scrappy.agent.response_parser import JSONResponseParser

        parser = JSONResponseParser()
        result = parser.parse("")

        # Should not raise, should return error result
        assert result.error is not None

    def test_native_parser_returns_parse_result(self):
        """NativeToolCallParser.parse() should return ParseResult."""
        from scrappy.agent.response_parser import NativeToolCallParser, ParseResult

        parser = NativeToolCallParser()
        # parse() only accepts text; use parse_response() for LLMResponse with tool_calls
        result = parser.parse("")

        assert isinstance(result, ParseResult)

    def test_unified_parser_returns_parse_result(self):
        """UnifiedResponseParser.parse() should return ParseResult."""
        from scrappy.agent.response_parser import UnifiedResponseParser, ParseResult

        parser = UnifiedResponseParser()
        result = parser.parse('{"thought": "test", "action": "complete", "parameters": {}}')

        assert isinstance(result, ParseResult)


class TestToolRegistryConformance:
    """Tests for ToolRegistry implementation."""








class TestToolRegistryBehavior:
    """Tests that verify actual registry behavior matches protocol contract."""

    def test_registry_register_and_get(self):
        """register() and get() should work together."""
        from scrappy.agent_tools.tools.registry import ToolRegistry
        from scrappy.agent_tools.tools.base import ToolBase, ToolParameter, ToolResult, ToolContext

        # Create a minimal test tool
        class TestTool(ToolBase):
            @property
            def name(self) -> str:
                return "test_tool"

            @property
            def description(self) -> str:
                return "Test tool"

            @property
            def parameters(self) -> list:
                return []

            def execute(self, context: ToolContext, **kwargs) -> ToolResult:
                return ToolResult(success=True, output="test")

        registry = ToolRegistry()
        tool = TestTool()

        registry.register(tool)
        retrieved = registry.get("test_tool")

        assert retrieved is tool

    def test_registry_list_all_returns_tools(self):
        """list_all() should return list of registered tools."""
        from scrappy.agent_tools.tools.registry import ToolRegistry
        from scrappy.agent_tools.tools.base import ToolBase, ToolParameter, ToolResult, ToolContext

        class TestTool(ToolBase):
            @property
            def name(self) -> str:
                return "list_test_tool"

            @property
            def description(self) -> str:
                return "Test tool"

            @property
            def parameters(self) -> list:
                return []

            def execute(self, context: ToolContext, **kwargs) -> ToolResult:
                return ToolResult(success=True, output="test")

        registry = ToolRegistry()
        tool = TestTool()
        registry.register(tool)

        tools = registry.list_all()

        assert isinstance(tools, list)
        assert tool in tools

    def test_registry_get_returns_none_for_missing(self):
        """get() should return None for non-existent tools."""
        from scrappy.agent_tools.tools.registry import ToolRegistry

        registry = ToolRegistry()
        result = registry.get("nonexistent")

        assert result is None


    def test_registry_unregister_removes_tool(self):
        """unregister() should remove tool from registry."""
        from scrappy.agent_tools.tools.registry import ToolRegistry
        from scrappy.agent_tools.tools.base import ToolBase, ToolResult, ToolContext

        class TestTool(ToolBase):
            @property
            def name(self) -> str:
                return "unregister_test"

            @property
            def description(self) -> str:
                return "Test tool"

            @property
            def parameters(self) -> list:
                return []

            def execute(self, context: ToolContext, **kwargs) -> ToolResult:
                return ToolResult(success=True, output="test")

        registry = ToolRegistry()
        tool = TestTool()
        registry.register(tool)

        registry.unregister("unregister_test")

        assert registry.get("unregister_test") is None


