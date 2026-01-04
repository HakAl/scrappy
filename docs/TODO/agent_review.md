# Review of LangGraph Agent

`src/scrappy/graph/agent.py`

### 1. The `run_agent` vs. Interrupt Trap
**The Issue:**
Your `run_agent` docstring says: *"This function runs to completion without confirmation prompts."*
However, `build_graph` hardcodes `interrupt_before=["confirm"]`.
If the LLM decides to route to `confirm`, `graph.invoke` inside `run_agent` will **halt** execution and raise a `GraphInterrupt` (or return the state snapshot depending on the version/config), leaving the agent in a suspended state. It will *not* auto-complete.

**The Fix:**
You need two distinct modes or a runtime override. Since `interrupt_before` is set at `compile()` time, you cannot easily toggle it off for `run_agent`.

**Recommendation:**
Modify `build_graph` to accept `enable_hitl: bool = True`.
```python
def build_graph(..., enable_hitl: bool = True) -> CompiledStateGraph:
    # ... setup ...
    interrupts = ["confirm"] if enable_hitl else []
    compiled = builder.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupts,
    )
    return compiled
```
Then `run_agent` can call it with `False` if the intention is truly autonomous execution, or handle the loop logic if it's meant to simulate a user approving everything.

### 2. The `verify` Loop Context (LLM Whispering)
**The Issue:**
You have a loop: `execute -> verify -> think`.
When `verify` (e.g., mypy) fails and routes back to `think`, does the `think` node know *why* it's back?
Standard `messages` history will show the tool output, but if `verify` adds a specialized "analysis" message, ensure `think` knows how to prioritize that over the previous context.

**Recommendation:**
Ensure `verify_node` injects a clear **System** or **Tool** message into the state:
> "Verification failed: Mypy error on line 10. Please correct the code."
Without this explicit feedback injection, the LLM might hallucinate that the previous step succeeded and try to move on, causing a loop.

### 3. The `confirm` Node Logic
**The Issue:**
In `create_agent_runner`, the docstring suggests:
```python
graph.update_state(config, {"confirmation_response": user_response})
```
However, your graph structure is:
`execute` -> (conditional) -> `confirm`.
If you `interrupt_before=["confirm"]`, the execution stops *after* `execute` but *before* `confirm_node` runs.
When you resume, `confirm_node` runs. Does `confirm_node` actually read `confirmation_response` from the state and map it to `state.done`?

**Recommendation:**
Ensure `confirm_node` looks like this logic:
```python
def confirm_node(state: AgentState):
    # Check if we have a user injection from update_state
    if state.confirmation_response == "deny":
        return {"done": True} # Triggers _route_after_confirm -> END
    return {"done": False} # Triggers _route_after_confirm -> THINK
```

### 4. Recursion Limit Calculation
**Observation:**
`recursion_limit=150` is a good heuristic.
**Nuance:** LangGraph counts *steps*.
1. `think` (1)
2. `execute` (2)
3. `verify` (3)
4. `think` (4)
If you have a strict loop, this works.
**Risk:** If `verify` fails 10 times, you burn 30 steps.
**Recommendation:** Add a `loop_count` or `retry_count` specifically for the `verify` -> `think` edge in your state. If the agent fails verification 3 times in a row for the same file, force a routing to `error` or `end` to prevent token burning on an unsolvable syntax error.

### 5. Dependency Injection Refinement
**The Code:**
```python
def wrapped(state: AgentState) -> AgentState:
    return think_node(state, llm_service, tool_adapter)
```
**Critique:**
This works perfectly. However, for maximum observability (e.g., LangSmith/LangFuse), ensure your `think_node` is traced *inside* the wrapper or the wrapper itself is decorated with `@traceable`. When using closures, sometimes the auto-instrumentation names the span `wrapped` instead of `think_node`, which makes the trace UI messy.

**fix:**
```python
def _wrap_think_node(...):
    def think_node_wrapper(state: AgentState): # Rename function for better trace labels
        return think_node(state, llm_service, tool_adapter)
    return think_node_wrapper
```

### 6. Minor Nits & Safety

*   **Callback Mutation:**
    ```python
    if langfuse_handler:
        compiled = compiled.with_config({"callbacks": [langfuse_handler]})
    ```
    This works, but be aware that if you pass `config` with different callbacks into `invoke`, they might overwrite or merge depending on LangGraph version specifics. It is often safer to pass the callback list at runtime in `run_agent` via the `config` object rather than baking it into the compiled graph.

*   **Error Handling in Routing:**
    In `_route_after_error`:
    ```python
    if state.error_count >= MAX_RETRIES:
        return Route.END
    ```
    Make sure `error_node` actually increments `state.error_count`. If `think` fails, routes to `error`, and `error` doesn't increment, you have an infinite loop (until recursion limit hits).
