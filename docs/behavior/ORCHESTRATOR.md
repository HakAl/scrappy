# Orchestrator

Allows any registered provider to act as the orchestrator brain. The orchestrator can automatically learn about your codebase and inject relevant context into prompts.

## Dependency Injection Pattern

The orchestrator uses constructor injection throughout, enabling testability and loose coupling.

```
AgentOrchestrator
    |
    +-- ProviderRegistry (injected)
    +-- ResponseCache (injected)
    +-- RateLimitTracker (injected)
    +-- ProviderSelector (injected)
    +-- OutputInterface (injected)
    +-- CodebaseContext (injected)
    |       |
    |       +-- SemanticSearchManager
    |
    +-- DelegationManager (composed internally)
    +-- UsageReporter (composed internally)
    +-- ProviderStatusReporter (composed internally)
```

## Core Components

| Component | Responsibility |
|-----------|----------------|
| `DelegationManager` | LLM calls, retry/fallback logic, caching |
| `ProviderSelector` | Provider routing, brain selection |
| `UsageReporter` | Usage stats, cache management |
| `ProviderStatusReporter` | Status display, selection info |
| `OutputInterface` | Abstracted logging (Console/Null/Capturing) |
| `CodebaseContext` | Codebase exploration, semantic search |

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
    provider_name=None,
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

## Testing

Inject test doubles via constructors:
```python
orchestrator = AgentOrchestrator(
    registry=mock_registry,
    output=CapturingOutput(),  # Capture instead of print
    enable_semantic_search=False,  # Disable for tests
    ...
)
```

See `tests/helpers.py` for `ConfigurableTestOrchestrator`.
