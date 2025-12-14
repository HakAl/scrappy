# CLI Reference Guide

Complete reference for the Scrappy command-line interface.

## Command Quick Reference

| Command | Description | Section |
|---------|-------------|---------|
| `scrappy` | Start interactive chat mode | [Interactive Mode](#interactive-mode-default) |
| `scrappy query` | Send one-shot query | [query](#query---send-a-single-query) |
| `scrappy plan` | Break down task into steps | [plan](#plan---create-task-plans) |
| `scrappy reason` | Analyze with evidence | [reason](#reason---complex-reasoning) |
| `scrappy agent` | AI writes code with approval | [agent](#agent---code-agent-with-human-approval) |
| `scrappy smart` | Research-first query with tools | [smart](#smart---research-first-query) |
| `scrappy explore` | Analyze codebase structure | [explore](#explore---codebase-analysis) |
| `scrappy context` | View context status | [context](#context---view-context-status) |
| `scrappy status` | System status | [status](#status---system-status) |
| `scrappy models` | List available models | [models](#models---list-models) |
| `scrappy usage` | Show usage statistics | [usage](#usage---usage-statistics) |

**Interactive Mode Commands:** [Slash Commands](#interactive-mode-commands) | [Context](#context-management) | [Cache](#cache-management) | [Session](#session-management)

---

## Quick Start

**Get API Keys**

[Cerebras](https://cloud.cerebras.ai/platform),
[Groq](https://console.groq.com/),
[Gemini](https://aistudio.google.com/),
[SambaNova](https://cloud.sambanova.ai/)


```bash
# Install dependencies
pip install -r requirements.txt

# Configure API keys
export CEREBRAS_API_KEY=your_key
export GROQ_API_KEY=your_key

# Start interactive mode
python scrappy.py

# Start with auto-exploration (recommended for new projects)
python scrappy.py --auto-explore

# One-time setup (from project directory)
cd scrappy
pip install -e .

# Now use from anywhere!
cd ~/any-project
scrappy --auto-explore    # Learns about current directory
scrappy query "How do I add auth?"
scrappy agent "Fix the login bug"
```

## Global Options

```bash
python scrappy.py [OPTIONS] [COMMAND]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--auto-explore` | `-a` | Automatically explore codebase on startup |
| `--no-context` | | Disable context-aware prompts |
| `--resume` | `-r` | Resume from last saved session |
| `--no-save` | | Disable auto-save on exit |

**Examples:**
```bash
# Auto-explore and use context
python scrappy.py --auto-explore

# Disable context awareness
python scrappy.py --no-context

# Resume previous session
python scrappy.py --resume
# or
scrappy -r

# Start without auto-saving
python scrappy.py --no-save

# Combine options
python scrappy.py -a -r
```

## Commands

### Interactive Mode (Default)

Start the interactive chat interface:

```bash
python scrappy.py
# or explicitly
python scrappy.py interactive
```

**Startup Output:**
```
Initializing Scrappy...
Mode: QUALITY
Configured providers: cerebras, groq, gemini
Context: Not explored (use /context to explore)

============================================================
Scrappy - Interactive Mode
============================================================
```

### One-Shot Commands

#### `query` - Send a Single Query

```bash
python scrappy.py query "Your question here"
```

**Options:**
| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--provider` | `-p` | brain | Specific provider to use |
| `--model` | `-m` | default | Specific model |
| `--temperature` | `-t` | 0.7 | Sampling temperature (0-1) |
| `--max-tokens` | | 1000 | Max response tokens |
| `--with-context` | `-c` | false | Include codebase context |

**Examples:**
```bash
# Basic query
python scrappy.py query "What is machine learning?"

# Use specific provider
python scrappy.py query "Explain Docker" --provider groq

# With codebase context
python scrappy.py query "How should I fix the auth bug?" --with-context

# Custom parameters
python scrappy.py query "Write a haiku" -t 0.9 --max-tokens 50
```

#### `plan` - Create Task Plans

Break down complex tasks into actionable steps:

```bash
python scrappy.py plan "Your task description"
```

**Options:**
| Option | Default | Description |
|--------|---------|-------------|
| `--max-steps` | 5 | Maximum number of steps |

**Example:**
```bash
python scrappy.py plan "Implement JWT authentication for REST API"
```

**Output:**
```
1. Design Authentication Schema
   Define user model and token structure
   [Recommended: quality]

2. Install Dependencies
   Add PyJWT and bcrypt to requirements
   [Recommended: fast]

3. Create Auth Endpoints
   Implement /login, /register, /refresh routes
   [Recommended: quality]
...
```

#### `reason` - Complex Reasoning

Analyze questions with evidence-based reasoning:

```bash
python scrappy.py reason "Your question" [OPTIONS]
```

**Options:**
| Option | Short | Description |
|--------|-------|-------------|
| `--context` | `-c` | Additional context information |
| `--evidence` | `-e` | Evidence points (can specify multiple) |

**Example:**
```bash
python scrappy.py reason "Should we use Redis or PostgreSQL for caching?" \
  --context "E-commerce platform with 10K daily users" \
  --evidence "Need sub-millisecond reads" \
  --evidence "Data is temporary session info" \
  --evidence "Budget is limited"
```

**Output:**
```
Analysis:
Given the requirements for sub-millisecond reads and temporary session data,
Redis is the optimal choice. PostgreSQL excels at relational data but adds
overhead for simple key-value caching...

Conclusion: Use Redis for session caching
Confidence: high
```

#### `explore` - Codebase Analysis

Analyze a project directory:

```bash
python scrappy.py explore [PATH] [OPTIONS]
```

**Options:**
| Option | Short | Description |
|--------|-------|-------------|
| `--save` | `-s` | Save summary to CODEBASE_SUMMARY.md |

**Examples:**
```bash
# Explore current directory
python scrappy.py explore

# Explore specific path
python scrappy.py explore /path/to/project

# Save summary to file
python scrappy.py explore . --save
```

**Output includes:**
- Project type (library, CLI, web app, etc.)
- Main purpose and functionality
- Key technologies and frameworks
- Code organization and architecture
- Entry points and dependencies
- Potential issues or improvements

#### `agent` - Code Agent with Human Approval

Run an AI code agent that can read, write, and modify files with your explicit approval:

```bash
python scrappy.py agent "Your task description" [OPTIONS]
```

**Options:**
| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--dry-run` | `-d` | false | Preview without making actual changes |
| `--no-checkpoint` | | false | Skip git checkpoint creation |
| `--auto-confirm` | | false | Skip approval prompts (use with caution) |
| `--max-iterations` | `-m` | 10 | Maximum agent iterations |

**Examples:**
```bash
# Basic task
python scrappy.py agent "Add a health check endpoint to the Flask app"

# Preview changes without executing
python scrappy.py agent "Refactor the auth module" --dry-run

# Limit iterations
python scrappy.py agent "Fix the login bug" --max-iterations 5

# Skip git checkpoint (not recommended)
python scrappy.py agent "Update docstrings" --no-checkpoint

# Auto-confirm (dangerous - use only for trusted tasks)
python scrappy.py agent "Format all Python files" --auto-confirm
```

**Output:**
```
Code Agent - Task: Add a health check endpoint
------------------------------------------------------------
Creating git checkpoint...
Checkpoint created: a1b2c3d4

Agent Configuration:
  Planner (smart tasks): gemini
  Executor (fast tasks): cerebras
  Project root: /path/to/project
  Max iterations: 10

--- Iteration 1/10 ---
[gemini] Thinking...

Thought: I need to understand the current API structure first

Agent wants to: read_file
Parameters: {
  "path": "src/app.py"
}
Allow? [y/N]: y
Executing: read_file
Result: [file contents...]

--- Iteration 2/10 ---
Thought: Now I'll add the health check endpoint

Agent wants to: write_file
Parameters: {
  "path": "src/app.py",
  "content": "..."
}

Content preview:
@app.route('/health')
def health_check():
    return {'status': 'healthy', 'timestamp': datetime.now().isoformat()}
...

Allow? [y/N]: y
Executing: write_file
Result: Successfully wrote 1523 characters to src/app.py

--- Iteration 3/10 ---
Thought: Task completed successfully

============================================================
Task Completed Successfully!
Result: Added /health endpoint that returns JSON status
Iterations: 3

Audit Log:
  [2025-01-15T10:30:45] read_file - Approved
  [2025-01-15T10:31:12] write_file - Approved
  [2025-01-15T10:31:45] complete - Approved

Audit log saved to: .scrappy/.audit.json  

To rollback changes: git reset --hard a1b2c3d4
```

**Available Tools:**
The agent has access to these tools:
- `read_file(path)` - Read file contents
- `write_file(path, content)` - Write to a file
- `list_files(directory, pattern)` - List files in directory
- `run_command(command)` - Execute shell command
- `search_code(pattern, file_pattern)` - Search for code patterns
- `git_log(n, file)` - View recent commits (optionally for specific file)
- `git_diff(ref, file)` - Show changes (unstaged or vs ref like HEAD~1)
- `git_blame(file, lines)` - Show who changed each line
- `git_show(commit)` - Show details of a specific commit

**Safety Features:**
- **Human-in-the-loop**: Every file operation requires your approval
- **Git checkpoint**: Automatic backup before changes (easy rollback)
- **Sandboxing**: All paths restricted to project directory
- **Audit logging**: Complete trail of all actions
- **Dangerous command blocking**: Blocks rm -rf, del /f, etc.
- **Content preview**: Shows file content before writing

#### `smart` - Research-First Query

Perform intelligent queries that automatically gather context using tools before answering:

```bash
python scrappy.py smart "Your query here"
```

**Features:**
- Automatically analyzes your query to determine what research is needed
- Uses tools (directory listing, code search, file reading) to gather relevant context
- Synthesizes findings with LLM response for more accurate answers
- Higher quota usage but more informed responses

**Examples:**
```bash
# Find project structure
python scrappy.py smart "What files are in this project?"

# Understand specific code
python scrappy.py smart "How does the CodeAgent class work?"

# Locate functionality
python scrappy.py smart "Where is authentication implemented?"
```

**Output:**
```
[Smart Query] Researching...
  - Checking directory structure...
  - Searching for 'CodeAgent'...

[Response based on actual code inspection]
```

**Interactive Mode:**
```
You: /smart What files are in this project?
[Smart Query] Researching...
  - Checking directory structure...
[Response based on actual directory scan]
```

**Smart Mode Toggle (Interactive Only):**
```
You: /smart
Smart query mode: OFF
Usage: /smart <query> or /smart toggle

You: /smart toggle
Smart query mode enabled.
All queries will now use tools for research (higher quota usage).
```

**When to Use:**
- Questions about project structure or specific files
- Finding where functionality is implemented
- Understanding how specific classes/functions work
- Any query that benefits from reading actual code

**Smart Mode vs Regular Query:**
| Aspect | Regular Query | Smart Query |
|--------|--------------|-------------|
| Context | Uses cached summary only | Actively researches codebase |
| Accuracy | Based on general knowledge | Based on actual code inspection |
| Speed | Faster | Slower (tool execution) |
| Quota Usage | Lower | Higher |

#### `context` - View Context Status

Show current codebase context:

```bash
python scrappy.py context
```

#### `status` - System Status

Show orchestrator status:

```bash
python scrappy.py status
```

#### `models` - List Models

Show available models grouped by tier (fast/quality):

```bash
# All configured models
python scrappy.py models

# Filter by tier
python scrappy.py models fast
python scrappy.py models quality

# Filter by provider
python scrappy.py models cerebras
```

#### `usage` - Usage Statistics

Show session usage statistics:

```bash
python scrappy.py usage
```

## Interactive Mode Commands

When in interactive mode, use slash commands:

### Chat Commands

| Command | Description |
|---------|-------------|
| `(text)` | Send message to current brain |
| `/clear` | Clear conversation history |

### Task Operations

| Command | Description |
|---------|-------------|
| `/plan <task>` | Create a task plan |
| `/reason <question>` | Analyze with reasoning |
| `/agent <task>` | Run code agent with human approval |
| `/classify <query>` | Preview task classification without executing |
| `/autoexec` | Toggle auto-execute for plan tasks |
| `/smart <query>` | Research-first query (uses tools to gather context) |
| `/smart toggle` | Toggle smart mode always-on |
| `/synthesize` | Query multiple providers and synthesize |
| `/delegate <provider> <prompt>` | Direct provider query |
| `/explore [path]` | Explore a codebase |
| `/tasks` | Show background tasks status |

### Provider Management

| Command | Description |
|---------|-------------|
| `/models [filter]` | List available models (filter: fast, quality, or provider name) |
| `/model [mode]` | Show or switch mode (fast/quality) |
| `/status` | Show system status and configured providers |
| `/usage` | Show usage statistics |
| `/limits [provider]` | Show rate limit usage (or filter by provider) |
| `/limits reset` | Reset rate limit tracking |

### Context Management

| Command | Description |
|---------|-------------|
| `/context` | Show context status and summary |
| `/context explore` | Explore current project (uses cache) |
| `/context refresh` | Force re-exploration |
| `/context clear` | Clear cached context |
| `/context toggle` | Enable/disable context awareness |

### Cache Management

| Command | Description |
|---------|-------------|
| `/cache` | Show cache statistics (hits, misses, hit rate) |
| `/cache clear` | Clear all cached responses |
| `/cache toggle` | Enable/disable response caching |

### Session Management

| Command | Description |
|---------|-------------|
| `/session` | Show session info and status |
| `/session save` | Save current session to disk |
| `/session load` | Load saved session |
| `/session clear` | Delete saved session file |
| `/session toggle` | Toggle auto-save on/off |

See [Session Management](SESSION_MANAGEMENT.md) for full documentation.

### System Commands

| Command | Description |
|---------|-------------|
| `/help` | Show all commands |
| `/quit`, `/exit`, `/q` | Exit CLI (auto-saves session by default) |
| `/verbose`, `/v` | Toggle verbose output mode |

## Task Routing and Auto-Execute

The CLI now includes intelligent task routing and automatic plan execution.

### Auto-Execute Mode

When enabled (default), tasks in plans are automatically executed using the TaskRouter:

```
You: /autoexec
Auto-execute tasks: ENABLED
  Tasks in plans will be automatically executed using intelligent routing
  (DIRECT_COMMAND → immediate, RESEARCH → fast LLM, CODE_GEN → agent with approval)
```

**How it works:**

1. Create a plan with `/plan <task>`
2. Start working on the plan
3. Each task is automatically routed:
   - **DIRECT_COMMAND** (e.g., `npm install`) → Runs immediately, no LLM
   - **RESEARCH** (e.g., `explain auth`) → Fast LLM call, no approval needed
   - **CODE_GENERATION** (e.g., `write login`) → Full agent with human approval
   - **CONVERSATION** (e.g., `acknowledge`) → Simple response

**Example:**
```
You: /plan Build a React app with authentication

1. Install dependencies: npm install react react-dom
   [Auto-executes immediately - DirectExecutor]

2. Create auth service
   [Routes to AgentExecutor - requires approval]

3. Write login component
   [Routes to AgentExecutor - requires approval]

What next?
  1. Mark complete & continue
  2. Stay on this task
  ...
```

### Auto-Route Mode

Toggle automatic task classification:

```
You: /auto
Task routing mode: ENABLED
All inputs will be automatically classified and routed to optimal strategies.

You: pip install requests
📋 Task Classification:
  Type: direct_command
  Confidence: 1.00
  Complexity: 1/10
  Provider: none (hint: None)
  Executing with: DirectExecutor
✓ Command executed successfully
```

### Provider Selection

The router automatically selects providers based on task complexity:

| Complexity | Provider Type | Actual Provider |
|------------|---------------|-----------------|
| 1-6 | fast | Cerebras (8B model) |
| 7-10 | quality | Gemini (70B model) |

**Override provider:**
```python
# In code
router.route("implement auth", provider="quality")
```

### Benefits

- **Speed**: Simple commands execute instantly without LLM overhead
- **Efficiency**: Uses fast providers for simple tasks, quality for complex
- **Safety**: Code generation still requires human approval
- **Visibility**: Shows classification and provider selection decisions

## Context Awareness System

The CLI includes intelligent codebase context management.

### How It Works

1. **Exploration**: Scans project files, structure, and key configs
2. **Analysis**: Uses LLM to generate project summary
3. **Caching**: Saves context to `.scrappy/context.json`
4. **Augmentation**: Automatically injects context into prompts

### Context Cache File

Located at: `<project_root>/.scrappy/context.json`

Contains:
- Exploration timestamp
- Project summary
- File structure analysis
- File index by type

### Enabling Context

```bash
# Auto-explore on startup
python scrappy.py --auto-explore

# Manual exploration in interactive mode
You: /context explore

# One-shot with context
python scrappy.py query "Fix bug" --with-context
```

### Disabling Context

```bash
# Disable for entire session
python scrappy.py --no-context

# Toggle in interactive mode
You: /context toggle
```

### Context Augmentation Example

**Without context:**
```
You: How should I implement the provider fallback?
```

**With context (automatically augmented):**
```
[Codebase Context]
Project Context:
Multi-provider LLM orchestrator with Cerebras (14,400 RPD), Groq (7,000 RPD),
and Gemini (auto-fallback). Uses swappable brain architecture for planning
and reasoning tasks.

Structure:
Project: scrappy
Files: 25 total
Languages: python, docs, config

[User Request]
How should I implement the provider fallback?
```

The LLM now understands your project architecture without explanation!

## Response Caching System

The CLI includes automatic response caching to avoid duplicate API calls and save quota.

### How It Works

1. **Request Hashing**: Each request is hashed based on provider, model, prompt, and parameters
2. **Cache Lookup**: Before API call, cache is checked for matching response
3. **TTL Expiration**: Cached responses expire after 24 hours (configurable)
4. **Persistence**: Cache is saved to `.llm_response_cache.json`

### Cache File

Located at: `<project_root>/.llm_response_cache.json`

Contains:
- Cached responses with timestamps
- Provider and model information
- Token usage statistics
- Auto-cleans expired entries on load

### Managing Cache

```
You: /cache
Cache Statistics:
--------------------------------------------------
Total Entries: 15
Cache Hits: 23
Cache Misses: 45
Cache Saves: 15
Hit Rate: 33.8%
Cache File: .llm_response_cache.json
Caching: Enabled

You: /cache clear
Response cache cleared.

You: /cache toggle
Response caching disabled.
```

### Benefits

- **Save API quota**: Don't waste requests on duplicate queries
- **Instant responses**: Cached hits return immediately (0ms latency)
- **Persist across sessions**: Cache survives CLI restarts
- **Automatic expiration**: Old entries cleaned up automatically
- **Per-request control**: Override caching for specific calls

### Programmatic Control

```python
# Disable caching for non-deterministic tasks
result = orch.delegate('groq', 'Generate random story', use_cache=False)

# Check cache stats
stats = orch.get_cache_stats()
print(f"Hit rate: {stats['hit_rate']}")

# Clear cache
orch.clear_cache()

# Toggle caching
orch.toggle_cache()
```

## Provider Information

### Available Providers

| Provider | Daily Quota | Best For |
|----------|------------|----------|
| **Cerebras** | 14,400 RPD | Fast tier, highest quota |
| **Groq** | 7,000 RPD | Fast and quality tiers |
| **Gemini** | varies | Quality tier, large context |
| **SambaNova** | varies | Fast tier alternative |

### Model Groups

Models are organized into two tiers with automatic fallback:

**FAST** (speed priority):
- 8B class models
- High throughput, low latency
- Best for quick tasks and high volume

**QUALITY** (reasoning priority):
- 70B+ class models
- Complex reasoning, larger context
- Best for planning and analysis

```bash
# Switch modes in interactive mode
You: /model fast
You: /model quality

# Check current mode
You: /status
```

## Usage Patterns

### Development Workflow

```bash
# 1. Start with auto-explore for new project
python scrappy.py --auto-explore

# 2. Use context-aware queries
You: /context explore
You: What's the best way to add rate limiting to this project?
You: /plan Add rate limiting middleware
```

### Quick Queries

```bash
# One-off questions
python scrappy.py query "Explain async/await in Python"

# With specific model
python scrappy.py query "Complex analysis..." --provider groq --model llama-3.3-70b-versatile
```

### Multi-Provider Synthesis

```
You: /synthesize
Enter your question: What are the trade-offs of microservices?
Providers to query: cerebras, groq
  Asking cerebras... Done (234 tokens)
  Asking groq... Done (198 tokens)
Synthesizing responses...

Synthesized Response:
[Combined insights from both providers]
```

### Reasoning with Evidence

```
You: /reason Should we refactor the monolith to microservices?
```

Or with CLI:
```bash
python scrappy.py reason "Monolith vs microservices?" \
  --context "Startup with 5 developers" \
  --evidence "Need to ship MVP in 2 months" \
  --evidence "Team has limited DevOps experience" \
  --evidence "Expecting rapid growth"
```

### Code Agent Workflow

Let the AI write code with your approval:

```
You: /agent Add input validation to the user registration endpoint

Code Agent - Task: Add input validation...
------------------------------------------------------------
Run in dry-run mode? [y/N]: n
Create git checkpoint before running? [Y/n]: y
Checkpoint created: f8e7d6c5

Agent Configuration:
  Planner (smart tasks): gemini
  Executor (fast tasks): cerebras
  Project root: /path/to/project

Start agent? [Y/n]: y

--- Iteration 1/10 ---
[gemini] Thinking...

Thought: First, I need to examine the current registration endpoint

Agent wants to: read_file
Parameters: {"path": "src/routes/auth.py"}
Allow? [y/N]: y
Executing: read_file
Result: [current file contents...]

--- Iteration 2/10 ---
Thought: I'll add Pydantic validation for the user registration

Agent wants to: write_file
Parameters: {"path": "src/routes/auth.py", "content": "..."}

Content preview:
from pydantic import BaseModel, EmailStr, validator

class UserRegistration(BaseModel):
    email: EmailStr
    password: str

    @validator('password')
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        return v
...

Allow? [y/N]: y
Executing: write_file
Result: Successfully wrote 2847 characters to src/routes/auth.py

============================================================
Task Completed Successfully!
Result: Added Pydantic validation with email and password checks
Iterations: 2

Save audit log to file? [y/N]: y
Saved to: .scrappy/.audit.json  

Rollback to checkpoint? [y/N]: n
```

**One-shot agent:**
```bash
# Dry run first to see what would happen
python scrappy.py agent "Add logging to all API endpoints" --dry-run

# Then run for real
python scrappy.py agent "Add logging to all API endpoints"
```

## Tips and Best Practices

### 1. Use Auto-Explore for New Projects
```bash
python scrappy.py -a
```
This builds context immediately, making all queries more informed.

### 2. Leverage Context for Code Questions
```bash
python scrappy.py query "Where should I add the new endpoint?" -c
```

### 3. Plan Before Implementing
```
You: /plan Implement user authentication
```
Get structured steps with provider recommendations.

### 4. Monitor Usage
```
You: /usage
```
Track token consumption across providers.

### 5. Switch Modes for Different Tasks
```
You: /model fast     # For quick tasks
You: /model quality  # For complex reasoning
```

### 6. Refresh Context After Major Changes
```
You: /context refresh
```
Re-scan after adding new modules or restructuring.

### 7. Use Code Agent for Complex Tasks
```bash
# Always dry-run first for safety
python scrappy.py agent "Refactor auth module" --dry-run

# Use git checkpoint (default) for easy rollback
python scrappy.py agent "Add new feature"

# Review audit logs after completion
cat .scrappy/.audit.json  
```

### 8. Combine Agent with Context
```bash
# Explore first so agent understands project
python scrappy.py --auto-explore

# Then agent has full context
You: /agent Add rate limiting middleware
```

## Error Handling

### Common Issues

**Provider Not Available:**
```
No models configured.
```
→ Check API key configuration in `.env` and run `/setup`

**Context Not Explored:**
```
Context: Not explored (use /context to explore)
```
→ Run `/context explore` or start with `--auto-explore`

**Rate Limit Hit:**
```
Error: Rate limit exceeded
```
→ Switch to fast mode with `/model fast` or wait for quota reset

### Debug Mode

Check system status:
```
You: /status
You: /models
You: /usage
```

## Configuration

### Environment Variables

```bash
# Required (at least one)
CEREBRAS_API_KEY=your_key
GROQ_API_KEY=your_key

# Optional
GEMINI_API_KEY=your_key
SAMBANOVA_API_KEY=your_key
```

### Cache Management

```bash
# Clear all context cache
You: /context clear

# Or delete file directly
rm .scrappy/context.json
```

## Examples

### Full Interactive Session

```
$ python scrappy.py --auto-explore

Initializing Scrappy...
Mode: QUALITY
Configured providers: cerebras, groq, gemini
[CONTEXT] Exploring codebase: /path/to/project
[CONTEXT] Found 25 files
[CONTEXT] Generated project summary
Context: scrappy (cached)

============================================================
Scrappy - Interactive Mode
============================================================

You: /context
Context Status:
--------------------------------------------------
Project: /path/to/scrappy
Explored: Yes
Has Summary: Yes
...

You: What's the main entry point for this project?
Assistant: Based on the project structure, the main entry point is
`scrappy.py` which imports from `src/cli.py`...
[cerebras/llama3.1-8b | 145 tokens | 234ms]

You: /plan Add WebSocket support for real-time chat

Planning: Add WebSocket support for real-time chat
--------------------------------------------------

1. Install WebSocket Dependencies
   Add websockets or socket.io library to requirements
   [Recommended: fast]

2. Create WebSocket Server
   Implement async WebSocket handler for connections
   [Recommended: quality]
...

You: /quit
Usage Statistics:
--------------------------------------------------
Total Tasks: 3
Session Duration: 0:05:23

Goodbye!
```

### One-Shot Workflow

```bash
# Explore project
python scrappy.py explore . --save

# Query with context
python scrappy.py query "What testing framework should I add?" -c

# Plan implementation
python scrappy.py plan "Add pytest test suite"

# Reason about decision
python scrappy.py reason "pytest vs unittest?" \
  --evidence "Need fixtures" \
  --evidence "Team prefers readable syntax"
```

## Comparison: Interactive vs One-Shot

| Feature | Interactive | One-Shot |
|---------|-------------|----------|
| Session persistence | Yes | No |
| Conversation history | Yes | No |
| Quick iterations | Better | Slower |
| Scripting/automation | Limited | Better |
| Context switching | Easy (`/model`) | Per-command |
| Usage tracking | Cumulative | Per-command |

Choose interactive for development sessions, one-shot for automation and scripts.
