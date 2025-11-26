## Issues

---
Integrate semantic search initial indexing w/status bar.
---

---
Problem:
/explore freezes app
---

---
Problem:
something is creating .lancedb outside of .scrappy directory. dir contains empty update.lock file

Solution:
find what's creating .lancedb/ dir at root, and correct path


---

<!-- todo -->

- Semantic LLM classification
- Add intent clarification mechanism

---
  Recommendations

  1. Configuration consolidation - Consider a RouterConfig dataclass for all thresholds/settings
  2. Pattern weight configuration - Allow runtime/file-based pattern weight adjustment
  3. Metrics persistence - Add optional persistence for MetricsCollector

  ---
  3. Fragile Pattern Matching

  Evidence:
  - Strategy pattern with pluggable ClassificationStrategy implementations
  - LLM-augmented classification for disambiguation
  - Intent clarification for ambiguous cases
  - Confidence scoring with escalation logic

  Remaining concerns:
  - Pattern weights still hardcoded in strategy classes
  - Could benefit from configurable patterns or learned weights

  Location: classification_strategies/*.py

  Remaining concerns:
  - Some thresholds hardcoded (e.g., 0.7 in pure_functions)
  - Pattern weights in strategy classes
  - Consider centralizing to a config object
----


- help table output is all white -- need ability to customize table display

---

## Feature 8: User-Facing Configuration

### Current State
Configuration is programmatic via `SemanticIndexConfig`. No user-facing config file support.

---
## Rate Limiting

Orchestrator should be aware of rate limits and delegate accordingly.


src\orchestrator\rate_limiter.py

<!-- todo -- define fallback strategies until all providers are exhausted -->
**Issues**
- Defined, not enforced
- warn users of limits when approaching

---

<!-- todo -->

- Add skip logic in task_executor.py
eg:   if complexity_score <= 3:
      return [{"step": "execute", "description": task, "provider_type": "fast"}]
- Update planning prompt to include: "For simple tasks, return 1-2 steps maximum. Minimize unnecessary steps."

<!-- EXISITING ISSUE -->
- context summary file always written, doesn't respect user choice
- Auto-explore Stale Context: Uses cached context from llm_team itself, not the new project

CodebaseContext is a 840-line god object with multiple responsibilities that would benefit from decomposition. The
   tests are better than average but don't fully prove correctness.




  Critical Issues Found

  ---

  8. Side Effects Everywhere ⚠️ Present

  Constructor loads cache (context.py:107):
  def __init__(self, project_path: Optional[str] = None):
      ...
      self._load_cache()  # Side effect in constructor

  Hidden explore call (context.py:633-634):
  def get_project_type(self) -> str:
      if not self.structure:
          self.explore()  # Hidden side effect


  10. Tight Coupling ⚠️ Present

  Hard dependencies on:
  - subprocess - git operations
  - os.walk / pathlib - file system
  - shutil.which - tool detection

  ---

<!-- todo -- Assess code / tests / maintainability -->

- multiline input (copy / paste)
- user choices stored in history (y, Y, n, N, 1, 2, 3, etc)

<!-- new features -->

- Diff preview
 - Structured output validation - Pydantic schemas for LLM responses
 - Streaming responses - Token-by-token generation for better UX
 
---


<!-- EXISITING ISSUE -->
- 2 audit logs created: 
  - .agent_audit.json
  - .llm_agent_audit.json
  usually happens because handlers are being added every time the function runs, rather than just once at startup.
The Fix:
Check if the logger already has handlers before adding a new one.
If you are using logging.getLogger(__name__) and also logging.getLogger(), the child logger might be propagating the message up to the root logger, causing it to print twice.
Fix: Set logger.propagate = False.
---

- Premature Task Completion: Agent stops after 4 iterations (7 seconds), completing ~5% of the task and declaring success
  - Naive Completion Detection: Any write_file operation triggers "task complete"
- No Task Decomposition: Doesn't break complex tasks into tracked subtasks
- Complex Import Structure: Relative imports fail when using programmatically

<!-- todo -->
- Agent composition - Chain multiple specialized agents
- Complexity-based planning
- Create HybridExecutor - Chain ResearchExecutor → Decision → AgentExecutor
- code review feature
- ensure proper context is included with requests -- path, files, env, etc



PROBLEM: Agent has error and fails. Also, no prompt for dry run or git checkpoint. It was all autoconfirmed.

Code Agent - Task: we have endpoints for user creation in api/v1/routes.py can we add a db repository to support them?
 ------------------------------------------------------------
 ╭───── SECURITY WARNING: Auto-Confirm ─────╮
 │  AUTO-CONFIRMED                          │
 │                                          │
 │ Run in dry-run mode? (no actual changes) │
 │                                          │
 │ Phase 1 Limitation: Auto-approved.       │
 │ Manual confirmation requires Phase 3.    │
 │                                          │
 │ Review destructive operations carefully! │
 ╰──────────────────────────────────────────╯
 Create git checkpoint before running? (auto-confirmed)
 Creating git checkpoint...
 Checkpoint created: 251414a8

 Agent Configuration:
   Planner (smart tasks): cerebras
   Executor (fast tasks): cerebras
   Project root: C:\Users\anyth\MINE\dev\test_repo
   Mode: DRY RUN (no actual changes)


 Agent error: signal only works in main thread of the main interpreter

SOLUTION:

---


problem:
/cache - command output:

[36m[1m
 Cache Statistics:[0m
 [36m--------------------------------------------------[0m
 Total Entries: 0
 Exact Cache Hits: 0
 Intent Cache Hits: 0
 Cache Misses: 0
 Cache Saves: 0
 Exact Hit Rate: [33m0.0%[0m
 Intent Hit Rate: [33m0.0%[0m
 Cache File: .scrappy\response_cache.json
 Caching: [32mEnabled[0m

solution:
output existing table from Usage Summary (/usage command)

---

## Issue 5: Agent keeps trying to apply changes after user declines

**Problem:**
Agent broken if user answers no, keeps trying to apply changes.

**Root Cause:**
Need to identify the specific code path. The agent loop is in `src/agent/core.py`. When a user declines an action in the approval flow, the agent may not be properly handling the rejection state and continues attempting the same action.

**Status:** NEEDS REPRODUCTION
- Awaiting reproduction steps from testing

**Solution:**
Research agent routing in `src/agent/core.py` to understand the approval loop and add proper exit conditions when user declines.

**Files:**
- `src/agent/core.py` - Agent main loop
- `src/cli/agent_manager.py` - Agent execution wrapper