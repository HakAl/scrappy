# Multi-Provider LLM Agent Team

A framework for orchestrating LLM agents across multiple free-tier providers with **swappable orchestrator brain** and **automatic codebase context awareness**.

>"For Users Without Claude Subscription: Yes, Useful"


**Where it shines:**

  1. 23K free requests/day - Real value for development without subscription costs
  2. Context augmentation - Makes weaker models more effective by injecting project knowledge they'd otherwise lack
  3. Structured workflows - /plan and /reason provide organized thinking patterns
  4. Redundancy - Multiple providers mean no single point of failure
  5. Interactive exploration - Good for learning codebases, brainstorming, getting quick answers


## Features

- **23,000+ free requests/day** across providers
- **Task-Type Aware Routing** - automatically routes tasks to optimal execution strategies
- **Dynamic Provider Selection** - uses fast providers (Cerebras) for simple tasks, quality providers (Gemini 70B) for complex ones
- **Session Persistence** - save and resume sessions with conversation history, working memory, and context
- **Response Caching** - avoid duplicate API calls, save quota, instant responses for repeated queries
- **Code Agent** - AI writes code with human-in-the-loop approval (uses Gemini for smart tasks)
- **Swappable orchestrator** - use any provider as the "brain" (no Claude subscription required)
- **Context-aware prompts** - automatically augments queries with project knowledge
- **Working Memory** - tracks file reads, searches, and discoveries within sessions
- **Auto-exploration** - learns your codebase structure and purpose
- **Auto-fallback** - automatically switches models on rate limits
- **Auto-Execute Plans** - intelligent task execution with appropriate approval levels
- **Task planning** - AI-powered task breakdown with structured JSON output
- **Multi-provider routing** - intelligent task delegation
- **Interactive CLI** - full-featured command-line interface with Click
- **Persistent caching** - context and responses survive session restarts
- **Safety features** - Git checkpoints, audit logging, sandboxing, dry-run mode

## Providers

| Provider | Daily Requests | Tokens/Min | Best For |
|----------|---------------|------------|----------|
| **Cerebras** | 14,400 | 60,000 | Primary workhorse, ultra-fast inference |
| **Groq** | 7,000+ | 20,000 | Secondary, model variety |
| **Gemini** | 1,650 | - | Auto-fallback, overflow capacity |
| **Cohere** | 33 (1K/month) | - | Embeddings only |

## Quick Start

### 1. Install

**Option A: Install as package (recommended)**
```bash
# Clone or download the project
cd llm_agent_team

# Install in development mode (editable)
pip install -e .

# Now available anywhere!
llm-team --help
```

**Option B: Install dependencies only**
```bash
pip install -r requirements.txt
# Run from project directory
python llm_team.py
```

### 2. Set API Keys

```bash
# Required (get free keys)
export CEREBRAS_API_KEY=your_key  # https://cloud.cerebras.ai
export GROQ_API_KEY=your_key      # https://console.groq.com

# Optional
export GEMINI_API_KEY=your_key    # https://aistudio.google.com
export COHERE_API_KEY=your_key    # https://dashboard.cohere.com
```

### 3. Basic Usage

```python
import sys
sys.path.insert(0, 'src')
from providers import CerebrasProvider, GroqProvider, ProviderRegistry

# Simple provider usage
provider = CerebrasProvider()
response = provider.chat(
    messages=[{"role": "user", "content": "Explain recursion briefly"}],
    max_tokens=100
)
print(response.content)
```

### 4. Orchestrator with Swappable Brain

```python
from src.orchestrator import AgentOrchestrator

# Default: Cerebras as brain
orch = AgentOrchestrator()

# Or specify your preferred brain
orch = AgentOrchestrator(orchestrator_provider='groq')

# Task planning (brain breaks down complex task)
steps = orch.plan("Implement user authentication with JWT")
for step in steps:
    print(f"{step['step']}: {step['description']}")

# Complex reasoning (brain analyzes and synthesizes)
answer = orch.reason(
    "Should we use microservices or monolith?",
    context="Small team, MVP phase",
    evidence=["Need to ship fast", "Limited DevOps experience"]
)

# Delegate simple tasks to fast providers
result = orch.delegate('cerebras', 'Summarize this code: ...')

# Smart delegation (auto-selects best provider)
result = orch.delegate_smart('Format this JSON', task_type='fast')
```

### 5. CLI Interface (No Claude Subscription Required)

Interactive command-line interface for users without Claude subscriptions:

```bash
# Start interactive mode
llm-team

# Resume from last session (conversation + context preserved)
llm-team --resume

# Auto-explore codebase on startup (recommended)
llm-team --auto-explore

# Or specify brain provider
llm-team --brain groq

# Works from any directory!
cd ~/my-project && llm-team --auto-explore
```

**One-shot commands:**

```bash
# Quick query
llm-team query "What is machine learning?"

# Query with codebase context
llm-team query "How should I fix the auth bug?" --with-context

# Query with specific provider
llm-team query "Explain Docker" --provider groq

# Plan a task
llm-team plan "Build REST API with authentication"

# Reason about a question
llm-team reason "Redis vs PostgreSQL for caching?" \
  --evidence "Need sub-ms latency" \
  --evidence "Data is temporary"

# Explore a codebase
llm-team explore .
llm-team explore /path/to/project --save

# View context status
llm-team context

# Check system status
llm-team status

# List providers
llm-team providers

# List models
llm-team models
llm-team models cerebras
```

**Interactive mode commands:**

```
You: /help              # Show all commands
You: /plan <task>       # Create task plan
You: /reason <question> # Analyze with reasoning
You: /agent <task>      # Run code agent with human approval
You: /explore [path]    # Explore codebase
You: /context           # View/manage context
You: /context explore   # Explore current project
You: /context toggle    # Enable/disable context awareness
You: /providers         # List available providers
You: /brain groq        # Switch brain provider
You: /models            # List all models
You: /usage             # Show usage statistics
You: /status            # System status
You: /synthesize        # Multi-provider synthesis
You: /delegate          # Direct provider delegation
You: /cache             # View cache statistics
You: /cache clear       # Clear response cache
You: /cache toggle      # Enable/disable caching
You: /quit              # Exit
```

### 6. Code Agent (AI Writes Code)

Let the AI write code with your approval for every action:

```bash
# One-shot command
llm-team agent "Add a health check endpoint to the Flask app"

# With options
llm-team agent "Refactor auth module" --dry-run  # Preview only
llm-team agent "Fix login bug" --max-iterations 5
```

**Interactive mode:**
```
You: /agent Add rate limiting to the API

Code Agent - Task: Add rate limiting to the API
------------------------------------------------------------
Run in dry-run mode? [y/N]: n
Create git checkpoint before running? [Y/n]: y
Checkpoint created: a1b2c3d4

Agent Configuration:
  Planner (smart tasks): gemini
  Executor (fast tasks): cerebras
  Project root: /path/to/project

--- Iteration 1/10 ---
[gemini] Thinking...

Thought: I need to first understand the current API structure

Agent wants to: read_file
Parameters: {"path": "src/api.py"}
Allow? [y/N]: y
Executing: read_file
Result: [file contents...]

--- Iteration 2/10 ---
Thought: Now I'll add rate limiting using flask-limiter

Agent wants to: write_file
Parameters: {"path": "src/api.py", "content": "..."}

Content preview:
from flask_limiter import Limiter
...

Allow? [y/N]: y
Executing: write_file
Result: Successfully wrote 2341 characters to src/api.py

--- Iteration 3/10 ---
Thought: Task completed successfully

============================================================
Task Completed Successfully!
Result: Added rate limiting decorator using flask-limiter
Iterations: 3

Audit Log:
  [2025-01-15T10:30:45] read_file - Approved
  [2025-01-15T10:31:12] write_file - Approved
  [2025-01-15T10:31:45] complete - Approved

Save audit log to file? [y/N]: y
Saved to: .agent_audit.json

Rollback to checkpoint? [y/N]: n
```

**Key safety features:**
- Human approval for every file operation
- Git checkpoint before changes (easy rollback)
- **Git history awareness** (checks commits, diffs, blame before changes)
- Sandboxed to project directory
- Audit logging of all actions
- Dry-run mode for previewing
- Dangerous command blocking

### 7. Context-Aware Development

The orchestrator automatically learns about your codebase:

```python
from src.orchestrator import AgentOrchestrator

# Auto-explore codebase on initialization
orch = AgentOrchestrator(auto_explore=True)

# Or manually explore
orch.explore_project()

# Check context status
print(orch.get_context_status())

# Queries are now context-aware
result = orch.delegate(
    'cerebras',
    'How should I add rate limiting?',
    use_context=True  # Automatically includes project info
)

# Disable context for specific calls
result = orch.delegate('groq', 'What is 2+2?', use_context=False)
```

**Context includes:**
- Project type and purpose
- Technologies and frameworks used
- File structure and organization
- Key dependencies
- Entry points

**Cache:**
- Stored in `.llm_team_context.json`
- Persists across sessions
- Auto-loads on startup

## Architecture

```
User Input
    │
    ▼
TaskRouter (NEW)
    ├─── TaskClassifier
    │     ├─ Pattern matching
    │     ├─ Complexity scoring (1-10)
    │     └─ Provider suggestion (fast/quality)
    │
    ├─── ProviderSelector
    │     ├─ "fast" → Cerebras > Groq > Gemini
    │     └─ "quality" → 70B models
    │
    └─── ExecutionStrategies
          ├─ DirectExecutor (shell, no LLM)
          ├─ ResearchExecutor (fast LLM, read-only)
          ├─ ConversationExecutor (simple responses)
          └─ AgentExecutor (full planning loop)
                │
                ▼
          CodeAgent
                ├─ Planner: Gemini (smart tasks)
                ├─ Executor: Cerebras (fast tasks)
                ├─ Tools: read_file, write_file, run_command, etc.
                └─ Human-in-the-loop approval
    │
    ▼
AgentOrchestrator
    │
    ├─── Brain Provider (Cerebras/Groq/Gemini)
    │     └─ Planning, reasoning, synthesis
    │
    ├─── Cerebras (Primary - 14,400 RPD)
    │     └─ llama3.1-8b, llama-3.3-70b, qwen-3-32b
    │
    ├─── Groq (Secondary - 7,000 RPD)
    │     └─ llama-3.x, mixtral, gemma
    │
    ├─── Gemini (Overflow - 1,650 RPD)
    │     └─ Auto-fallback between models
    │
    └─── Cohere (Embeddings only - 1K/month)
          └─ command-r, embeddings
```

## Key Capabilities

### Swappable Orchestrator Brain

No Claude subscription? No problem:

```python
# Use Cerebras (default)
orch = AgentOrchestrator()

# Use Groq instead
orch = AgentOrchestrator(orchestrator_provider='groq')

# Use Gemini
orch = AgentOrchestrator(orchestrator_provider='gemini')
```

### Task Planning

```python
steps = orch.plan("Add dark mode to React app")
# Returns structured steps with provider recommendations
```

### Complex Reasoning

```python
answer = orch.reason(
    question="Redis vs PostgreSQL for caching?",
    evidence=["Need sub-ms latency", "Data is temporary"]
)
```

### Result Synthesis

```python
# Combine outputs from multiple agents
summary = orch.synthesize([result1, result2, result3])
```

### Smart Routing

```python
# Automatically selects best provider
orch.delegate_smart(prompt, task_type='fast')      # → Cerebras
orch.delegate_smart(prompt, task_type='quality')   # → Cerebras 70b
orch.delegate_smart(prompt, task_type='reasoning') # → Brain
```

### Task-Type Aware Routing (NEW)

Automatically classifies tasks and routes to optimal execution strategies:

```python
from src.task_router.router import TaskRouter

router = TaskRouter(orchestrator)

# Direct commands - no LLM needed, instant execution
router.route("pip install requests")
# → DirectExecutor (immediate, no approval)

# Research tasks - fast LLM, no file changes
router.route("explain how the auth module works")
# → ResearchExecutor (Cerebras, no approval)

# Code generation - full agent with approval
router.route("implement user authentication")
# → AgentExecutor (Gemini 70B for complex tasks, human approval)

# Provider selection based on complexity
router.route("fix simple typo")           # → Fast provider (Cerebras)
router.route("refactor entire module")    # → Quality provider (Gemini 70B)
```

**Key Features:**
- **No agent overhead** for simple commands
- **Dynamic provider selection** based on task complexity
- **Safety checks** - dangerous commands blocked automatically
- **Metrics tracking** - monitor execution patterns

See [Task Routing Documentation](docs/task_routing.md) for full details.

### Code Agent

```python
from src.agent import CodeAgent

# Create agent with hybrid model approach
agent = CodeAgent(orch)
# Uses Gemini for planning, Cerebras for fast tasks

# Run a task with human approval
result = agent.run("Add input validation to the API")

# Check results
print(f"Success: {result['success']}")
print(f"Iterations: {result['iterations']}")
print(f"Audit log: {result['audit_log']}")

# Save audit trail
agent.save_audit_log(".agent_audit.json")
```

## Examples

```bash
# Basic usage
python examples/basic_usage.py

# Test swappable orchestrator
python examples/orchestrator_demo.py

# Code agent demo
python examples/agent_demo.py
```

**Using the CLI from anywhere:**

```bash
# Navigate to any project
cd ~/projects/my-app

# Start LLM Team with auto-exploration
llm-team --auto-explore

# It automatically learns about my-app!
You: How should I structure the database models?
Assistant: [Context-aware response based on your project]
```

## Adding New Providers

1. Create provider class in `src/providers/`
2. Implement `LLMProvider` interface
3. Register in `src/providers/__init__.py`
4. Add to orchestrator auto-register

See `src/providers/cerebras_provider.py` for example.

## Rate Limits

See [docs/RATE_LIMITS.md](docs/RATE_LIMITS.md) for detailed limits and usage strategy.

**TL;DR**: 23,000 requests/day is plenty for serious development work.

## Documentation

- **[5-Minute Quickstart](docs/QUICKSTART.md)** - Get running fast, no fluff
- [CLI Reference](docs/CLI.md) - Complete CLI guide and commands
- [Architecture](docs/ARCHITECTURE.md) - System design and patterns
- [Rate Limits](docs/RATE_LIMITS.md) - Provider limits and usage strategy

## Requirements

- Python 3.10+
- API keys for providers you want to use
- Required packages: `groq`, `cohere`, `google-generativeai`, `openai`, `click`, `python-dotenv`

## License

MIT

## Status

**Production-ready for prototyping**. Core features implemented:
- Multi-provider orchestration
- Swappable orchestrator brain
- **Task-Type Aware Routing** - intelligent task classification and strategy selection
- **Dynamic Provider Selection** - automatic provider/model selection based on task complexity
- **Auto-Execute Plans** - intelligent plan execution with TaskRouter integration
- **Response caching** - avoid duplicate API calls, TTL-based expiration
- **Context-aware prompts** with codebase exploration
- **Interactive CLI** with Click
- **Code Agent** with human-in-the-loop approval
- Task planning and reasoning (structured JSON output)
- Usage tracking with cache hit statistics
- Auto-fallback (Gemini)
- **Persistent caching** - both context and responses cached to disk
- **Safety features**: Git checkpoints, audit logging, sandboxing

**Future work**:
- Async/parallel execution
- Persistent rate limit tracking
- More provider integrations
- Embedding-based context relevance
- Provider performance tracking and learning
- Automatic strategy tuning based on success rates
- Batch task optimization
