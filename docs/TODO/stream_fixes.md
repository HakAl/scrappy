# Streaming Integration - Scope

## Problem Statement

Streaming infrastructure exists but is not wired to user-facing entry points.
User runs a query, expects streaming output, but sees all output at once (buffered).

Test case:
```
> name the top software engineer for each decade from 1950 - 2020...
| It's challenging to definitively name the "top" software engineer...
```
Expected: tokens stream in real-time. Actual: entire response appears at once.

---

## Architecture Gap

The original spec (_WIP.md lines 138-165) defined this flow:

```
User sees streaming output
        ^
        | (5) CLI/TUI displays tokens
OutputInterface.stream_token(token)
        ^
        | (4) NOT WIRED
+-------+--------------------+
|                            |
AgentExecutor                ResearchExecutor
.execute_streaming()         .execute_streaming()
   |                              |
   | MISSING                      | EXISTS (not called)
   v                              v
CodeAgent.run_streaming()    orchestrator.stream_delegate()
   |                              |
   | EXISTS                       | (3) NOT EXPOSED
   v                              v
AgentEvent yields            AgentOrchestrator.stream_delegate()  <-- MISSING
                                  |
                             DelegationManager.stream_delegate()  <-- EXISTS
                                  |
                             LiteLLMService.stream_completion()   <-- EXISTS
                                  |
                             LiteLLM Router (stream=True)         <-- EXISTS
```

**Low-level streaming exists. Executor and routing layers are missing.**

---

## What EXISTS (Implemented)

| Component | Location | Status | Tests |
|-----------|----------|--------|-------|
| VCR Integration | tests/integration/ | DONE | 7 cassettes |
| StreamChunk, ToolCallFragment types | orchestrator/types.py | Done | - |
| StreamingCompletionProtocol | orchestrator/protocols.py:891 | Done | - |
| ToolCallAccumulator | streaming_util.py | Done | test_tool_call_accumulator.py |
| LiteLLMService.stream_completion() | litellm_service.py:334 | Done | test_litellm_streaming.py |
| DelegationManager.stream_delegate() | delegation.py:533 | Done | test_delegation_streaming.py |
| **AgentOrchestrator.stream_delegate()** | orchestrator/core.py:561 | **DONE** | test_orchestrator_streaming.py (9 tests) |
| StreamingOutputProtocol | protocols/output.py:218 | Done | - |
| ResearchExecutor.execute_streaming() | research_executor.py:392 | Done | test_streaming_executor.py |
| **AgentExecutor.execute_streaming()** | agent_executor.py:154 | **DONE** | test_agent_executor_streaming.py (13 tests) |
| AgentEvent dataclass | agent/types.py:87 | Done | - |
| CodeAgent.run_streaming() | agent/core.py:689 | Done | test_agent_streaming.py |
| Test helpers | helpers.py:2881+ | Done | - |

---

## What's MISSING (Not Implemented)

### ~~Layer 1: AgentOrchestrator.stream_delegate()~~ DONE

Implemented in orchestrator/core.py:561. Tests in test_orchestrator_streaming.py.

---

### ~~Layer 1b: AgentExecutor.execute_streaming()~~ DONE

Implemented in agent_executor.py:154. Wraps CodeAgent.run_streaming() and yields AgentEvent objects.
Tests in test_agent_executor_streaming.py (13 tests).

---

### ~~Layer 2: TaskRouter.route_streaming()~~ DONE

Implemented in router.py with:
- `_prepare_for_execution()` - shared prep logic extracted from route()
- `route_streaming()` - async method that streams via output protocol
- `_execute_streaming()` - handles both Pattern A and Pattern B strategies
Tests in test_router_streaming.py (13 tests).

---

### ~~Layer 3: CLI Entry Point~~ DONE

**File:** `src/scrappy/cli/task_router_handler.py`

Implemented:
- `CLIStreamingOutput` class implementing StreamingOutputProtocol
- `handle_auto_route_streaming()` async method
- `handle_auto_route_streaming_sync()` wrapper using asyncio.run()
- Line-buffering (flush on newlines or 80 chars) for TUI compatibility

Tests: `tests/cli/test_streaming_handler.py` (21 tests)

---

### ~~Layer 4: interactive.py Entry Point~~ DONE

**File:** `src/scrappy/cli/interactive.py`

Implemented:
- Changed `handle_auto_route()` to `handle_auto_route_streaming_sync()`
- Conditional output display (skip if already streamed)
- Works in both CLI and TUI modes via CLIIOProtocol abstraction

---

## Threading Model

### Current State

**TUI Mode (Textual):**
- `_process_input()` already runs in worker thread via `@work(thread=True)` (main_screen.py:276)
- UI runs on main thread
- Thread-safe communication via `post_message()` using `WriteOutput`, `WriteRenderable` messages
- `ThreadSafeAsyncBridge` exists for blocking on UI responses from worker thread

**CLI Mode (plain terminal):**
- `_process_input()` is sync, runs on main thread
- No async handling currently

### Approach: Minimal Changes

We don't need new threading machinery. Existing infrastructure supports streaming:

**TUI - use existing message pattern:**
```python
# In worker thread (already runs _process_input)
async def _handle_streaming(self, user_input: str):
    async for chunk in stream:
        # Post token to UI thread (existing pattern)
        self.app.post_message(WriteOutput(chunk.content))
```

**CLI - bridge sync to async:**
```python
def _process_input(self, user_input: str):
    # Run async streaming, blocking until complete
    asyncio.run(self._handle_streaming_async(user_input))
```

### Output Adapters by Mode

| Mode | Adapter | Token Delivery |
|------|---------|----------------|
| CLI | CLIStreamingOutput | `io.echo(token, nl=False)` direct write |
| TUI | TUIStreamingOutput | `app.post_message(WriteOutput(token))` |

Both implement `StreamingOutputProtocol`. Injected based on runtime mode.

### No New Threading Required

- TUI worker thread already exists
- `asyncio.run()` bridges sync entry to async streaming
- Message posting handles thread-safe UI updates
- Output adapters abstract the difference

---

## ~~Layer 5: Edge Case Handling~~ DONE

**File:** `src/scrappy/orchestrator/litellm_service.py`

All edge cases implemented:

### ~~5a. Stuck stream detection~~ DONE
- Added `timeout_ms` parameter (default 30000ms)
- Raises `StreamStuckError` if no chunk received within timeout
- Exception includes `partial_content` for recovery

### ~~5b. Groq double-final chunk dedup~~ DONE
- Track `seen_final` flag
- Skip duplicate chunks with `finish_reason` after first one

### ~~5c. Cancellation token support~~ DONE
- Added `cancellation_token: Optional[asyncio.Event]` parameter
- Check `cancellation_token.is_set()` each iteration
- Raises `StreamCancelledError` with partial content

### ~~5d. Deleted `_trigger_stream_callbacks`~~ DONE
- Method was dead code (never called)
- Deleted - streaming callbacks handled at higher level (CLIStreamingOutput)

### ~~5e. Error handling mid-stream~~ DONE
- Wrap mid-stream exceptions with partial content info
- Exception message includes char count for debugging

**Tests:** `tests/orchestrator/test_litellm_streaming.py` (5 new tests)
- `test_stream_completion_stuck_stream_detection`
- `test_stream_completion_cancellation_token`
- `test_stream_completion_double_final_chunk_dedup`
- `test_stream_completion_mid_stream_error_preserves_content`
- `test_stream_completion_default_timeout_is_reasonable`

---

## Implementation Order

1. ~~**AgentOrchestrator.stream_delegate()**~~ DONE - thin wrapper, low risk
2. ~~**AgentExecutor.execute_streaming()**~~ DONE - wrap CodeAgent.run_streaming()
3. ~~**TaskRouter refactor**~~ DONE - extract shared logic, add route_streaming()
4. ~~**CLI adapter + handler**~~ DONE - CLIStreamingOutput, handle_auto_route_streaming()
5. ~~**interactive.py wiring**~~ DONE - final connection to user
6. ~~**Edge Case Handling**~~ DONE - stuck detection, cancellation, dedup, error recovery

**STREAMING IMPLEMENTATION COMPLETE!**

Additional fixes made during integration:
- Line-buffering in CLIStreamingOutput (flush on newlines or 80 chars) for TUI/RichLog compatibility
- Force httpx transport in litellm_service.py (aiohttp caused incomplete streams)
- Fixed RateLimitTracker callback signature mismatch (was causing exception on final chunk)

### StreamingConfig (Added)

Introduced `StreamingConfig` dataclass in `orchestrator/types.py` to centralize streaming behavior:

```python
from scrappy.orchestrator.types import StreamingConfig

# Default (slight pacing, line-buffered)
config = StreamingConfig()  # buffer=80, delay=8ms

# Comfortable reading pace
config = StreamingConfig.readable()  # buffer=80, delay=20ms

# Slow for demos
config = StreamingConfig.slow()  # buffer=0, delay=40ms

# Maximum speed
config = StreamingConfig.fast()  # buffer=0, delay=0
```

Parameters:
- `buffer_threshold`: Characters before flush (default 80, 0=immediate)
- `token_delay_ms`: Delay between tokens in ms (default 8ms for slight pacing)
- `line_buffer`: Always flush on newlines (default True)
- `show_metadata`: Display stream start/end info (default False)

Usage in CLI:
```python
from scrappy.orchestrator.types import StreamingConfig

# Default has slight pacing (8ms) - good balance
result = handler.handle_auto_route_streaming_sync(user_input)

# Use readable for slower, comfortable pacing (20ms)
result = handler.handle_auto_route_streaming_sync(
    user_input,
    streaming_config=StreamingConfig.readable()
)
```

### StreamErrorFormatter (Added)

Added `StreamErrorFormatter` in `orchestrator/streaming_util.py` for user-friendly error display:

```python
from scrappy.orchestrator.streaming_util import format_stream_error

error_display = format_stream_error(
    error="Rate limit exceeded",
    chunks_received=42,
    provider="groq"
)
# Output:
# --- Stream Error ---
# [Rate Limit] Rate limit exceeded
# Provider: groq
# (42 chunks received before error)
# Partial response above may still be useful.
# Tip: Wait a moment and retry, or use /provider to switch.
# --------------------
```

Auto-detected error categories with actionable suggestions:
- **Rate Limit** - throttling, 429 errors
- **Timeout** - stalls, deadlines
- **Context Overflow** - token limits exceeded
- **Auth Error** - API key issues
- **Network Error** - connection problems
- **Model Error** - invalid model names

Each layer requires:
- Protocol definition (if new)
- Implementation
- Unit tests
- Integration verification

---

## Test Strategy

**Unit tests per layer:**
- AgentOrchestrator.stream_delegate() forwards to delegation_manager
- AgentExecutor.execute_streaming() yields AgentEvent tokens to output
- TaskRouter.route_streaming() calls execute_streaming()
- CLIStreamingOutput implements StreamingOutputProtocol
- handle_auto_route_streaming() uses route_streaming()

**Integration test:**
- End-to-end RESEARCH: user input -> streaming tokens captured
- End-to-end CODE_GENERATION: user input -> thought tokens + action events captured
- Use CapturingStreamOutput from helpers.py

---

## Files to Modify

**Source:**
1. `src/scrappy/orchestrator/core.py` - add stream_delegate()
2. `src/scrappy/task_router/strategies/agent_executor.py` - add execute_streaming()
3. `src/scrappy/task_router/router.py` - refactor + add route_streaming()
4. `src/scrappy/cli/task_router_handler.py` - add CLIStreamingOutput + handler
5. `src/scrappy/cli/interactive.py` - wire streaming entry point, asyncio.run() bridge
6. `src/scrappy/cli/screens/main_screen.py` - TUIStreamingOutput adapter (optional, may reuse CLI adapter)

**Tests:**
7. `tests/orchestrator/test_core_streaming.py` - NEW
8. `tests/task_router/test_agent_executor_streaming.py` - NEW
9. `tests/task_router/test_router_streaming.py` - NEW
10. `tests/cli/test_streaming_handler.py` - NEW

---

## Open Questions (Resolved)

1. **TUI vs CLI adapter** - RESOLVED: CLIStreamingOutput works for both modes via CLIIOProtocol abstraction. TUI mode routes through UnifiedIO which handles thread-safe message posting.

2. **Golden files vs VCR cassettes** - CLARIFIED: Two different systems:
   - `scripts/record_stream.py` -> `tests/orchestrator/golden/` - Custom JSON format for replaying provider-specific chunk patterns
   - VCR cassettes -> `tests/integration/cassettes/` - HTTP-level recording for integration tests
   Both are valid, serve different purposes.

3. **Mid-stream error UX** - RESOLVED: Errors append `[Error: {message}]` to output stream and set success=False in result.

4. **`_trigger_stream_callbacks` decision** - RESOLVED: Deleted as dead code (line 193-196 above).
