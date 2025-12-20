# **Test Runner Tool**

## Status: IMPLEMENTED

See `src/scrappy/agent_tools/tools/testing_tools.py`

**What was built:**
- Tool name: `run_tests`
- Parameter: `command` (str, default: `pytest -v`) - agent provides full command
- Security: Uses `CommandSecurity` for validation (no framework auto-detection)
- Output: Smart truncation (1000 head + 3000 tail if > 4000 chars)
- Tests: 20 tests in `tests/agent_tools/test_testing_tools.py`

**Deferred:** Context priming for test config (scrappy-982)

---

### 1. Objective (Original Spec)
Create a tool (`run_tests`) that allows the LLM to execute project tests.
It needs to be smart enough to detect the test framework (pytest/unittest)
but flexible enough to run specific test files or filtered cases (essential for the debugging loop).

### 2. Location & Dependencies
*   **New File:** `agent_tools/tools/testing_tools.py`
*   **Inheritance:** Inherit from `ToolBase` (from `tools/base.py`).
*   **Key Component:** Utilize `components/subprocess_runner.py` for the actual execution to ensure consistent timeouts, environment variable handling, and signal safety.

### 3. Tool Specification (The "API")
This defines what the LLM "sees" and how it interacts with the tool.

**Name:** `run_tests`
**Description:** "Executes the test suite. Can run full suite, specific files, or filter by pattern."

**Parameters:**
1.  **`path`** (`Optional[str]`):
    *   Target file or directory relative to project root.
    *   *Use case:* Agent modified `login.py`, so it requests to run `tests/test_login.py`.
2.  **`pattern`** (`Optional[str]`):
    *   Keyword matching for test names (equivalent to `-k` in pytest).
    *   *Use case:* Agent wants to run only the `test_password_hashing` function.
3.  **`framework`** (`Optional[str]`):
    *   Manual override (e.g., "pytest", "unittest", "npm").
    *   *Default:* "auto" (autodetect).

### 4. Implementation Logic Flow

#### Step A: Security & Validation
*   **Path Check:** Use `context.is_safe_path(path)` (just like in `ReadFileTool`) to prevent the agent from trying to test files outside the workspace.
*   **Injection Check:** If you aren't using `shlex` or a list-based subprocess call in `subprocess_runner.py`, validate the `pattern` string to ensure no shell injection chars (`;`, `|`, `&`) are present.

#### Step B: Framework Detection Strategy
Implement a private helper method `_detect_framework(root_path)`.
1.  **Check 1:** Existence of `pytest.ini`, `conftest.py`, or `pyproject.toml` (containing `[tool.pytest]`) -> **Return 'pytest'**.
2.  **Check 2:** Existence of `package.json` -> **Return 'npm'** (future proofing).
3.  **Fallback:** Default to `unittest` (standard library) if Python files exist but no pytest config is found.

#### Step C: Command Construction
Map the abstract parameters to concrete shell commands.
*   **For Pytest:**
    *   Base: `['pytest']`
    *   If `path`: Append path.
    *   If `pattern`: Append `['-k', pattern]`
    *   Flags: Always add `-v` (verbose) so the LLM sees *which* tests passed/failed.
*   **For Unittest:**
    *   Base: `['python', '-m', 'unittest']`
    *   If `path`: Append path.
    *   Limitations: Unittest doesn't have a simple native `-k` equivalent in older versions, so `pattern` might need to filter `path` or be ignored with a warning.

#### Step D: Output Handling (Critical for LLMs)
Raw test output can be massive. You need a sanitation layer before returning `ToolResult`.
1.  **Truncation:** Define a `MAX_OUTPUT_CHARS` (e.g., 4000). If the output is larger, keep the **head** (summary of collected tests) and the **tail** (the failure summary/traceback). The middle passing tests are noise.
2.  **Strip ANSI:** If your `subprocess_runner` captures color codes, strip them. LLMs process raw text better without `\x1b[31m` clutter.

### 5. Integration Plan
1.  **Draft the Tool:** Create `testing_tools.py` implementing the logic above.
2.  **Register:** Add the new tool to `agent_tools/tools/registry.py` (or `registry_factory.py`).
3.  **Config:** Update your agent config to include a `test_timeout` setting (default to ~30-60s) to prevent infinite loops from hanging the agent.

### 6. Edge Cases to Handle
*   **Missing Dependencies:** If `pytest` is detected but not installed in the environment, the tool should catch the `CommandNotFound` error and return a helpful message: *"Pytest configuration detected, but 'pytest' command not found. Do I need to install dependencies?"*
*   **Flaky Tests:** The tool generally reports what happened. No special retry logic needed for V1.
*   **Hanging Tests:** Rely on the `subprocess_runner` timeout mechanism.
