import json

from scrappy.graph.nodes.tool_call_processor import ToolCallProcessor


def test_extract_text_tool_call_handles_nested_arguments() -> None:
    processor = ToolCallProcessor()
    content = (
        'before <function(codebase_search {"query": "scrappy", '
        '"options": {"limit": 2}})></function> after'
    )

    remaining, tool_calls = processor.extract_text_tool_calls(content)

    assert "<function" not in remaining
    assert "before" in remaining
    assert "after" in remaining
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "codebase_search"
    arguments = json.loads(tool_calls[0]["function"]["arguments"])
    assert arguments == {"query": "scrappy", "options": {"limit": 2}}


def test_extract_text_tool_call_preserves_malformed_markup() -> None:
    processor = ToolCallProcessor()
    content = '<function(codebase_search {"query": )></function>'

    remaining, tool_calls = processor.extract_text_tool_calls(content)

    assert remaining == content
    assert tool_calls == []
