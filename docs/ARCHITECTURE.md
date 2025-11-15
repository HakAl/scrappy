# Multi-Provider LLM Agent Team Architecture

## Overview

This system creates a **swappable orchestrator** for multi-provider LLM coordination. The orchestrator brain can be any provider (Cerebras, Groq, Gemini), making the system usable without Claude Code or any specific subscription.

```
User / External System
    │
    ▼
AgentOrchestrator
    │
    ├─── Brain (Swappable: Cerebras/Groq/Gemini)
    │     └─ Planning, reasoning, synthesis
    │
    ├─── Cerebras (Primary - 14,400 RPD)
    │     └─ llama3.1-8b, llama-3.3-70b, qwen-3-32b
    │
    ├─── Groq (Secondary - 7,000 RPD)
    │     └─ llama-3.1-8b-instant, llama-3.3-70b-versatile, mixtral, gemma
    │
    ├─── Gemini (Overflow - 1,650 RPD, auto-fallback)
    │     └─ gemini-2.5-flash-lite, gemini-2.0-flash, etc.
    │
    └─── Cohere (Embeddings - 1,000/month)
          └─ command-r-08-2024, embed-english-v3.0
```

## Key Innovation: Swappable Orchestrator Brain

Unlike traditional setups that require a specific "master" LLM (like Claude Code), this system allows any registered provider to act as the orchestrator brain:

```python
# Default: Cerebras (best free tier)
orch = AgentOrchestrator()

# Explicit selection
orch = AgentOrchestrator(orchestrator_provider='groq')
orch = AgentOrchestrator(orchestrator_provider='gemini')

# Brain performs complex reasoning
steps = orch.plan("Add authentication to API")
answer = orch.reason("Which database for this use case?")
summary = orch.synthesize([result1, result2])
```

## Core Components

### 1. Provider Abstraction (`src/providers/base.py`)

All providers implement a common interface:
- `chat()` - Send messages, get responses
- `get_limits()` - Check rate limits
- `is_available()` - Verify configuration
- `get_model_for_task()` - Recommend model based on task type

### 2. Provider Implementations

**CerebrasProvider** (`src/providers/cerebras_provider.py`)
- Best for: Primary workhorse, ultra-fast inference
- Models: llama3.1-8b, llama-3.3-70b, qwen-3-32b
- Limits: 14,400 RPD, 60,000 TPM
- Default orchestrator brain

**GroqProvider** (`src/providers/groq_provider.py`)
- Best for: Secondary provider, model variety
- Models: llama-3.1-8b-instant, llama-3.3-70b-versatile, mixtral-8x7b, gemma2-9b
- Limits: 30 RPM, 7,000 RPD, 20K TPM

**GeminiProvider** (`src/providers/gemini_provider.py`)
- Best for: Overflow capacity, auto-fallback
- Models: gemini-2.5-flash-lite (1000 RPD), gemini-2.0-flash (200 RPD), etc.
- Special feature: Auto-fallback between models on rate limits

**CohereProvider** (`src/providers/cohere_provider.py`)
- Best for: Embeddings only (trial is severely limited)
- Models: command-r-08-2024, embed-english-v3.0
- Limits: **1,000 calls/month total** (CRITICAL - use sparingly)

### 3. Orchestrator (`src/orchestrator.py`)

Central coordinator that:
- Registers available providers automatically
- Sets up swappable brain (default: Cerebras)
- Provides planning, reasoning, and synthesis via brain
- Routes tasks to appropriate providers
- Tracks usage across all providers

## Usage Patterns

### Pattern 1: Autonomous Operation (No Claude Code)

```python
from src.orchestrator import AgentOrchestrator

# Cerebras as brain
orch = AgentOrchestrator()

# Brain plans the task
steps = orch.plan("Build REST API with authentication")

# Execute each step
for step in steps:
    if step['provider_type'] == 'fast':
        result = orch.delegate_smart(step['description'], task_type='fast')
    else:
        result = orch.delegate_smart(step['description'], task_type='quality')
```

### Pattern 2: Simple Delegation

```python
# Direct provider call
result = orch.delegate('cerebras', 'Summarize this text: ...')
print(result.content)
```

### Pattern 3: Smart Delegation

```python
# Auto-selects best provider for task type
result = orch.delegate_smart(
    'What are the benefits of microservices?',
    task_type='fast'  # Uses Cerebras (14,400 RPD)
)
```

### Pattern 4: Complex Reasoning

```python
# Brain analyzes with evidence
answer = orch.reason(
    "Should we use JWT or sessions?",
    context="Building mobile app backend",
    evidence=[
        "Need offline support",
        "Multiple devices per user",
        "Token refresh complexity"
    ]
)
```

### Pattern 5: Multi-Agent Synthesis

```python
# Get perspectives from multiple models
result1 = orch.delegate('cerebras', question, model='llama3.1-8b')
result2 = orch.delegate('groq', question, model='llama-3.3-70b-versatile')
result3 = orch.delegate('gemini', question)

# Brain synthesizes
summary = orch.synthesize(
    [result1, result2, result3],
    "Identify common themes and key differences:"
)
```

## Adding New Providers

### Step 1: Create Provider Class

```python
# src/providers/newprovider_provider.py
from .base import LLMProvider, LLMResponse, ProviderLimits

class NewProvider(LLMProvider):
    @property
    def name(self) -> str:
        return 'newprovider'

    @property
    def available_models(self) -> list[str]:
        return ['model-a', 'model-b']

    @property
    def default_model(self) -> str:
        return 'model-a'

    def chat(self, messages, model=None, max_tokens=1000, **kwargs):
        # Implementation
        pass

    def get_limits(self):
        return ProviderLimits(requests_per_day=1000)

    def get_model_for_task(self, task_type):
        if task_type == 'quality':
            return 'model-b'
        return 'model-a'
```

### Step 2: Register in `__init__.py`

```python
from .newprovider_provider import NewProvider
__all__ = [..., 'NewProvider']
```

### Step 3: Auto-register in Orchestrator

```python
# In orchestrator.py _auto_register_providers()
try:
    self.registry.register(NewProvider())
    print("[OK] NewProvider registered")
except Exception as e:
    print(f"[X] NewProvider unavailable: {e}")
```

### Step 4: Add to Brain Priority (optional)

```python
# In _setup_brain()
priority = ['cerebras', 'groq', 'gemini', 'newprovider']
```

## Rate Limit Strategy

### Combined Capacity

- **Cerebras**: 14,400 RPD
- **Groq**: 7,000 RPD
- **Gemini**: 1,650 RPD
- **Total**: ~23,000 requests/day

### Routing Priority

1. **Cerebras** (primary) - highest quota, fast inference
2. **Groq** (secondary) - good variety, proven reliability
3. **Gemini** (overflow) - auto-fallback handles limits
4. **Cohere** (embeddings only) - preserve monthly quota

### Best Practices

1. **Use Cerebras for orchestrator brain** - 14,400 RPD is plenty
2. **Route simple tasks to Cerebras** - maximize throughput
3. **Reserve Groq for variety** - different models for different needs
4. **Let Gemini handle overflow** - auto-fallback is smart
5. **Avoid Cohere for chat** - 1K/month is too limited

## Error Handling

The system handles:
- Missing API keys (provider won't register, skipped gracefully)
- Rate limit errors (Gemini auto-fallback)
- Model unavailability (checked at runtime)
- JSON parsing failures (fallback to raw response)

## Future Enhancements

1. **Response caching** - Store responses to avoid duplicate calls
2. **Async/parallel execution** - Speed up multi-agent workflows
3. **Persistent rate limit tracking** - Survive session restarts
4. **Cost estimation** - Even for free tiers, track usage
5. **Retry logic** - Automatic retry on transient failures
6. **Provider health checks** - Monitor availability

## Testing

```bash
# Test provider connectivity
python test_orchestrator.py

# Test basic usage patterns
python examples/basic_usage.py
```

## Current Limitations

1. **Synchronous only** - No async/parallel execution yet
2. **Session-based tracking** - Rate limits reset on restart
3. **No caching** - Every call hits the API
4. **Limited error recovery** - Basic error handling only

## Project Structure

```
src/
├── __init__.py
├── orchestrator.py           # Main orchestrator with swappable brain
└── providers/
    ├── __init__.py           # Provider exports
    ├── base.py               # Abstract base class
    ├── cerebras_provider.py  # Cerebras (primary)
    ├── groq_provider.py      # Groq (secondary)
    ├── gemini_provider.py    # Gemini (auto-fallback)
    └── cohere_provider.py    # Cohere (embeddings)

docs/
├── ARCHITECTURE.md           # This file
└── RATE_LIMITS.md           # Detailed rate limits

examples/
├── basic_usage.py           # Basic orchestrator usage
└── claude_orchestration.py  # Claude Code patterns
```
