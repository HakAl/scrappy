# src/task_router/strategies/agent_executor.py

The public surface is already thin, but the *implementation* still mixes three different responsibilities and can be tightened without changing the API.**

--------------------------------------------------
1.  What the class is *supposed* to do
--------------------------------------------------
- “I am an **adapter** that turns a `ClassifiedTask` into an `ExecutionResult` by delegating to the real brain (`CodeAgent`).”  
That is **one** responsibility – so the *public* side respects SRP.

--------------------------------------------------
2.  Where it *still* does too much
--------------------------------------------------
A. **Hard-wired policy decisions**  
- `_get_task_specific_guidance` contains **400 lines of business rules** (requirements.txt, Dockerfile, config-file heuristics).  
- These rules change whenever the team changes tech stack, yet they live inside the executor.

B. **Planning orchestration**  
- `_run_planning` reaches into the orchestrator and massages the plan format.  
- Planning is a *cross-cutting* concern; the executor should only ask for a plan, not know *how* to format it.

C. **Fallback production code**  
- `_fallback_execution` duplicates prompt construction and token counting that the orchestrator already knows how to do.  
- Fallback is a *resilience* policy, not an execution concern.

D. **Hidden dependency creation**  
- `CodeAgent` and `AgentOrchestratorAdapter` are created **inside* `execute`, so the class is still a *factory* as well as a *service*.

--------------------------------------------------
3.  Low-risk fixes (no public change)
--------------------------------------------------
Move each coloured block into its own *policy* object and **inject** it:

| Policy | Extracted class | Constructor default |
|---|---|---|
| Task-specific guidance | `GuidancePolicy` | `GuidancePolicy.default()` |
| Planning | `PlanningService` | `PlanningService(orchestrator)` |
| Fallback generator | `FallbackExecutor` | `FallbackExecutor(orchestrator)` |
| Agent factory | `AgentFactory` | `AgentFactory(project_root)` |

After extraction the `execute` method shrinks to:

```python
plan      = self._planning.plan(task) if task.requires_planning else None
guidance  = self._guidance.for_task(task)
prompt    = self._build_prompt(task, plan, guidance)
result    = self._agent.create(adapter).run(prompt)
return self._map_result(result)
```

Every collaborator is < 80 lines, unit-testable in isolation, and the
`AgentExecutor` now **only** coordinates the pipeline.

--------------------------------------------------
4.  SOLID checklist after refactor
--------------------------------------------------
✓ SRP – executor = coordination; policy objects own the rules.  
✓ OCP – new guidance rule → new `GuidancePolicy` implementation; no touch in executor.  
✓ DIP – executor depends on *protocols* (`PlanningService`, `GuidancePolicy`); fakes can be injected in tests.  
✓ ISP – each protocol exposes only one capability.  
✓ LSP – any implementation of the protocols can be substituted without breaking `AgentExecutor`.

Do the extractions above and the answer becomes: **“No, the class is now doing exactly one thing – orchestrating the agent loop.”**