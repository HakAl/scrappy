# Multi-Provider LLM Agent Team

A framework for orchestrating LLM agents across multiple free-tier providers with **swappable orchestrator brain** and **automatic codebase context awareness**.

## Features

- **23,000+ free requests/day** across providers
- **Swappable orchestrator** - use any provider as the "brain" (no Claude subscription required)
- **Context-aware prompts** - automatically augments queries with project knowledge
- **Auto-exploration** - learns your codebase structure and purpose
- **Auto-fallback** - automatically switches models on rate limits
- **Task planning** - AI-powered task breakdown with structured JSON output
- **Multi-provider routing** - intelligent task delegation
- **Interactive CLI** - full-featured command-line interface with Click
- **Persistent caching** - context survives session restarts

## Providers

| Provider | Daily Requests | Tokens/Min | Best For |
|----------|---------------|------------|----------|
| **Cerebras** | 14,400 | 60,000 | Primary workhorse, ultra-fast inference |
| **Groq** | 7,000+ | 20,000 | Secondary, model variety |
| **Gemini** | 1,650 | - | Auto-fallback, overflow capacity |
| **Cohere** | 33 (1K/month) | - | Embeddings only |

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
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
python llm_team.py

# Auto-explore codebase on startup (recommended)
python llm_team.py --auto-explore

# Or specify brain provider
python llm_team.py --brain groq
```

**One-shot commands:**

```bash
# Quick query
python llm_team.py query "What is machine learning?"

# Query with codebase context
python llm_team.py query "How should I fix the auth bug?" --with-context

# Query with specific provider
python llm_team.py query "Explain Docker" --provider groq

# Plan a task
python llm_team.py plan "Build REST API with authentication"

# Reason about a question
python llm_team.py reason "Redis vs PostgreSQL for caching?" \
  --evidence "Need sub-ms latency" \
  --evidence "Data is temporary"

# Explore a codebase
python llm_team.py explore .
python llm_team.py explore /path/to/project --save

# View context status
python llm_team.py context

# Check system status
python llm_team.py status

# List providers
python llm_team.py providers

# List models
python llm_team.py models
python llm_team.py models cerebras
```

**Interactive mode commands:**

```
You: /help              # Show all commands
You: /plan <task>       # Create task plan
You: /reason <question> # Analyze with reasoning
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
You: /quit              # Exit
```

### 6. Context-Aware Development

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
User (or Swappable Brain)
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

## Examples

```bash
# Basic usage
python examples/basic_usage.py

# Test swappable orchestrator
python test_orchestrator.py
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
- **Context-aware prompts** with codebase exploration
- **Interactive CLI** with Click
- Task planning and reasoning (structured JSON output)
- Usage tracking with context tracking
- Auto-fallback (Gemini)
- **Persistent context caching**

**Future work**:
- Response caching
- Async/parallel execution
- Persistent rate limit tracking
- More provider integrations
- Embedding-based context relevance
- Conversation memory
