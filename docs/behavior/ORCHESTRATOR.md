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

## Key Protocols

- `OutputInterface` - Swappable output (production vs test)
- `Orchestrator` - Type hints for any orchestrator implementation

## Testing

Inject test doubles via constructors:
```python
orchestrator = AgentOrchestrator(
    registry=mock_registry,
    output=CapturingOutput(),  # Capture instead of print
    ...
)
```

See `tests/helpers.py` for `ConfigurableTestOrchestrator`.
