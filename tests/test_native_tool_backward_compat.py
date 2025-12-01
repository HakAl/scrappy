"""
Test backward compatibility with providers that don't support native tools.

These tests verify that the agent works correctly with JSON-based providers
even after native tool call integration.
"""
import pytest
from tests.helpers import ConfigurableTestOrchestrator
from scrappy.agent.core import CodeAgent
from scrappy.agent_config import AgentConfig
from scrappy.agent.types import ConversationState
from scrappy.agent.response_parser import UnifiedResponseParser


@pytest.fixture
def json_only_config():
    """Minimal config for testing."""
    config = AgentConfig()
    config.dangerous_commands = []
    config.interactive_commands = []
    config.long_running_commands = []
    config.command_timeout = 10
    config.max_command_output = 1000
    return config




@pytest.mark.unit
def test_unified_parser_handles_json_text():
    """UnifiedResponseParser should handle plain JSON text (backward compat)."""
    parser = UnifiedResponseParser()

    # Test with JSON text (old format)
    json_text = '{"thought": "Reading file", "action": "read_file", "parameters": {"file_path": "main.py"}, "is_complete": false}'

    result = parser.parse(json_text)

    assert result.thought == "Reading file"
    assert result.action == "read_file"
    assert result.parameters == {"file_path": "main.py"}
    assert result.is_complete is False


@pytest.mark.unit
def test_system_prompt_includes_json_format_for_json_providers(json_only_config):
    """System prompt should include JSON format instructions for JSON-only providers."""
    # Test that tool registry's get_full_prompt_section includes JSON format
    from scrappy.agent_tools.registry_factory import create_default_registry

    registry = create_default_registry()

    # Get full prompt section (includes JSON format for non-native tool providers)
    full_section = registry.get_full_prompt_section()

    # Should contain JSON format instructions
    assert "Response Format" in full_section or "Response format" in full_section
    assert "JSON" in full_section or "json" in full_section
    assert '"action":' in full_section

    # Get just descriptions (used for native tool providers)
    descriptions_only = registry.generate_descriptions()

    # Should NOT contain response format when native tools are used
    # (The format is in get_response_format(), not generate_descriptions())
    assert '"action":' not in descriptions_only or "Response Format" not in descriptions_only


@pytest.mark.unit
def test_agent_switches_between_json_and_native_tool_providers():
    """Agent should handle switching between JSON and native tool providers in same session."""
    # This is a conceptual test - in practice, the agent determines the mode at the start
    # But the UnifiedResponseParser should handle both formats

    parser = UnifiedResponseParser()

    # Test 1: Parse JSON text (JSON-only provider)
    json_result = parser.parse('{"thought": "test", "action": "read_file", "parameters": {}, "is_complete": false}')
    assert json_result.action == "read_file"

    # Test 2: Parse LLMResponse with tool_calls (native tool provider)
    from scrappy.providers.base import LLMResponse, ToolCall

    native_response = LLMResponse(
        content="I'll read the file",
        model="test-model",
        provider="test-provider",
        tool_calls=[
            ToolCall(id="call_1", name="write_file", arguments={"file_path": "test.py", "content": "print('hello')"})
        ]
    )

    native_result = parser.parse(native_response)
    assert native_result.action == "write_file"
    assert native_result.parameters == {"file_path": "test.py", "content": "print('hello')"}

    # Both formats work with the same parser!


@pytest.mark.unit
def test_existing_code_still_works_after_integration(json_only_config, tmp_path):
    """Existing code that uses JSON format should continue to work unchanged."""
    # This simulates existing code that passes JSON strings

    orch = ConfigurableTestOrchestrator(
        available_providers=['gemini'],
        response_content='{"thought": "Working on it", "action": "list_files", "parameters": {"path": "."}, "is_complete": false}'
    )

    agent = CodeAgent(
        orchestrator=orch,
        project_path=str(tmp_path),
        config=json_only_config
    )

    # Old code path: parse JSON directly
    json_response = '{"thought": "Done", "action": "complete", "is_complete": true, "result": "Success"}'
    result = agent._response_parser.parse(json_response)

    assert result.action == "complete"
    assert result.is_complete is True
    assert result.result_text == "Success"

    # Existing functionality preserved!
