# Graph Agent VS Orchestrator

## Core Responsibilities

| Aspect | Graph Agent | Orchestrator |
|--------|-------------|--------------|
| **Primary Role** | Reason, decide actions, execute tools | Route to providers, handle retries |
| **LLM Interaction** | Think node calls LLM service | LiteLLM Router selects providers |
| **Context** | ContextFactory builds RAG context | Augments prompts with codebase context |
| **Semantic Search** | Explicit tool + RAG in system prompt | Implicit context augmentation |

## Semantic Search Integration

Both graph agent and orchestrator use semantic search, but differently:

```
Orchestrator (implicit)                 Graph Agent (explicit)
=======================                 ======================
CodebaseContext                         ContextFactory
    |                                       |
    +-- augment_prompt()                    +-- build_rag_context()
    |       |                               |
    |       +-- Semantic search             +-- build_search_strategy_section()
    |           for context                 |
    |                                       +-- SemanticSearchTool
    +-- use_context=True in                     |
        delegate() calls                        +-- LLM calls codebase_search
```

**Orchestrator**: When `use_context=True`, automatically injects relevant code into prompts.

**Graph Agent**:
1. `ContextFactory` builds RAG context for system prompt
2. `codebase_search` tool lets LLM explicitly search when needed
3. Think node includes context in system prompt

## Provider Selection

Graph agent uses LiteLLM Router for provider selection:

```python
# Graph agent uses tier-based selection:
response = llm_service.completion_sync(
    model="fast",  # or "quality" - tier, not specific provider
    messages=messages,
    ...
)
```

LiteLLM Router decides based on:
- Model tier (fast vs quality)
- Current rate limit status
- Provider availability
- Fallback chains

## Benefits

- Automatic provider rotation via LiteLLM Router
- Rate limiting handled transparently
- Graph nodes stay focused on their responsibility
- Easy to add new providers without touching graph code
- Semantic search works at both levels