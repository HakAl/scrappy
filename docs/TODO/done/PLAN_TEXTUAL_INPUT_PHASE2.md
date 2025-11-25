# Plan: Textual Input Handling - Phase 2 & 3

## Status: Future Work

This document tracks remaining issues and planned improvements for Textual input handling, following the Phase 1 implementation in `PLAN_BLOCKING_INPUT_FIX.md`.

---

## Architectural Principles

### Protocol-First Design

All new components MUST define protocols before implementation:

```python
class ClarificationConfigProtocol(Protocol):
    """Configuration for clarification behavior."""
    @property
    def confidence_threshold(self) -> float: ...

    @property
    def high_confidence_bypass(self) -> float: ...


class InputRequestProtocol(Protocol):
    """Contract for input request data."""
    prompt: str
    default: Optional[str]
    request_type: Literal["text", "confirm"]


class InputResponseProtocol(Protocol):
    """Contract for input response data."""
    value: Optional[str]
    cancelled: bool


class InputQueueProtocol(Protocol):
    """Thread-safe queue for cross-thread input coordination."""
    def post_request(self, request: InputRequestProtocol) -> None: ...
    def await_response(self, timeout: Optional[float] = None) -> InputResponseProtocol: ...
    def post_response(self, response: InputResponseProtocol) -> None: ...


class InputModalProtocol(Protocol):
    """Contract for modal dialog behavior."""
    def show(self, request: InputRequestProtocol) -> None: ...
    def on_submit(self, value: str) -> None: ...
    def on_cancel(self) -> None: ...
```

### Configuration Schema

Add to `.scrappy.example.yaml`:

```yaml
clarification:
  confidence_threshold: 0.7      # Below this, always clarify
  high_confidence_bypass: 0.9    # Above this, skip conflicting signal checks
```

---

## Known Issues (Phase 2)

### 1. Clarification Triggered Incorrectly

**Problem:** `InteractiveClarifier.clarify()` outputs the menu even when clarification should not be needed.

**Root Cause:** The `has_conflicting_signals()` function in `pure_functions.py` triggers clarification for queries like "how to make google?" because:
- Task is classified as RESEARCH with 100% confidence
- But "make" is in `strong_action_verbs` list, triggering "conflicting signals"

**Observed Behavior:**
```
Intent Clarification Needed
   Classified as: research (confidence: 100%)
   Input: "how to make google?"

Did you want me to:
  [1] EXPLAIN how to do this (research/information only)
  [2] Actually DO this for you (execute/create/modify)
  [3] Keep current classification (research)
```

**Expected Behavior:** High confidence (>= high_confidence_bypass) should bypass conflicting signal checks.

**Fix Location:** `src/task_router/pure_functions.py:needs_clarification()`

**Proposed Fix:**
```python
def needs_clarification(
    task: ClassifiedTask,
    config: ClarificationConfigProtocol,
) -> bool:
    """
    Determine if user clarification is needed for a classified task.

    Args:
        task: The classified task to evaluate
        config: Configuration with threshold values (injectable for testing)

    Returns:
        True if clarification should be requested
    """
    # Low confidence always needs clarification
    if task.confidence < config.confidence_threshold:
        return True

    # High confidence means classifier is sure - trust it
    # Only check conflicting signals for medium confidence range
    if task.confidence < config.high_confidence_bypass:
        if has_conflicting_signals(task.original_input, task.task_type):
            return True

    return False
```

---

## Phase 3: Modal Dialogs for User Input

### Current Limitation

The `OutputSinkAdapter` in `unified_io.py` currently auto-approves all input requests with a warning panel:

```
+------------------------------- Auto-Response -------------------------------+
| PHASE 1 LIMITATION                                                          |
|                                                                             |
| Attempted to request input:                                                 |
| Choice [1/2/3]:                                                             |
|                                                                             |
| Interactive prompts return defaults in Textual mode.                        |
| Phase 3 will enable modal dialogs for user input.                           |
|                                                                             |
| Returning default: 3                                                        |
+-----------------------------------------------------------------------------+
```

### Planned Implementation

Replace auto-approve with actual Textual modal screens that:
1. Display the prompt/confirmation request
2. Wait for user input via Textual widgets
3. Return the user's response to the worker thread

### Technical Challenges

#### Async Input Methods
- Worker threads run synchronously
- Textual event loop runs on main thread
- Need mechanism for worker to wait for UI response without blocking event loop

#### Input Request Queue
- Bi-directional communication between worker and UI threads
- Worker posts input request to queue
- UI thread picks up request, shows modal
- User response posted back to worker
- Worker resumes with response

### Proposed Architecture

```
Worker Thread                    Main Thread (Textual)
     |                                  |
     | -- InputRequest --> Queue        |
     |                                  |
     | (wait on Event)                  | <-- poll queue
     |                                  |
     |                           Show Modal Dialog
     |                                  |
     |                           User types response
     |                                  |
     | <-- InputResponse -- Queue       |
     |                                  |
     | (Event set, resume)              |
     v                                  v
```

### Components to Implement

1. **InputRequest dataclass** - Implements `InputRequestProtocol`
2. **InputResponse dataclass** - Implements `InputResponseProtocol`
3. **InputRequestQueue** - Implements `InputQueueProtocol`, uses `threading.Event` and `queue.Queue`
4. **TextualInputModal** - Implements `InputModalProtocol` for text input
5. **TextualConfirmModal** - Implements `InputModalProtocol` for yes/no confirmations
6. **InputCoordinator** - New class to handle input request/response cycle (extracted from OutputSinkAdapter)
7. **Updated OutputSinkAdapter** - Delegates input handling to `InputCoordinator`

### Single Responsibility Separation

The current `OutputSinkAdapter` violates SRP by handling both output formatting AND input coordination. Split into:

- `OutputSinkAdapter` - Formats and displays output only
- `InputCoordinator` - Handles input request/response cycle via queue

```python
class InputCoordinatorProtocol(Protocol):
    """Coordinates input requests between worker and UI threads."""
    def request_input(self, prompt: str, default: Optional[str] = None) -> str: ...
    def request_confirmation(self, prompt: str, default: bool = False) -> bool: ...
```

### Error Handling

| Scenario | Behavior |
|----------|----------|
| Modal dismissed without response | Return `InputResponse(value=None, cancelled=True)` |
| Timeout waiting for user | Return default value after configurable timeout |
| Queue full | Block with timeout, raise `InputQueueFullError` if exceeded |
| Worker thread dies while modal open | Queue cleanup via context manager `__exit__` |

### Thread Safety Implementation

```python
class InputRequestQueue:
    def __init__(self, timeout: float = 30.0):
        self._request_queue: queue.Queue[InputRequest] = queue.Queue(maxsize=1)
        self._response_queue: queue.Queue[InputResponse] = queue.Queue(maxsize=1)
        self._response_event = threading.Event()
        self._timeout = timeout

    def await_response(self, timeout: Optional[float] = None) -> InputResponse:
        effective_timeout = timeout or self._timeout
        if not self._response_event.wait(timeout=effective_timeout):
            return InputResponse(value=None, cancelled=True)  # Timeout
        return self._response_queue.get_nowait()
```

### Dependency Injection

Workers receive `InputCoordinatorProtocol` via constructor injection:

```python
class TaskWorker:
    def __init__(
        self,
        input_coordinator: InputCoordinatorProtocol,
        # ... other dependencies
    ):
        self._input = input_coordinator
```

---

## Files to Modify

| File | Phase | Changes |
|------|-------|---------|
| `.scrappy.example.yaml` | 2 | Add `clarification` config section |
| `src/config/schema.py` | 2 | Add `ClarificationConfig` dataclass |
| `src/task_router/protocols.py` | 2 | Add `ClarificationConfigProtocol` |
| `src/task_router/pure_functions.py` | 2 | Update `needs_clarification()` to use config |
| `src/cli/protocols.py` | 3 | Add input coordination protocols |
| `src/cli/input_coordinator.py` | 3 | New file for `InputCoordinator` class |
| `src/cli/unified_io.py` | 3 | Extract input handling to `InputCoordinator` |
| `src/textual_app/app.py` | 3 | Add modal screens and queue polling |
| `src/textual_app/modals.py` | 3 | New file for input modal screens |

---

## Testing Strategy

### Phase 2

**Unit Tests:**
- `needs_clarification()` returns `True` for confidence < `confidence_threshold`
- `needs_clarification()` returns `False` for confidence >= `high_confidence_bypass`
- `needs_clarification()` checks conflicting signals only in medium confidence range
- Config values are properly loaded from yaml

**Integration Tests:**
- High-confidence RESEARCH task skips clarification menu
- Medium-confidence task with conflicting signals shows clarification
- Config override via yaml changes behavior

**Test Doubles:**
```python
@dataclass
class TestClarificationConfig:
    """Test double for ClarificationConfigProtocol."""
    confidence_threshold: float = 0.7
    high_confidence_bypass: float = 0.9
```

### Phase 3

**Unit Tests:**
- `InputRequestQueue.post_request()` is thread-safe
- `InputRequestQueue.await_response()` returns on timeout
- `InputRequestQueue.await_response()` returns response when available
- `InputCoordinator.request_input()` returns user value
- `InputCoordinator.request_confirmation()` returns boolean

**Integration Tests:**
- Modal appears when input requested from worker thread
- Worker receives user response after modal submission
- Worker receives default on modal cancellation
- Worker receives default on timeout

**Test Doubles:**
```python
class FakeInputCoordinator:
    """Test double for InputCoordinatorProtocol."""
    def __init__(self, responses: list[str]):
        self._responses = responses
        self._index = 0

    def request_input(self, prompt: str, default: Optional[str] = None) -> str:
        if self._index >= len(self._responses):
            return default or ""
        response = self._responses[self._index]
        self._index += 1
        return response
```

**Manual Tests:**
- End-to-end flow in Textual app
- Modal keyboard navigation (Tab, Enter, Escape)
- Modal styling matches app theme

---

## Dependencies

- Phase 2 has no dependencies, can be implemented immediately
- Phase 3 requires understanding of Textual's `push_screen()` and async patterns
- Phase 3 depends on Phase 2 config infrastructure for timeout values
