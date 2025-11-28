# TODO Tool 

### 1. Objective
Enable the agent to maintain a persistent state of its progress.
This is critical for complex refactors or multi-file features where the agent often "forgets" what it has already done
or what step comes next.

### 2. Storage Strategy
*   **File-Based Persistence:** Store tasks in a file named `.scrappy/.todo.md`.
*   **Format:** Standard Markdown checkbox syntax. This allows both the Agent (via tools) and the User (via IDE) to read/edit the file without conflict.
    ```markdown
    # Agent Tasks
    - [x] Analyze project structure
    - [ ] Create database schema
    - [ ] Write API endpoints
    ```

### 3. Location
*   **New File:** `agent_tools/tools/task_tools.py`

### 4. Tool Specifications

We will implement three specific tools to manage the lifecycle of tasks.

#### Tool A: `AddTaskTool`
*   **Name:** `add_task`
*   **Description:** "Add a new task to the plan."
*   **Parameters:**
    *   `task` (str): Description of the task.
    *   `priority` (str, optional): 'high', 'medium', 'low' (could prepend an emoji like 🔴, 🟡, 🔵).
*   **Logic:**
    1.  Check if `.agent_tasks.md` exists; create if not.
    2.  Append a new line: `- [ ] {task}`.
    3.  Return success with the current count of pending tasks.

#### Tool B: `ListTasksTool`
*   **Name:** `list_tasks`
*   **Description:** "View the current task list with status and IDs."
*   **Parameters:**
    *   `status` (str, optional): 'all', 'pending', 'completed'. Default: 'all'.
*   **Logic:**
    1.  Read `.agent_tasks.md`.
    2.  Parse lines starting with `- [ ]` or `- [x]`.
    3.  **Crucial Step:** Assign a temporary "ID" (index) to each task based on its line number or list position so the agent can reference it later.
    4.  Format output:
        ```text
        1. [x] Analyze project structure
        2. [ ] Create database schema
        ```
    5.  Return the formatted string.

#### Tool C: `UpdateTaskTool`
*   **Name:** `update_task`
*   **Description:** "Mark a task as complete or update its description."
*   **Parameters:**
    *   `task_id` (int): The index of the task (from `list_tasks`).
    *   `status` (str, optional): 'todo' or 'done'.
    *   `new_description` (str, optional): If provided, rewrites the text.
*   **Logic:**
    1.  Read the file into memory.
    2.  Identify the line corresponding to `task_id`.
    3.  Modify the line (change `[ ]` to `[x]` or update text).
    4.  Write back to file (atomic write preferred).

### 5. Implementation Logic Details

#### Helper: The Task Parser
You will need a private helper method `_parse_todo_file(path)` inside `task_tools.py` to robustly handle the file I/O.

*   **Handling User Edits:** Since the user might edit the markdown file manually, the parser needs to be forgiving (e.g., handle extra whitespace, different bullet characters like `*` or `-`).

#### Step-by-Step Execution Plan

1.  **Safety Check:** Use `context.project_root` for all file operations.
2.  **Concurrency:** While full file locking is overkill, ensure you read-modify-write in a single execution block to minimize race conditions if the user is typing in the file simultaneously.
3.  **Context Injection:** (Optional but recommended) In your main agent loop, you might want to automatically run `list_tasks` invisibly at the start of a session so the agent knows where it left off.

### 6. Edge Cases & Handling

*   **File Deletion:** If `.scrappy/.todo.md` is deleted by the user, `list_tasks` should return "No active plan found."
*   **Invalid IDs:** If the agent tries to update Task #5 but only 3 exist, return a descriptive error: "Task ID 5 not found. Please run list_tasks to see current IDs."
*   **Empty Tasks:** Reject empty strings in `add_task`.

### 7. Proposed "System Prompt" Addition
Once implemented, you will need to update your Agent's system prompt to encourage usage:

> "When starting a complex request, first use `add_task` to create a plan. As you complete steps, use `update_task` to mark them done. This helps you stay on track if an error occurs."

### 8. Draft Implementation Snippet (The "meat" of the logic)

This logic handles the tricky part of modifying a specific line based on an index.

```python
def _update_task_line(lines: list[str], index: int, status: str = None) -> list[str]:
    """
    Updates the specific task in the list of lines.
    index is 1-based index of the *task*, not necessarily the file line number.
    """
    task_count = 0
    new_lines = lines.copy()
    
    for i, line in enumerate(new_lines):
        clean = line.strip()
        if clean.startswith('- [ ]') or clean.startswith('- [x]'):
            task_count += 1
            if task_count == index:
                # Found the target
                if status == 'done':
                    new_lines[i] = line.replace('[ ]', '[x]', 1)
                elif status == 'todo':
                    new_lines[i] = line.replace('[x]', '[ ]', 1)
                return new_lines
                
    raise IndexError(f"Task ID {index} not found")
```