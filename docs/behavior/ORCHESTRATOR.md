# Orchestrator

Manages LLM interactions through LiteLLM Router with automatic model selection based on task complexity.

## Architecture

```
AgentOrchestrator
    |
    +-- LiteLLMService (injected)
    |       |
    |       +-- LiteLLM Router
    |       +-- Model Groups (fast/quality)
    |       +-- Automatic Fallback
    |
    +-- ResponseCache (injected)
    +-- RateLimitTracker (injected)
    +-- OutputInterface (injected)
    +-- CodebaseContext (injected)
    |       |
    |       +-- SemanticSearchManager
    |
    +-- DelegationManager (composed internally)
    +-- UsageReporter (composed internally)
```

## Core Components

| Component | Responsibility |
|-----------|----------------|
| `LiteLLMService` | LLM calls via LiteLLM Router, model selection |
| `DelegationManager` | Orchestrates LLM calls, caching |
| `UsageReporter` | Usage stats, cache management |
| `OutputInterface` | Abstracted logging (Console/Null/Capturing) |
| `CodebaseContext` | Codebase exploration, semantic search |

## Model Groups

Instead of individual providers, models are organized into two tiers:

| Group | Model Class | Use Case |
|-------|-------------|----------|
| **fast** | 8B models | Quick tasks, high throughput |
| **quality** | 70B+ models | Complex reasoning, planning |

The orchestrator automatically selects the appropriate group based on task complexity.

## LiteLLM Integration

All LLM calls go through LiteLLM Router which handles:
- Provider abstraction (Cerebras, Groq, Gemini, SambaNova)
- Automatic failover between providers
- Context window escalation (fast -> quality when needed)
- Rate limit handling

```python
# Delegation with automatic model selection
response = orchestrator.delegate(
    prompt="explain authentication",
    use_context=True,
)

# Force quality tier for complex tasks
response = orchestrator.delegate(
    prompt="design the architecture",
    model_group="quality",
)
```

## Semantic Search Integration

The orchestrator uses semantic search for implicit context augmentation:

```python
# OrchestratorFactory creates CodebaseContext with semantic search
context = CodebaseContext(project_path)
context._semantic_manager = SemanticSearchManager(...)
context.start_background_initialization()  # Indexes in background
```

When `use_context=True` in delegate calls:

```python
response = orchestrator.delegate(
    prompt="explain authentication",
    use_context=True,  # Triggers semantic search
)
```

The `PromptAugmenter` calls `CodebaseContext.augment_prompt()` which uses semantic search to find relevant code and inject it into the prompt.

### Configuration

```python
orchestrator = AgentOrchestrator(
    enable_semantic_search=True,  # Enable background indexing (default: True for CLI)
    context_aware=True,           # Enable context augmentation
)
```

### How It Works

1. `OrchestratorFactory.create_codebase_context()` creates `SemanticSearchManager`
2. Background thread starts indexing via `SemanticSearchInitializer`
3. When `delegate()` called with `use_context=True`:
   - `PromptAugmenter.augment()` is called
   - `CodebaseContext.augment_prompt()` uses semantic search
   - Relevant code is injected into the prompt

## Key Protocols

- `OutputInterface` - Swappable output (production vs test)
- `Orchestrator` - Type hints for any orchestrator implementation
- `SemanticSearchManagerProtocol` - Semantic search abstraction
- `LiteLLMServiceProtocol` - LLM service abstraction

## Testing

Inject test doubles via constructors:
```python
orchestrator = AgentOrchestrator(
    litellm_service=mock_litellm_service,
    output=CapturingOutput(),  # Capture instead of print
    enable_semantic_search=False,  # Disable for tests
    ...
)
```

See `tests/helpers.py` for `ConfigurableTestOrchestrator`.
