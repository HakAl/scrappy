# Streaming Integration - Status

## Current State

**Streaming is implemented for chat/research tasks only.**

Agent tasks (code generation, refactoring, etc.) do NOT stream - they use a different
UX pattern with progress indicators and tool execution feedback. This is intentional;
token streaming doesn't fit the iterative tool-execution nature of agent work.

---

## What Works (Chat/Research Streaming)

```
User Input
    |
    v
interactive.py -> handle_auto_route_streaming_sync()
    |
    v
TaskRouter.route_streaming()
    |
    v
ResearchExecutor.execute_streaming()  <-- STREAMS
    |
    v
AgentOrchestrator.stream_delegate()
    |
    v
LiteLLMService.stream_completion()
    |
    v
Tokens appear in real-time
```

## What Does NOT Stream (Agent Tasks)

Agent tasks (CODE_GENERATION, REFACTORING, etc.) go through:
```
TaskRouter.route_streaming()
    |
    v
AgentExecutor.execute()  <-- NON-STREAMING (intentional)
    |
    v
CodeAgent.run()
    |
    v
Output appears after completion
```

Agent UX will be redesigned separately with:
- Progress indicators ("Thinking...", "Executing write_file...")
- Live action feed
- Iteration markers

---

## Implemented Components

| Component | Location | Status |
|-----------|----------|--------|
| StreamChunk, ToolCallFragment types | orchestrator/types.py | Done |
| StreamingConfig | orchestrator/types.py | Done |
| StreamErrorFormatter | orchestrator/streaming_util.py | Done |
| LiteLLMService.stream_completion() | litellm_service.py | Done |
| DelegationManager.stream_delegate() | delegation.py | Done |
| AgentOrchestrator.stream_delegate() | orchestrator/core.py | Done |
| ResearchExecutor.execute_streaming() | research_executor.py | Done |
| TaskRouter.route_streaming() | router.py | Done |
| CLIStreamingOutput | task_router_handler.py | Done |
| Golden files | tests/orchestrator/golden/ | Done (20 files) |

---

## Configuration

### StreamingConfig

Controls streaming behavior via `orchestrator/types.py`:

```python
from scrappy.orchestrator.types import StreamingConfig

# Default (slight pacing, line-buffered)
config = StreamingConfig()  # buffer=80, delay=8ms

# Comfortable reading pace
config = StreamingConfig.readable()  # buffer=80, delay=20ms

# Maximum speed
config = StreamingConfig.fast()  # buffer=0, delay=0
```

### Stream Error Formatting

Errors during streaming display with context via `StreamErrorFormatter`:

```
--- Stream Error ---
[Rate Limit] Rate limit exceeded
Provider: groq
(42 chunks received before error)
Partial response above may still be useful.
Tip: Wait a moment and retry, or use /provider to switch.
--------------------
```

---

## Tests

| Test File | Coverage |
|-----------|----------|
| test_litellm_streaming.py | LiteLLM service streaming |
| test_delegation_streaming.py | Delegation manager streaming |
| test_orchestrator_streaming.py | AgentOrchestrator.stream_delegate() |
| test_streaming_executor.py | ResearchExecutor.execute_streaming() |
| test_router_streaming.py | TaskRouter.route_streaming() |
| test_streaming_handler.py | CLIStreamingOutput, handler methods |
| test_stream_golden.py | Golden file validation |

---

## Future Work

### Agent UX (Not Token Streaming)

Agent tasks need a different UX - not token streaming. Ideas:
- Progress indicators ("Thinking...", "Writing file...")
- Live tool execution feed
- Iteration markers [1/10], [2/10]
- Collapsible action output

This is a separate design effort from chat streaming.
