
## Phase 1: Core Tool + ToolContext Extension

1. Add `semantic_search: Optional[SemanticSearchProtocol]` to ToolContext
2. Create SemanticSearchTool (`codebase_search`) with `success=True` on unavailable
3. Register in ToolRegistry
4. Wire SemanticSearchManager into ToolContext via CodeAgent
5. Update FindExactTextTool description to emphasize "exact match only"

## Phase 2: AgentContextFactory + Dynamic Tool Filtering

1. Create AgentContext dataclass (system_prompt, active_tools, passive_rag_context)
2. Create AgentContextFactory that:
   - Filters out `codebase_search` when index not ready
   - Computes passive RAG context string
   - Builds search strategy prompt section
3. Implement budget heuristics (file refs, identifiers boost budget)
4. Add `passive_rag_enabled`, `passive_rag_max_tokens` to AgentConfig

## Phase 3: Stateless AgentLoop Integration

1. Modify AgentLoop.think() to accept AgentContext parameter
2. RAG injection happens in CodeAgent before think()
3. Wire factory into CodeAgent

---