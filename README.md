# Scrappy: The Free AI Coding Assistant

A powerful, context-aware coding assistant for everyone—students, learners, anyone who doesn't want to pay for subscriptions.

> "For Users Without Claude Subscription: Yes, Useful"

This tool combines the power of multiple free-tier LLM APIs to give you **23,000+ free, context-aware AI requests per day**. No credit card, subscriptions, or geographic restrictions.

### The Mission: AI for Everyone

Paid AI tools like ChatGPT Plus ($20/month) and Claude Pro ($20+/month) are fantastic, but their cost creates a barrier for:
*   **Students** learning to code. I wish this existed when I was in university, I would have had a lot more free time!
*   **Developers** in regions where $20 is significant or payments are blocked.
*   **Frugal folks** who don't like subscriptions, but like to build and learn.

Scrappy exists to make powerful AI coding assistance accessible to anyone, anywhere.

---

## Requirements

- Python 3.10+
- Git (for checkpoints and safety features)
- Windows, macOS, or Linux

## Quick Start (5 Minutes)

Get up and running with Scrappy in your terminal.

**1. Install the Tool**
```bash
# Mac/Linux
python3 -m venv venv
source venv/bin/activate

# Windows (PowerShell)
# python -m venv venv
# .\venv\Scripts\activate

pip install scrappy-ai
```

**2. Get Your Free API Keys**
You need at least **one** of the following (getting all three is recommended for maximum requests). All are free and require no credit card.

| Provider | How to Get Key                               | Daily Limit     |
| :---     | :---                                         | :---            |
| **Cerebras** | [cloud.cerebras.ai](https://cloud.cerebras.ai) → Sign up → Copy key     | 14,400 requests |
| **Groq**     | [console.groq.com](https://console.groq.com) → Sign up → API Keys | 7,000+ requests |
| **Gemini**   | [aistudio.google.com](https://aistudio.google.com) → Get API Key      | 1,650 requests  |

**3. Run the Setup Wizard**
Scrappy comes with an interactive setup wizard to get you started in seconds.

```bash
scrappy
```

The wizard will:
1.  Prompt you to paste your free API keys (saved securely locally).
2.  **Automatically download** the embedding model (BGE-Small) in the background.
3.  **Index your codebase** using LanceDB for ultra-fast retrieval.

*Note: You'll see a progress bar at the bottom of the screen. You can start chatting immediately while Scrappy indexes your code in the background!*

**4. Instant Coding**
Once configured, Scrappy will immediately start **auto-exploring** your directory.

*   **Zero-Wait:** You can start chatting right away.
*   **Background Indexing:** Scrappy uses `FastEmbed` and `LanceDB` to index your code on a background thread. Watch the status bar at the bottom for real-time progress.

---

## Supported Models & Architecture

Scrappy uses a "Mixture of Providers" strategy. Instead of relying on one expensive model, it dynamically routes tasks to the best free-tier model for the job.

### 1. The Heavy Lifters (High Volume & Speed)
These providers power the core of Scrappy, handling the bulk of agent loops, refactoring, and general chat.

| Provider | Key Models | Why we use it |
| :--- | :--- | :--- |
| **Cerebras** | **Llama 3.3 70B**, **Qwen 3 32B**, **Llama 3.1 8B**<br>*(Plus Qwen-3-235B Instruct)* | **Incredible Speed.** With ~14,400 requests/day and ultra-fast inference, this is the default engine for the "Agent" loop, allowing it to iterate on code rapidly without hitting limits. |
| **Groq** | **Llama 3.3 70B**, **Mixtral 8x7B**, **Llama 4 Scout**<br>*(Plus Kimi-k2-instruct)* | **Low Latency.** Groq provides near-instant responses. We use the 70B Versatile models for complex reasoning tasks that require more intelligence than the 8B models can provide. |
| **Google** | **Gemini 2.5 Flash**, **Gemini 2.0 Flash-Exp** | **Huge Context.** When you need to analyze multiple files or large documentation, Scrappy routes to Gemini. It handles large context windows better than Llama-based models. |

### 2. The Specialists (High Intelligence / Specific Tasks)
Scrappy also integrates specialized providers for hard reasoning problems or "second opinions."

*   **GitHub Models:** Includes access to **GPT-4o**, **DeepSeek-R1** (Reasoning), and **Phi-4**.
    *   *Limitation:* These are strictly for **Chat/Query** mode. Due to strict Rate Limits (TPM/RPM), they cannot be used for the autonomous `agent` loop.
*   **Cohere:** Integrated but currently inactive by default due to low free-tier quotas.

### 3. Model Routing Logic
You don't need to manually switch models (though you can). Scrappy classifies your intent:

1.  **"Fix this function"** $\rightarrow$ **Cerebras (Llama 3.1 8B)**
    *   *Reason:* Fast, cheap, and capable enough for small logic changes.
2.  **"Plan a new architecture for my app"** $\rightarrow$ **Groq (Llama 3.3 70B)** or **Gemini 2.5**
    *   *Reason:* Requires high-level reasoning and instruction following.
3.  **"Explain how this entire module works"** $\rightarrow$ **Gemini 2.0 Flash**
    *   *Reason:* Needs a massive context window to read all the files.
4.  **"Why is this logic failing?" (Hard Logic)** $\rightarrow$ **DeepSeek-R1 (via GitHub)**
    *   *Reason:* Specialized reasoning model required.

---

## Real-World Examples

**Example 1: Understand Existing Code**
Ask a question about your project, and get an answer based on your actual code.
```
> Explain how authentication works in this app.

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
*   **Conversation Memory**: Automatically remembers conversations across sessions. Just run `scrappy` and pick up where you left off.
*   **Semantic Code Search**: Find code by meaning, not just text. Ask "where is authentication handled?" and get relevant results.
*   **Local & Fast Indexing**: Uses **LanceDB** and **FastEmbed** to index your code locally. No vector databases to manage, no heavy PyTorch dependencies, and your code structure never leaves your machine. 
*   **Codebase Context**: Explores your project to provide context-aware answers.
*   **Task-Aware Routing**: Intelligently routes simple tasks to fast models (Cerebras) and complex tasks to quality models (Gemini, Llama-3 70B).
*   **Code Agent**: AI writes and modifies code with a human-in-the-loop for approval, ensuring safety.
*   **Safety First**: Features Git checkpoints for easy rollbacks, sandboxing, audit logs, and a dry-run mode.
*   **Swappable "Brain"**: You can choose which LLM acts as the primary orchestrator (no Claude subscription required).
*   **Resilient & Redundant**: Automatically falls back to other providers if one hits a rate limit or fails.
*   **Response Caching**: Saves your quota and provides instant responses for repeated queries.

### Roadmap

* Todo/Planning tool for structured task management
* Test runner integration with verification loop
* Episodic memory for long conversation recall

---

## Who Is This For?

| Perfect for:                                                                | Maybe not for:                                                                |
|:-----------------------------------------------------------------------------|:-------------------------------------------------------------------------------|
| **Students** learning to code without expensive subscriptions.               | **Large enterprises** needing paid SLAs and guaranteed 24/7 uptime.            |
| **International developers** in regions with payment restrictions.           | **Users who already pay for** and are happy with Claude Pro / GPT-4.           |
| **Beginners** who want clear explanations and working code examples.         | **Production-critical applications** where free-tier reliability is a concern. |
| **Hobbyists & tinkerers** building projects without API costs.               |                                                                                |

---

## Command-Line Interface (CLI)

You can use `scrappy` for quick, one-shot commands or in a persistent, interactive session.

#### **Starting an Interactive Session**
```bash
# Start interactive mode (conversations auto-load from previous sessions)
scrappy

# Start and auto-explore the current directory
scrappy --auto-explore

# Start with a specific provider as the main "brain"
scrappy --brain groq
```

> **Note:** Conversations are automatically saved and restored. Just run `scrappy` in any project directory and your previous context loads automatically.

#### **Interactive Commands**
Once inside a session, use these commands:
```
You: /help              # Show all commands
You: /agent <task>      # Run the code agent with human approval
You: /plan <task>       # Create a structured, step-by-step plan
You: /explore [path]    # Explore and learn a codebase
You: /history [n]       # Show last n messages (default: 10)
You: /limits            # Check rate limit status across providers
You: /context           # View what the AI knows about your project
You: /clear             # Clear conversation history
You: /quit              # Exit the session
```

#### **One-Shot Commands**
```bash
# Explore a codebase (no interactive session)
scrappy explore

# Ask a quick question with codebase context
scrappy query "How should I fix the auth bug?" --with-context

# Plan a feature without starting a session
scrappy plan "Build a REST API with authentication"

# Let the agent work on a task directly
scrappy agent "Add a health check endpoint to the Flask app" --dry-run
```

For a full command reference, see the [CLI Documentation](docs/CLI.md).

To customize themes, display settings, and behavior, see the [Customization Guide](docs/CUSTOMIZATION.md).

---

## Common Questions

*   **Q: Is this really free?**
    *   **A:** Yes. It orchestrates the generous free tiers offered by AI providers. No credit card is needed to sign up for their keys.

*   **Q: What if a free tier disappears?**
    *   **A:** The system is designed to be modular. It's easy to add new providers as they become available. As long as *any* free tier exists, this tool will work.

*   **Q: Will my code be kept private?**
    *   **A:** Scrappy has no servers. However, necessary code snippets are sent to the third-party LLM providers (Cerebras/Groq/Google, etc.) to generate answers. Check their privacy policies regarding data training.

*   **Q: What languages does it support?**
    *   **A:** It is language-agnostic and works with any codebase: Python, JavaScript, Java, Go, Rust, etc.

*   **Q: Does Scrappy work offline?**
    *   **A:** The chat requires an internet connection to reach the LLM providers. However, the code indexing and search happen entirely **offline** on your device after the initial 20MB model download.

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
*   [Task Routing Logic](docs/TASK_ROUTING.md)
*   [Rate Limit Strategy](docs/RATE_LIMITS.md)

</details>

---

## Disclaimer

Use at your own risk. Be smart: create a branch or work from a clean git state with no uncommitted changes so you can quickly revert.

Best practices:
- Don't give code agents a shell with admin access
- Use dry-run mode or git checkpoints

---

## License
This project is licensed under the **MIT License**. Use it, modify it, and share it to help others access modern AI tools.

If this project helps you, please give it a star on GitHub so others can discover it.