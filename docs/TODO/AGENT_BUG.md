# Threading and Signal Handler Bug Analysis

## Problem Statement

User prompts agent: `/agent please add a db repository for the api api/v1/routes.py`, agent crashes with:

```
Code Agent - Task: please add a db repository for the api api/v1/routes.py
------------------------------------------------------------

Agent Configuration:
  Planner (smart tasks): cerebras
  Executor (fast tasks): cerebras
  Project root: C:\Users\anyth\MINE\dev\test_repo


Agent error: signal only works in main thread of the main interpreter
```

---

## Root Cause Analysis

### The Core Problem

When running the `/agent` command, the `AuditLogger._register_crash_handlers()` method attempts to register signal handlers from a background thread. Python's `signal.signal()` can only be called from the main thread, causing a `RuntimeError`.

### Key Files and Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/agent/audit.py` | 81-99 | Signal registration in `_register_crash_handlers()` |
| `src/agent/core.py` | 684 | `enable_auto_save()` call that triggers signal registration |
| `src/context/semantic/initializer.py` | 110-127 | `wait_with_callback()` spawns worker thread |
| `src/context/codebase_context.py` | 220-223 | Registers callback with semantic initializer |

### Execution Flow

```
Main Thread                           Worker Thread (Callback)
===========                           ========================
/agent command
    |
    v
agent_manager.run_agent()
    |
    v
CodeAgent.__init__()
    |
    +---> Orchestrator created
    |         |
    |         v
    |     context.start_background_initialization()
    |         |
    |         v
    |     SemanticSearchInitializer.start()
    |         |
    |         v
    |     wait_with_callback() ---------> Creates Thread
    |                                         |
    v                                         v
CodeAgent.run()                         _on_semantic_search_ready()
    |                                         |
    v                                         v
enable_auto_save()                      _index_for_semantic_search()
    |                                         |
    v                                         v
_register_crash_handlers()              [If any audit logging triggered]
    |                                         |
    v                                         v
signal.signal() [OK - main thread]      signal.signal() [CRASH!]
```

### Why It Crashes

1. `CodeAgent.__init__()` creates an orchestrator which starts background semantic search initialization
2. `SemanticSearchInitializer.wait_with_callback()` (line 125-127) spawns a **new thread** to execute the callback when initialization completes
3. The callback `_on_semantic_search_ready()` runs in this worker thread
4. If any code path in the callback triggers `AuditLogger.enable_auto_save()`, it calls `signal.signal()` from a non-main thread
5. Python raises: `signal only works in main thread of the main interpreter`

### The Architectural Issue

The `wait_with_callback()` method creates a separate thread just to run the callback:

```python
# src/context/semantic/initializer.py:121-127
def wait_thread():
    completed = self.wait_for_completion(timeout=timeout)
    callback(completed, self.get_result(), self.get_error())

thread = threading.Thread(target=wait_thread)
thread.daemon = True
thread.start()
```

This means the callback (`_on_semantic_search_ready`) executes in a worker thread, not the main thread. Any signal registration attempted from within this callback chain will fail.

---

## Related Threading Issues in Codebase

This is not an isolated issue. The codebase has several threading-related problems that follow similar patterns:

### 1. HIGH RISK: Race Conditions in SubprocessRunner

**File:** `src/agent_tools/components/subprocess_runner.py` (lines 92-127)

```python
def read_output():
    nonlocal last_output_time
    try:
        for line in iter(process.stdout.readline, ''):
            if line:
                output_lines.append(line.rstrip())  # Worker thread writes
                last_output_time = time.time()       # Worker thread writes
    except Exception:
        pass

reader_thread = threading.Thread(target=read_output)
reader_thread.daemon = True
reader_thread.start()

# Main thread reads these same variables:
while process.poll() is None:
    stall_time = time.time() - last_output_time  # Race condition!
```

**Issues:**
- `output_lines` list accessed by both main thread and worker thread without synchronization
- `last_output_time` read/written by both threads without locks
- Worker thread may be appending while main thread reads length

### 2. MEDIUM RISK: Callback Invocation from Worker Threads

**File:** `src/context/codebase_context.py` (lines 194-205, 589-614)

```python
def _notify_indexing_progress(self, message: str) -> None:
    if self._indexing_progress_callback:
        try:
            self._indexing_progress_callback(message)  # Called from worker!
        except Exception as e:
            logger.debug(f"Error in indexing progress callback: {e}")

def _on_semantic_search_ready(self, success: bool, result, error) -> None:
    # This method runs in worker thread!
    if success and result:
        self._notify_indexing_progress("...")  # Callback in worker
        self._semantic_search = result         # Shared state modified in worker
        self._index_for_semantic_search()      # Complex code in worker
```

**Issues:**
- User-provided callbacks may not be thread-safe
- Shared state (`_semantic_search`) modified from worker thread
- No synchronization on callback registration/invocation

### 3. MEDIUM RISK: Daemon Threads with No Cleanup

**File:** `src/context/semantic/initializer.py` (lines 53-71, 125-127)

```python
self._thread = threading.Thread(
    target=self._initialize_semantic_search,
    daemon=True,  # Daemon thread!
    name="SemanticSearchInit"
)
self._thread.start()

# Later, another daemon thread:
thread = threading.Thread(target=wait_thread)
thread.daemon = True  # Another daemon!
thread.start()
```

**Issues:**
- Daemon threads are killed abruptly when main thread exits
- File I/O (LanceDB operations) may be interrupted mid-write
- No graceful shutdown mechanism
- Thread spawning another thread creates complex lifecycle

### 4. LOW-MEDIUM RISK: Asyncio Task Callbacks

**File:** `src/orchestrator/background.py` (lines 58-78)

```python
def on_done(t):
    self._tasks.pop(task_id, None)  # Dict modification
    try:
        exc = t.exception()
        if exc:
            self._errors.append({...})  # List modification
            if len(self._errors) > 50:
                self._errors = self._errors[-50:]  # List replacement
    except asyncio.CancelledError:
        pass

task.add_done_callback(on_done)
```

**Issues:**
- Task done callbacks run in event loop context
- `_tasks` dict and `_errors` list modified without synchronization
- If event loop runs in different thread, race conditions occur

---

## Comprehensive Solution

### Immediate Fix (Signal Handler Bug)

Option 1 - Guard signal registration:
```python
import threading

def _register_crash_handlers(self) -> None:
    if threading.current_thread() is not threading.main_thread():
        return  # Skip signal registration if not main thread
    # ... existing signal registration code
```

Option 2 - Register signals early in main thread:
```python
# In application startup (before any threads spawn)
audit_logger = AuditLogger(...)
audit_logger.enable_auto_save(...)  # Register signals here, in main thread
```

### Broader Architectural Fixes

1. **Eliminate `wait_with_callback()` pattern:**
   - Use async/await instead of spawning callback threads
   - Or use a thread-safe event queue for main thread callbacks

2. **Add synchronization to SubprocessRunner:**
   ```python
   self._output_lock = threading.Lock()

   def read_output():
       with self._output_lock:
           output_lines.append(line.rstrip())
           last_output_time = time.time()
   ```

3. **Document thread safety requirements:**
   - Mark methods with `@main_thread_only` decorator
   - Document which callbacks must be thread-safe
   - Add thread safety assertions in debug mode

4. **Replace daemon threads with managed threads:**
   ```python
   self._shutdown_event = threading.Event()

   def _initialize_semantic_search(self) -> None:
       while not self._shutdown_event.is_set():
           # ... do work

   def shutdown(self):
       self._shutdown_event.set()
       self._thread.join(timeout=5.0)
   ```

5. **Use thread-safe collections:**
   ```python
   from queue import Queue
   from collections import deque
   import threading

   self._errors = deque(maxlen=50)  # Thread-safe for append/popleft
   self._error_lock = threading.Lock()  # For complex operations
   ```

---

## Summary of All Threading Issues

| Issue | File | Severity | Type |
|-------|------|----------|------|
| Signal from worker thread | `audit.py:81-99` | HIGH | Crashes app |
| `wait_with_callback` spawns thread | `initializer.py:110-127` | HIGH | Root cause |
| Race on `output_lines` | `subprocess_runner.py:92-127` | HIGH | Data corruption |
| Race on `last_output_time` | `subprocess_runner.py:98,111` | MEDIUM | Stale reads |
| Callback from worker thread | `codebase_context.py:203` | MEDIUM | Undefined behavior |
| Shared state in worker | `codebase_context.py:606` | MEDIUM | Race condition |
| Daemon threads no cleanup | `initializer.py:67,126` | MEDIUM | Data loss |
| Asyncio callback races | `background.py:59-76` | LOW-MEDIUM | Dict/list races |

---

## Recommended Fix Order

1. **Immediate:** Add main thread check to `_register_crash_handlers()` (unblocks users)
2. **Short-term:** Add locks to `SubprocessRunner` (prevents data corruption)
3. **Medium-term:** Refactor `wait_with_callback()` to use event queue pattern
4. **Long-term:** Replace daemon threads with managed shutdown, add thread safety docs
