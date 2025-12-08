# Agent VS Orchestrator

## Core Responsibilities

| Aspect | Agent | Orchestrator |
|--------|-------|--------------|
| **Primary Role** | Decide what to do (reason, plan, execute tools) | Decide which provider to use |
| **LLM Interaction** | Sends prompts via orchestrator | Routes to providers, handles retries |
| **Context** | Builds per-iteration context with RAG | Augments prompts with codebase context |
| **Semantic Search** | Explicit tool + passive RAG in system prompt | Implicit context augmentation |

## Semantic Search Integration

Both agent and orchestrator use semantic search, but differently:

```
Orchestrator (implicit)                 Agent (explicit)
=======================                 ================
CodebaseContext                         AgentContextFactory
    |                                       |
    +-- augment_prompt()                    +-- Passive RAG (system prompt)
    |       |                               |
    |       +-- Semantic search             +-- Tool filtering
    |           for context                 |
    |                                       +-- SemanticSearchTool
    +-- use_context=True in                     |
        delegate() calls                        +-- LLM calls codebase_search
```

**Orchestrator**: When `use_context=True`, automatically injects relevant code into prompts.

**Agent**:
1. `AgentContextFactory` pre-fetches relevant context into system prompt (passive RAG)
2. `codebase_search` tool lets LLM explicitly search when needed
3. Tool is hidden until index is ready (dynamic filtering)

## Provider Selection

Agent delegates provider selection to orchestrator:

```python
# Agent should NOT hardcode providers:
response = self.orch.delegate('gemini', prompt, ...)  # Bad

# Agent lets orchestrator decide:
response = self.orch.delegate(
    provider_name=None,  # Let orchestrator pick
    prompt=prompt,
    ...
)
```

Orchestrator decides based on:
- Task type requirements (planning vs execution)
- Current rate limit status
- Provider availability
- Provider health/error rates

## Benefits

- Rate limiting actually works
- Provider rotation when limits approached
- Agent code stays clean and focused
- Easy to add new providers without touching agent
- Semantic search works at both levels