# Semantic Search Tool 

## Implementation Details

Look here: docs/TODO/SEMANTIC_SEARCH_TOOL.md

---

## Concerns to Address During Implementation

1. **SearchResult Structure**: Verify `result.chunks[0]["path"]`, `["lines"]`, `["content"]`, `["score"]` match actual protocol

2. **remember_search() Signature**: Verify `context.remember_search(query, files)` signature in base.py

3. **Wiring Path**: Trace `OrchestratorFactory -> codebase_context -> semantic_manager` to find correct injection point

4. **DI Cycle**: Filter tools by name string, not by importing tool classes:
   ```python
   active_tools = [t for t in all_tools if t.name != "codebase_search"]
   ```

---
## Current State Summary

  | Component                   | Status                     | Location                                      |
  |-----------------------------|----------------------------|-----------------------------------------------|
  | SemanticSearchProtocol      | EXISTS                     | src/scrappy/context/protocols.py:639          |
  | LanceDBSearchProvider       | EXISTS                     | src/scrappy/context/semantic/provider.py      |
  | SemanticSearchManager       | EXISTS                     | src/scrappy/context/semantic_manager.py       |
  | ToolBase/ToolContext        | EXISTS                     | src/scrappy/agent_tools/tools/base.py         |
  | ToolRegistry                | EXISTS                     | src/scrappy/agent_tools/tools/registry.py     |
  | FindExactTextTool           | EXISTS                     | src/scrappy/agent_tools/tools/search_tools.py |
  | AgentLoop                   | EXISTS (already stateless) | src/scrappy/agent/agent_loop.py               |
  | SemanticSearchTool          | EXISTS                     | -                                             |
  | ToolContext.semantic_search | EXISTS                     | -                                             |
  | AgentContextFactory         | EXISTS                     | -                                             |

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Tool name | `codebase_search` | Primary search, emphasizes semantic |
| Mode parameter | NONE | LanceDB hybrid auto-balances |
| Unavailable behavior | `success=True` with guidance | LLMs panic on False |
| Dynamic tool filtering | YES | Don't present unusable tools |
| Passive RAG | YES | Makes app smart |
| Budget heuristics | File refs, identifiers boost | Simple regex, clear rationale |


## Phase 3: Stateless AgentLoop Integration

1. Modify AgentLoop.think() to accept AgentContext parameter
2. RAG injection happens in CodeAgent before think()
3. Wire factory into CodeAgent