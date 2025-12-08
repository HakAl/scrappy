# Semantic File Search

Vector-based semantic search for codebase understanding using LanceDB and FastEmbed.

## Integration Points

Semantic search is used at two levels:

| Level | Component | Usage |
|-------|-----------|-------|
| **Orchestrator** | `CodebaseContext.augment_prompt()` | Implicit context injection when `use_context=True` |
| **Agent** | `SemanticSearchTool` (`codebase_search`) | Explicit tool LLM can call |
| **Agent** | `AgentContextFactory` | Passive RAG in system prompt |

## Architecture Diagram

```
                      +-------------------+
                      |   User Config     |
                      | (.scrappy/config) |
                      +--------+----------+
                               |
                               v
  +------------------+   +-----+------+   +-------------------+
  | FilePrioritizer  |-->|  File      |-->| SemanticFile      |
  | Protocol         |   | Collector  |   | Collector         |
  +------------------+   +------------+   +-------------------+
                                                |
                                                v
  +------------------+   +------------+   +-----+-------------+
  | Composite        |-->|  LanceDB   |-->| cleanup_deleted   |
  | CodeChunker      |   | Provider   |   | _files()          |
  +--------+---------+   +-----+------+   +-------------------+
           |                   |
           v                   v
  +--------+---------+   +-----+-------------+
  | PythonASTChunker |   | ResultRanker      |
  | (+ future langs) |   | Protocol          |
  +------------------+   +-------------------+
                               |
                               v
                      +--------+----------+
                      | Ranked Search     |
                      | Results           |
                      +-------------------+
```

## Key Components

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `LanceDBSearchProvider` | `context/semantic/provider.py` | Vector storage, hybrid search |
| `SemanticSearchManager` | `context/semantic_manager.py` | Manages indexing lifecycle |
| `SemanticSearchInitializer` | `context/semantic/initializer.py` | Background initialization |
| `SemanticCodeChunker` | `context/code_chunker.py` | Splits code into chunks |
| `SemanticSearchTool` | `agent_tools/tools/semantic_search_tool.py` | Agent tool wrapper |
| `AgentContextFactory` | `agent/context_factory.py` | Passive RAG, tool filtering |

## Agent Integration

### SemanticSearchTool (`codebase_search`)

```python
# Tool the LLM can call explicitly
tool = SemanticSearchTool(semantic_search=provider)
result = tool.execute(ctx, query="how does auth work", max_tokens=4000)
```

When unavailable, returns `success=True` with guidance message (prevents LLM panic).

### AgentContextFactory

Builds per-iteration context with:
1. **Passive RAG** - Pre-fetches relevant code into system prompt
2. **Tool filtering** - Hides `codebase_search` until index ready

```python
factory = AgentContextFactory(
    semantic_manager=manager,
    config=config,
    tool_registry=registry,
)
context = factory.build_context(task, base_prompt)
# context.system_prompt includes relevant code
# context.active_tools excludes unavailable tools
```

### Configuration

In `AgentConfig`:
- `passive_rag_enabled` - Enable passive RAG (default: True)
- `passive_rag_max_tokens` - Token budget (default: 2000)

## Orchestrator Integration

`CodebaseContext` uses semantic search in `augment_prompt()`:

```python
# When use_context=True in delegate()
augmented = context.augment_prompt(prompt)
# Uses semantic search to find relevant code
```

## Database Location

Index stored at: `{project}/.scrappy/lancedb/`
