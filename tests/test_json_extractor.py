"""
Tests for JSONExtractor utility.

Tests JSON extraction from LLM responses that may contain:
- Markdown code blocks (```json ... ```)
- Generic code blocks (``` ... ```)
- Plain text with JSON objects
- Malformed or edge case inputs
"""

import json
import pytest

from scrappy.task_router.json_extractor import JSONExtractor


class TestJSONExtractorBasicExtractions:
    """Test basic JSON extraction scenarios."""

    def test_extract_from_json_code_block(self):
        """Extract JSON from markdown ```json code block."""
        response = '''Here is the result:
```json
{"task_type": "RESEARCH", "confidence": 0.85}
```
Hope this helps!'''

        extractor = JSONExtractor()
        result = extractor.extract(response)

        assert result == '{"task_type": "RESEARCH", "confidence": 0.85}'
        # Verify it's valid JSON
        parsed = json.loads(result)
        assert parsed["task_type"] == "RESEARCH"
        assert parsed["confidence"] == 0.85

    def test_extract_from_generic_code_block(self):
        """Extract JSON from generic ``` code block without json marker."""
        response = '''The classification is:
```
{"task_type": "CODE_GENERATION", "confidence": 0.92}
```'''

        extractor = JSONExtractor()
        result = extractor.extract(response)

        assert result == '{"task_type": "CODE_GENERATION", "confidence": 0.92}'
        parsed = json.loads(result)
        assert parsed["task_type"] == "CODE_GENERATION"

    def test_extract_from_plain_text(self):
        """Extract JSON object from plain text without code blocks."""
        response = 'The answer is {"task_type": "CONVERSATION", "confidence": 1.0} as shown above.'

        extractor = JSONExtractor()
        result = extractor.extract(response)

        assert result == '{"task_type": "CONVERSATION", "confidence": 1.0}'
        parsed = json.loads(result)
        assert parsed["task_type"] == "CONVERSATION"

    def test_extract_pure_json(self):
        """Extract from response that is pure JSON with no extra text."""
        response = '{"task_type": "DIRECT_COMMAND", "confidence": 0.95}'

        extractor = JSONExtractor()
        result = extractor.extract(response)

        assert result == '{"task_type": "DIRECT_COMMAND", "confidence": 0.95}'
        parsed = json.loads(result)
        assert parsed["task_type"] == "DIRECT_COMMAND"


class TestJSONExtractorEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_extract_with_whitespace_in_code_block(self):
        """Handle extra whitespace inside code blocks."""
        response = '''```json

{"task_type": "RESEARCH", "confidence": 0.75}

```'''

        extractor = JSONExtractor()
        result = extractor.extract(response)

        # Should strip whitespace
        assert result.strip() == '{"task_type": "RESEARCH", "confidence": 0.75}'
        parsed = json.loads(result.strip())
        assert parsed["confidence"] == 0.75

    def test_extract_with_multiple_json_blocks_takes_first(self):
        """When multiple JSON blocks exist, extract the first one."""
        response = '''First result:
```json
{"task_type": "RESEARCH", "confidence": 0.80}
```
Second result:
```json
{"task_type": "CODE_GENERATION", "confidence": 0.90}
```'''

        extractor = JSONExtractor()
        result = extractor.extract(response)

        # Should extract first block
        parsed = json.loads(result)
        assert parsed["task_type"] == "RESEARCH"

    def test_extract_nested_json_objects(self):
        """Extract JSON with nested objects."""
        response = '''```json
{"task_type": "RESEARCH", "metadata": {"confidence": 0.85, "reasoning": "test"}}
```'''

        extractor = JSONExtractor()
        result = extractor.extract(response)

        parsed = json.loads(result)
        assert parsed["metadata"]["confidence"] == 0.85
        assert parsed["metadata"]["reasoning"] == "test"

    def test_extract_json_array(self):
        """Extract JSON array instead of object."""
        response = '```json\n[{"type": "A"}, {"type": "B"}]\n```'

        extractor = JSONExtractor()
        result = extractor.extract(response)

        parsed = json.loads(result)
        assert len(parsed) == 2
        assert parsed[0]["type"] == "A"

    def test_extract_with_text_containing_curly_braces(self):
        """Handle text with curly braces that aren't JSON."""
        response = '''Some text with {curly braces} in it.
```json
{"task_type": "RESEARCH", "confidence": 0.80}
```'''

        extractor = JSONExtractor()
        result = extractor.extract(response)

        # Should prefer code block over text braces
        parsed = json.loads(result)
        assert parsed["task_type"] == "RESEARCH"


class TestJSONExtractorFailureModes:
    """Test error handling and failure scenarios."""

    def test_extract_from_empty_string_returns_empty(self):
        """Return empty string when input is empty."""
        extractor = JSONExtractor()
        result = extractor.extract("")

        assert result == ""

    def test_extract_from_none_returns_empty(self):
        """Handle None input gracefully."""
        extractor = JSONExtractor()
        result = extractor.extract(None)

        assert result == ""


    def test_extract_with_malformed_code_block(self):
        """Handle code block with missing closing marker."""
        response = '''```json
{"task_type": "RESEARCH", "confidence": 0.80}
No closing marker here!'''

        extractor = JSONExtractor()
        result = extractor.extract(response)

        # Should still find the JSON object
        assert '{' in result and '}' in result


    def test_extract_from_whitespace_only(self):
        """Handle whitespace-only input."""
        extractor = JSONExtractor()
        result = extractor.extract("   \n\t  ")

        assert result.strip() == ""


class TestJSONExtractorPriorityOrdering:
    """Test extraction priority when multiple formats are present."""

    def test_json_code_block_takes_priority_over_plain(self):
        """When both ```json block and plain JSON exist, prefer code block."""
        response = '''{"task_type": "WRONG", "confidence": 0.1}
```json
{"task_type": "CORRECT", "confidence": 0.95}
```'''

        extractor = JSONExtractor()
        result = extractor.extract(response)

        parsed = json.loads(result)
        assert parsed["task_type"] == "CORRECT"

    def test_json_code_block_takes_priority_over_generic(self):
        """Prefer ```json over ``` when both exist."""
        response = '''```
{"task_type": "GENERIC", "confidence": 0.5}
```
```json
{"task_type": "SPECIFIC", "confidence": 0.95}
```'''

        extractor = JSONExtractor()
        result = extractor.extract(response)

        parsed = json.loads(result)
        # Should prefer ```json marker
        assert parsed["task_type"] == "SPECIFIC"

    def test_generic_code_block_takes_priority_over_plain(self):
        """When both ``` block and plain JSON exist, prefer code block."""
        response = '''{"task_type": "PLAIN", "confidence": 0.1}
```
{"task_type": "BLOCK", "confidence": 0.95}
```'''

        extractor = JSONExtractor()
        result = extractor.extract(response)

        parsed = json.loads(result)
        assert parsed["task_type"] == "BLOCK"


class TestJSONExtractorRealWorldScenarios:
    """Test with real-world LLM response patterns."""

    def test_extract_from_chatgpt_style_response(self):
        """Extract from ChatGPT-style response with explanation."""
        response = '''Based on the user's request, I will classify this as a research task.

```json
{
  "task_type": "RESEARCH",
  "confidence": 0.85,
  "reasoning": "User is asking for information"
}
```

This classification is appropriate because the query contains question words.'''

        extractor = JSONExtractor()
        result = extractor.extract(response)

        parsed = json.loads(result)
        assert parsed["task_type"] == "RESEARCH"
        assert parsed["confidence"] == 0.85
        assert "reasoning" in parsed

    def test_extract_from_claude_style_response(self):
        """Extract from Claude-style response with thinking."""
        response = '''I need to analyze this request carefully.

The classification would be:
```json
{"task_type": "CODE_GENERATION", "confidence": 0.92, "reasoning": "Action verb detected"}
```

Hope this helps!'''

        extractor = JSONExtractor()
        result = extractor.extract(response)

        parsed = json.loads(result)
        assert parsed["task_type"] == "CODE_GENERATION"

    def test_extract_multiline_formatted_json(self):
        """Extract nicely formatted multi-line JSON."""
        response = '''```json
{
  "task_type": "RESEARCH",
  "confidence": 0.88,
  "reasoning": "This is a longer reasoning that spans multiple words",
  "metadata": {
    "complexity": "medium",
    "requires_context": true
  }
}
```'''

        extractor = JSONExtractor()
        result = extractor.extract(response)

        parsed = json.loads(result)
        assert parsed["task_type"] == "RESEARCH"
        assert parsed["metadata"]["complexity"] == "medium"
        assert parsed["metadata"]["requires_context"] is True


class TestJSONExtractorInterface:
    """Test the public interface and API design."""

    def test_extractor_is_reusable(self):
        """Same extractor instance can be used multiple times."""
        extractor = JSONExtractor()

        result1 = extractor.extract('{"a": 1}')
        result2 = extractor.extract('{"b": 2}')

        assert json.loads(result1)["a"] == 1
        assert json.loads(result2)["b"] == 2

    def test_extractor_can_be_used_as_static_utility(self):
        """Should work as a utility without instance state."""
        # Create two instances and verify independence
        ext1 = JSONExtractor()
        ext2 = JSONExtractor()

        r1 = ext1.extract('{"x": 1}')
        r2 = ext2.extract('{"y": 2}')

        assert r1 != r2
        assert json.loads(r1)["x"] == 1
        assert json.loads(r2)["y"] == 2
