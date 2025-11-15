# CLI Reference Guide

Complete reference for the LLM Agent Team command-line interface.

## Quick Start

**Get API Keys**

[Cerebras](https://cloud.cerebras.ai/platform), 
[Groq](https://console.groq.com/), 
[Gemini](https://aistudio.google.com/), 
[Cohere](https://dashboard.cohere.com/)


```bash
# Install dependencies
pip install -r requirements.txt

# Configure API keys
export CEREBRAS_API_KEY=your_key
export GROQ_API_KEY=your_key

# Start interactive mode
python llm_team.py

# Start with auto-exploration (recommended for new projects)
python llm_team.py --auto-explore
```

## Global Options

```bash
python llm_team.py [OPTIONS] [COMMAND]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--brain` | `-b` | Set orchestrator brain provider (cerebras, groq, gemini) |
| `--auto-explore` | `-a` | Automatically explore codebase on startup |
| `--no-context` | | Disable context-aware prompts |

**Examples:**
```bash
# Use Groq as brain
python llm_team.py --brain groq

# Auto-explore and use context
python llm_team.py --auto-explore

# Disable context awareness
python llm_team.py --no-context

# Combine options
python llm_team.py -b groq -a
```

## Commands

### Interactive Mode (Default)

Start the interactive chat interface:

```bash
python llm_team.py
# or explicitly
python llm_team.py interactive
```

**Startup Output:**
```
Initializing LLM Agent Team...
[OK] Cerebras provider registered (14,400 RPD)
[OK] Groq provider registered (7,000 RPD)
[BRAIN] Using cerebras as orchestrator brain
Brain: cerebras
Available providers: cerebras, groq
Context: Not explored (use /context to explore)

============================================================
LLM Agent Team - Interactive Mode
============================================================
```

### One-Shot Commands

#### `query` - Send a Single Query

```bash
python llm_team.py query "Your question here"
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
python llm_team.py query "What is machine learning?"

# Use specific provider
python llm_team.py query "Explain Docker" --provider groq

# With codebase context
python llm_team.py query "How should I fix the auth bug?" --with-context

# Custom parameters
python llm_team.py query "Write a haiku" -t 0.9 --max-tokens 50
```

#### `plan` - Create Task Plans

Break down complex tasks into actionable steps:

```bash
python llm_team.py plan "Your task description"
```

**Options:**
| Option | Default | Description |
|--------|---------|-------------|
| `--max-steps` | 5 | Maximum number of steps |

**Example:**
```bash
python llm_team.py plan "Implement JWT authentication for REST API"
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
python llm_team.py reason "Your question" [OPTIONS]
```

**Options:**
| Option | Short | Description |
|--------|-------|-------------|
| `--context` | `-c` | Additional context information |
| `--evidence` | `-e` | Evidence points (can specify multiple) |

**Example:**
```bash
python llm_team.py reason "Should we use Redis or PostgreSQL for caching?" \
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
python llm_team.py explore [PATH] [OPTIONS]
```

**Options:**
| Option | Short | Description |
|--------|-------|-------------|
| `--save` | `-s` | Save summary to CODEBASE_SUMMARY.md |

**Examples:**
```bash
# Explore current directory
python llm_team.py explore

# Explore specific path
python llm_team.py explore /path/to/project

# Save summary to file
python llm_team.py explore . --save
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
python llm_team.py agent "Your task description" [OPTIONS]
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
python llm_team.py agent "Add a health check endpoint to the Flask app"

# Preview changes without executing
python llm_team.py agent "Refactor the auth module" --dry-run

# Limit iterations
python llm_team.py agent "Fix the login bug" --max-iterations 5

# Skip git checkpoint (not recommended)
python llm_team.py agent "Update docstrings" --no-checkpoint

# Auto-confirm (dangerous - use only for trusted tasks)
python llm_team.py agent "Format all Python files" --auto-confirm
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

Audit log saved to: .agent_audit.json

To rollback changes: git reset --hard a1b2c3d4
```

**Available Tools:**
The agent has access to these tools:
- `read_file(path)` - Read file contents
- `write_file(path, content)` - Write to a file
- `list_files(directory, pattern)` - List files in directory
- `run_command(command)` - Execute shell command
- `search_code(pattern, file_pattern)` - Search for code patterns

**Safety Features:**
- **Human-in-the-loop**: Every file operation requires your approval
- **Git checkpoint**: Automatic backup before changes (easy rollback)
- **Sandboxing**: All paths restricted to project directory
- **Audit logging**: Complete trail of all actions
- **Dangerous command blocking**: Blocks rm -rf, del /f, etc.
- **Content preview**: Shows file content before writing

#### `context` - View Context Status

Show current codebase context:

```bash
python llm_team.py context
```

#### `status` - System Status

Show orchestrator status:

```bash
python llm_team.py status
```

#### `providers` - List Providers

Show all available providers with details:

```bash
python llm_team.py providers
```

#### `models` - List Models

Show available models:

```bash
# All models
python llm_team.py models

# Specific provider
python llm_team.py models cerebras
```

#### `usage` - Usage Statistics

Show session usage statistics:

```bash
python llm_team.py usage
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
| `/synthesize` | Query multiple providers and synthesize |
| `/delegate <provider> <prompt>` | Direct provider query |
| `/explore [path]` | Explore a codebase |

### Provider Management

| Command | Description |
|---------|-------------|
| `/providers` | List all providers with details |
| `/brain [name]` | Show/switch brain provider |
| `/models [provider]` | List available models |
| `/status` | Show system status |
| `/usage` | Show usage statistics |

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

### System Commands

| Command | Description |
|---------|-------------|
| `/help` | Show all commands |
| `/quit` or `/exit` | Exit CLI |

## Context Awareness System

The CLI includes intelligent codebase context management.

### How It Works

1. **Exploration**: Scans project files, structure, and key configs
2. **Analysis**: Uses LLM to generate project summary
3. **Caching**: Saves context to `.llm_team_context.json`
4. **Augmentation**: Automatically injects context into prompts

### Context Cache File

Located at: `<project_root>/.llm_team_context.json`

Contains:
- Exploration timestamp
- Project summary
- File structure analysis
- File index by type

### Enabling Context

```bash
# Auto-explore on startup
python llm_team.py --auto-explore

# Manual exploration in interactive mode
You: /context explore

# One-shot with context
python llm_team.py query "Fix bug" --with-context
```

### Disabling Context

```bash
# Disable for entire session
python llm_team.py --no-context

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
Project: llm_agent_team
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
| **Cerebras** | 14,400 RPD | Primary brain, fastest inference |
| **Groq** | 7,000 RPD | Secondary, model variety |
| **Gemini** | 1,650 RPD | Auto-fallback between models |
| **Cohere** | 33 RPD (~1K/month) | Embeddings only |

### Brain Selection

The orchestrator "brain" handles complex operations:
- Task planning
- Complex reasoning
- Result synthesis

Default priority: Cerebras > Groq > Gemini

```bash
# Specify brain
python llm_team.py --brain groq

# Switch brain in interactive mode
You: /brain gemini
```

## Usage Patterns

### Development Workflow

```bash
# 1. Start with auto-explore for new project
python llm_team.py --auto-explore

# 2. Use context-aware queries
You: /context explore
You: What's the best way to add rate limiting to this project?
You: /plan Add rate limiting middleware
```

### Quick Queries

```bash
# One-off questions
python llm_team.py query "Explain async/await in Python"

# With specific model
python llm_team.py query "Complex analysis..." --provider groq --model llama-3.3-70b-versatile
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
python llm_team.py reason "Monolith vs microservices?" \
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
Saved to: .agent_audit.json

Rollback to checkpoint? [y/N]: n
```

**One-shot agent:**
```bash
# Dry run first to see what would happen
python llm_team.py agent "Add logging to all API endpoints" --dry-run

# Then run for real
python llm_team.py agent "Add logging to all API endpoints"
```

## Tips and Best Practices

### 1. Use Auto-Explore for New Projects
```bash
python llm_team.py -a
```
This builds context immediately, making all queries more informed.

### 2. Leverage Context for Code Questions
```bash
python llm_team.py query "Where should I add the new endpoint?" -c
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

### 5. Switch Brains for Different Tasks
```
You: /brain groq  # For variety
You: /brain cerebras  # For speed
```

### 6. Refresh Context After Major Changes
```
You: /context refresh
```
Re-scan after adding new modules or restructuring.

### 7. Use Code Agent for Complex Tasks
```bash
# Always dry-run first for safety
python llm_team.py agent "Refactor auth module" --dry-run

# Use git checkpoint (default) for easy rollback
python llm_team.py agent "Add new feature"

# Review audit logs after completion
cat .agent_audit.json
```

### 8. Combine Agent with Context
```bash
# Explore first so agent understands project
python llm_team.py --auto-explore

# Then agent has full context
You: /agent Add rate limiting middleware
```

## Error Handling

### Common Issues

**Provider Not Available:**
```
Provider 'cohere' not available.
Available: cerebras, groq
```
→ Check API key configuration in `.env`

**Context Not Explored:**
```
Context: Not explored (use /context to explore)
```
→ Run `/context explore` or start with `--auto-explore`

**Rate Limit Hit:**
```
Error: Rate limit exceeded
```
→ Switch providers with `/brain` or wait for quota reset

### Debug Mode

Check system status:
```
You: /status
You: /providers
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
COHERE_API_KEY=your_key  # Limited to 1K/month
```

### Cache Management

```bash
# Clear all context cache
You: /context clear

# Or delete file directly
rm .llm_team_context.json
```

## Examples

### Full Interactive Session

```
$ python llm_team.py --auto-explore

Initializing LLM Agent Team...
[OK] Cerebras provider registered (14,400 RPD)
[OK] Groq provider registered (7,000 RPD)
[BRAIN] Using cerebras as orchestrator brain
[CONTEXT] Exploring codebase: /path/to/project
[CONTEXT] Found 25 files
[CONTEXT] Generated project summary
Brain: cerebras
Available providers: cerebras, groq
Context: llm_agent_team (cached)

============================================================
LLM Agent Team - Interactive Mode
============================================================

You: /context
Context Status:
--------------------------------------------------
Project: /path/to/llm_agent_team
Explored: Yes
Has Summary: Yes
...

You: What's the main entry point for this project?
Assistant: Based on the project structure, the main entry point is
`llm_team.py` which imports from `src/cli.py`...
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
python llm_team.py explore . --save

# Query with context
python llm_team.py query "What testing framework should I add?" -c

# Plan implementation
python llm_team.py plan "Add pytest test suite"

# Reason about decision
python llm_team.py reason "pytest vs unittest?" \
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
| Context switching | Easy (`/brain`) | Per-command |
| Usage tracking | Cumulative | Per-command |

Choose interactive for development sessions, one-shot for automation and scripts.
