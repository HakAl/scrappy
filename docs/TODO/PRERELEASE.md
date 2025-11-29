# (Features for v1.0 Release)
```
  PRERELEASE.md vs Actual State

  The "Holy Trinity"

  | Feature           | Status          | Details
                                                 |
  |-------------------|-----------------|---------------------------------------------------------------------------
  -----------------------------------------------|
  | Plan (Todo Tool)  | NOT IMPLEMENTED | No add_task, list_tasks, update_task tools exist. No .scrappy/.todo.md
  persistence.                                      |
  | Search (Semantic) | IMPLEMENTED     | LanceDB + fastembed, incremental indexing, hybrid search - all working
                                                 |
  | Test Runner       | PARTIAL         | command_tool.py can run shell commands (including pytest), but no
  dedicated test_runner tool with verification semantics |

  Onboarding Experience

  | Feature                        | Status          | Details                                               |
  |--------------------------------|-----------------|-------------------------------------------------------|
  | Config command (scrappy init)  | NOT IMPLEMENTED | No init or configure command in commands.py           |
  | Dependency check (git, pytest) | NOT IMPLEMENTED | App starts without checking                           |
  | Fast startup / lazy imports    | PARTIALLY       | .env loads early, but no explicit "setup wizard" flow |

  Safety Rails

  | Feature                    | Status          | Details
           |
  |----------------------------|-----------------|------------------------------------------------------------------
  ---------|
  | Y/N confirmation gate      | IMPLEMENTED     | SafetyChecker + ActionExecutor - unsafe actions require
  confirmation      |
  | .git protection            | PARTIAL         | CommandSecurity blocks rm -rf / patterns, but no explicit .git/
  blocklist |
  | Dangerous command patterns | IMPLEMENTED     | Fork bombs, sudo rm, format C:, etc. blocked
           |
  | Disclaimers                | NOT IMPLEMENTED | No visible disclaimers
           |

  Help & Status

  | Feature                           | Status          | Details                                     |
  |-----------------------------------|-----------------|---------------------------------------------|
  | /help command                     | IMPLEMENTED     | Full help with all commands                 |
  | /clear command                    | IMPLEMENTED     | Clears conversation history                 |
  | /quit, /exit                      | IMPLEMENTED     | Clean exit with session save                |
  | /plan, /agent                     | IMPLEMENTED     | Both work                                   |
  | Visual mode indicator (Plan: 2/5) | NOT IMPLEMENTED | No progress indicator in prompt             |
  | Ctrl+C handling                   | IMPLEMENTED     | KeyboardInterrupt caught in commands.py:513 |
  | Ctrl+Q                            | UNCLEAR         | Not seeing explicit binding in Textual app  |

  Agent Tools Available

  File:     ReadFileTool, WriteFileTool, ListFilesTool, ListDirectoryTool
  Git:      GitLogTool, GitDiffTool, GitBlameTool, GitShowTool, GitStatusTool, GitRecentChangesTool
  Search:   SearchCodeTool
  Web:      WebFetchTool, WebSearchTool
  Control:  CompleteTool
  Shell:    ShellCommandExecutor (run_command)
  Python:   AnalyzePythonDependenciesTool

  No: AddTaskTool, ListTasksTool, UpdateTaskTool, TestRunnerTool
```

  ---
  Realistic Assessment for v1.0

  Already Done (just verify):

  - Semantic search
  - Safety confirmation gates
  - Dangerous command blocking
  - /help, /clear, /quit, /plan, /agent
  - Ctrl+C handling
  - Session save/restore

  Quick Wins (hours, not days):

  1. Add .git/ to blocked paths - 5 lines in CommandSecurity
  2. Add disclaimer - Banner text in interactive_banner.py
  3. Verify Ctrl+Q works or add binding

  Medium Effort (1 day each):

  1. Todo Tool - 3 new tools + file persistence + prompt injection
  2. Test Runner Tool - Shell wrapper with stdout capture + "Definition of Done" logic
  3. Config command (scrappy init) - Setup wizard flow

  The "Definition of Done" Pattern

  This is the clever part from PRERELEASE.md - forcing verification before completion. Would require:
  - Tracking test_runner in conversation history
  - Intercepting complete action if no tests ran
  - Prompt injection for "every plan ends with verification"

  ---


Ship **Todo (Planning)**, **Semantic Search (Context)**, and the **Test Runner (Verification)**, you have a complete "Agentic Loop."

*   **Plan:** "I know what to do."
*   **Search:** "I found the code to change."
*   **Test:** "I proved that my changes work."

That is the "Holy Trinity" of a coding assistant.

However, "Feature Complete" is not the same as "Release Ready." 
Since you are looking to release this (even if just to friends or open source), 
here are the **3 boring things** you need to wrap around those features to make it actually usable by others.

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


**Release with the Test Runner.** It closes the loop.

### Final Pre Release Checklist
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

The biggest mistake agents make is assuming they are done because they finished writing the code. 
They often forget to check if it actually runs.

You should "include" the Test Runner in the Todo feature by **biasing the Planner to always add a verification step.**

**1. The Implicit Prompting Strategy**
When the user asks the agent to create a plan (or when your classifier triggers it), inject a rule into the `create_plan` system prompt:

> "Every plan must end with a 'Verification' step. If the user did not provide a specific test, 
> your last step must be to run existing tests or create a minimal reproduction script to verify the changes."

**2. The "Refusal to Exit" Logic**
In your agent loop, if the agent tries to mark the final task as `[x] Done` but has *not* called the `test_runner` tool in the conversation history:

*   **Intercept the action.**
*   **System Response:** "You are trying to complete the plan, but you haven't run any tests to verify your changes. 
* Please run the `test_runner` or explain why verification is unnecessary."
