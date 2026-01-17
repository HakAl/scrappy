# CLI Reference Guide

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
python main.py

# Start with auto-exploration (recommended for new projects)
python main.py --auto-explore

# One-time setup (from project directory)
cd scrappy
pip install -e .

# Now use from anywhere!
cd ~/any-project
scrappy  # Learns about current directory
```

## Global Options

```bash
python main.py [OPTIONS] [COMMAND]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--no-context` | | Disable context-aware prompts |
| `--resume` | `-r` | Resume from last saved session |

**Example:**
```bash
# Disable context awareness
python main.py --no-context
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
| `/agent <task>` | Run code agent with human approval |
| `/explore [path]` | Explore a codebase |

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

### System Commands

| Command | Description |
|---------|-------------|
| `/help` | Show all commands |
| `/quit`, `/exit`, `/q` | Exit CLI (auto-saves session by default) |
| `/verbose`, `/v` | Toggle verbose output mode |


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
You: /context explore

# One-shot with context
python main.py query "Fix bug" --with-context
```

### Disabling Context

```bash
# Disable for entire session
python main.py --no-context

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

### Code Agent Workflow

The agent uses a graph-based architecture with distinct phases:

- **Think**: LLM decides what action to take next
- **Execute**: Runs the chosen tool (read/write files, run commands)
- **Verify**: Checks changes with linting (ruff, mypy)
- **Confirm**: Prompts before destructive operations
- **Error**: Handles failures with automatic retry

**Safety features:**
- Undo points before each run (rollback with `/undo`)
- Human approval for file writes and commands
- Docker sandbox for command execution (when available)
- Automatic linting verification after changes

**Models:** Requires tool-capable models (Gemini, Qwen, Kimi K2). Llama models cannot call tools.

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
