# Parallel Tool Execution

Since `ToolContext` relies on an external `orchestrator` for memory persistence, must ensure **access to that orchestrator** is thread-safe.

### Phase 1: Harden `ToolContext` (File: `tools/base.py`)
We need to modify `ToolContext` to handle concurrency. Since it is a dataclass, we use `field(default_factory=...)` for the lock.

**Changes Required:**
1.  Import `threading`.
2.  Add a `_lock` field.
3.  Wrap `orchestrator` calls in the lock.
4.  Add a `clone()` method for worker threads.

```python
# In tools/base.py

@dataclass
class ToolContext:
    # ... existing fields ...
    # New field for thread safety
    _lock: threading.Lock = field(default_factory=threading.Lock)

    # ... is_safe_path remains same ...

    def remember_file_read(self, path: str, content: str, lines: int):
        if self.orchestrator:
            with self._lock:  # <--- CRITICAL: Serialize access to orchestrator
                self.orchestrator.remember_file_read(path, content, lines)
    
    # ... apply 'with self._lock' to remember_search and remember_git_operation too ...

    def clone_for_thread(self) -> "ToolContext":
        """Create a thread-safe copy sharing the orchestrator and lock."""
        return ToolContext(
            project_root=self.project_root,
            dry_run=self.dry_run,
            config=self.config,
            orchestrator=self.orchestrator,
            _lock=self._lock  # Share the SAME lock instance
        )
```

### Phase 2: Parallel Tool Implementation (File: `tools/concurrency_tools.py`)
This tool acts as a "Meta-Tool" that orchestrates others. It requires the tool registry to function.

**Logic:**
1.  Accepts a list of `tool_calls`.
2.  Uses `ThreadPoolExecutor`.
3.  Clones the context for each thread to ensure safety.
4.  Returns a combined string, but formatted so `Rich` can handle it cleanly (e.g., Markdown headers).

(Registry-Aware) This tool needs the registry to look up *other* tools.

Since `RunParallelTool` will now be in the registry, it technically has the ability to **call itself** (e.g., the LLM asks to run parallel tasks, and one of those tasks is another parallel run). This could explode your thread pool.

```python
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from .base import ToolBase, ToolParameter, ToolResult, ToolContext

class RunParallelTool(ToolBase):
    def __init__(self, registry: Any):
        self.registry = registry

    @property
    def name(self) -> str:
        return "run_parallel"

    @property
    def description(self) -> str:
        return "Execute multiple tools simultaneously. Returns combined results."

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                "tool_calls", 
                list, 
                "List of objects: [{'tool_name': '...', 'arguments': {...}}]"
            )
        ]

    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        calls = kwargs.get("tool_calls", [])
        
        # --- NEW SAFETY CHECK ---
        # Prevent the LLM from nesting parallel calls inside parallel calls
        # which could exhaust the thread pool or cause deadlocks.
        if context.metadata.get("is_parallel_worker", False):
            return ToolResult(False, "Error: Nested parallel execution is not allowed.")

        results = []

        def _worker(call_data):
            name = call_data.get("tool_name")
            args = call_data.get("arguments", {})
            
            # Prevent calling itself explicitly
            if name == self.name:
                return f"### {name} (Skipped)\nRecursion not allowed."

            tool = self.registry.get_tool(name)
            if not tool:
                return f"### {name} (Error)\nTool not found."
            
            # Clone context for thread safety
            # We mark this context so sub-tools know they are in a worker thread
            thread_ctx = context.clone_for_thread()
            thread_ctx.metadata["is_parallel_worker"] = True 
            
            try:
                # Execute the tool synchronously in this thread
                res = tool.execute(thread_ctx, **args)
                
                # Format simple output
                icon = "success" if res.success else "fail"
                return f"### {icon} {name}\n{res.output}"
            except Exception as e:
                return f"### fail {name} (Exception)\n{str(e)}"

        # Execute
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(_worker, call) for call in calls]
            results = [f.result() for f in futures]

        return ToolResult(True, "\n\n".join(results))
```

### Summary of Changes required for this to work:

1.  **`tools/base.py`**:
    *   Add `_lock` to `ToolContext`.
    *   Add `clone_for_thread()` to `ToolContext`.
    *   Add `metadata: dict = field(default_factory=dict)` to `ToolContext` (if not already present) to handle the recursion flag.

2.  **`tools/meta_tools.py`**:
    *   Create the file with the code above.

3.  **`agent_loop.py` (The Cleanup)**:
    *   Remove the manual `tools.append(...)` hacks.
    *   Register `RunParallelTool(registry)`, `CommandTool`, and `CompleteTool` in your initialization phase.

### Phase 3: Textual Integration Safety
Since your `ToolResult` class supports `__rich__`, the Textual UI will likely try to render the output.

*   **Risk:** If `RunParallelTool` returns a huge string (combined contents of 5 files), the TUI might lag while computing the syntax highlighting for the `Syntax` object in `__rich__`.
*   **Mitigation:** The `metadata={"language": "text"}` implicitly defaults to text.
    *   If you want syntax highlighting for the *combined* output, `ToolResult.__rich__` might struggle because it's a mix of different file types.
    *   **Recommendation:** For `RunParallelTool`, keep the output simple (Markdown headers) and let the UI render it as Markdown or Plain Text, rather than trying to auto-detect a specific coding language.

### Checklist for Success
1.  [ ] Update `ToolContext` in `base.py` with `_lock` and `clone_for_thread`.
2.  [ ] Inject `registry` into `RunParallelTool` during app startup.
3.  [ ] Ensure the Agent loop calls `run_parallel` from a `Worker` thread (Textual requirement).