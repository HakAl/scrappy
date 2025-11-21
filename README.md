# Scrappy: The Free AI Coding Assistant

A powerful, context-aware coding assistant for everyone—students, learners, and developers who can't afford paid AI subscriptions.

> "For Users Without Claude Subscription: Yes, Useful"

This tool combines the power of multiple free-tier LLM APIs to give you **23,000+ free, context-aware AI requests per day**. No credit card, subscriptions, or geographic restrictions.

### The Mission: AI for Everyone

Paid AI tools like ChatGPT Plus ($20/month) and Claude Pro ($20/month) are fantastic, but their cost creates a barrier for:
*   **Students** learning to code.
*   **Developers** in regions where $20 is significant or payments are blocked.
*   **Anyone** on a tight budget who wants to build and learn.

Scrappy exists to make powerful AI coding assistance accessible to anyone, anywhere.

---

## Quick Start (5 Minutes)

Get up and running with AI-powered coding assistance in your own terminal.

**1. Install the Tool**
Clone the repository and install the command-line tool.
```bash
git clone https://github.com/HakAl/scrappy
cd scrappy
pip install -e .
```

**2. Get Your Free API Keys**
You need at least **one** of the following (getting all three is recommended for maximum requests). All are free and require no credit card.

| Provider | How to Get Key                               | Daily Limit     |
| :---     | :---                                         | :---            |
| **Cerebras** | [cloud.cerebras.ai](https://cloud.cerebras.ai) → Sign up → Copy key     | 14,400 requests |
| **Groq**     | [console.groq.com](https://console.groq.com) → Sign up → API Keys | 7,000+ requests |
| **Gemini**   | [aistudio.google.com](https://aistudio.google.com) → Get API Key      | 1,650 requests  |

**3. Set Your API Keys**
You can set them as environment variables or place them in a `.env` file in the project root.

```bash
# Option A: Environment Variables (Recommended)
export CEREBRAS_API_KEY=your_key_here
export GROQ_API_KEY=your_key_here
export GEMINI_API_KEY=your_key_here

# Option B: Create a .env file in the scrappy directory
# CEREBRAS_API_KEY=your_key_here
# GROQ_API_KEY=your_key_here
```

**4. Start Coding with AI!**
Navigate to any of your coding projects and run the assistant. It will automatically learn about your codebase.

```bash
cd ~/path/to/your-project
scrappy --auto-explore
```

You can now ask questions, plan features, or even have the AI write code for you.

---

## Real-World Examples

**Example 1: Understand Existing Code**
Ask a question about your project, and get an answer based on your actual code.
```
You: Explain how authentication works in this app.

AI: [Reads your codebase automatically]
Your app uses JWT tokens stored in localStorage. The main logic is in `src/auth/jwt.js`, where the `createToken` function is called after a successful login in the `src/controllers/userController.js` file...
```

**Example 2: Let the AI Write Code (Safely)**
Use the `/agent` command to give the AI a task. You approve every step.
```
You: /agent Add input validation to my signup form

Code Agent - Task: Add input validation to my signup form
------------------------------------------------------------
Run in dry-run mode? [y/N]: n
Create git checkpoint before running? [Y/n]: y
Checkpoint created: a1b2c3d4

Agent wants to: read_file
Parameters: {"path": "src/views/signup.js"}
...
Agent wants to: write_file
Parameters: {"path": "src/views/signup.js", "content": "..."}
Allow? [y/N]: y

Task completed in 3 iterations!
```

---

## Key Features

This isn't just a simple wrapper around APIs. It's a smart, resilient system.

*   **23,000+ Free Requests/Day**: Combines multiple providers for a massive daily quota.
*   **Automatic Codebase Context**: Automatically explores your project to provide context-aware answers.
*   **Task-Aware Routing**: Intelligently routes simple tasks to fast models (Cerebras) and complex tasks to quality models (Gemini, Llama-3 70B).
*   **Code Agent**: AI writes and modifies code with a human-in-the-loop for approval, ensuring safety.
*   **Safety First**: Features Git checkpoints for easy rollbacks, sandboxing, audit logs, and a dry-run mode.
*   **Swappable "Brain"**: You can choose which LLM acts as the primary orchestrator (no Claude subscription required).
*   **Resilient & Redundant**: Automatically falls back to other providers if one hits a rate limit or fails.
*   **Response Caching**: Saves your quota and provides instant responses for repeated queries.
*   **Session Persistence**: Resume your conversations and context exactly where you left off.

---

## Smart Codebase Understanding

Scrappy automatically understands your codebase through **semantic search**. When you ask a question, it finds the most relevant code to answer you - no configuration needed.

### How It Works

1. **First Run**: Scrappy scans and indexes your project (30-60 seconds for large codebases)
2. **Subsequent Runs**: Only changed files are re-indexed (fast)
3. **Query Time**: AI-powered vector search finds relevant code chunks

### Features

- **Semantic search**: Finds code by meaning, not just keywords
- **Hybrid search**: Combines vector similarity with keyword matching
- **Incremental updates**: Only re-indexes changed files
- **Fully automatic**: Works out of the box, no extra steps

### What Gets Indexed?

- All source code files in your project
- Configuration files (package.json, requirements.txt, etc.)
- Documentation files (README, etc.)

The index is stored locally in `.lancedb/` and never leaves your machine.

## Who Is This For?

| ✅ Perfect for:                                                               | ⚠️ Maybe not for:                                                     |
| :---                                                                          | :---                                                                      |
| **Students** learning to code without expensive subscriptions.                | **Large enterprises** needing paid SLAs and guaranteed 24/7 uptime.         |
| **International developers** in regions with payment restrictions.            | **Users who already pay for** and are happy with Claude Pro / GPT-4.    |
| **Beginners** who want clear explanations and working code examples.          | **Production-critical applications** where free-tier reliability is a concern. |
| **Hobbyists & tinkerers** building projects without API costs.                |                                                                           |

---

## Command-Line Interface (CLI)

You can use `scrappy` for quick, one-shot commands or in a persistent, interactive session.

#### **Starting an Interactive Session**
```bash
# Start and auto-explore the current directory
scrappy --auto-explore

# Resume your last session (history and context are saved)
scrappy --resume

# Start with a specific provider as the main "brain"
scrappy --brain groq
```

#### **Interactive Commands**
Once inside a session, use these commands:
```
You: /help              # Show all commands
You: /agent <task>       # Run the code agent with human approval
You: /plan <task>        # Create a structured, step-by-step plan for a task
You: /reason <question>  # Get a deep analysis of a technical question
You: /explore [path]     # Explore and learn a codebase
You: /context            # View what the AI knows about your project
You: /status             # Check provider status and usage stats
You: /quit               # Exit the session
```

#### **One-Shot Commands**
```bash
# Ask a quick question with codebase context
scrappy query "How should I fix the auth bug?" --with-context

# Plan a feature without starting a session
scrappy plan "Build a REST API with authentication"

# Let the agent work on a task directly
scrappy agent "Add a health check endpoint to the Flask app" --dry-run
```
For a full command reference, see the [CLI Documentation](docs/CLI.md).

---

## Common Questions

*   **Q: Is this really free?**
    *   **A:** Yes. It orchestrates the generous free tiers offered by AI providers. No credit card is needed to sign up for their keys.

*   **Q: What if a free tier disappears?**
    *   **A:** The system is designed to be modular. It's easy to add new providers as they become available. As long as *any* free tier exists, this tool will work.

*   **Q: Will my code be kept private?**
    *   **A:** Your code never leaves your machine. Only the prompts (which may include snippets of your code for context) are sent to the AI providers. Please review the privacy policies of the providers you use.

*   **Q: What languages does it support?**
    *   **A:** It is language-agnostic and works with any codebase: Python, JavaScript, Java, Go, Rust, etc.

---

## Technical Details

<details>
<summary><b>Click to expand Architecture and Advanced Usage</b></summary>

The system uses a `TaskRouter` to classify user input and route it to the most efficient execution strategy.

*   **Simple commands** (`pip install...`) → `DirectExecutor` (no LLM)
*   **Research questions** (`explain this...`) → `ResearchExecutor` (fast, read-only LLM)
*   **Code generation** (`implement...`) → `AgentExecutor` (quality LLM with planning and human approval)

This ensures that simple tasks are instant and free, while complex tasks use the best available model without wasting your quota.

For more information, please see the detailed documentation:
*   [Architecture Deep Dive](docs/ARCHITECTURE.md)
*   [Task Routing Logic](docs/task_routing.md)
*   [Rate Limit Strategy](docs/RATE_LIMIT.md)

</details>

---

## License
This project is licensed under the **MIT License**. Use it, modify it, and share it to help others access modern AI tools.

If this project helps you, please give it a ⭐ on GitHub so others can discover it