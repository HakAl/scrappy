## Issues

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

Ship **Todo (Planning)**, **Semantic Search (Context)**, and the **Test Runner (Verification)**, you have a complete "Agentic Loop."

*   **Plan:** "I know what to do."
*   **Search:** "I found the code to change."
*   **Test:** "I proved that my changes work."

That is the "Holy Trinity" of a coding assistant.

However, "Feature Complete" is not the same as "Release Ready." Since you are looking to release this (even if just to friends or open source), here are the **3 boring things** you need to wrap around those features to make it actually usable by others.

### The "Onboarding" Experience (The Setup)
You know how to run your app because you have your `.env` file set up and your Python environment perfect. A new user does not.

*   **The Config Command:** You need a `my-cli init` or `configure` command.
    *   Don't make them manually edit a `.env` file.
    *   Prompt them: "Enter your API Key:" -> Save it securely (or to `~/.my_cli_config`).
    *   Prompt them: "Select your model (GPT-4o, Claude 3.5, etc)."
*   **The Dependency Check:**
    *   When the app starts, check if `git` is installed. Check if `pytest` or `npm` is available (for the test runner). Fail gracefully if they aren't.

**Bad UX:**
`Loading AI models... (10 seconds)` -> `Error: No API Key found.`

**Good UX:**
```python
# main.py
def main():
    # 1. Fast check (read .env or config file)
    if not has_api_key():
        print("Welcome! Let's set up your API keys.")
        setup_wizard() # input() loop -> save to file
        print("Setup complete! Initializing engine...\n")

    # 2. ONLY NOW import the heavy stuff
    from my_app.heavy_engine import Agent 
    # ...
```

This makes the CLI feel snappy and respectful of the user's time.

### The "Safety" Rails (Crucial for Release)
You are giving an LLM access to the file system and shell. If you release this, you are liable (socially, if not legally) if it deletes someone's project.

*   **The "Y/N" Gate:**
    *   For the **Test Runner** and **Shell Commands**: **Default to "Ask User" mode.**
    *   *Agent:* "I want to run `rm -rf ./temp_build`."
    *   *App:* "Allow? [y/N]"
    *   *Config:* Allow power users to set `--auto-approve` flag, but **never** make it default.
*   **The "System Ignore":**
    *   Hardcode a block on modifying `.git/` folder contents directly. You don't want the LLM corrupting the git index.
*   * Disclaimers!

### The "Help" & "Status" (UX)
With the **Todo Tool** running, the agent has invisible state. Users will get confused.

*   **Visibility:**
    *   When the agent is in "Planning Mode," the CLI prompt should look different.
    *   *Normal:* `>>>`
    *   *Agent Mode:* `(Plan: 2/5) >>>`
*   **The "Reset" Button:**
    *   Users *will* get stuck in a bad plan loop.
    *   Ensure you have a command like `/clear` or `/reset` that wipes the `TODO.md` and memory context without crashing the app.

### A Note on Tool #3 (Test Runner vs DB)
Just to clarify: I am assuming by "1, 2, 3" you adopted the priority list of **Todo / Semantic / Test Runner**.

If you meant your *original* list where #3 was the **Database Tool**:
**Swap it.**
*   A **Test Runner** is essential for 100% of developers.
*   A **Database Tool** is useful for maybe 30% of tasks, and it introduces massive setup friction (connection strings, tunnels, etc.).

**Release with the Test Runner.** It closes the loop.

### Final "Pre-Job" Checklist
You start next week. Don't burn out trying to make it perfect.
1.  **Todo Tool:** Working + saves to `.md` file.
2.  **Semantic Search:** Working (using your Priority Queue / Background indexing).
3.  **Test Runner:** Keep it simple. Just run a shell command and capture `stdout/stderr`. Don't try to parse XML reports yet.
4.  **README:** Write 3 sentences on how to use the "Agent" mode.

Good luck! Shipping a working agent CLI is a massive achievement.


---


Including Test Runner with the TODO feature, here is a specific piece of advice on how to make those two work 
together to actually "close the loop."

### The "Definition of Done" Pattern

The biggest mistake agents make is assuming they are done because they finished writing the code. They often forget to check if it actually runs.

You should "include" the Test Runner in the Todo feature by **biasing the Planner to always add a verification step.**

**1. The Implicit Prompting Strategy**
When the user asks the agent to create a plan (or when your classifier triggers it), inject a rule into the `create_plan` system prompt:

> "Every plan must end with a 'Verification' step. If the user did not provide a specific test, your last step must be to run existing tests or create a minimal reproduction script to verify the changes."

**2. The "Refusal to Exit" Logic**
In your agent loop, if the agent tries to mark the final task as `[x] Done` but has *not* called the `test_runner` tool in the conversation history:

*   **Intercept the action.**
*   **System Response:** "You are trying to complete the plan, but you haven't run any tests to verify your changes. Please run the `test_runner` or explain why verification is unnecessary."
