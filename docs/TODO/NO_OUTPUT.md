# Bug: No Output From Chat

## Problem

No output from chat. Output is literally: "|"

## Example

```
Verbose mode: ON
  Metadata (provider, tokens, time) will be shown for responses.

> how would we add rag to this codebase?

Task Classification:
  Type: research
  Confidence: 1.00
  Complexity: 2/10
  Reasoning: Information gathering task: question, question_mark
  Provider: cerebras (llama3.1-8b) (hint: fast)
  Executing with: ResearchExecutor

|
  cerebras (llama3.1-8b) | 641 tokens | 0.7ms
```

## Root Cause Analysis

There are TWO issues causing this bug:

### Issue 1: Response Cleaner Strips JSON-Only Responses

The llama3.1-8b model, when given tool-calling instructions in the system prompt,
often outputs ONLY a JSON tool call without any accompanying text:

```json
{"tool": "web_search", "parameters": {"query": "adding RAG to codebase"}}
```

The `ResponseCleaner.clean_response()` method in
`src/task_router/strategies/response_cleaner.py` strips all JSON artifacts:

- Line 36: Removes JSON code blocks
- Lines 49-55: Removes bare JSON lines starting with `{"tool"`

Result: The response becomes an empty string after cleaning.

### Issue 2: Fallback Logic Doesn't Trigger

In `src/task_router/strategies/research_loop.py` lines 142-148:

```python
if not final_response and tool_calls_made:
    final_response = self.response_cleaner.generate_fallback_response(...)
```

The fallback only triggers when BOTH conditions are true:
1. `final_response` is empty
2. `tool_calls_made` is non-empty

But in this case, `tool_calls_made` is EMPTY because:
- The model output JSON-looking text, but no tool was actually EXECUTED
- This happens when:
  - It's the first iteration and model just outputs JSON
  - The research subtype is GENERAL (only web tools allowed, model can't use them)
  - The tool call parsing failed

### Issue 3 (Potential): Unhandled None Content -- All Providers

EG: 

In `src/providers/cerebras_provider.py`:

- Line 164 in `chat()`: `content=response.choices[0].message.content` - NO null handling
- Line 249 in `chat_with_tools()`: `content=message.content or ""` - HAS null handling

If the Cerebras API returns `None` for content, the regular `chat()` method
passes it through, but this is less likely the cause here (641 tokens suggests
actual content was returned).

## Data Flow

1. Task classified as `research` with hint `fast`
2. Provider resolver: `fast` hint -> `cerebras.get_model_for_task('fast')` -> `llama3.1-8b`
3. ResearchSubclassifier: Question about RAG = GENERAL research (not codebase-specific)
4. `_execute_general_research()` runs with web tools only (or no tools)
5. llama3.1-8b responds with JSON-only tool call (following system prompt instructions)
6. `response_cleaner.clean_response()` strips all JSON -> empty string
7. `research_loop` check: `not "" and []` = `True and False` = `False` -> no fallback
8. `ExecutionResult.output = ""`
9. `interactive.py` line 136: `io.echo(f"| {response_content}")` -> displays "|"

## Files Involved

1. `src/providers/*`
2. `src/providers/cerebras_provider.py:164` - Missing `or ""` for None handling
2. `src/providers/cerebras_provider.py:287-288` - llama3.1-8b selected for "fast" tasks
3. `src/task_router/strategies/response_cleaner.py:36,49-55` - Strips JSON aggressively
4. `src/task_router/strategies/research_loop.py:142-148` - Fallback logic gap
5. `src/task_router/strategies/research_executor.py:166-219` - General research path
6. `src/cli/interactive.py:136` - Display with "|" prefix

## Suggested Fixes

### Fix 1: Handle Empty Response After Cleaning (Primary Fix)

In `research_loop.py`, change the fallback condition:

```python
# Before
if not final_response and tool_calls_made:

# After
if not final_response:
    if tool_calls_made:
        final_response = self.response_cleaner.generate_fallback_response(...)
    else:
        # Model responded with only tool-call JSON but no tool was executed
        final_response = "I apologize, but I wasn't able to generate a response. Please try rephrasing your question."
```

### Fix 2: Add None Handling to cerebras_provider.chat()

```python
# Line 164 - Before
content=response.choices[0].message.content,

# After
content=response.choices[0].message.content or "",
```

### Fix 3: Consider Using Better Model for Research

In `cerebras_provider.py` line 287-288, consider using a more capable model:

```python
# Before
if task_type == 'fast' or task_type == 'high_volume':
    return 'llama3.1-8b'

# After - use larger model that handles tool instructions better
if task_type == 'fast' or task_type == 'high_volume':
    return 'qwen-3-32b'  # or llama-3.3-70b
```

### Fix 4: Improve Response Cleaner

Don't strip JSON if it's the ONLY content. Check if cleaning would result in
empty string and preserve original if so.

---

## Implementation Plan

**Prerequisite**: Complete `MODEL_SELECTION_REFACTOR.md` first - moves model selection
logic from providers to orchestrator.

### Step 1: Fix None Content in All Providers

**File**: `src/providers/cerebras_provider.py`

**Change**: Line 164, add null coalescing to match `chat_with_tools()` behavior.

```python
# Before
content=response.choices[0].message.content,

# After
content=response.choices[0].message.content or "",
```

**Test**: Add test in `tests/test_cerebras_provider.py`

```python
def test_chat_handles_none_content():
    """Verify chat() returns empty string when API returns None content."""
    mock_client = Mock()
    mock_client.chat.completions.create.return_value = Mock(
        choices=[Mock(message=Mock(content=None), finish_reason='stop')],
        usage=Mock(prompt_tokens=10, completion_tokens=0)
    )
    provider = CerebrasProvider(client=mock_client)

    response = provider.chat(messages=[{'role': 'user', 'content': 'test'}])

    assert response.content == ""
    assert isinstance(response.content, str)
```

### Step 2: Fix Response Cleaner to Preserve Content

**File**: `src/task_router/strategies/response_cleaner.py`

**Change**: `clean_response()` should not return empty string if original had content. If cleaning results in empty, return original response instead.

```python
def clean_response(self, response: str) -> str:
    if not response:
        return response

    # ... existing cleaning logic ...

    result = cleaned.strip()

    # If cleaning removed everything, return original
    # (model responded with only tool-call syntax but we couldn't execute it)
    if not result and response.strip():
        return response.strip()

    return result
```

**Test**: Add test in `tests/test_response_cleaner.py`

```python
def test_clean_response_preserves_json_only_content():
    """Verify JSON-only response is preserved, not stripped to empty."""
    cleaner = ResponseCleaner()
    json_only = '{"tool": "search_code", "parameters": {"pattern": "rag"}}'

    result = cleaner.clean_response(json_only)

    assert result != ""
    assert result == json_only

def test_clean_response_strips_json_when_text_remains():
    """Verify JSON is stripped when other text content exists."""
    cleaner = ResponseCleaner()
    mixed = 'Here is my answer.\n{"tool": "search_code", "parameters": {}}'

    result = cleaner.clean_response(mixed)

    assert '{"tool"' not in result
    assert 'Here is my answer' in result
```

### Step 3: Fix Fallback Logic in Research Loop

**File**: `src/task_router/strategies/research_loop.py`

**Change**: Lines 142-148, handle empty response even when no tools were executed.

```python
# Before
if not final_response and tool_calls_made:
    final_response = self.response_cleaner.generate_fallback_response(...)

# After
if not final_response:
    if tool_calls_made:
        final_response = self.response_cleaner.generate_fallback_response(
            task, tool_calls_made, conversation_history
        )
    else:
        # Model failed to produce usable output
        final_response = self._generate_empty_response_fallback(task)
```

Add method to ResearchLoop:

```python
def _generate_empty_response_fallback(self, task: ClassifiedTask) -> str:
    """Generate fallback when model produces no usable output."""
    return (
        "I wasn't able to generate a helpful response. "
        "Could you rephrase your question or provide more context?"
    )
```

**Test**: Add test in `tests/test_research_loop.py`

```python
def test_run_handles_empty_response_no_tools():
    """Verify fallback is generated when response is empty and no tools called."""
    mock_orchestrator = create_mock_orchestrator(response_content="")
    mock_tool_bundle = Mock(has_tools=Mock(return_value=False))
    mock_cleaner = Mock(clean_response=Mock(return_value=""))

    loop = ResearchLoop(mock_orchestrator, mock_tool_bundle, mock_cleaner)
    task = ClassifiedTask(original_input="test question", task_type=TaskType.RESEARCH)

    response, tools, tokens = loop.run(
        provider="test",
        initial_prompt="test",
        system_prompt="test",
        task=task,
        max_iterations=1
    )

    assert response != ""
    assert "rephrase" in response.lower() or "context" in response.lower()
```

### Step 4: Run Tests and Verify

```bash
python -m pytest tests/test_cerebras_provider.py -v -k "test_chat_handles_none"
python -m pytest tests/test_response_cleaner.py -v
python -m pytest tests/test_research_loop.py -v -k "test_run_handles_empty"
```

### Step 5: Manual Verification

Run the original failing scenario:

```
> how would we add rag to this codebase?
```

Verify output is no longer just "|".

---

## Checklist

- [ ] Step 1: Cerebras None handling
- [ ] Step 1: Test for None handling
- [ ] Step 2: Response cleaner preserves content
- [ ] Step 2: Tests for cleaner behavior
- [ ] Step 3: Research loop fallback logic
- [ ] Step 3: Test for empty response fallback
- [ ] Step 4: All tests pass
- [ ] Step 5: Manual verification passes