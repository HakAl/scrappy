# **"Seamless Escalation."**

Instead of forcing the user to decide "Is this an `/agent` task or a simple chat?", 
your classifier makes that decision. The `todo_tool` becomes the mechanism that powers the "Complex" branch of your flow.

Here is how I would architect this integration:

### The "Seamless Escalation" Workflow

You don't need a separate "feature"; you need a branching logic path based on your classifier.

**1. The User Input**
> User: "Read through the codebase and implement a new Redis caching layer for the user endpoints."

**2. The Classifier (The Router)**
Your system analyzes the prompt.
*   **If Simple:** Route to standard `chat` loop.
*   **If Complex:** Route to `agent_loop` (Planning Mode).

**3. The Agent Loop (Powered by `todo_tool`)**
Once the classifier routes to "Complex," the system strictly enforces the `todo_tool` workflow:

*   **Step 1 (Mandatory):** The Agent *must* call `todo_tool.create_plan()` before doing anything else.
*   **Step 2 (Execution):** The Agent enters the loop, executing steps and calling `todo_tool.mark_done()`.
*   **Step 3 (Visibility):** Because this is happening automatically, the Agent should print the plan to the console so the user knows *why* the response isn't immediate.

### Why this is better than a manual `/agent` command

1.  **Lower Cognitive Load:** The user doesn't have to guess if a task is too big for the LLM's context window. The system protects itself by creating a plan automatically when it detects complexity.
2.  **Recovery:** If the classifier is wrong and the task is actually huge, the `todo_tool` saves you. If the classifier is wrong and the task is tiny, the overhead of making a 1-item todo list is negligible.

### Implementation Detail: The "Plan Artifact"

Since this triggers automatically, you need to decide where the plan lives.

**Recommendation:**
When the classifier triggers the `todo_tool`, create a temporary file (e.g., `.cursor_plan.md` or `.agent_todo.md`) in the root.

*   **User Feedback:** "I see you asked for a Redis integration. That's a complex task. I've created a plan in `.agent_todo.md` and I'm starting on item 1."

### Revised Architecture Diagram

```text
User Input
    │
    ▼
[Classifier] ───(Simple)───▶ Standard Chat (No overhead)
    │
    │ (Complex)
    ▼
[Agent Mode Initialization]
    │
    ├──▶ Check: Does a plan already exist?
    │       │
    │       ├──(No)──▶ Force Tool: `todo_tool.create_plan()`
    │       │
    │       └──(Yes)──▶ Load Plan
    ▼
[Execution Loop]
    │
    ├──▶ Tool: `file_ops`, `python`, etc.
    │
    └──▶ Tool: `todo_tool.update()` (Required to proceed)
```

### Summary
1.  **Don't make it a separate command.** Use your classifier to trigger it.
2.  **Integrate `todo_tool` as the "State Machine"** for the complex path.
3.  **Keep `/agent` as an override.** Keep the manual command just in case the classifier creates a false negative (thinks a task is simple when you know it's hard), allowing you to force the planning mode.