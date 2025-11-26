# Threading and Signal Handler Bug - Remediation Plan

## Executive Summary

The agent crashes with `signal only works in main thread of the main interpreter` because `AuditLogger._register_crash_handlers()` is called from a worker thread spawned by `SemanticSearchInitializer.wait_with_callback()`. This document provides a comprehensive remediation plan following SOLID principles and the project's architectural guidelines.

---

## Phase 1: Immediate Fix (Unblock Users) - COMPLETED 2025-11-26

### 1.1 Guard Signal Registration in AuditLogger

**File:** `src/agent/audit.py`

**Problem:** `_register_crash_handlers()` calls `signal.signal()` which fails from non-main threads.

**Solution:** Add main thread check before signal registration.

**Protocol-First Design:**

```python
# src/agent/protocols.py (new or existing)
class CrashHandlerProtocol(Protocol):
    """Protocol for crash handling strategies."""

    def register(self) -> bool:
        """Register crash handlers. Returns True if successful."""
        ...

    def unregister(self) -> None:
        """Unregister crash handlers."""
        ...

    def is_registered(self) -> bool:
        """Check if handlers are registered."""
        ...
```

**Implementation:**

```python
# src/agent/audit.py
import threading

def _register_crash_handlers(self) -> None:
    """Register handlers to save audit log on crash or unexpected exit."""
    if self._crash_handlers_registered:
        return

    # Signal handlers can only be registered from the main thread
    if threading.current_thread() is not threading.main_thread():
        logger.debug("Skipping signal registration - not main thread")
        return

    # Register atexit handler for normal exit
    atexit.register(self._on_exit)

    # ... existing signal registration code ...

    self._crash_handlers_registered = True
```

**Testing:**

```python
# tests/agent/test_audit.py
def test_signal_registration_skipped_in_worker_thread():
    """Signal registration should be skipped when called from non-main thread."""
    logger = AuditLogger()

    def worker():
        logger.enable_auto_save(path=Path("/tmp"))
        # Should not crash, just skip signal registration

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()

    # Verify signals were not registered (still False from worker context)
    # The flag should be False because registration was skipped
    assert not logger._crash_handlers_registered
```

### Phase 1 Implementation Notes

**Completed:** 2025-11-26

**Changes made:**
- Added `import threading` and `import logging` to `src/agent/audit.py`
- Added main thread check at line 90-95 in `_register_crash_handlers()`
- Key improvement: `atexit` handler is still registered from worker threads (it works from any thread), only signal handlers are skipped
- The `_crash_handlers_registered` flag remains `False` when called from worker thread, allowing re-registration if called later from main thread

**Tests added to `tests/test_audit_logger.py`:**
- `test_signal_registration_skipped_in_worker_thread` - verifies no crash occurs when called from worker thread
- `test_enable_auto_save_works_from_main_thread` - verifies normal behavior from main thread

**Test results:** All 19 tests pass

---

## Phase 2: Fix SubprocessRunner Race Conditions - COMPLETED 2025-11-26

### 2.1 Add Thread-Safe Output Collection

**File:** `src/agent_tools/components/subprocess_runner.py`

**Problem:** `output_lines` list and `last_output_time` variable are accessed by multiple threads without synchronization.

**Protocol-First Design:**

```python
# src/agent_tools/protocols.py (add to existing)
class ThreadSafeOutputCollectorProtocol(Protocol):
    """Protocol for thread-safe output collection."""

    def append(self, line: str) -> None:
        """Thread-safe append."""
        ...

    def get_lines(self) -> List[str]:
        """Get copy of all lines."""
        ...

    def get_last_output_time(self) -> float:
        """Get last output timestamp."""
        ...

    def line_count(self) -> int:
        """Get current line count."""
        ...
```

**Implementation:**

```python
# src/agent_tools/components/output_collector.py (new file)
import threading
import time
from typing import List


class ThreadSafeOutputCollector:
    """Thread-safe collector for subprocess output."""

    def __init__(self):
        self._lines: List[str] = []
        self._last_output_time: float = time.time()
        self._lock = threading.Lock()

    def append(self, line: str) -> None:
        """Thread-safe append of output line."""
        with self._lock:
            self._lines.append(line)
            self._last_output_time = time.time()

    def get_lines(self) -> List[str]:
        """Get copy of all lines."""
        with self._lock:
            return list(self._lines)

    def get_last_output_time(self) -> float:
        """Get last output timestamp."""
        with self._lock:
            return self._last_output_time

    def line_count(self) -> int:
        """Get current line count."""
        with self._lock:
            return len(self._lines)
```

**Updated SubprocessRunner:**

```python
# src/agent_tools/components/subprocess_runner.py
from .output_collector import ThreadSafeOutputCollector

def execute(self, command: str, cwd: str, ...):
    collector = ThreadSafeOutputCollector()

    def read_output():
        try:
            for line in iter(process.stdout.readline, ''):
                if line:
                    collector.append(line.rstrip())
                    if stream_output and collector.line_count() % 10 == 0 and self._io:
                        self._io.echo(f"   ... {collector.line_count()} lines processed")
        except Exception:
            pass

    # Main loop now uses thread-safe access
    while process.poll() is None:
        elapsed = time.time() - start_time
        stall_time = time.time() - collector.get_last_output_time()
        # ...

    stdout = "\n".join(collector.get_lines())
```

**Testing:**

```python
# tests/agent_tools/test_output_collector.py
def test_concurrent_append_is_thread_safe():
    """Multiple threads appending should not cause data corruption."""
    collector = ThreadSafeOutputCollector()
    threads = []

    def append_lines(prefix: str, count: int):
        for i in range(count):
            collector.append(f"{prefix}-{i}")

    # Start 10 threads each appending 100 lines
    for i in range(10):
        t = threading.Thread(target=append_lines, args=(f"thread{i}", 100))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # Should have exactly 1000 lines with no corruption
    assert collector.line_count() == 1000
    lines = collector.get_lines()
    assert len(set(lines)) == 1000  # All unique
```

### Phase 2 Implementation Notes

**Completed:** 2025-11-26

**Changes made:**
- Added `ThreadSafeOutputCollectorProtocol` to `src/agent_tools/protocols/__init__.py`
- Created `src/agent_tools/components/output_collector.py` with `ThreadSafeOutputCollector` implementation
- Updated `src/agent_tools/components/subprocess_runner.py` to use `ThreadSafeOutputCollector`:
  - Replaced `output_lines = []` with `collector = ThreadSafeOutputCollector()`
  - Replaced `last_output_time = start_time` with collector's internal timestamp
  - Updated `read_output()` to use `collector.append()` and `collector.line_count()`
  - Updated main loop to use `collector.get_last_output_time()`
  - Updated output joining to use `collector.get_lines()`

**Tests added to `tests/agent_tools/test_output_collector.py`:**
- `test_append_and_get_lines` - basic functionality
- `test_get_lines_returns_copy` - ensures isolation
- `test_line_count_accurate` - count tracking
- `test_last_output_time_updated_on_append` - timestamp updates
- `test_last_output_time_initialized` - initial state
- `test_concurrent_append_is_thread_safe` - 10 threads x 100 lines stress test
- `test_concurrent_read_write` - simultaneous read/write operations
- `test_empty_collector` - edge case
- `test_empty_string_append` - edge case
- `test_special_characters` - unicode and special chars
- `test_high_volume_stress` - 10000 lines via ThreadPoolExecutor

**Test results:** All 11 tests pass

---

## Phase 3: Refactor Background Initialization Pattern - COMPLETED 2025-11-26

### 3.1 Replace `wait_with_callback()` with Event Queue Pattern

**Problem:** `wait_with_callback()` spawns a thread that runs user callbacks, which may contain code that must run on the main thread (signal registration, UI updates).

**Architectural Decision:** Use an event queue pattern where:
1. Worker threads submit events to a queue
2. Main thread processes events from the queue
3. Callbacks always execute on the main thread

**Protocol-First Design:**

```python
# src/infrastructure/threading/protocols.py (new file)
from typing import Protocol, Callable, Any, Optional
from enum import Enum


class EventType(Enum):
    """Types of background events."""
    INIT_COMPLETE = "init_complete"
    INIT_FAILED = "init_failed"
    PROGRESS = "progress"


class BackgroundEvent:
    """Event from background thread."""
    def __init__(
        self,
        event_type: EventType,
        source: str,
        data: Any = None,
        error: Optional[Exception] = None
    ):
        self.event_type = event_type
        self.source = source
        self.data = data
        self.error = error


class EventQueueProtocol(Protocol):
    """Protocol for thread-safe event queue."""

    def put(self, event: BackgroundEvent) -> None:
        """Submit event to queue (thread-safe)."""
        ...

    def get(self, timeout: Optional[float] = None) -> Optional[BackgroundEvent]:
        """Get next event (blocks if empty until timeout)."""
        ...

    def get_nowait(self) -> Optional[BackgroundEvent]:
        """Get next event without blocking (returns None if empty)."""
        ...

    def process_pending(self) -> int:
        """Process all pending events. Returns count processed."""
        ...


class MainThreadCallbackProtocol(Protocol):
    """Protocol for scheduling callbacks on main thread."""

    def schedule(self, callback: Callable[[], None]) -> None:
        """Schedule callback to run on main thread."""
        ...

    def process_callbacks(self) -> int:
        """Process pending callbacks. Returns count processed."""
        ...
```

**Implementation:**

```python
# src/infrastructure/threading/event_queue.py (new file)
import queue
import threading
from typing import Optional, Callable, List

from .protocols import BackgroundEvent, EventQueueProtocol


class ThreadSafeEventQueue:
    """Thread-safe event queue for background-to-main communication."""

    def __init__(self):
        self._queue: queue.Queue[BackgroundEvent] = queue.Queue()
        self._handlers: dict[str, Callable[[BackgroundEvent], None]] = {}

    def put(self, event: BackgroundEvent) -> None:
        """Submit event to queue (thread-safe, can be called from any thread)."""
        self._queue.put(event)

    def get(self, timeout: Optional[float] = None) -> Optional[BackgroundEvent]:
        """Get next event (blocks if empty until timeout)."""
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_nowait(self) -> Optional[BackgroundEvent]:
        """Get next event without blocking."""
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def register_handler(self, source: str, handler: Callable[[BackgroundEvent], None]) -> None:
        """Register handler for events from a specific source."""
        self._handlers[source] = handler

    def process_pending(self) -> int:
        """Process all pending events on current thread. Returns count processed."""
        count = 0
        while True:
            event = self.get_nowait()
            if event is None:
                break

            handler = self._handlers.get(event.source)
            if handler:
                handler(event)
            count += 1

        return count
```

**Updated SemanticSearchInitializer:**

```python
# src/context/semantic/initializer.py
from ...infrastructure.threading.protocols import EventQueueProtocol, BackgroundEvent, EventType


class SemanticSearchInitializer:
    """Background initializer with event-based completion notification."""

    def __init__(
        self,
        project_path: Path,
        event_queue: Optional[EventQueueProtocol] = None
    ):
        self._project_path = project_path
        self._event_queue = event_queue
        # ... rest of init ...

    def _initialize_semantic_search(self) -> None:
        """Internal initialization in background thread."""
        try:
            # ... existing initialization code ...

            with self._lock:
                self._result = search_provider
                self._status = "Complete"
                self._complete = True

            # Notify via event queue instead of callback thread
            if self._event_queue:
                self._event_queue.put(BackgroundEvent(
                    event_type=EventType.INIT_COMPLETE,
                    source="semantic_search",
                    data=search_provider
                ))

        except Exception as e:
            with self._lock:
                self._error = e
                self._complete = True

            if self._event_queue:
                self._event_queue.put(BackgroundEvent(
                    event_type=EventType.INIT_FAILED,
                    source="semantic_search",
                    error=e
                ))

    # DEPRECATE wait_with_callback - it spawns threads
    def wait_with_callback(self, callback, timeout=None) -> None:
        """DEPRECATED: Use event_queue pattern instead."""
        import warnings
        warnings.warn(
            "wait_with_callback is deprecated. Use event_queue pattern.",
            DeprecationWarning,
            stacklevel=2
        )
        # Keep for backwards compatibility but log warning
        # ...existing implementation...
```

**Updated CodebaseContext:**

```python
# src/context/codebase_context.py
class CodebaseContext:
    def __init__(
        self,
        # ... existing params ...
        event_queue: Optional[EventQueueProtocol] = None,
    ):
        self._event_queue = event_queue
        # ...

    def start_background_initialization(self) -> None:
        """Start background initialization with event-based notification."""
        if self._semantic_initializer:
            # Register event handler for semantic search completion
            if self._event_queue:
                self._event_queue.register_handler(
                    "semantic_search",
                    self._handle_semantic_event
                )

            self._semantic_initializer.start()

            # DEPRECATED: Don't use wait_with_callback anymore
            # The main event loop will process events

    def _handle_semantic_event(self, event: BackgroundEvent) -> None:
        """Handle semantic search events (runs on main thread)."""
        if event.event_type == EventType.INIT_COMPLETE:
            self._semantic_search = event.data
            self._index_for_semantic_search()
        elif event.event_type == EventType.INIT_FAILED:
            logger.warning(f"Semantic search init failed: {event.error}")
```

### Phase 3 Implementation Notes

**Completed:** 2025-11-26

**Files created:**
- `src/infrastructure/threading/__init__.py` - Package exports
- `src/infrastructure/threading/protocols.py` - EventType, BackgroundEvent, EventQueueProtocol, MainThreadCallbackProtocol
- `src/infrastructure/threading/event_queue.py` - ThreadSafeEventQueue implementation

**Files modified:**
- `src/context/semantic/initializer.py`:
  - Added `event_queue` parameter to `__init__()`
  - Added `_emit_completion_event()` and `_emit_failure_event()` methods
  - Added deprecation warning to `wait_with_callback()`

- `src/context/codebase_context.py`:
  - Added `event_queue` parameter to `__init__()`
  - Added `event_queue` property
  - Added `process_background_events()` method
  - Added `_handle_semantic_event()` method (main-thread-safe event handler)
  - Updated `start_background_initialization()` to use event queue instead of callback thread
  - Updated `_create_default_semantic_initializer()` to pass event_queue
  - Deprecated `_on_semantic_search_ready()` (kept for backwards compatibility)

**Tests added to `tests/infrastructure/threading/test_event_queue.py`:**
- `TestThreadSafeEventQueue` - 10 unit tests for basic functionality
- `TestThreadSafeEventQueueConcurrency` - 3 stress tests for thread safety
- `TestBackgroundEvent` - 3 tests for event creation
- `TestEventType` - 2 tests for enum

**Test results:** All 18 tests pass

**Key behavioral changes:**
1. `CodebaseContext.start_background_initialization()` now registers an event handler instead of spawning a callback thread
2. Callers should periodically call `context.process_background_events()` from the main thread to process completion events
3. The old `wait_with_callback()` method is deprecated but still functional (emits deprecation warning)
4. Events are processed on whatever thread calls `process_pending()`, which should be the main thread

---

## Phase 4: Managed Thread Lifecycle - COMPLETED 2025-11-26

### 4.1 Replace Daemon Threads with Managed Threads

**Problem:** Daemon threads are killed abruptly on process exit, potentially corrupting file I/O operations.

**Protocol-First Design:**

```python
# src/infrastructure/threading/protocols.py (add to existing)
class ManagedThreadProtocol(Protocol):
    """Protocol for threads with proper lifecycle management."""

    def start(self) -> None:
        """Start the thread."""
        ...

    def stop(self, timeout: float = 5.0) -> bool:
        """Request thread stop and wait. Returns True if stopped cleanly."""
        ...

    def is_running(self) -> bool:
        """Check if thread is running."""
        ...

    def join(self, timeout: Optional[float] = None) -> None:
        """Wait for thread to complete."""
        ...
```

**Implementation:**

```python
# src/infrastructure/threading/managed_thread.py (new file)
import threading
from typing import Optional, Callable


class ManagedThread:
    """Thread with proper lifecycle management and graceful shutdown."""

    def __init__(
        self,
        target: Callable[['ManagedThread'], None],
        name: Optional[str] = None
    ):
        """
        Args:
            target: Function to run. Receives self to check shutdown_requested.
            name: Thread name for debugging
        """
        self._target = target
        self._name = name
        self._thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()
        self._started = False

    @property
    def shutdown_requested(self) -> bool:
        """Check if shutdown has been requested."""
        return self._shutdown_event.is_set()

    def start(self) -> None:
        """Start the thread."""
        if self._started:
            return

        self._thread = threading.Thread(
            target=self._run,
            name=self._name,
            daemon=False  # NOT a daemon - we manage lifecycle
        )
        self._thread.start()
        self._started = True

    def _run(self) -> None:
        """Internal wrapper that passes self to target."""
        self._target(self)

    def stop(self, timeout: float = 5.0) -> bool:
        """Request stop and wait for thread to finish."""
        if not self._started or self._thread is None:
            return True

        self._shutdown_event.set()
        self._thread.join(timeout=timeout)

        return not self._thread.is_alive()

    def is_running(self) -> bool:
        """Check if thread is running."""
        return self._thread is not None and self._thread.is_alive()

    def join(self, timeout: Optional[float] = None) -> None:
        """Wait for thread to complete."""
        if self._thread:
            self._thread.join(timeout=timeout)
```

**Updated SemanticSearchInitializer:**

```python
# src/context/semantic/initializer.py
from ...infrastructure.threading.managed_thread import ManagedThread


class SemanticSearchInitializer:
    def __init__(self, project_path: Path, event_queue=None):
        self._managed_thread: Optional[ManagedThread] = None
        # ...

    def start(self) -> None:
        """Start background initialization with managed thread."""
        with self._lock:
            if self._managed_thread is not None:
                return

            self._status = "Initializing..."
            self._managed_thread = ManagedThread(
                target=self._initialize_worker,
                name="SemanticSearchInit"
            )
            self._managed_thread.start()

    def _initialize_worker(self, thread: ManagedThread) -> None:
        """Worker function that checks for shutdown."""
        try:
            # Check shutdown periodically during long operations
            if thread.shutdown_requested:
                return

            # ... model loading ...

            if thread.shutdown_requested:
                return

            # ... database setup ...

            # Mark complete
            with self._lock:
                self._result = search_provider
                self._complete = True

        except Exception as e:
            with self._lock:
                self._error = e
                self._complete = True

    def shutdown(self, timeout: float = 5.0) -> bool:
        """Gracefully shutdown background initialization."""
        if self._managed_thread:
            return self._managed_thread.stop(timeout)
        return True
```

### Phase 4 Implementation Notes

**Completed:** 2025-11-26

**Files created:**
- `src/infrastructure/threading/managed_thread.py` - ManagedThread implementation with:
  - `shutdown_requested` property for cooperative shutdown
  - `start()`, `stop()`, `join()`, `is_running()` methods
  - `get_result()` and `get_error()` for capturing worker results
  - `wait_for_shutdown()` helper for blocking workers
  - NOT a daemon thread (`daemon=False`) - lifecycle is managed explicitly

**Files modified:**
- `src/infrastructure/threading/protocols.py` - Added `ManagedThreadProtocol`
- `src/infrastructure/threading/__init__.py` - Export `ManagedThread` and `ManagedThreadProtocol`
- `src/context/semantic/initializer.py`:
  - Replaced `threading.Thread` with `ManagedThread`
  - Renamed `_initialize_semantic_search()` to `_initialize_worker(thread)`
  - Worker now receives ManagedThread instance and checks `thread.shutdown_requested` at key points
  - Added `shutdown(timeout)` method for graceful termination
  - No longer uses `daemon=True` threads

**Tests added to `tests/infrastructure/threading/test_managed_thread.py`:**
- `TestManagedThread` - 6 tests for basic functionality
- `TestManagedThreadShutdown` - 6 tests for graceful shutdown
- `TestManagedThreadResults` - 4 tests for result/error handling
- `TestManagedThreadConcurrency` - 2 stress tests

**Test results:** All 18 ManagedThread tests pass, all 36 threading infrastructure tests pass

**Key behavioral changes:**
1. `SemanticSearchInitializer` now uses `ManagedThread` instead of daemon `threading.Thread`
2. Worker function checks `shutdown_requested` at 8 key points during initialization
3. New `shutdown(timeout)` method allows graceful termination
4. Threads are NOT daemon threads - they will complete or be explicitly stopped before process exit
5. If shutdown is requested mid-initialization, the worker exits cleanly without corrupting I/O

---

## Phase 5: Asyncio Callback Safety - COMPLETED 2025-11-26

### 5.1 Use Thread-Safe Collections in BackgroundTaskManager

**File:** `src/orchestrator/background.py`

**Problem:** `_tasks` dict and `_errors` list are modified in callbacks which may run from different contexts.

**Implementation:**

```python
# src/orchestrator/background.py
import threading
from collections import deque


class BackgroundTaskManager:
    def __init__(self):
        self._tasks: dict[str, asyncio.Task] = {}
        self._errors: deque = deque(maxlen=50)  # Thread-safe for append
        self._lock = threading.Lock()  # For _tasks dict operations

    def submit_background_task(self, coro) -> str:
        task_id = str(uuid.uuid4())
        task = asyncio.create_task(coro)

        with self._lock:
            self._tasks[task_id] = task

        def on_done(t):
            with self._lock:
                self._tasks.pop(task_id, None)

            try:
                exc = t.exception()
                if exc:
                    # deque.append is thread-safe
                    self._errors.append({
                        'timestamp': datetime.now().isoformat(),
                        'error': str(exc),
                        'type': type(exc).__name__
                    })
            except asyncio.CancelledError:
                pass

        task.add_done_callback(on_done)
        return task_id
```

### Phase 5 Implementation Notes

**Completed:** 2025-11-26

**Changes made:**
- Added `import threading` and `from collections import deque` to `src/orchestrator/background.py`
- Changed `self._errors` from `list[dict]` to `deque(maxlen=50)` - thread-safe for append, auto-limits size
- Added `self._lock = threading.Lock()` to protect `_tasks` dict operations
- Wrapped all `_tasks` accesses in `with self._lock:` blocks:
  - `submit_background_task()`: task addition
  - `on_done()` callback: task removal
  - `get_task_status()`: reading task count
  - `wait_for_background_tasks()`: checking empty and getting task list
  - `cancel_task()`: getting task by ID
- Removed manual error list trimming (deque maxlen handles it automatically)

**Tests added to `tests/test_background_manager.py` (TestBackgroundTaskManagerThreadSafety class):**
- `test_concurrent_task_submission` - verifies rapid submissions don't corrupt tracking
- `test_concurrent_status_access` - verifies concurrent status reads are safe
- `test_error_deque_thread_safety` - verifies error recording is thread-safe
- `test_error_deque_maxlen_respected` - verifies auto-limit to 50 errors
- `test_concurrent_cancel_and_status_access` - verifies concurrent cancel/status operations
- `test_has_lock_attribute` - verifies lock exists
- `test_errors_is_deque` - verifies deque with maxlen=50

**Test results:** All 26 BackgroundTaskManager tests pass (19 existing + 7 new thread safety tests)

---

## Implementation Order and Dependencies

```
Phase 1 (IMMEDIATE - 1-2 hours)
    |
    +-- 1.1 Guard signal registration in AuditLogger
    |       - Unblocks all users immediately
    |       - Zero risk, backwards compatible
    |
Phase 2 (SHORT-TERM - 2-4 hours)
    |
    +-- 2.1 ThreadSafeOutputCollector for SubprocessRunner
    |       - Prevents data corruption
    |       - Self-contained change
    |
Phase 3 (MEDIUM-TERM - 1-2 days)
    |
    +-- 3.1 Event queue protocol and implementation
    |       - New infrastructure component
    |
    +-- 3.2 Update SemanticSearchInitializer to use events
    |       - Deprecate wait_with_callback
    |
    +-- 3.3 Update CodebaseContext to handle events
    |       - Main thread processes events
    |
Phase 4 (MEDIUM-TERM - 1 day)
    |
    +-- 4.1 ManagedThread implementation
    |       - Proper lifecycle management
    |
    +-- 4.2 Update SemanticSearchInitializer to use ManagedThread
    |       - Graceful shutdown
    |
Phase 5 (LONG-TERM - 2-4 hours)
    |
    +-- 5.1 Thread-safe BackgroundTaskManager
            - Use deque and locks
```

---

## Testing Strategy

### Unit Tests Required

1. **AuditLogger thread safety:**
   - `test_signal_registration_skipped_in_worker_thread`
   - `test_atexit_always_registered`
   - `test_enable_auto_save_idempotent`

2. **ThreadSafeOutputCollector:**
   - `test_concurrent_append_is_thread_safe`
   - `test_get_lines_returns_copy`
   - `test_last_output_time_updated_on_append`

3. **ThreadSafeEventQueue:**
   - `test_put_from_multiple_threads`
   - `test_process_pending_calls_handlers`
   - `test_handler_called_on_processing_thread`

4. **ManagedThread:**
   - `test_graceful_shutdown`
   - `test_shutdown_timeout`
   - `test_not_daemon_thread`

### Integration Tests Required

1. **Agent lifecycle:**
   - `test_agent_runs_with_semantic_search_enabled`
   - `test_agent_shutdown_waits_for_background_threads`

2. **Event flow:**
   - `test_semantic_ready_triggers_indexing_on_main_thread`
   - `test_events_processed_in_order`

---

## Risk Assessment

| Change | Risk | Mitigation |
|--------|------|------------|
| Signal guard (Phase 1) | Very Low | Simple boolean check, no behavior change for main thread |
| Output collector (Phase 2) | Low | New class, doesn't change interface |
| Event queue (Phase 3) | Medium | New pattern, requires careful integration |
| Managed threads (Phase 4) | Medium | Changes thread lifecycle, needs thorough testing |
| Asyncio safety (Phase 5) | Low | Uses stdlib thread-safe collections |

---

## Rollback Plan

Each phase can be rolled back independently:

1. **Phase 1:** Remove thread check, restore original `_register_crash_handlers`
2. **Phase 2:** Remove ThreadSafeOutputCollector, restore inline variables
3. **Phase 3:** Remove event queue, restore `wait_with_callback`
4. **Phase 4:** Replace ManagedThread with daemon Thread
5. **Phase 5:** Remove locks from BackgroundTaskManager

---

## Success Criteria

1. `/agent` command works without signal error
2. No data corruption in subprocess output collection
3. Callbacks execute on main thread
4. Graceful shutdown within 5 seconds
5. All existing tests pass
6. No new race conditions detected by thread sanitizer
