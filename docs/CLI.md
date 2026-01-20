# CLI Reference Guide

## Quick Start

**Get API Keys**

[Cerebras](https://cloud.cerebras.ai/platform),
[Groq](https://console.groq.com/),
[Gemini](https://aistudio.google.com/),
[SambaNova](https://cloud.sambanova.ai/)


```bash
# One-time setup (from project directory)
cd scrappy
pip install -e .

# Now use from anywhere!
cd ~/any-project
scrappy  # Interactive mode with TUI
```

## Global Options

```bash
scrappy [OPTIONS]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--resume` | `-r` | Resume from last saved session |
| `--no-save` | | Disable auto-save on exit |
| `--help` | | Show help |
| `--version` | | Show version |

**Example:**
```bash
# Resume previous session
scrappy --resume

# Disable session auto-save
scrappy --no-save
```

## One-Shot Commands

Run a single command and exit:

```bash
scrappy version              # Show scrappy version
scrappy undo [n]             # Undo the last N agent runs
scrappy undo --force         # Bypass worktree path check
scrappy undo-list            # List all available undo points
scrappy undo-gc --keep N     # Clean up old undo points, keep N most recent
```

## Interactive Mode Commands

When in interactive mode, use slash commands:

### Chat Commands

| Command | Description |
|---------|-------------|
| `(text)` | Send message to agent (LangGraph routes to tools as needed) |
| `/ml` | Toggle multiline input mode |
| `/clear` | Clear conversation history |
| `/history [n]` | Show last n messages (default: 10) |

### Task Operations

| Command | Description |
|---------|-------------|
| `/plan <task>` | Break down a task into actionable steps |
| `/tasks` | View current plan progress |
| `/agent <task>` | Run code agent with human approval |
| `/reason <question>` | Analyze with step-by-step reasoning |
| `/smart <query>` | Research-first query (prioritizes research) |
| `/explore [path]` | Explore a codebase |

**Agent Options:**
- `--dry-run` - Simulate actions without making changes
- `--verbose, -v` - Show full output (thinking, params, results)
- `--clear` - Clear previous task list before starting

### Provider Management

| Command | Description |
|---------|-------------|
| `/setup` | Configure API keys via interactive wizard |
| `/models [filter]` | List available models (filter: fast, chat, instruct, or provider name) |
| `/model [mode]` | Show or switch mode (fast/chat/instruct) |
| `/status` | Show system status and configured providers |
| `/usage` | Show usage statistics |
| `/limits` | Show rate limit usage |

### Model Tiers

| Tier | Description |
|------|-------------|
| `fast` | 8B models, high throughput |
| `chat` | 70B models, conversation |
| `instruct` | Instruction-tuned models for agent/tools |

### Context Management

| Command | Description |
|---------|-------------|
| `/context` | Show context status and summary |
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
| `/session` | Show session info |
| `/session save` | Save current session |
| `/session load` | Load previous session |
| `/session clear` | Delete saved session |

### System Commands

| Command | Description |
|---------|-------------|
| `/help` | Show all commands |
| `/quit`, `/exit`, `/q` | Exit CLI (auto-saves session by default) |
| `/verbose`, `/v` | Toggle verbose output mode |
| `/autoexec` | Toggle automatic task execution in plans |


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
# Manual exploration in interactive mode
You: /context refresh

# Check context status
You: /context
```

### Disabling Context

```bash
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
Multi-provider LLM orchestrator with Cerebras, Groq, Gemini, and SambaNova.
Uses swappable brain architecture for planning and reasoning tasks.

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

## Provider Information

### Available Providers

| Provider | Best For |
|----------|----------|
| **Cerebras** | Fast tier, high throughput |
| **Groq** | Fast and chat tiers |
| **Gemini** | Chat and instruct tiers, large context |
| **SambaNova** | Fast tier alternative |

### Code Agent Workflow

The agent uses a graph-based architecture with distinct phases:

- **Think**: LLM decides what action to take next
- **Execute**: Runs the chosen tool (read/write files, run commands)
- **Verify**: Checks changes with linting (ruff, mypy)
- **Confirm**: Prompts before destructive operations
- **Error**: Handles failures with automatic retry

**Safety features:**
- Undo points before each run (rollback with `scrappy undo`)
- Human approval for file writes and commands
- Automatic linting verification after changes

**Models:** Requires tool-capable models (Gemini, Qwen). Llama models cannot call tools.

**Usage:**
```
You: /agent Add input validation to the signup form
```

The agent will show its thinking, request approval before making changes, and verify the results.


## Error Handling

### Common Issues

**Provider Not Available:**
```
No models configured.
```
- Check API key configuration in `.env` and run `/setup`

**Context Not Explored:**
```
Context: Not explored (use /context to explore)
```
- Run `/context refresh` to explore the codebase

**Rate Limit Hit:**
```
Error: Rate limit exceeded
```
- Switch to fast mode with `/model fast` or wait for quota reset

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
