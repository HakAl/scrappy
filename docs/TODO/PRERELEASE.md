# (Features for Release)

Ship **Todo (Planning)**, **Semantic Search (Context)**, and the **Test Runner (Verification)**, you have a complete "Agentic Loop."

*   **Plan:** "I know what to do."
*   **Search:** "I found the code to change."
*   **Test:** "I proved that my changes work."

That is the "Holy Trinity" of a coding assistant.

However, "Feature Complete" is not the same as "Release Ready." 
Since you are looking to release this (even if just to friends or open source), here are the **3 boring things** you need to wrap around those features to make it actually usable by others.

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

## Additional Ideas (Claude's Notes)

### Graceful Degradation
What happens when the API is down, rate-limited, or returns garbage? Users will blame your tool, not OpenAI.
- Retry with exponential backoff
- Clear error messages: "OpenAI returned 429. Waiting 30s..." vs "Error: Unknown"
- Offline mode for semantic search (local embeddings only)

### Session Persistence
Users will close the terminal mid-task. Can they resume?
- Auto-save conversation state to `.scrappy/session.json`
- `scrappy resume` command
- Clear "session expired" vs "session resumed" messaging

### Audit Log
For trust and debugging:
- Log every file modification with before/after hashes
- Log every shell command with exit code
- `scrappy history` to view recent actions
- This also helps users report bugs with context

### Cost Tracking
Users will want to know:
- Token usage per session
- Estimated cost (even rough)
- "This session used ~15k tokens (~$0.02)" at exit

### Interrupt Handling
What happens when users hit Ctrl+C mid-operation?
- Clean shutdown, not stack trace
- Save partial state if possible
- "Operation cancelled. Your work has been saved."

### Version Compatibility Check
- Check if user's config file schema matches current version
- Migrate old configs gracefully
- Warn if using deprecated settings

### Dry Run Mode
- `--dry-run` flag that shows what would happen without doing it
- Especially valuable for shell commands and file modifications
- Builds trust with new users

### Priority Order (If Time-Limited)

1. **Safety rails** (Y/N gate, .git protection) - Required
2. **Config command** - Required
3. **Interrupt handling** - Required (users WILL hit Ctrl+C)
4. **Audit log** - High value for trust/debugging
5. **Session persistence** - Nice to have
6. **Cost tracking** - Nice to have
7. **Dry run** - Nice to have


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
