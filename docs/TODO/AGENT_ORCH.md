#### AgentOrchestrator (`src/orchestrator/core.py` - 875 lines)

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

**Issues:**
- 16 injected dependencies in `__init__` (lines 53-75)
- 13 factory methods (lines 193-305)
- Violates Single Responsibility Principle
- Each responsibility = different reason to change

**Refactor Plan (CLAUDE.md Phase 2):**
```python
# Break up into focused components
orchestrator/
  ├── core.py (Orchestrator - high-level coordination only)
  ├── context_coordinator.py (ContextCoordinator)
  ├── background_manager.py (BackgroundTaskManager)
  ├── usage_reporter.py (UsageReporter)
  ├── session_manager.py (SessionManager)
  └── delegation_handler.py (DelegationHandler)
```

This is a significant refactoring effort. You have successfully transformed `AgentOrchestrator` into a **Facade**, which is the correct architectural move. The Orchestrator now delegates work instead of doing it itself.

To make your `core.py` work, we need to implement the component classes it depends on. Based on your imports and method calls, here are the implementations for the broken-out components.

### 1. Delegation Manager (`src/orchestrator/delegation.py`)
This handles the core complexity: prompt augmentation, caching checks, and the retry/fallback loop.

```python
import asyncio
from typing import Optional, Tuple, List, Any, Dict
from datetime import datetime

try:
    from ..providers import LLMResponse
    from ..exceptions.delegation import ProviderNotFoundError
except ImportError:
    from providers import LLMResponse
    from exceptions.delegation import ProviderNotFoundError

class DelegationManager:
    """
    Handles the execution of LLM tasks, including:
    1. Context augmentation
    2. Caching checks
    3. Retry/Fallback logic (via RetryOrchestrator)
    4. Batch scheduling
    """

    def __init__(
        self,
        retry_orchestrator: Any,
        cache: Any,
        output: Any,
        prompt_augmenter: Any,
        batch_scheduler: Any,
        context_aware: bool = True
    ):
        self.retry_orchestrator = retry_orchestrator
        self.cache = cache
        self.output = output
        self.prompt_augmenter = prompt_augmenter
        self.batch_scheduler = batch_scheduler
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
    ) -> Tuple[LLMResponse, Dict]:
        """Synchronous delegation flow."""
        
        # 1. Augment Prompt
        should_augment = use_context if use_context is not None else self.context_aware
        final_prompt, system_prompt, augmented_flag = self._prepare_prompts(
            prompt, system_prompt, should_augment
        )

        # 2. Check Cache
        if use_cache:
            cached_resp = self.cache.get(
                provider_name, model, final_prompt, system_prompt, intent_classification
            )
            if cached_resp:
                self.output.debug(f"Cache hit for {provider_name}")
                return cached_resp, {
                    'provider': provider_name,
                    'cached': True,
                    'latency_ms': 0,
                    'tokens_used': 0,
                    'model': model
                }

        # 3. Execute with Retry/Fallback
        response = self.retry_orchestrator.execute_with_retry(
            provider_name=provider_name,
            func=lambda p, m: self._execute_request(p, m, final_prompt, system_prompt, **kwargs),
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
                system_prompt, 
                response, 
                intent_classification
            )

        # 5. Prepare Task Record
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
    ) -> Tuple[LLMResponse, Dict]:
        """Asynchronous delegation flow."""
        
        # 1. Augment
        should_augment = use_context if use_context is not None else self.context_aware
        # Note: Prompt augmentation might be CPU bound, usually okay in async unless huge
        final_prompt, system_prompt, augmented_flag = self._prepare_prompts(
            prompt, system_prompt, should_augment
        )

        # 2. Cache
        if use_cache:
            # Assuming cache.get is synchronous (file I/O), might wrap in thread if strict async needed
            cached_resp = self.cache.get(
                provider_name, model, final_prompt, system_prompt, intent_classification
            )
            if cached_resp:
                return cached_resp, {
                    'provider': provider_name,
                    'cached': True, 
                    'async': True,
                    'latency_ms': 0
                }

        # 3. Execute Async
        # retry_orchestrator needs an execute_with_retry_async method
        response = await self.retry_orchestrator.execute_with_retry_async(
            provider_name=provider_name,
            func=lambda p, m: self._execute_request_async(p, m, final_prompt, system_prompt, **kwargs),
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
                system_prompt, 
                response, 
                intent_classification
            )

        task_record = self._create_task_record(response, augmented_flag, final_prompt)
        task_record['async'] = True
        return response, task_record

    def delegate_batch(self, tasks: List[Dict], provider_name: str) -> List[LLMResponse]:
        """Delegates to BatchScheduler."""
        return self.batch_scheduler.process_batch(tasks, provider_name)

    async def batch_delegate_async(
        self, 
        tasks: List[Dict], 
        provider_name: str, 
        max_concurrent: int
    ) -> List[LLMResponse]:
        """Delegates to BatchScheduler async implementation."""
        return await self.batch_scheduler.process_batch_async(
            tasks, provider_name, max_concurrent
        )

    # --- Internal Helpers ---

    def _prepare_prompts(self, prompt, system_prompt, should_augment):
        if should_augment:
            return self.prompt_augmenter.augment(prompt, system_prompt)
        return prompt, system_prompt, False

    def _execute_request(self, provider, model, prompt, sys_prompt, **kwargs):
        # This retrieves the actual provider instance from registry logic inside RetryOrchestrator
        # or assumes provider is the instance.
        # To keep strict separation, RetryOrchestrator passes the provider INSTANCE here.
        return provider.generate(prompt, model=model, system_prompt=sys_prompt, **kwargs)

    async def _execute_request_async(self, provider, model, prompt, sys_prompt, **kwargs):
        return await provider.generate_async(prompt, model=model, system_prompt=sys_prompt, **kwargs)

    def _create_task_record(self, response: LLMResponse, augmented: bool, prompt: str) -> Dict:
        return {
            'id': f"task_{datetime.now().timestamp()}",
            'timestamp': datetime.now().isoformat(),
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
```

### 2. Context Manager (`src/orchestrator/context_manager.py`)
Handles interaction with the CodebaseContext and abstracting high-level context operations.

```python
from typing import Callable, Optional, Dict
from pathlib import Path

try:
    from ..context import CodebaseContext
except ImportError:
    from context import CodebaseContext

class ContextManager:
    """
    Manages high-level context operations for the orchestrator.
    """

    def __init__(
        self,
        context: CodebaseContext,
        output: Any,
        generate_summary_func: Callable[[CodebaseContext], str]
    ):
        self.context = context
        self.output = output
        self._generate_summary_func = generate_summary_func
        self._has_explored = False

    def explore_project(self, force: bool = False) -> Dict:
        """Trigger a scan of the codebase."""
        if self._has_explored and not force:
            self.output.info("Project already explored. Use force=True to rescan.")
            return self.context.get_status()

        self.output.section("Exploring Project Context")
        stats = self.context.scan(force=force)
        
        self.output.info(f"Scanned {stats.get('files_scanned', 0)} files.")
        
        # Generate a semantic summary using the injected brain function
        try:
            summary = self._generate_summary_func(self.context)
            self.output.info("Generated context summary.")
        except Exception as e:
            self.output.warn(f"Could not generate semantic summary: {e}")
        
        self._has_explored = True
        return stats

    def auto_explore(self):
        """Automatically explore if cache is empty or stale."""
        # Logic to check if cache exists on disk
        # This is a simplified heuristic
        if not self._has_explored:
            self.explore_project()

    def get_context_summary(self) -> str:
        """Retrieve the summarized context."""
        return self.context.get_summary_text()
```

### 3. Background Manager (`src/orchestrator/background.py`)
Handles fire-and-forget tasks and asyncio management.

```python
import asyncio
import uuid
from typing import Dict, Set, Any, Coroutine

class BackgroundTaskManager:
    """
    Manages fire-and-forget background tasks (asyncio).
    """

    def __init__(self):
        self.active_tasks: Set[asyncio.Task] = set()
        self.task_errors: list = []
        self.task_map: Dict[str, asyncio.Task] = {}

    def submit_background_task(self, coro: Coroutine) -> str:
        """
        Schedule a coroutine to run in the background.
        Returns a Task ID.
        """
        task_id = str(uuid.uuid4())[:8]
        
        # Create task
        task = asyncio.create_task(coro, name=f"bg_task_{task_id}")
        
        # track it
        self.active_tasks.add(task)
        self.task_map[task_id] = task
        
        # Add callback to clean up
        task.add_done_callback(lambda t: self._handle_task_completion(t, task_id))
        
        return task_id

    def _handle_task_completion(self, task: asyncio.Task, task_id: str):
        """Cleanup callback."""
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
                # Ideally log this using the OutputInterface if injected, or print
                print(f"[Background Error] Task {task_id} failed: {exc}")
        except (asyncio.CancelledError, InvalidStateError):
            pass

    async def wait_for_background_tasks(self, timeout: float = 5.0) -> Dict:
        """Wait for active tasks to finish."""
        if not self.active_tasks:
            return {'pending': 0, 'completed': 0}

        pending_count = len(self.active_tasks)
        done, pending = await asyncio.wait(
            self.active_tasks, 
            timeout=timeout, 
            return_when=asyncio.ALL_COMPLETED
        )
        
        return {
            'finished': len(done),
            'still_pending': len(pending),
            'initial_count': pending_count
        }

    def cancel_task(self, task_id: str) -> bool:
        task = self.task_map.get(task_id)
        if task:
            task.cancel()
            return True
        return False

    def get_task_status(self) -> Dict:
        return {
            'active_count': len(self.active_tasks),
            'recent_errors': len(self.task_errors),
            'errors': self.task_errors[-5:] # Last 5 errors
        }
        
    def clear_background_errors(self):
        self.task_errors = []
```

### 4. Session Manager (`src/orchestrator/session.py`)
Handles serialization of state.

```python
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

try:
    from ..memory import WorkingMemory
except ImportError:
    from memory import WorkingMemory

class SessionManager:
    """
    Manages persistence of the orchestrator's state.
    """

    def __init__(self, project_path: Optional[Path] = None):
        self.project_path = project_path or Path.cwd()
        self.session_file = self.project_path / ".llm_session.json"

    def save_session(
        self, 
        working_memory: WorkingMemory, 
        task_history: List[Dict], 
        created_at: datetime,
        conversation_history: Optional[List] = None
    ) -> str:
        """Serialize state to JSON."""
        data = {
            'saved_at': datetime.now().isoformat(),
            'created_at': created_at.isoformat(),
            'working_memory': working_memory.to_dict(),
            'task_history': task_history,
            'conversation_history': conversation_history or []
        }

        try:
            with open(self.session_file, 'w') as f:
                json.dump(data, f, indent=2)
            return str(self.session_file)
        except IOError as e:
            return f"Error saving session: {e}"

    def load_session(self) -> Dict:
        """Load state from JSON."""
        if not self.session_file.exists():
            return {'status': 'no_file'}

        try:
            with open(self.session_file, 'r') as f:
                data = json.load(f)

            # Rehydrate WorkingMemory
            wm_data = data.get('working_memory', {})
            working_memory = WorkingMemory.from_dict(wm_data)

            return {
                'status': 'loaded',
                'working_memory': working_memory,
                'task_history': data.get('task_history', []),
                'conversation_history': data.get('conversation_history', []),
                'saved_at': data.get('saved_at'),
                # Extract counts for reporting
                'files_restored': len(wm_data.get('files', {})),
                'searches_restored': len(wm_data.get('searches', [])),
                'git_ops_restored': len(wm_data.get('git_ops', [])),
                'discoveries_restored': len(wm_data.get('discoveries', [])),
                'tasks_restored': len(data.get('task_history', [])),
            }
        except (json.JSONDecodeError, IOError) as e:
            return {'status': 'error', 'message': str(e)}

    def clear_session(self):
        if self.session_file.exists():
            self.session_file.unlink()
```

### 5. Usage Reporter (`src/orchestrator/usage_reporter.py`)
Handles tracking usage and reporting.

```python
from datetime import datetime
from typing import Dict, Any, List
from collections import defaultdict

class UsageReporter:
    """
    Tracks token usage, costs (estimated), and performance metrics.
    """

    def __init__(self, cache: Any = None, created_at: Optional[datetime] = None):
        self.cache = cache
        self.created_at = created_at or datetime.now()
        self.usage_log: List[Dict] = []
        self.provider_totals = defaultdict(lambda: {'tokens': 0, 'calls': 0, 'errors': 0})

    def record(
        self, 
        provider: str, 
        tokens_used: int, 
        cached: bool, 
        metadata: Dict[str, Any]
    ):
        """Record a completed task."""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'provider': provider,
            'tokens': tokens_used,
            'cached': cached,
            **metadata
        }
        self.usage_log.append(entry)
        
        # Aggregates
        if not cached:
            self.provider_totals[provider]['tokens'] += tokens_used
            self.provider_totals[provider]['calls'] += 1

    def get_usage_report(self) -> Dict:
        """Generate summary report."""
        uptime = datetime.now() - self.created_at
        
        total_tokens = sum(p['tokens'] for p in self.provider_totals.values())
        total_calls = sum(p['calls'] for p in self.provider_totals.values())
        
        return {
            'uptime_seconds': uptime.total_seconds(),
            'total_tokens': total_tokens,
            'total_llm_calls': total_calls,
            'provider_breakdown': dict(self.provider_totals),
            'recent_activity': self.usage_log[-10:] # Last 10 actions
        }

    def get_cache_stats(self) -> Dict:
        """Delegates to cache component if available."""
        if self.cache:
            return self.cache.get_stats()
        return {'status': 'disabled'}

    def clear_cache(self):
        if self.cache:
            self.cache.clear()
```

### Summary of Refactoring
*   **`AgentOrchestrator` (core.py)**: Now acting as the **Entry Point** and **Wiring Container**. It is readable and adheres to the Open/Closed principle better (adding a new reporting mechanism doesn't require changing the orchestration logic, just injecting a new reporter).
*   **`DelegationManager`**: Contains the complex logic for retries and fallback, removing ~300 lines from the main class.
*   **`ContextManager`**: Isolates codebase operations.
*   **`SessionManager`**: Isolates file I/O and JSON handling.
*   **`BackgroundTaskManager`**: Isolates `asyncio` complexity.

This structure aligns perfectly with your P0 Critical priority.
