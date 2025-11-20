# AgentOrchestrator Refactoring Plan

## Problem Analysis

**AgentOrchestrator (`src/orchestrator/core.py` - 875 lines)**

**Multiple Responsibilities:**
1. Provider management (lines 309-369)
2. Context management (lines 370-387)
3. Session management (lines 389-427)
4. Task execution (lines 429-440)
5. Provider selection (lines 442-467)
6. Delegation (lines 469-764)
7. Async delegation (lines 630-764)
8. Usage reporting (lines 766-788)
9. Background task management (lines 790-844)
10. Rate limit management (lines 846-868)

**Critical Issues:**
- 16 injected dependencies in `__init__` (lines 53-75)
- 13 factory methods (lines 193-305)
- Violates Single Responsibility Principle
- Each responsibility = different reason to change
- Missing protocol definitions (violates Dependency Inversion)
- Direct file system access (tight coupling)
- No clear test boundaries

---

## PHASE 1: DEFINE PROTOCOLS (DO THIS FIRST)

**CRITICAL: No implementation code until all protocols are defined.**

### File Structure
```
orchestrator/
  ├── protocols.py         <- START HERE
  ├── core.py             <- Facade/Coordinator
  ├── delegation.py       <- DelegationManager
  ├── context_manager.py  <- ContextManager
  ├── session_manager.py  <- SessionManager
  ├── background.py       <- BackgroundTaskManager
  └── usage_reporter.py   <- UsageReporter
```

### Protocol Definitions (`src/orchestrator/protocols.py`)

```python
"""
Protocol definitions for orchestrator components.
Defines contracts before implementations (CLAUDE.md Phase 1).
"""

from typing import Protocol, Optional, Dict, Any, List, Callable, Tuple, Coroutine
from datetime import datetime
from pathlib import Path

# --- Core Provider & Response Protocols ---

class LLMResponse(Protocol):
    """Protocol for LLM provider responses."""
    provider: str
    model: str
    content: str
    tokens_used: int
    latency_ms: float
    metadata: Dict[str, Any]

class LLMProvider(Protocol):
    """Protocol for LLM provider implementations."""
    def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse: ...

    async def generate_async(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse: ...

# --- Cache Protocol ---

class CacheProtocol(Protocol):
    """Protocol for response caching."""

    def get(
        self,
        provider: str,
        model: Optional[str],
        prompt: str,
        system_prompt: Optional[str],
        intent: Optional[dict]
    ) -> Optional[LLMResponse]:
        """Retrieve cached response if exists."""
        ...

    def set(
        self,
        provider: str,
        model: str,
        prompt: str,
        system_prompt: Optional[str],
        response: LLMResponse,
        intent: Optional[dict]
    ) -> None:
        """Store response in cache."""
        ...

    def get_stats(self) -> Dict[str, Any]:
        """Return cache statistics (hit rate, size, etc)."""
        ...

    def clear(self) -> None:
        """Clear all cached entries."""
        ...

# --- Output/Logging Protocol ---

class OutputProtocol(Protocol):
    """Protocol for output and logging operations."""

    def debug(self, message: str) -> None: ...
    def info(self, message: str) -> None: ...
    def warn(self, message: str) -> None: ...
    def error(self, message: str) -> None: ...
    def section(self, title: str) -> None: ...
    def success(self, message: str) -> None: ...

# --- Retry/Fallback Protocol ---

class RetryOrchestratorProtocol(Protocol):
    """Protocol for retry and fallback logic."""

    def execute_with_retry(
        self,
        provider_name: str,
        func: Callable[[LLMProvider, Optional[str]], LLMResponse],
        model: Optional[str],
        auto_fallback: bool,
        max_retries: int
    ) -> LLMResponse:
        """Execute with retry/fallback logic (sync)."""
        ...

    async def execute_with_retry_async(
        self,
        provider_name: str,
        func: Callable[[LLMProvider, Optional[str]], Coroutine[Any, Any, LLMResponse]],
        model: Optional[str],
        auto_fallback: bool,
        max_retries: int
    ) -> LLMResponse:
        """Execute with retry/fallback logic (async)."""
        ...

# --- Prompt Augmentation Protocol ---

class PromptAugmenterProtocol(Protocol):
    """Protocol for prompt enhancement with context."""

    def augment(
        self,
        prompt: str,
        system_prompt: Optional[str]
    ) -> Tuple[str, Optional[str], bool]:
        """
        Augment prompt with context.
        Returns: (augmented_prompt, system_prompt, was_augmented)
        """
        ...

# --- Batch Scheduling Protocol ---

class BatchSchedulerProtocol(Protocol):
    """Protocol for batch request processing."""

    def process_batch(
        self,
        tasks: List[Dict[str, Any]],
        provider_name: str
    ) -> List[LLMResponse]:
        """Process batch of tasks synchronously."""
        ...

    async def process_batch_async(
        self,
        tasks: List[Dict[str, Any]],
        provider_name: str,
        max_concurrent: int
    ) -> List[LLMResponse]:
        """Process batch of tasks asynchronously."""
        ...

# --- File System Protocol ---

class FileSystemProtocol(Protocol):
    """Protocol for file system operations."""

    def read_json(self, path: Path) -> Dict[str, Any]:
        """Read JSON file."""
        ...

    def write_json(self, path: Path, data: Dict[str, Any]) -> None:
        """Write JSON file."""
        ...

    def exists(self, path: Path) -> bool:
        """Check if path exists."""
        ...

    def delete(self, path: Path) -> None:
        """Delete file."""
        ...

# --- Context Protocol ---

class CodebaseContextProtocol(Protocol):
    """Protocol for codebase context operations."""

    def scan(self, force: bool = False) -> Dict[str, Any]:
        """Scan codebase and return statistics."""
        ...

    def get_status(self) -> Dict[str, Any]:
        """Get current context status."""
        ...

    def get_summary_text(self) -> str:
        """Get text summary of context."""
        ...

# --- Working Memory Protocol ---

class WorkingMemoryProtocol(Protocol):
    """Protocol for session working memory."""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        ...

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "WorkingMemoryProtocol":
        """Deserialize from dictionary."""
        ...

# --- Clock Protocol (for testability) ---

class ClockProtocol(Protocol):
    """Protocol for time operations (enables time-travel testing)."""

    def now(self) -> datetime:
        """Get current datetime."""
        ...

    def timestamp(self) -> float:
        """Get current timestamp."""
        ...
```

---

## PHASE 2: TEST PLANS (BEFORE IMPLEMENTATION)

### Test Strategy

**Test Doubles Location:** `tests/helpers.py`

**Principle:** Test behavior, not structure. Test edge cases, not initialization.

### 2.1 DelegationManager Tests

**File:** `tests/test_delegation_manager.py`

**Test Cases:**
```python
# Behavior Tests
def test_checks_cache_before_executing_request()
def test_stores_response_in_cache_after_success()
def test_returns_cached_response_when_available()
def test_skips_cache_when_use_cache_is_false()
def test_augments_prompt_when_context_aware_is_true()
def test_skips_augmentation_when_context_aware_is_false()
def test_respects_use_context_override()
def test_delegates_to_retry_orchestrator_for_execution()
def test_creates_task_record_with_correct_metadata()

# Edge Cases
def test_handles_none_system_prompt()
def test_handles_empty_prompt()
def test_handles_cache_returning_none()
def test_handles_augmentation_failure()
def test_includes_augmented_flag_in_task_record()

# Async Tests
def test_async_delegation_checks_cache()
def test_async_delegation_calls_async_retry_method()
def test_async_task_record_includes_async_flag()

# Batch Tests
def test_batch_delegation_calls_scheduler()
def test_async_batch_delegation_respects_max_concurrent()

# Error Conditions
def test_handles_provider_not_found()
def test_handles_retry_exhaustion()
```

**Test Doubles Needed:**
- `MockCache` (implements `CacheProtocol`)
- `MockOutput` (implements `OutputProtocol`)
- `MockRetryOrchestrator` (implements `RetryOrchestratorProtocol`)
- `MockPromptAugmenter` (implements `PromptAugmenterProtocol`)
- `MockBatchScheduler` (implements `BatchSchedulerProtocol`)

### 2.2 ContextManager Tests

**File:** `tests/test_context_manager.py`

**Test Cases:**
```python
# Behavior Tests
def test_explore_project_scans_codebase()
def test_explore_returns_scan_statistics()
def test_explore_outputs_progress_messages()
def test_explore_generates_summary_after_scan()
def test_explore_marks_as_explored()
def test_explore_skips_rescan_when_already_explored()
def test_explore_rescans_when_force_is_true()
def test_auto_explore_triggers_scan_when_not_explored()
def test_auto_explore_skips_scan_when_already_explored()
def test_get_context_summary_returns_summary_text()

# Edge Cases
def test_handles_scan_failure()
def test_handles_summary_generation_failure()
def test_warns_when_summary_fails()

# Error Conditions
def test_handles_context_not_available()
```

**Test Doubles Needed:**
- `MockCodebaseContext` (implements `CodebaseContextProtocol`)
- `MockOutput` (implements `OutputProtocol`)

### 2.3 SessionManager Tests

**File:** `tests/test_session_manager.py`

**Test Cases:**
```python
# Behavior Tests
def test_save_session_writes_json_file()
def test_save_session_includes_all_required_fields()
def test_save_session_returns_file_path()
def test_load_session_reads_json_file()
def test_load_session_returns_status_loaded()
def test_load_session_rehydrates_working_memory()
def test_load_session_returns_counts()
def test_clear_session_deletes_file()

# Edge Cases
def test_load_returns_no_file_when_missing()
def test_handles_empty_task_history()
def test_handles_empty_conversation_history()
def test_handles_missing_optional_fields()

# Error Conditions
def test_handles_write_permission_error()
def test_handles_read_permission_error()
def test_handles_corrupted_json()
def test_handles_invalid_working_memory_data()
def test_returns_error_status_on_load_failure()
```

**Test Doubles Needed:**
- `MockFileSystem` (implements `FileSystemProtocol`)
- `MockWorkingMemory` (implements `WorkingMemoryProtocol`)

### 2.4 BackgroundTaskManager Tests

**File:** `tests/test_background_manager.py`

**Test Cases:**
```python
# Behavior Tests
def test_submit_creates_background_task()
def test_submit_returns_task_id()
def test_tracks_active_tasks()
def test_removes_task_from_active_when_complete()
def test_wait_for_tasks_waits_until_completion()
def test_wait_returns_completion_stats()
def test_cancel_task_cancels_by_id()
def test_get_status_returns_active_count()
def test_get_status_includes_error_count()
def test_clear_errors_empties_error_list()

# Edge Cases
def test_handles_task_completion_callback()
def test_handles_task_raising_exception()
def test_records_task_errors()
def test_outputs_error_message_on_failure()
def test_handles_cancellation_gracefully()
def test_wait_returns_immediately_when_no_tasks()
def test_wait_respects_timeout()

# Error Conditions
def test_cancel_returns_false_for_unknown_task_id()
def test_handles_multiple_simultaneous_completions()
```

**Test Doubles Needed:**
- `MockOutput` (implements `OutputProtocol`)
- Async test fixtures

### 2.5 UsageReporter Tests

**File:** `tests/test_usage_reporter.py`

**Test Cases:**
```python
# Behavior Tests
def test_record_adds_entry_to_log()
def test_record_includes_timestamp()
def test_record_increments_provider_totals()
def test_record_skips_totals_for_cached_requests()
def test_get_report_returns_uptime()
def test_get_report_returns_total_tokens()
def test_get_report_returns_provider_breakdown()
def test_get_report_includes_recent_activity()
def test_get_cache_stats_delegates_to_cache()
def test_get_cache_stats_returns_disabled_when_no_cache()
def test_clear_cache_delegates_to_cache()

# Edge Cases
def test_handles_no_cache_provided()
def test_recent_activity_limits_to_last_ten()
def test_multiple_providers_tracked_separately()
def test_calculates_uptime_correctly()

# Error Conditions
def test_handles_cache_stats_failure()
```

**Test Doubles Needed:**
- `MockCache` (implements `CacheProtocol`)
- `MockClock` (implements `ClockProtocol`)

---

## PHASE 3: IMPLEMENT COMPONENTS

### 3.1 DelegationManager (`src/orchestrator/delegation.py`)

**Responsibilities:**
1. Orchestrate delegation flow (augment -> cache check -> execute -> cache store)
2. Coordinate retry/fallback via RetryOrchestrator
3. Generate task records
4. Handle both sync and async delegation

**Implementation:**

```python
"""
DelegationManager - Orchestrates LLM request execution.

Handles:
1. Prompt augmentation with context
2. Cache lookups and updates
3. Retry/fallback coordination
4. Task record generation
"""

import asyncio
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime

from .protocols import (
    LLMResponse,
    CacheProtocol,
    OutputProtocol,
    RetryOrchestratorProtocol,
    PromptAugmenterProtocol,
    BatchSchedulerProtocol,
    ClockProtocol
)

class DelegationManager:
    """
    Orchestrates LLM task execution with caching, augmentation, and retry logic.

    Single Responsibility: Coordinate delegation flow
    Dependencies: All injected via constructor
    """

    def __init__(
        self,
        retry_orchestrator: RetryOrchestratorProtocol,
        cache: CacheProtocol,
        output: OutputProtocol,
        prompt_augmenter: PromptAugmenterProtocol,
        batch_scheduler: BatchSchedulerProtocol,
        clock: ClockProtocol,
        context_aware: bool = True
    ):
        """
        Initialize delegation manager.

        NO side effects - only assigns dependencies.
        """
        self.retry_orchestrator = retry_orchestrator
        self.cache = cache
        self.output = output
        self.prompt_augmenter = prompt_augmenter
        self.batch_scheduler = batch_scheduler
        self.clock = clock
        self.context_aware = context_aware

    def delegate(
        self,
        provider_name: str,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        use_context: Optional[bool] = None,
        use_cache: bool = True,
        intent_classification: Optional[dict] = None,
        auto_fallback: bool = True,
        max_retries: int = 3,
        **kwargs
    ) -> Tuple[LLMResponse, Dict[str, Any]]:
        """
        Execute LLM request synchronously.

        Flow: Augment -> Cache Check -> Execute -> Cache Store -> Record
        """

        # 1. Augment Prompt
        should_augment = use_context if use_context is not None else self.context_aware
        final_prompt, final_system_prompt, augmented_flag = self._prepare_prompts(
            prompt, system_prompt, should_augment
        )

        # 2. Check Cache
        if use_cache:
            cached_resp = self.cache.get(
                provider_name, model, final_prompt, final_system_prompt, intent_classification
            )
            if cached_resp:
                self.output.debug(f"Cache hit for {provider_name}")
                return cached_resp, self._create_cached_task_record(
                    provider_name, model, cached_resp
                )

        # 3. Execute with Retry/Fallback
        response = self.retry_orchestrator.execute_with_retry(
            provider_name=provider_name,
            func=lambda p, m: self._execute_request(p, m, final_prompt, final_system_prompt, **kwargs),
            model=model,
            auto_fallback=auto_fallback,
            max_retries=max_retries
        )

        # 4. Update Cache
        if use_cache and response:
            self.cache.set(
                provider_name,
                response.model,
                final_prompt,
                final_system_prompt,
                response,
                intent_classification
            )

        # 5. Generate Task Record
        task_record = self._create_task_record(response, augmented_flag, final_prompt)

        return response, task_record

    async def delegate_async(
        self,
        provider_name: str,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        use_context: Optional[bool] = None,
        use_cache: bool = True,
        intent_classification: Optional[dict] = None,
        auto_fallback: bool = True,
        max_retries: int = 3,
        **kwargs
    ) -> Tuple[LLMResponse, Dict[str, Any]]:
        """Execute LLM request asynchronously."""

        # 1. Augment
        should_augment = use_context if use_context is not None else self.context_aware
        final_prompt, final_system_prompt, augmented_flag = self._prepare_prompts(
            prompt, system_prompt, should_augment
        )

        # 2. Cache Check
        if use_cache:
            cached_resp = self.cache.get(
                provider_name, model, final_prompt, final_system_prompt, intent_classification
            )
            if cached_resp:
                return cached_resp, self._create_cached_task_record(
                    provider_name, model, cached_resp, async_flag=True
                )

        # 3. Execute Async
        response = await self.retry_orchestrator.execute_with_retry_async(
            provider_name=provider_name,
            func=lambda p, m: self._execute_request_async(p, m, final_prompt, final_system_prompt, **kwargs),
            model=model,
            auto_fallback=auto_fallback,
            max_retries=max_retries
        )

        # 4. Update Cache
        if use_cache and response:
            self.cache.set(
                provider_name,
                response.model,
                final_prompt,
                final_system_prompt,
                response,
                intent_classification
            )

        # 5. Generate Task Record
        task_record = self._create_task_record(response, augmented_flag, final_prompt)
        task_record['async'] = True

        return response, task_record

    def delegate_batch(
        self,
        tasks: List[Dict[str, Any]],
        provider_name: str
    ) -> List[LLMResponse]:
        """Delegate batch processing to scheduler."""
        return self.batch_scheduler.process_batch(tasks, provider_name)

    async def batch_delegate_async(
        self,
        tasks: List[Dict[str, Any]],
        provider_name: str,
        max_concurrent: int
    ) -> List[LLMResponse]:
        """Delegate async batch processing to scheduler."""
        return await self.batch_scheduler.process_batch_async(
            tasks, provider_name, max_concurrent
        )

    # --- Internal Helpers (Private Methods) ---

    def _prepare_prompts(
        self,
        prompt: str,
        system_prompt: Optional[str],
        should_augment: bool
    ) -> Tuple[str, Optional[str], bool]:
        """Prepare prompts with optional augmentation."""
        if should_augment:
            return self.prompt_augmenter.augment(prompt, system_prompt)
        return prompt, system_prompt, False

    def _execute_request(self, provider, model, prompt, sys_prompt, **kwargs):
        """Execute synchronous request on provider."""
        return provider.generate(
            prompt,
            model=model,
            system_prompt=sys_prompt,
            **kwargs
        )

    async def _execute_request_async(self, provider, model, prompt, sys_prompt, **kwargs):
        """Execute asynchronous request on provider."""
        return await provider.generate_async(
            prompt,
            model=model,
            system_prompt=sys_prompt,
            **kwargs
        )

    def _create_task_record(
        self,
        response: LLMResponse,
        augmented: bool,
        prompt: str
    ) -> Dict[str, Any]:
        """Generate task record from response."""
        return {
            'id': f"task_{self.clock.timestamp()}",
            'timestamp': self.clock.now().isoformat(),
            'provider': response.provider,
            'model': response.model,
            'prompt_length': len(prompt),
            'response_length': len(response.content),
            'tokens_used': response.tokens_used,
            'latency_ms': response.latency_ms,
            'cached': False,
            'context_augmented': augmented,
            'status': 'success'
        }

    def _create_cached_task_record(
        self,
        provider: str,
        model: Optional[str],
        response: LLMResponse,
        async_flag: bool = False
    ) -> Dict[str, Any]:
        """Generate task record for cached response."""
        record = {
            'provider': provider,
            'cached': True,
            'latency_ms': 0,
            'tokens_used': 0,
            'model': model or response.model
        }
        if async_flag:
            record['async'] = True
        return record
```

### 3.2 ContextManager (`src/orchestrator/context_manager.py`)

**Responsibilities:**
1. Coordinate codebase scanning
2. Manage exploration state
3. Provide context summaries

**Implementation:**

```python
"""
ContextManager - Manages codebase context operations.

Handles:
1. Triggering codebase scans
2. Managing exploration state
3. Retrieving context summaries
"""

from typing import Dict, Any

from .protocols import CodebaseContextProtocol, OutputProtocol

class ContextManager:
    """
    Manages codebase context operations for the orchestrator.

    Single Responsibility: Coordinate context operations
    Dependencies: Injected via constructor
    """

    def __init__(
        self,
        context: CodebaseContextProtocol,
        output: OutputProtocol
    ):
        """
        Initialize context manager.

        NO side effects - only assigns dependencies.
        """
        self.context = context
        self.output = output
        self._has_explored = False

    def explore_project(self, force: bool = False) -> Dict[str, Any]:
        """
        Trigger codebase scan.

        Args:
            force: Force rescan even if already explored

        Returns:
            Scan statistics
        """
        if self._has_explored and not force:
            self.output.info("Project already explored. Use force=True to rescan.")
            return self.context.get_status()

        self.output.section("Exploring Project Context")

        try:
            stats = self.context.scan(force=force)
            self.output.info(f"Scanned {stats.get('files_scanned', 0)} files.")
            self._has_explored = True
            return stats
        except Exception as e:
            self.output.error(f"Failed to scan project: {e}")
            raise

    def auto_explore(self) -> None:
        """Automatically explore if not yet explored."""
        if not self._has_explored:
            self.explore_project()

    def get_context_summary(self) -> str:
        """Retrieve context summary text."""
        return self.context.get_summary_text()

    def reset_exploration_state(self) -> None:
        """Reset exploration flag (useful for testing)."""
        self._has_explored = False
```

### 3.3 SessionManager (`src/orchestrator/session_manager.py`)

**Responsibilities:**
1. Serialize orchestrator state
2. Deserialize orchestrator state
3. Manage session file lifecycle

**Implementation:**

```python
"""
SessionManager - Manages session persistence.

Handles:
1. Saving orchestrator state to JSON
2. Loading orchestrator state from JSON
3. Session file management
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

from .protocols import FileSystemProtocol, WorkingMemoryProtocol

class SessionManager:
    """
    Manages session state persistence.

    Single Responsibility: Handle session serialization
    Dependencies: FileSystem abstraction injected
    """

    def __init__(
        self,
        project_path: Path,
        file_system: FileSystemProtocol
    ):
        """
        Initialize session manager.

        Args:
            project_path: Explicit path (no defaults)
            file_system: Injected file system abstraction

        NO side effects - only assigns dependencies.
        """
        self.project_path = project_path
        self.file_system = file_system
        self.session_file = self.project_path / ".llm_session.json"

    def save_session(
        self,
        working_memory: WorkingMemoryProtocol,
        task_history: List[Dict[str, Any]],
        created_at: datetime,
        conversation_history: List[Dict[str, Any]]
    ) -> str:
        """
        Serialize session state to JSON.

        Returns:
            Path to saved file or error message
        """
        data = {
            'saved_at': datetime.now().isoformat(),
            'created_at': created_at.isoformat(),
            'working_memory': working_memory.to_dict(),
            'task_history': task_history,
            'conversation_history': conversation_history
        }

        try:
            self.file_system.write_json(self.session_file, data)
            return str(self.session_file)
        except Exception as e:
            return f"Error saving session: {e}"

    def load_session(self) -> Dict[str, Any]:
        """
        Load session state from JSON.

        Returns:
            Dict with 'status' key and session data if loaded
        """
        if not self.file_system.exists(self.session_file):
            return {'status': 'no_file'}

        try:
            data = self.file_system.read_json(self.session_file)

            # Rehydrate WorkingMemory
            wm_data = data.get('working_memory', {})
            working_memory = self._rehydrate_working_memory(wm_data)

            return {
                'status': 'loaded',
                'working_memory': working_memory,
                'task_history': data.get('task_history', []),
                'conversation_history': data.get('conversation_history', []),
                'saved_at': data.get('saved_at'),
                'files_restored': len(wm_data.get('files', {})),
                'searches_restored': len(wm_data.get('searches', [])),
                'git_ops_restored': len(wm_data.get('git_ops', [])),
                'discoveries_restored': len(wm_data.get('discoveries', [])),
                'tasks_restored': len(data.get('task_history', [])),
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def clear_session(self) -> None:
        """Delete session file if exists."""
        if self.file_system.exists(self.session_file):
            self.file_system.delete(self.session_file)

    def _rehydrate_working_memory(
        self,
        wm_data: Dict[str, Any]
    ) -> WorkingMemoryProtocol:
        """Reconstruct WorkingMemory from dict."""
        # Import here to avoid circular dependency
        from ..memory import WorkingMemory
        return WorkingMemory.from_dict(wm_data)
```

### 3.4 BackgroundTaskManager (`src/orchestrator/background.py`)

**Responsibilities:**
1. Schedule background coroutines
2. Track active tasks
3. Handle task completion and errors
4. Provide task status

**Implementation:**

```python
"""
BackgroundTaskManager - Manages async background tasks.

Handles:
1. Scheduling fire-and-forget tasks
2. Tracking task lifecycle
3. Recording errors
4. Cleanup
"""

import asyncio
import uuid
from typing import Dict, Set, Any, Coroutine, List
from asyncio import InvalidStateError

from .protocols import OutputProtocol

class BackgroundTaskManager:
    """
    Manages fire-and-forget background tasks.

    Single Responsibility: Coordinate asyncio tasks
    Dependencies: Output injected for error logging
    """

    def __init__(self, output: OutputProtocol):
        """
        Initialize background task manager.

        NO side effects - only initializes state.
        """
        self.output = output
        self.active_tasks: Set[asyncio.Task] = set()
        self.task_errors: List[Dict[str, Any]] = []
        self.task_map: Dict[str, asyncio.Task] = {}

    def submit_background_task(self, coro: Coroutine) -> str:
        """
        Schedule a coroutine to run in background.

        Args:
            coro: Coroutine to execute

        Returns:
            Task ID for tracking
        """
        task_id = str(uuid.uuid4())[:8]

        # Create task
        task = asyncio.create_task(coro, name=f"bg_task_{task_id}")

        # Track it
        self.active_tasks.add(task)
        self.task_map[task_id] = task

        # Add cleanup callback
        task.add_done_callback(lambda t: self._handle_task_completion(t, task_id))

        return task_id

    def _handle_task_completion(self, task: asyncio.Task, task_id: str) -> None:
        """
        Handle task completion (callback).

        Records errors and cleans up tracking.
        """
        self.active_tasks.discard(task)
        self.task_map.pop(task_id, None)

        try:
            exc = task.exception()
            if exc:
                err_info = {
                    'task_id': task_id,
                    'error': str(exc),
                    'type': type(exc).__name__
                }
                self.task_errors.append(err_info)
                self.output.error(f"Background task {task_id} failed: {exc}")
        except (asyncio.CancelledError, InvalidStateError):
            pass

    async def wait_for_background_tasks(self, timeout: float = 5.0) -> Dict[str, int]:
        """
        Wait for all active tasks to complete.

        Args:
            timeout: Max time to wait in seconds

        Returns:
            Completion statistics
        """
        if not self.active_tasks:
            return {'finished': 0, 'still_pending': 0, 'initial_count': 0}

        initial_count = len(self.active_tasks)
        done, pending = await asyncio.wait(
            self.active_tasks,
            timeout=timeout,
            return_when=asyncio.ALL_COMPLETED
        )

        return {
            'finished': len(done),
            'still_pending': len(pending),
            'initial_count': initial_count
        }

    def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a task by ID.

        Returns:
            True if task was found and cancelled
        """
        task = self.task_map.get(task_id)
        if task:
            task.cancel()
            return True
        return False

    def get_task_status(self) -> Dict[str, Any]:
        """Get current task status."""
        return {
            'active_count': len(self.active_tasks),
            'recent_errors': len(self.task_errors),
            'errors': self.task_errors[-5:]  # Last 5 errors
        }

    def clear_background_errors(self) -> None:
        """Clear error log."""
        self.task_errors = []
```

### 3.5 UsageReporter (`src/orchestrator/usage_reporter.py`)

**Responsibilities:**
1. Record task completions
2. Track token usage
3. Generate usage reports
4. Delegate cache statistics

**Implementation:**

```python
"""
UsageReporter - Tracks usage metrics.

Handles:
1. Recording task completions
2. Aggregating token usage
3. Generating usage reports
4. Delegating cache stats
"""

from datetime import datetime
from typing import Dict, Any, List, Optional
from collections import defaultdict

from .protocols import CacheProtocol, ClockProtocol

class UsageReporter:
    """
    Tracks token usage and performance metrics.

    Single Responsibility: Usage tracking and reporting
    Dependencies: Cache and Clock injected
    """

    def __init__(
        self,
        clock: ClockProtocol,
        created_at: datetime,
        cache: Optional[CacheProtocol] = None
    ):
        """
        Initialize usage reporter.

        NO side effects - only assigns dependencies.
        """
        self.clock = clock
        self.cache = cache
        self.created_at = created_at
        self.usage_log: List[Dict[str, Any]] = []
        self.provider_totals = defaultdict(
            lambda: {'tokens': 0, 'calls': 0, 'errors': 0}
        )

    def record(
        self,
        provider: str,
        tokens_used: int,
        cached: bool,
        metadata: Dict[str, Any]
    ) -> None:
        """
        Record a completed task.

        Args:
            provider: Provider name
            tokens_used: Number of tokens consumed
            cached: Whether response was cached
            metadata: Additional task metadata
        """
        entry = {
            'timestamp': self.clock.now().isoformat(),
            'provider': provider,
            'tokens': tokens_used,
            'cached': cached,
            **metadata
        }
        self.usage_log.append(entry)

        # Aggregate totals (skip cached requests)
        if not cached:
            self.provider_totals[provider]['tokens'] += tokens_used
            self.provider_totals[provider]['calls'] += 1

    def get_usage_report(self) -> Dict[str, Any]:
        """
        Generate usage summary report.

        Returns:
            Dict with uptime, tokens, calls, and breakdown
        """
        uptime = self.clock.now() - self.created_at

        total_tokens = sum(p['tokens'] for p in self.provider_totals.values())
        total_calls = sum(p['calls'] for p in self.provider_totals.values())

        return {
            'uptime_seconds': uptime.total_seconds(),
            'total_tokens': total_tokens,
            'total_llm_calls': total_calls,
            'provider_breakdown': dict(self.provider_totals),
            'recent_activity': self.usage_log[-10:]  # Last 10 actions
        }

    def get_cache_stats(self) -> Dict[str, Any]:
        """Delegate to cache for statistics."""
        if self.cache:
            return self.cache.get_stats()
        return {'status': 'disabled'}

    def clear_cache(self) -> None:
        """Delegate cache clearing."""
        if self.cache:
            self.cache.clear()
```

---

## PHASE 4: UPDATE ORCHESTRATOR TO USE COMPONENTS

**Goal:** Transform `AgentOrchestrator` into a thin Facade that delegates to focused components.

**Key Changes:**
1. Replace direct implementations with component delegation
2. Reduce line count from 875 to ~200-300 lines
3. Maintain public API compatibility
4. All dependencies injected as protocols

**This phase will be a separate task after Phases 1-3 are complete.**

---

## Success Criteria

- [ ] All protocols defined in `protocols.py`
- [ ] All test files created with comprehensive test cases
- [ ] All test doubles created in `tests/helpers.py`
- [ ] All tests passing (behavior-focused, not structure-focused)
- [ ] All components use protocol types (no `Any` types)
- [ ] All dependencies injected via constructor
- [ ] No side effects in constructors
- [ ] No direct file system or network access
- [ ] Each component < 300 lines
- [ ] AgentOrchestrator reduced to < 300 lines (Facade pattern)

---

## Implementation Order

1. Create `protocols.py` with ALL protocol definitions
2. Create test doubles in `tests/helpers.py`
3. Write tests for each component (TDD approach)
4. Implement components one at a time:
   - DelegationManager
   - ContextManager
   - SessionManager
   - BackgroundTaskManager
   - UsageReporter
5. Refactor AgentOrchestrator to use components
6. Verify all existing tests still pass
7. Add integration tests

---

## Notes

- This follows CLAUDE.md Protocol-First Design mandate
- All dependencies are abstractions (protocols), not concretions
- Tests prove behavior, not structure
- Components are focused and single-purpose
- No god classes, no tight coupling
- Fully testable without I/O
