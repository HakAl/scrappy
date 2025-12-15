# Lite LLM Phase 2

## Implementation Progress

### Streaming Wiring Status

| Layer | Component | Status | Tests |
|-------|-----------|--------|-------|
| 0 | VCR Integration | DONE | 7 cassettes recorded |
| 1 | LiteLLMService.stream_completion() | DONE | test_litellm_streaming.py |
| 1 | DelegationManager.stream_delegate() | DONE | test_delegation_streaming.py |
| 1 | AgentOrchestrator.stream_delegate() | DONE | test_orchestrator_streaming.py (9 tests) |
| 1b | AgentExecutor.execute_streaming() | DONE | test_agent_executor_streaming.py (13 tests) |
| 1b | ResearchExecutor.execute_streaming() | DONE | test_streaming_executor.py |
| 2 | TaskRouter.route_streaming() | DONE | test_router_streaming.py (13 tests) |
| 3 | CLI handler (handle_auto_route_streaming) | DONE | test_streaming_handler.py (19 tests) |
| 4 | interactive.py wiring | DONE | - |

**STREAMING IS NOW FULLY WIRED!** User queries stream responses in real-time.

### VCR Cassettes (tests/integration/cassettes/)

Recorded cassettes for replay-based testing (no API keys needed):
- `test_basic_completion.yaml` - Basic non-streaming completion
- `test_streaming_completion.yaml` - Streaming completion
- `test_streaming_with_tool_calls.yaml` - Streaming with tool calls
- `test_tool_call_extraction.yaml` - Tool call parsing
- `test_empty_chunks_handled.yaml` - Provider quirk handling
- `test_max_tokens_truncation.yaml` - Token limit behavior
- `test_unicode_content.yaml` - Unicode handling

**Usage:**
```bash
# Default: replay from cassettes (no API keys)
pytest tests/integration/

# Record new cassettes (needs API keys in .env)
pytest tests/integration/ --vcr-record=all
```

---

## Current State

**Main Service:** `src/scrappy/orchestrator/litellm_service.py`
- `LiteLLMService` with `completion()` (async) and `completion_sync()`
- `stream_completion()` for streaming responses
- Response normalization to `LLMResponse`
- Exception mapping (ContextWindowExceededError, RateLimitError)
- Smart escalation: fast -> quality tier on context overflow

**Config:** `src/scrappy/orchestrator/litellm_config.py`
- `MODEL_METADATA` for groq, cerebras, gemini, sambanova
- `build_model_list()`, `create_litellm_router()`

**Callbacks:** `src/scrappy/orchestrator/litellm_callbacks.py`
- `RateTrackingCallback` (implements litellm.CustomLogger)
- `EscalationMetrics`

**Tests:** `tests/orchestrator/`
- `test_litellm_service.py` - Response conversion, exception mapping, completion flow
- `test_litellm_config.py` - Model list building, router creation
- `test_litellm_callbacks.py` - Rate tracking, escalation metrics
- `test_litellm_escalation.py` - Depth guards

**Test Helpers:** `tests/helpers.py`
- `MockLiteLLMRouter` - sync/async completion mocking
- `MockLiteLLMResponse`, `MockLiteLLMChoice`, `MockLiteLLMUsage`
- `make_mock_litellm_response()` factory

---

## Feature 1: Streaming

Streaming flows through the full stack - not just LiteLLM, but orchestrator, executors, and agent output.

### Architecture Overview

```
User sees streaming output
        ^
        |
OutputInterface.stream_token(token)
        ^
        |
+-------+-------+
|               |
AgentExecutor   ResearchExecutor
(streams        (streams
 thoughts +      response
 tool output)    tokens)
        ^               ^
        |               |
        +-------+-------+
                |
        DelegationManager.stream_delegate()
                |
                v
        LiteLLMService.stream_completion()
                |
                v
        LiteLLM Router (stream=True)
                |
                v
        Provider API (SSE chunks)
```

### Layer 1: LiteLLMService (Low-Level)

```python
# In orchestrator/types.py
@dataclass
class ToolCallFragment:
    """Partial tool call from streaming delta."""
    index: int
    id: Optional[str] = None          # Only in first fragment
    type: Optional[str] = None
    function_name: Optional[str] = None
    function_arguments: Optional[str] = None  # Partial JSON string

@dataclass
class StreamChunk:
    """Single chunk from streaming response."""
    content: str
    index: int                                  # Monotonic chunk number (dedup/reorder detection)
    created: int = field(default_factory=lambda: int(time.time() * 1000))  # Timing analysis
    finish_reason: Optional[str] = None
    tool_calls: Optional[list[ToolCallFragment]] = None  # Fragments, not complete calls
    provider: Optional[str] = None              # Extracted from model string
    # Metadata for final chunk
    usage: Optional[dict] = None                # {prompt_tokens, completion_tokens}
    model: Optional[str] = None                 # Actual model used
```

```python
# In orchestrator/protocols.py
class StreamingCompletionProtocol(Protocol):
    """Contract for streaming LLM completions."""

    async def stream_completion(
        self,
        model: str,
        messages: list[dict],
        cancellation_token: Optional[asyncio.Event] = None,  # Ctrl-C support
        max_empty_chunk_ms: int = 5_000,                     # Stuck stream detection
        **kwargs
    ) -> AsyncIterator[StreamChunk]: ...
```

```python
# In orchestrator/streaming_util.py
from scrappy.orchestrator.types import ToolCall, ToolCallFragment

class ToolCallAccumulator:
    """Accumulates tool call fragments across chunks into complete ToolCalls.

    Handles edge cases:
    - Arguments arriving in tiny fragments (e.g., `{"`, `ar`, `g":`)
    - Missing indices (falls back to last_seen_index)
    - ID only present in first fragment
    - Out-of-order fragments (sorts on finalize)
    """

    def __init__(self):
        self.pending: dict[int, dict] = {}  # index -> partial call
        self.last_seen_index: int = 0  # Fallback for missing indices

    def feed(self, fragments: list[ToolCallFragment]) -> None:
        """Feed fragments from a chunk. Call finalize() when stream ends."""
        for frag in fragments:
            # Defensive: use last_seen_index if index is None
            idx = frag.index if frag.index is not None else self.last_seen_index
            self.last_seen_index = idx

            if idx not in self.pending:
                self.pending[idx] = {
                    "id": frag.id or "",  # ID might only be in first frag
                    "type": "function",
                    "function": {"name": "", "arguments": ""}
                }

            entry = self.pending[idx]

            # Merge fields (only update ID if we have one and entry doesn't)
            if frag.id and not entry["id"]:
                entry["id"] = frag.id
            if frag.function_name:
                entry["function"]["name"] += frag.function_name
            if frag.function_arguments:
                entry["function"]["arguments"] += frag.function_arguments

    def finalize(self) -> list[ToolCall]:
        """Call when chunk.finish_reason is set. Returns complete tool calls.

        Sorts by index to ensure deterministic order regardless of arrival order.
        """
        sorted_calls = sorted(self.pending.items())
        result = [ToolCall(**data) for _, data in sorted_calls]
        self.pending.clear()
        self.last_seen_index = 0
        return result
```

```python
# In litellm_service.py
async def stream_completion(
    self,
    model: str,
    messages: list[dict],
    cancellation_token: Optional[asyncio.Event] = None,
    max_empty_chunk_ms: int = 5_000,
    **kwargs
) -> AsyncIterator[StreamChunk]:
    """Stream completion chunks from LLM.

    Context Window Escalation:
    - Pre-first-chunk: ContextWindowExceededError can be caught and escalated
    - Post-first-chunk: Committed to current model, cannot fallback gracefully

    Callback Handling:
    - Aggregates content/usage across stream
    - Triggers callbacks in finally block (handles normal exit, exceptions, partial consumption)
    """
    # Pre-stream: can catch and escalate context window errors
    try:
        response = await self._router.acompletion(
            model=model,
            messages=messages,
            stream=True,
            **kwargs
        )
    except ContextWindowExceededError:
        # Pre-first-chunk: can escalate to quality tier
        async for chunk in self._escalate_and_stream(model, messages, **kwargs):
            yield chunk
        return

    # Post-first-chunk: committed to this model
    chunk_index = 0
    last_content_time = time.time() * 1000
    seen_final = False  # Groq double-final-chunk dedup

    # Callback aggregation state
    start_time = time.time()
    full_content: list[str] = []
    final_usage: Optional[dict] = None
    callbacks_triggered = False

    try:
        async for chunk in response:
            # Cancellation check
            if cancellation_token and cancellation_token.is_set():
                break

            # Stuck stream detection
            now = time.time() * 1000
            delta = chunk.choices[0].delta
            has_content = delta.content or delta.tool_calls

            if has_content:
                last_content_time = now
            elif (now - last_content_time) > max_empty_chunk_ms:
                raise StreamStuckError(f"No content for {max_empty_chunk_ms}ms")

            # Groq double-final dedup
            finish = chunk.choices[0].finish_reason
            if finish and seen_final:
                continue  # Skip duplicate final chunk
            if finish:
                seen_final = True

            # Capture usage from final chunk (if provider sends it)
            if hasattr(chunk, 'usage') and chunk.usage:
                final_usage = chunk.usage

            # Yield chunk (include even if content=None but tool_calls present - Gemini edge case)
            if has_content or finish:
                content = delta.content or ""
                full_content.append(content)

                model_str = getattr(chunk, 'model', '') or ''
                yield StreamChunk(
                    content=content,
                    index=chunk_index,
                    finish_reason=finish,
                    tool_calls=self._extract_tool_fragments(delta),
                    provider=model_str.split("/")[0] if "/" in model_str else model_str,
                    usage=getattr(chunk, 'usage', None),
                    model=model_str,
                )
                chunk_index += 1
    finally:
        # Trigger callbacks for RateTrackingCallback (handles normal exit, exceptions, partial consumption)
        if not callbacks_triggered:
            callbacks_triggered = True
            total_time = time.time() - start_time
            aggregated_content = "".join(full_content)

            # Fallback usage for providers that don't send it (e.g., Cerebras)
            usage = final_usage or {
                "prompt_tokens": 0,  # Unknown without provider support
                "completion_tokens": len(aggregated_content) // 4,  # Rough estimate
            }

            self._trigger_stream_callbacks(
                content=aggregated_content,
                usage=usage,
                latency=total_time,
                model=model,
            )

async def _escalate_and_stream(
    self,
    model: str,
    messages: list[dict],
    **kwargs
) -> AsyncIterator[StreamChunk]:
    """Escalate to quality tier and stream. Called on pre-first-chunk context error."""
    quality_model = self._get_quality_model(model)
    async for chunk in self.stream_completion(
        model=quality_model,
        messages=messages,
        **kwargs
    ):
        yield chunk
```

### Layer 2: DelegationManager (Mid-Level)

```python
# In delegation_manager.py or orchestrator
async def stream_delegate(
    self,
    prompt: str,
    model_group: str = "fast",
    use_context: bool = False,
    **kwargs
) -> AsyncIterator[StreamChunk]:
    """Stream a delegation with context augmentation."""
    # Augment prompt if needed
    if use_context:
        prompt = self._augment_prompt(prompt)

    messages = self._build_messages(prompt)

    async for chunk in self._litellm_service.stream_completion(
        model=model_group,
        messages=messages,
        **kwargs
    ):
        yield chunk
```

### Layer 3: OutputInterface (Display)

**Back-pressure required:** Terminal output can be slower than token arrival (SSH, CI).
Use bounded queue to prevent memory bloat and event loop blocking.

```python
# In output/protocols.py
class StreamingOutputProtocol(Protocol):
    """Output that can display streaming tokens."""

    def stream_start(self, label: Optional[str] = None) -> None:
        """Signal start of streaming output."""
        ...

    async def stream_token(self, token: str) -> None:
        """Display a single token (no newline). Async for back-pressure."""
        ...

    async def stream_end(self) -> None:
        """Signal end of streaming output. Waits for drain."""
        ...
```

```python
# In output/console.py
class ConsoleOutput:
    """Console output with streaming support and back-pressure handling.

    Back-pressure: Terminal output can be slower than token arrival (SSH, CI).
    Uses bounded queue to prevent memory bloat and event loop blocking.
    """

    def __init__(self, max_pending: int = 1_000, drain_timeout: float = 5.0):
        self._stream_queue: Optional[asyncio.Queue[str]] = None
        self._drain_task: Optional[asyncio.Task] = None
        self._max_pending = max_pending
        self._drain_timeout = drain_timeout

    def stream_start(self, label: Optional[str] = None) -> None:
        if label:
            self.info(f"{label}:")
        # Create fresh queue for this stream
        self._stream_queue = asyncio.Queue(maxsize=self._max_pending)
        self._drain_task = asyncio.create_task(self._drain_loop())

    async def stream_token(self, token: str) -> None:
        """Back-pressures upstream if queue full."""
        if self._stream_queue:
            await self._stream_queue.put(token)

    async def stream_end(self) -> None:
        """Wait for queue to drain, then cleanup.

        Uses timeout to prevent hanging if drain gets stuck.
        """
        if self._stream_queue:
            try:
                # Wait for queue to empty with timeout
                await asyncio.wait_for(
                    self._stream_queue.join(),
                    timeout=self._drain_timeout
                )
            except asyncio.TimeoutError:
                # Queue didn't drain in time - force cleanup
                pass

        if self._drain_task:
            self._drain_task.cancel()
            try:
                await self._drain_task
            except asyncio.CancelledError:
                pass

        print()  # Final newline
        self._stream_queue = None
        self._drain_task = None

    async def _drain_loop(self) -> None:
        """Background task that prints tokens."""
        while True:
            token = await self._stream_queue.get()
            # Debug timestamp when SCRAPPY_DEBUG=1
            if os.environ.get("SCRAPPY_DEBUG") == "1":
                print(f"[{time.time():.3f}]", end="")
            print(token, end="", flush=True)
            self._stream_queue.task_done()
```

```python
# In output/null.py
class NullOutput:
    """No-op output for tests."""
    def stream_start(self, label: Optional[str] = None) -> None:
        pass

    async def stream_token(self, token: str) -> None:
        pass

    async def stream_end(self) -> None:
        pass
```

### Layer 4: ExecutionStrategies

**ResearchExecutor** - Simple streaming:
```python
# In task_router/strategies.py
class ResearchExecutor:
    async def execute_streaming(self, task: ClassifiedTask) -> AsyncIterator[str]:
        """Stream research response tokens to user."""
        self._output.stream_start("Research")

        full_response = ""
        async for chunk in self._orchestrator.stream_delegate(
            prompt=task.original_input,
            model_group="fast",
            use_context=True,
        ):
            self._output.stream_token(chunk.content)
            full_response += chunk.content
            yield chunk.content

        self._output.stream_end()
        return full_response
```

**AgentExecutor** - Streams thoughts + tool output:
```python
# In agent/core.py or agent_loop.py
class CodeAgent:
    async def run_streaming(self, task: str) -> AsyncIterator[AgentEvent]:
        """Run agent loop with streaming output."""
        while not done:
            # Stream the "thinking" phase
            yield AgentEvent(type="thinking_start")
            async for chunk in self._think_streaming(state):
                yield AgentEvent(type="thought_token", content=chunk.content)
            yield AgentEvent(type="thinking_end")

            # Execute action (non-streaming, but stream the result)
            action = self._plan(thought)
            yield AgentEvent(type="action", action=action)

            result = await self._execute(action)
            yield AgentEvent(type="result", result=result)

@dataclass
class AgentEvent:
    """Event emitted during streaming agent execution."""
    type: Literal["thinking_start", "thought_token", "thinking_end",
                  "action", "result", "complete", "error"]
    content: Optional[str] = None
    action: Optional[AgentAction] = None
    result: Optional[ActionResult] = None
```

### Edge Cases

**General:**
1. **Connection drop mid-stream** - Wrap in try/except, emit error event
2. **Empty chunks** - Skip chunks with no content (but see Gemini below)
3. **Tool call streaming** - Use `ToolCallAccumulator`, finalize on `finish_reason`
4. **Rate limits mid-stream** - Map to exception, emit error event
5. **User cancellation** - Check `cancellation_token.is_set()` each chunk
6. **Stuck stream** - Raise `StreamStuckError` after `max_empty_chunk_ms` of empty chunks
7. **Partial consumption** - Generator abandoned without exception. `finally` block triggers callbacks regardless.

**Provider-Specific:**
8. **Groq double-final-chunk** - Streams final chunk twice (once with finish_reason, once empty). Deduplicate with `seen_final` flag.
9. **Gemini content=None + tool_calls** - Sometimes returns `content=None` but `tool_calls=[...]` in same delta. Must yield these chunks (check `has_content = delta.content or delta.tool_calls`).
10. **Cerebras no streaming usage** - Does not send usage in final chunk when `stream=True`. Fallback to estimated usage: `{"prompt_tokens": 0, "completion_tokens": len(content) // 4}`.
11. **Missing tool call index** - Some providers omit index. Use `last_seen_index` as fallback in `ToolCallAccumulator`.

**Context Window Escalation:**
12. **Pre-first-chunk error** - `ContextWindowExceededError` thrown before any chunks yield. **CAN escalate** to quality tier transparently. User sees no interruption.
13. **Post-first-chunk error** - Error after first chunk yields. **CANNOT fallback** without UI glitches. Emit `AgentEvent(type="error", content="Context exceeded mid-stream")` and let caller handle retry.

```python
# Pre-first-chunk: can escalate
try:
    response = await router.acompletion(stream=True, ...)
except ContextWindowExceededError:
    async for chunk in self._escalate_and_stream(...):
        yield chunk
    return

# Post-first-chunk: committed
async for chunk in response:
    yield chunk  # Once we yield, we're committed
```

**Callback Edge Cases:**
14. **Double callback trigger** - Use `callbacks_triggered` flag to prevent firing twice on exception + finally.
15. **Escalation callbacks** - When escalating, callbacks should reflect the escalated model, not the original.

### Test Strategy

```python
# In tests/helpers.py
class MockStreamingRouter:
    """Mock that yields chunks for streaming tests."""

    def __init__(self, chunks: list[MockStreamChunk]):
        self.chunks = chunks
        self.calls = []

    async def acompletion(self, stream=False, **kwargs):
        self.calls.append(kwargs)
        if stream:
            return self._stream_chunks()
        # Non-stream fallback
        return MockLiteLLMResponse(...)

    async def _stream_chunks(self):
        for chunk in self.chunks:
            yield chunk

@dataclass
class MockStreamChunk:
    choices: list
    model: str = "groq/llama-3.1-8b-instant"
    usage: Optional[dict] = None

class CapturingStreamOutput:
    """Captures streamed tokens for test assertions."""
    def __init__(self):
        self.tokens: list[str] = []
        self.started = False
        self.ended = False

    def stream_start(self, label: Optional[str] = None) -> None:
        self.started = True

    async def stream_token(self, token: str) -> None:
        self.tokens.append(token)

    async def stream_end(self) -> None:
        self.ended = True

    @property
    def full_text(self) -> str:
        return "".join(self.tokens)
```

**Unit Tests:**
```python
# tests/orchestrator/test_litellm_streaming.py
# - test_stream_yields_content_chunks
# - test_stream_handles_empty_chunks
# - test_stream_extracts_tool_fragments
# - test_stream_handles_connection_error
# - test_stream_finish_reason_propagated
# - test_stream_usage_on_final_chunk
# - test_stream_cancellation_stops_iteration
# - test_stream_stuck_raises_after_timeout
# - test_groq_double_final_deduped
# - test_gemini_tool_calls_without_content_yielded
# - test_callbacks_triggered_on_normal_completion
# - test_callbacks_triggered_on_exception
# - test_callbacks_triggered_on_partial_consumption
# - test_callbacks_not_double_triggered
# - test_pre_first_chunk_context_error_escalates
# - test_post_first_chunk_context_error_not_recoverable
# - test_cerebras_missing_usage_fallback

# tests/orchestrator/test_delegation_streaming.py
# - test_delegation_manager_streams_with_context
# - test_delegation_passes_cancellation_token

# tests/task_router/test_streaming_executor.py
# - test_research_executor_streams_to_output
# - test_executor_accumulates_tool_calls

# tests/agent/test_agent_streaming.py
# - test_agent_streams_thought_tokens
# - test_agent_emits_action_events

# tests/orchestrator/test_tool_call_accumulator.py
# - test_accumulator_handles_tiny_fragments
# - test_accumulator_handles_missing_index
# - test_accumulator_sorts_by_index_on_finalize
# - test_accumulator_handles_id_in_first_fragment_only
```

**Golden File Tests (Provider Quirks):**
```python
# tests/orchestrator/test_stream_golden.py
# Record real provider stream dumps, replay through accumulator

def test_groq_tool_call_reassembly():
    """Golden: Groq streams tool calls across 5 chunks."""
    chunks = load_golden("groq_tool_call_stream.json")
    accumulator = ToolCallAccumulator()
    for chunk in chunks:
        if chunk.tool_calls:
            accumulator.feed(chunk.tool_calls)
    result = accumulator.finalize()
    assert result[0].function.arguments == '{"location": "San Francisco"}'

def test_groq_double_final_dedup():
    """Golden: Groq sends duplicate final chunk."""
    chunks = load_golden("groq_double_final.json")
    output = CapturingStreamOutput()
    # ... run through service
    assert output.full_text.count("\n") == 1  # Not 2
```

**Stress Tests:**
```python
# tests/orchestrator/test_stream_cancel.py
async def test_cancellation_closes_connection():
    """Cancel mid-stream, verify no lingering awaits."""
    cancel = asyncio.Event()
    router = MockStreamingRouter(chunks=[...] * 10_000)

    async def cancel_after_5ms():
        await asyncio.sleep(0.005)
        cancel.set()

    asyncio.create_task(cancel_after_5ms())
    chunks_received = 0
    async for _ in service.stream_completion(..., cancellation_token=cancel):
        chunks_received += 1

    assert chunks_received < 100  # Stopped early

# tests/orchestrator/test_stream_backpressure.py
async def test_backpressure_limits_memory():
    """1MB of tokens instantly, memory stays bounded."""
    big_chunks = [MockStreamChunk(content="x" * 1000) for _ in range(1000)]
    router = MockStreamingRouter(chunks=big_chunks)
    output = ConsoleOutput(max_pending=100)

    # Memory should not exceed ~100KB (queue size * token size)
    # ... measure with tracemalloc
```

### Files to Modify/Create

**Scripts (One-Time Use):**
0. `scripts/record_stream.py` - Record golden files from real providers

**Layer 1 - LiteLLMService:**
1. `src/scrappy/orchestrator/types.py` - Add `StreamChunk`, `ToolCallFragment`, `StreamStuckError`
2. `src/scrappy/orchestrator/protocols.py` - Add `StreamingCompletionProtocol`
3. `src/scrappy/orchestrator/streaming_util.py` - NEW: `ToolCallAccumulator`, cancellation helpers
4. `src/scrappy/orchestrator/litellm_service.py` - Add methods:
   - `stream_completion()` - Main streaming entry point
   - `_trigger_stream_callbacks()` - Callback aggregation for streaming
   - `_escalate_and_stream()` - Pre-first-chunk context window escalation
   - `_extract_tool_fragments()` - Extract ToolCallFragment from delta

**Layer 2 - Orchestrator:**
5. `src/scrappy/orchestrator/delegation_manager.py` - Add `stream_delegate()` method
6. `src/scrappy/orchestrator/core.py` - Expose streaming via `AgentOrchestrator`

**Layer 3 - Output:**
7. `src/scrappy/output/protocols.py` - Add `StreamingOutputProtocol` (async methods)
8. `src/scrappy/output/console.py` - Bounded queue drain, drain timeout, debug timestamps
9. `src/scrappy/output/null.py` - No-op streaming for tests

**Layer 4 - Executors/Agent:**
10. `src/scrappy/task_router/strategies.py` - Add `execute_streaming()` to ResearchExecutor
11. `src/scrappy/agent/core.py` - Add `run_streaming()` method
12. `src/scrappy/agent/types.py` - Add `AgentEvent` dataclass

**Tests - Helpers:**
13. `tests/helpers.py` - Add `MockStreamingRouter`, `MockStreamChunk`, `CapturingStreamOutput`

**Tests - Unit:**
14. `tests/orchestrator/test_litellm_streaming.py` - LiteLLMService streaming tests
15. `tests/orchestrator/test_delegation_streaming.py` - DelegationManager streaming tests
16. `tests/task_router/test_streaming_executor.py` - Executor streaming tests
17. `tests/agent/test_agent_streaming.py` - Agent streaming tests

**Tests - Golden Files:**
18. `tests/orchestrator/test_stream_golden.py` - Provider quirk replay tests
19. `tests/orchestrator/golden/` - Directory for recorded stream dumps
    - `groq_tool_call_stream.json`
    - `groq_double_final.json`
    - `gemini_tool_calls_no_content.json`
    - `cerebras_no_usage.json`

**Tests - Stress:**
20. `tests/orchestrator/test_stream_cancel.py` - Cancellation/interruption tests
21. `tests/orchestrator/test_stream_backpressure.py` - Memory/queue pressure tests

---

## Feature 2: Integration Tests (VCR.py)

### Setup

PHASE 0:
- add to toml dev dependencies: vcrpy pytest-recording

```bash
pip install vcrpy pytest-recording
```

### Directory Structure

```
tests/
  integration/
    cassettes/
      groq_completion.yaml
      cerebras_completion.yaml
      gemini_completion.yaml
      sambanova_completion.yaml
      groq_tool_calls.yaml
      streaming_groq.yaml
    conftest.py           # VCR fixtures, API key handling
    test_provider_responses.py
    test_tool_calls.py
    test_streaming.py
```

### conftest.py Setup

```python
import os
import pytest
import vcr

# Filter sensitive data from cassettes
vcr_config = vcr.VCR(
    cassette_library_dir='tests/integration/cassettes',
    record_mode='once',  # Record once, replay forever
    match_on=['method', 'scheme', 'host', 'port', 'path', 'query'],
    filter_headers=['authorization', 'x-api-key'],
    filter_post_data_parameters=['api_key'],
    decode_compressed_response=True,
)

@pytest.fixture
def vcr_cassette(request):
    """Auto-named cassette based on test name."""
    cassette_name = f"{request.node.name}.yaml"
    with vcr_config.use_cassette(cassette_name):
        yield

# Skip integration tests unless explicitly requested
def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-integration"):
        skip_integration = pytest.mark.skip(reason="need --run-integration to run")
        for item in items:
            if "integration" in item.nodeid:
                item.add_marker(skip_integration)

def pytest_addoption(parser):
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="run integration tests",
    )
```

### Test Examples

```python
# test_provider_responses.py
import vcr
from scrappy.orchestrator.litellm_service import LiteLLMService

@vcr.use_cassette('cassettes/groq_completion.yaml')
async def test_groq_response_format():
    """Verify Groq response parses correctly."""
    service = create_real_service()  # Uses real API keys
    response, _ = await service.completion(
        model="fast",
        messages=[{"role": "user", "content": "Say hello"}],
    )
    assert response.content
    assert response.provider == "groq"
    assert response.tokens_used > 0

@vcr.use_cassette('cassettes/groq_tool_calls.yaml')
async def test_tool_calls_extraction():
    """Verify tool calls parse from real response."""
    service = create_real_service()
    response, _ = await service.completion(
        model="fast",
        messages=[{"role": "user", "content": "What's the weather?"}],
        tools=[WEATHER_TOOL_SCHEMA],
    )
    assert response.tool_calls is not None
    assert response.tool_calls[0].name == "get_weather"
```

### Recording Workflow

1. **First run (record):**
   ```bash
   # Set real API keys
   export GROQ_API_KEY=xxx
   export GEMINI_API_KEY=xxx

   # Run with recording
   pytest tests/integration/ --run-integration -v
   ```

2. **Subsequent runs (replay):**
   ```bash
   # No API keys needed - cassettes replay
   pytest tests/integration/ -v
   ```

3. **Re-record when providers change:**
   ```bash
   rm tests/integration/cassettes/*.yaml
   pytest tests/integration/ --run-integration -v
   ```

### CI Configuration

```yaml
# In CI, cassettes are committed - no API keys needed
- name: Run integration tests (replay mode)
  run: pytest tests/integration/ -v
```

### Files to Create

1. `tests/integration/conftest.py` - VCR setup, fixtures
2. `tests/integration/test_provider_responses.py` - Basic completion tests
3. `tests/integration/test_tool_calls.py` - Tool call extraction
4. `tests/integration/test_streaming.py` - Streaming tests (after Feature 1)
5. `tests/integration/cassettes/` - Recorded responses (gitignored initially, committed after recording)

### Value

- Catches provider API changes before they hit production
- No mocking - tests real response parsing
- Fast CI - replays don't hit network
- Documents expected response formats

---

## Implementation Order

### Critical: VCR vs Golden Files

**Understand the distinction to avoid duplicate effort:**

| Aspect | VCR (Integration) | Golden Files (Unit) |
|--------|-------------------|---------------------|
| **Purpose** | Prove LiteLLM + Provider talks to Service | Test logic without network |
| **Coverage** | 10% of tests | 90% of tests |
| **Assertions** | "Did we get 200 OK and a response?" | "Does accumulator handle this edge case?" |
| **Speed** | Slow (even with replay) | Fast |
| **What NOT to test** | Deep logic, exact token counts | Network integration |

**VCR tests should NOT assert:**
- Exact token counts (varies by provider)
- Specific response content
- Internal state changes

**Golden file tests SHOULD assert:**
- ToolCallAccumulator reassembly
- Stuck-stream detection
- Groq double-final deduplication
- Gemini tool_calls-without-content handling

---

### Phase 1: Streaming (Bottom-Up)

**Step 1.0 - Record Golden Files FIRST**
> Record real stream dumps before writing complex logic. You need to see actual provider quirks.

- Create `tests/orchestrator/golden/` directory
- Write recording script (one-time use):
```python
# scripts/record_stream.py
async def record_provider_stream(provider: str, output_path: str):
    """Record raw chunks from provider for golden file tests."""
    router = create_real_router()
    chunks = []
    async for chunk in router.acompletion(model=f"{provider}/...", stream=True, ...):
        chunks.append(chunk.model_dump())
    Path(output_path).write_text(json.dumps(chunks, indent=2))
```
- Record from Groq (tool calls, double-final)
- Record from Gemini (tool_calls without content)
- Record from Cerebras (no streaming usage)

**Step 1.1 - Data Models & Utils**
- Add `StreamChunk`, `ToolCallFragment`, `StreamStuckError` to `types.py`
- Add `StreamingCompletionProtocol` to `protocols.py`
- Create `streaming_util.py` with `ToolCallAccumulator`
- Add `MockStreamingRouter`, `MockStreamChunk` to `helpers.py`

**Step 1.2 - LiteLLMService Layer**
- Implement `stream_completion()` in LiteLLMService
  - Pre-first-chunk context window escalation
  - Post-first-chunk commitment (no fallback)
  - Callback aggregation with finally block
  - Cancellation token support
  - Stuck stream detection
  - Groq double-final dedup
  - Gemini tool_calls-without-content handling
  - Usage fallback for Cerebras
- Add `_trigger_stream_callbacks()` method
- Add `_escalate_and_stream()` method
- Write `test_litellm_streaming.py` (unit tests using golden files)

**Step 1.3 - Orchestrator Layer**
- Add `stream_delegate()` to DelegationManager
- Expose via AgentOrchestrator
- Write `test_delegation_streaming.py`

**Step 1.4 - Output Layer**
- Add `StreamingOutputProtocol` (async methods) to `output/protocols.py`
- Implement bounded queue drain in `ConsoleOutput`
  - Timeout on join() to prevent hanging
  - Debug timestamps (`SCRAPPY_DEBUG=1`)
- Add `NullOutput` streaming stubs
- Add `CapturingStreamOutput` to helpers.py

**Step 1.5 - Executor Layer**
- Add `execute_streaming()` to ResearchExecutor
- Write `test_streaming_executor.py`

**Step 1.6 - Golden File Tests (Full Suite)**
- Write `test_stream_golden.py` for provider quirks:
  - `test_groq_tool_call_reassembly`
  - `test_groq_double_final_dedup`
  - `test_gemini_tool_calls_without_content`
  - `test_cerebras_missing_usage_fallback`

**Step 1.7 - Stress Tests**
- Write `test_stream_cancel.py` (cancellation/interruption)
- Write `test_stream_backpressure.py` (memory bounds)

**Step 1.8 - Agent Layer**
- Add `AgentEvent` dataclass to `agent/types.py`
- Add `run_streaming()` to CodeAgent
- Write `test_agent_streaming.py`

### Phase 2: VCR.py Integration Tests

**Step 2.0 - Dependencies**
- Add `vcrpy`, `pytest-recording` to pyproject.toml dev dependencies

**Step 2.1 - Setup**
- Create `tests/integration/` directory structure
- Create `conftest.py` with VCR config and `--run-integration` flag

**Step 2.2 - Basic Tests**
- `test_provider_responses.py` - Completion parsing per provider
- Record cassettes with real API keys
- **Keep assertions shallow:** response exists, has content, has provider field

**Step 2.3 - Advanced Tests**
- `test_tool_calls.py` - Tool call extraction (structure only, not logic)
- `test_streaming.py` - Streaming response handling (after Phase 1)

### Why This Order

1. **Golden files FIRST** - You cannot write correct provider-quirk handling without seeing real data
2. Data models second - everything else depends on `StreamChunk` shape
3. Streaming bottom-up (LiteLLM -> Orchestrator -> Output -> Executors)
4. Golden file tests with LiteLLMService - proves the logic works
5. Stress tests after output layer - need back-pressure implementation
6. VCR tests last - proves integration, not logic
