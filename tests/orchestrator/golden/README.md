# Golden Stream Response Files

This directory contains captured streaming responses from real LLM providers for testing.

## Directory Structure

- `openai/` - OpenAI provider stream dumps
- `anthropic/` - Anthropic (Claude) provider stream dumps
- `gemini/` - Google Gemini provider stream dumps
- `scenarios/` - Complex multi-provider or edge case scenarios

## File Naming Convention

Stream dump files should follow this pattern:
```
<provider>_<scenario>_<date>.json
```

Examples:
- `openai_simple_completion_20231214.json`
- `anthropic_tool_call_20231214.json`
- `gemini_context_window_error_20231214.json`

## Purpose

These golden files are used to:
1. Test streaming response parsing without making real API calls
2. Capture provider-specific quirks and edge cases
3. Verify tool call extraction from streaming chunks
4. Test error handling and recovery scenarios
5. Ensure consistent behavior across provider updates

## Recording New Golden Files

Use `scripts/record_stream.py` to capture new streaming responses:

```bash
python scripts/record_stream.py --provider openai --output tests/orchestrator/golden/openai/
```

## Test Usage

Tests load these files to replay streaming responses and verify parsing logic.
See `tests/orchestrator/test_stream_golden.py` for examples.
