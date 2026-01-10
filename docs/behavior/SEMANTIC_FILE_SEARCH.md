# Semantic File Search

Vector-based semantic search for codebase understanding using LanceDB and FastEmbed.

## Integration Points

Semantic search is used at two levels:

| Level | Component | Usage |
|-------|-----------|-------|
| **Orchestrator** | `CodebaseContext.augment_prompt()` | Implicit context injection when `use_context=True` |
| **Graph Agent** | `SemanticSearchTool` (`codebase_search`) | Explicit tool LLM can call |
| **Graph Agent** | `ContextFactory` | RAG context in system prompt |

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
| `ContextFactory` | `graph/context_factory.py` | RAG context augmentation |

## Graph Agent Integration

### SemanticSearchTool (`codebase_search`)

```python
# Tool the LLM can call explicitly
tool = SemanticSearchTool(semantic_search=provider)
result = tool.execute(ctx, query="how does auth work", max_tokens=4000)
```

When unavailable, returns `success=True` with guidance message (prevents LLM panic).

### ContextFactory

Builds RAG context for the think node:
1. **Search strategy** - Builds search guidance based on available tools
2. **RAG context** - Fetches relevant code for the current task

```python
factory = ContextFactory(semantic_manager=manager)
rag_context = factory.build_rag_context(task)
search_strategy = factory.build_search_strategy_section(tool_names)
# Used in build_system_prompt() for think node
```

## Orchestrator Integration

`CodebaseContext` uses semantic search in `augment_prompt()`:

```python
# When use_context=True in delegate()
augmented = context.augment_prompt(prompt)
# Uses semantic search to find relevant code
```

## Database Location

Index stored at: `{project}/.scrappy/lancedb/`
