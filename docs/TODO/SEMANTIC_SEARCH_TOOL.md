# Semantic Search Tool Implementation Plan

# PLAN REVIEW

**Three critical architectural risks** and **two simplifications** that will save you lines of code and debugging time.

### 1. Critical Architecture Fixes

#### A. The `AgentLoop` State Problem
**The Issue:** Your plan has `AgentContextFactory` deciding the strategy per query, but `AgentLoop` seems to be designed as a persistent object.
In your plan:
1. `CodeAgent` calls `factory.build_context()`.
2. `CodeAgent` calls `loop.think()`.
3. But `loop.think()` in your snippet relies on `self._passive_rag_enabled` (internal state).

**The Fix:** Don't set state on the loop. Pass the **Context** into `think()`.
Make `AgentLoop.think` stateless regarding configuration.

```python
# In AgentLoop
def think(self, state: ConversationState, context: AgentContext) -> AgentThought:
    # Use context.system_prompt
    # Use context.tools
    # Use context.enable_passive_rag
```

This ensures that if the index finishes processing *during* a conversation, the very next turn picks it up automatically without you having to call `loop.set_passive_rag()`.

#### B. The "Mode" Parameter Over-Engineering
**The Issue:** You added a `mode` parameter (`auto`, `semantic`, `keyword`) and a regex-based `_detect_mode` method in the tool.
**The Reality:** LLMs are terrible at selecting abstract "modes". Furthermore, unless your `LanceDBSearchProvider` explicitly supports switching between sparse (BM25) and dense (Vector) retrieval based on a flag, this is a "placebo button."

**The Fix:** **Delete the `mode` parameter.**
Modern vector stores (and LanceDB specifically) handle Hybrid Search internally.
*   If the query is "auth_token_provider", the sparse (keyword) score will naturally dominate.
*   If the query is "how does auth work", the dense (vector) score will dominate.
*   *Result:* You save ~30 lines of regex logic and prompt token space.

#### C. The Dependency Injection (DI) Cycle
**The Issue:**
`AgentContextFactory` needs `ToolRegistry`.
`ToolRegistry` imports `SemanticSearchTool`.
`SemanticSearchTool` needs `ToolContext`.
`CodeAgent` initializes all of them.

**The Fix:** Ensure `AgentContextFactory` receives the **Tool Instances**, not the Registry, or allow the Registry to return a subset.
In your `AgentContextFactory.build_context`:
```python
# Don't list_all() every time.
# The tools should be constant, but the LIST passed to the LLM changes.
all_tools = self._tool_registry.list_all()
if not is_semantic_ready:
    # Filter out the semantic tool by name
    tools = [t for t in all_tools if t.name != "codebase_search"]
```

---

### 2. Code Review & Refinements

#### Refinement 1: `AgentContextFactory` Budget Logic
Your heuristic for `_estimate_context_budget` is good, but `query.split() < 10` is risky for code.
*   *Query:* `Fix bug in UserFactory.java null pointer` (7 words) -> Requires LOTS of context.
*   *Fix:* Checks for code extension or CamelCase words in the query. If the user mentions a specific filename, boost the budget.

#### Refinement 2: The `SemanticSearchTool` Error Handling
In `src/agent_tools/tools/semantic_search_tool.py`:
You return a `ToolResult(success=False)` if the index isn't ready.
**Change this to `success=True`**.

*   *Why?* If you return `success=False`, many LLMs treat this as a "system error" and panic or retry the exact same loop.
*   *Better Output:*
    ```text
    (Success=True)
    OUTPUT: [System Notification] Semantic search is currently initializing (45%).
    Please use 'find_exact_text' (grep) for now, or use 'list_files' to explore.
    ```
    This allows the LLM to gracefully pivot ("Oh, I see, I will use grep instead") rather than thinking the tool is broken.

---

### 3. Revised Modifications


#### 1. Core Tool (No `mode`, simpler error handling)
**`src/agent_tools/tools/semantic_search_tool.py`**
```python
class SemanticSearchTool(ToolBase):
    @property
    def name(self) -> str: return "codebase_search"
    # ... description ...
    @property
    def parameters(self):
        # REMOVED: "mode" parameter
        return [
            ToolParameter("query", str, "Natural language query...", required=True),
            ToolParameter("max_results", int, default=10)
        ]

    def execute(self, context, **kwargs):
        if not context.semantic_search or not context.semantic_search.is_indexed():
            # Return SUCCESS so the agent can read the message and pivot
            return ToolResult(success=True, output="Index not ready. Use find_exact_text.")
        
        # ... standard search ...
```

#### 2. Agent Context (Stateless)
**`src/agent/context_factory.py`**
```python
@dataclass
class AgentContext:
    system_prompt: str
    active_tools: list[ToolBase] # Tools enabled for THIS turn
    passive_rag_context: Optional[str] # The actual string to inject, not just the boolean
```

#### 3. Integration Point
```python
# Inside the main loop
user_input = input("> ")

# 1. Build Context
ctx = self.context_factory.build_context(user_input)

# 2. Augment Query (Passive RAG)
actual_input = user_input
if ctx.passive_rag_context:
    actual_input = f"{ctx.passive_rag_context}\n\nUser: {user_input}"

# 3. Think (Pass tools explicitly)
thought = self.agent_loop.think(
    state=self.state,
    input=actual_input,
    tools=ctx.active_tools,         # Dynamic tool list
    system_prompt=ctx.system_prompt # Dynamic prompt
)
```

### Summary
1.  **Drop the `mode` parameter** (it's fake complexity).
2.  **Make `think()` stateless** (pass the context in).
3.  **Return `success=True` on index-not-ready** (so the agent can recover).

# END PLAN REVIEW

# Extended Scope: Supporting Features

This section defines the supporting infrastructure needed to make semantic search effective.
The semantic search tool alone is not enough - we need prompt engineering, tool biasing,
and automatic context injection to guide the LLM toward effective usage.

---

## Design Decisions (Locked In)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Passive RAG token budget | Global default + query heuristics | System adjusts based on file refs, identifiers, query complexity |
| Indexing trigger | Autonomous only | Tool reports status, doesn't trigger indexing |
| Hybrid search params | No `mode` param - LanceDB handles internally | Sparse/dense scoring auto-balances based on query type |
| RAG caching | No caching | Fresh search each turn; avoids stale/wrong context |
| AgentLoop state | Stateless - pass AgentContext into think() | Enables mid-conversation index readiness changes |
| Tool unavailable behavior | Return success=True with guidance | LLMs panic on success=False; graceful pivot instead |

---

## Feature 1: AgentContextFactory

**Purpose:** Coordinate prompt, tools, and RAG strategy based on semantic search availability.

**File:** `src/agent/context_factory.py` (NEW)

### Protocol

```python
@dataclass
class AgentContext:
    """Runtime context for agent execution - passed into think()."""
    system_prompt: str
    active_tools: list[ToolBase]          # Tools enabled for THIS turn
    passive_rag_context: Optional[str]    # Pre-computed context string to inject


class AgentContextFactoryProtocol(Protocol):
    """Builds agent context based on system state."""

    def build_context(self, query: str) -> AgentContext:
        """Build context for a specific query."""
        ...
```

### Implementation

```python
import re
from typing import Optional
from dataclasses import dataclass


class AgentContextFactory:
    """
    Builds agent execution context based on semantic search availability.

    Coordinates:
    - System prompt (with appropriate search strategy section)
    - Tool list (filters out codebase_search when not ready)
    - Passive RAG (pre-computes context string)
    """

    def __init__(
        self,
        semantic_manager: Optional[SemanticSearchManager],
        context_augmenter: Optional[ContextAugmenter],
        prompt_builder: SystemPromptBuilder,
        tool_registry: ToolRegistry,
        config: AgentConfig,
    ):
        self._semantic_manager = semantic_manager
        self._context_augmenter = context_augmenter
        self._prompt_builder = prompt_builder
        self._tool_registry = tool_registry
        self._config = config

    def build_context(self, query: str) -> AgentContext:
        """Build context for a specific query."""
        is_semantic_ready = self._is_semantic_ready()

        # Build prompt with appropriate search strategy
        self._prompt_builder.set_section(
            "search_strategy",
            self._build_search_strategy_section(is_semantic_ready)
        )
        system_prompt = self._prompt_builder.build()

        # Filter tools based on semantic availability
        all_tools = self._tool_registry.list_all()
        if is_semantic_ready:
            active_tools = all_tools
        else:
            # Remove semantic search tool when not ready
            active_tools = [t for t in all_tools if t.name != "codebase_search"]

        # Compute passive RAG context (the actual string, not just a flag)
        passive_rag_context = None
        if is_semantic_ready and self._config.passive_rag_enabled and self._context_augmenter:
            budget = self._estimate_context_budget(query)
            passive_rag_context = self._context_augmenter.get_relevant_context(
                query=query,
                max_tokens=budget,
            )
            # Don't inject empty context
            if not passive_rag_context or not passive_rag_context.strip():
                passive_rag_context = None

        return AgentContext(
            system_prompt=system_prompt,
            active_tools=active_tools,
            passive_rag_context=passive_rag_context,
        )

    def _is_semantic_ready(self) -> bool:
        """Check if semantic search is available."""
        if not self._semantic_manager:
            return False
        return self._semantic_manager.is_ready()

    def _estimate_context_budget(self, query: str) -> int:
        """
        Adjust passive RAG budget based on query characteristics.

        Smarter than word count - checks for file references and identifiers.
        """
        base_budget = self._config.passive_rag_max_tokens

        # File reference (e.g., "UserFactory.java", "auth.py") = needs more context
        if re.search(r'\.\w{2,4}\b', query):
            return int(base_budget * 1.5)

        # Identifier pattern (CamelCase or snake_case) = needs more context
        if re.search(r'[A-Z][a-z]+[A-Z]|_\w+_', query):
            return int(base_budget * 1.5)

        # Refactoring/architecture queries = needs more context
        if any(word in query.lower() for word in ['refactor', 'architecture', 'all', 'every']):
            return int(base_budget * 1.5)

        # Short natural language without code patterns = less context
        words = query.split()
        has_code_patterns = re.search(r'[A-Z]{2,}|_|\.|::', query)
        if len(words) < 8 and not has_code_patterns:
            return base_budget // 2

        return base_budget

    def _build_search_strategy_section(self, semantic_available: bool) -> str:
        """Build search strategy instructions based on availability."""
        if semantic_available:
            return """
## Information Retrieval Strategy

1. **Semantic First:** When asked to find, explain, or fix code, ALWAYS start
   with `codebase_search`. This finds relevant code even when terminology differs.

2. **Exact Match Second:** Only use `find_exact_text` if:
   - User provides a specific error ID (e.g., `ERR-402`)
   - Performing rename refactor needing every usage
   - Semantic search returned no results

3. **Read Files:** After finding relevant code, use `read_file` to examine
   full context before making changes.
"""
        else:
            return """
## Information Retrieval Strategy

NOTE: Semantic search is currently UNAVAILABLE (index not ready).

1. Use `find_exact_text` for code discovery with specific keywords.
2. If query is vague (e.g., "how does auth work?"), ask user for
   specific keywords or file names to search.
3. Use `list_files` and `list_directory` to explore codebase structure.
"""
```

### Integration Point

In `CodeAgent.__init__` or agent setup:

```python
self._context_factory = AgentContextFactory(
    semantic_manager=self._semantic_manager,
    context_augmenter=self._context_augmenter,
    prompt_builder=self._prompt_builder,
    tool_registry=self._tool_registry,
    config=self._config,
)
```

In the main loop (query handling):

```python
# 1. Build context for this query
ctx = self._context_factory.build_context(user_query)

# 2. Augment query with passive RAG context if available
actual_input = user_query
if ctx.passive_rag_context:
    actual_input = f"[Relevant Code Context]\n{ctx.passive_rag_context}\n\n[User Query]\n{user_query}"

# 3. Call think() with context (stateless)
thought = self._agent_loop.think(
    state=self._state,
    user_input=actual_input,
    context=ctx,  # Pass context explicitly
)
```

---

## Feature 2: Stateless AgentLoop

**Purpose:** Make AgentLoop stateless regarding configuration - receive context per-call.

**File:** Modify `src/agent/agent_loop.py`

### Key Principle

AgentLoop should NOT hold RAG/tool configuration state. Each call to `think()` receives
its configuration explicitly via `AgentContext`. This ensures:
- Mid-conversation index readiness changes take effect immediately
- No temporal coupling between factory and loop
- Easier testing (no hidden state)

### Changes to AgentLoop

```python
class AgentLoop:
    def __init__(
        self,
        orchestrator: "OrchestratorAdapter",
        action_executor: ActionExecutorProtocol,
        response_parser: ResponseParserProtocol,
        ui: AgentUIProtocol,
        config: "AgentConfig",
        # ... other existing params ...
        # REMOVED: context_augmenter (now handled by factory)
        # REMOVED: _passive_rag_enabled state
        # REMOVED: _passive_rag_budget state
    ):
        # ... existing init, no RAG state ...

    def think(
        self,
        state: ConversationState,
        context: AgentContext,  # NEW: explicit context per call
    ) -> AgentThought:
        """
        Generate the next thought/action from the LLM.

        Args:
            state: Current conversation state
            context: AgentContext with system_prompt, tools, etc.
        """
        # Use context.system_prompt instead of state.system_prompt
        # Use context.active_tools for tool schemas

        current_provider = self._provider_strategy.get_planner()

        # ... existing provider selection ...

        # Build user prompt from conversation history
        if len(state.messages) == 2:
            user_prompt = state.messages[-1]['content']
        else:
            # ... existing history building ...

        # NOTE: Passive RAG injection happens BEFORE this method is called
        # The caller (CodeAgent) pre-augments the user message with context
        # This keeps AgentLoop stateless and focused on the think-plan-execute cycle

        # Get tool schemas from context (dynamic per-call)
        tools = [t.to_openai_schema() for t in context.active_tools]

        response = self._orchestrator.delegate_with_tools(
            provider_name=current_provider,
            prompt=user_prompt,
            tools=tools,
            system_prompt=context.system_prompt,  # From context, not state
            # ...
        )

        # ... rest of think() ...
```

### Where RAG Injection Happens

RAG injection is done by the **caller** (CodeAgent), NOT inside AgentLoop:

```python
# In CodeAgent or main loop
ctx = self._context_factory.build_context(user_query)

# Augment BEFORE calling think()
actual_input = user_query
if ctx.passive_rag_context:
    actual_input = f"[Relevant Code Context]\n{ctx.passive_rag_context}\n\n[User Query]\n{user_query}"

# Update conversation state with augmented input
state.messages.append({"role": "user", "content": actual_input})

# Call think() - it just uses what it's given
thought = self._agent_loop.think(state=state, context=ctx)
```

### Config Additions

In `src/agent_config.py`:

```python
@dataclass
class AgentConfig:
    # ... existing fields ...

    # Passive RAG settings (used by AgentContextFactory)
    passive_rag_enabled: bool = True
    passive_rag_max_tokens: int = 2000
```

---

## Feature 3: Tool Description Biasing

**Purpose:** Make LLM prefer semantic search for discovery, grep for exact matches.

### A. Rename SearchCodeTool

**File:** `src/agent_tools/tools/search_tools.py`

```python
class FindExactTextTool(ToolBase):
    """Exact text/pattern search - use for precise string matching."""

    @property
    def name(self) -> str:
        return "find_exact_text"

    @property
    def description(self) -> str:
        return (
            "Strict exact-match text search. Only use when you know the precise, "
            "case-sensitive string (e.g., a specific error code, variable name, or "
            "function signature) and need to find every occurrence. "
            "Do NOT use for general conceptual questions."
        )

    # ... rest unchanged ...
```

### B. Update SemanticSearchTool

**File:** `src/agent_tools/tools/semantic_search_tool.py`

**Key changes:**
1. Name: `codebase_search`
2. NO `mode` parameter (LanceDB hybrid search handles this internally)
3. Return `success=True` when unavailable (so LLM can pivot gracefully)

```python
class SemanticSearchTool(ToolBase):
    """Primary search tool for codebase exploration."""

    @property
    def name(self) -> str:
        return "codebase_search"

    @property
    def description(self) -> str:
        return (
            "The PRIMARY search tool. Searches codebase using natural language. "
            "Use this to find code logic, concepts, functionality, or when unsure "
            "of exact names. ALWAYS use this first for exploration and discovery."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        # SIMPLIFIED: No mode parameter - LanceDB handles hybrid search internally
        return [
            ToolParameter(
                "query",
                str,
                "Natural language search query (e.g., 'authentication logic', 'error handling')",
                required=True,
            ),
            ToolParameter(
                "max_results",
                int,
                "Maximum number of results to return",
                required=False,
                default=10,
            ),
        ]

    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        query = kwargs["query"]
        max_results = kwargs.get("max_results", 10)

        # CRITICAL: Return success=True so LLM can read message and pivot
        # Returning success=False causes LLMs to panic/retry
        if context.semantic_search is None:
            return ToolResult(
                success=True,  # NOT False!
                output=(
                    "[Notice] Semantic search is not available. "
                    "The index may still be initializing.\n"
                    "Please use `find_exact_text` for keyword search, "
                    "or `list_files` to explore the codebase structure."
                ),
                metadata={"unavailable": True},
            )

        if not context.semantic_search.is_indexed():
            return ToolResult(
                success=True,  # NOT False!
                output=(
                    "[Notice] Semantic search index is not ready yet.\n"
                    "Please use `find_exact_text` for keyword search, "
                    "or `list_files` to explore the codebase structure."
                ),
                metadata={"unavailable": True, "reason": "not_indexed"},
            )

        try:
            result = context.semantic_search.search(
                query=query,
                max_results=max_results,
            )

            if not result.chunks:
                return ToolResult(
                    success=True,
                    output=f"No results found for: {query}",
                    metadata={"matches": 0, "query": query},
                )

            output = self._format_results(result)
            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "matches": len(result.chunks),
                    "query": query,
                    "tokens_used": result.tokens_used,
                },
            )

        except Exception as e:
            # Even errors return success=True with explanation
            return ToolResult(
                success=True,
                output=f"[Error] Semantic search failed: {str(e)}\nTry `find_exact_text` instead.",
                metadata={"error": str(e)},
            )
```

### Why No Mode Parameter?

LanceDB's hybrid search automatically balances sparse (BM25) and dense (vector) scoring:
- Query `"auth_token_provider"` -> BM25 naturally dominates (exact identifier)
- Query `"how does authentication work"` -> Vector naturally dominates (conceptual)

Adding a `mode` parameter would be a "placebo button" - it looks like control but
provides no value. The ~30 lines of regex detection logic were deleted.

---

## Feature 4: System Prompt Strategy Section

**Purpose:** Explicitly instruct LLM on search tool selection order.

**File:** `src/agent/system_prompt_builder.py`

Already covered in Feature 1 (AgentContextFactory._build_search_strategy_section).

The section is injected via:
```python
self._prompt_builder.set_section("search_strategy", strategy_text)
```

---

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `src/agent/context_factory.py` | NEW | AgentContextFactory + AgentContext dataclass |
| `src/agent/protocols.py` | MODIFY | Add AgentContextFactoryProtocol |
| `src/agent/agent_loop.py` | MODIFY | Accept AgentContext in think(), remove RAG state |
| `src/agent/core.py` | MODIFY | Wire factory, handle RAG injection before think() |
| `src/agent/system_prompt_builder.py` | MODIFY | Support set_section() for search_strategy |
| `src/agent_tools/tools/search_tools.py` | MODIFY | Rename to FindExactTextTool, update description |
| `src/agent_tools/tools/semantic_search_tool.py` | NEW | codebase_search tool (no mode param, success=True on unavailable) |
| `src/agent_tools/tools/base.py` | MODIFY | Add semantic_search to ToolContext |
| `src/agent_config.py` | MODIFY | Add passive_rag_enabled, passive_rag_max_tokens |
| `tests/agent/test_context_factory.py` | NEW | Unit tests for factory |
| `tests/agent/test_agent_loop_stateless.py` | NEW | Tests for stateless think() |

---

## Implementation Order

1. **Phase 1: Semantic Search Tool**
   - Create `codebase_search` tool with success=True error handling
   - Extend ToolContext with semantic_search field
   - Register in ToolRegistry

2. **Phase 2: Tool Description Biasing**
   - Rename search_code -> find_exact_text
   - Update descriptions to bias LLM toward semantic search

3. **Phase 3: AgentContextFactory**
   - Create factory with AgentContext dataclass
   - Implement tool filtering, budget heuristics, RAG context computation
   - Add search strategy section builder

4. **Phase 4: Stateless AgentLoop**
   - Modify think() to accept AgentContext parameter
   - Remove internal RAG state
   - Update CodeAgent to handle RAG injection before think()

5. **Phase 5: Config + Wiring**
   - Add passive_rag_* to AgentConfig
   - Wire factory into CodeAgent
   - Integration testing

---

## Testing Strategy

### Context Factory Tests

```python
class TestAgentContextFactory:
    def test_semantic_ready_returns_rag_context(self):
        """When semantic ready, factory returns pre-computed RAG context."""
        manager = Mock()
        manager.is_ready.return_value = True

        augmenter = Mock()
        augmenter.get_relevant_context.return_value = "def authenticate(): ..."

        factory = AgentContextFactory(
            semantic_manager=manager,
            context_augmenter=augmenter,
            ...
        )
        context = factory.build_context("find auth logic")

        assert context.passive_rag_context == "def authenticate(): ..."
        assert "codebase_search" not in context.system_prompt  # Strategy section, not tool list

    def test_semantic_not_ready_filters_tool_and_no_rag(self):
        """When semantic not ready, tool filtered out and no RAG context."""
        manager = Mock()
        manager.is_ready.return_value = False

        factory = AgentContextFactory(semantic_manager=manager, ...)
        context = factory.build_context("find auth logic")

        # No RAG context
        assert context.passive_rag_context is None

        # Tool filtered out
        tool_names = [t.name for t in context.active_tools]
        assert "codebase_search" not in tool_names
        assert "find_exact_text" in tool_names

        # Fallback prompt
        assert "UNAVAILABLE" in context.system_prompt

    def test_file_reference_boosts_budget(self):
        """Queries with file references get higher budget."""
        augmenter = Mock()
        augmenter.get_relevant_context.return_value = "code..."

        factory = AgentContextFactory(...)

        # Call with file reference
        factory.build_context("fix bug in UserFactory.java")

        # Verify augmenter called with boosted budget
        call_args = augmenter.get_relevant_context.call_args
        assert call_args[1]['max_tokens'] > factory._config.passive_rag_max_tokens

    def test_identifier_pattern_boosts_budget(self):
        """Queries with CamelCase/snake_case get higher budget."""
        augmenter = Mock()
        augmenter.get_relevant_context.return_value = "code..."

        factory = AgentContextFactory(...)
        factory.build_context("fix AuthTokenProvider null check")

        call_args = augmenter.get_relevant_context.call_args
        assert call_args[1]['max_tokens'] > factory._config.passive_rag_max_tokens
```

### Stateless AgentLoop Tests

```python
class TestStatelessAgentLoop:
    def test_think_uses_context_system_prompt(self):
        """think() uses system_prompt from AgentContext, not ConversationState."""
        loop = AgentLoop(...)

        context = AgentContext(
            system_prompt="Custom prompt from factory",
            active_tools=[...],
            passive_rag_context=None,
        )
        state = ConversationState(...)

        # Call think with explicit context
        thought = loop.think(state=state, context=context)

        # Verify orchestrator received context.system_prompt
        call_args = loop._orchestrator.delegate_with_tools.call_args
        assert call_args[1]['system_prompt'] == "Custom prompt from factory"

    def test_think_uses_context_tools(self):
        """think() uses active_tools from AgentContext."""
        loop = AgentLoop(...)

        # Context with filtered tools (no semantic search)
        context = AgentContext(
            system_prompt="...",
            active_tools=[find_exact_text_tool, read_file_tool],
            passive_rag_context=None,
        )

        thought = loop.think(state=state, context=context)

        # Verify only context tools passed to orchestrator
        call_args = loop._orchestrator.delegate_with_tools.call_args
        tool_names = [t['function']['name'] for t in call_args[1]['tools']]
        assert "codebase_search" not in tool_names
        assert "find_exact_text" in tool_names
```

### Semantic Search Tool Tests

```python
class TestSemanticSearchTool:
    def test_unavailable_returns_success_true(self):
        """When unavailable, returns success=True so LLM can pivot."""
        tool = SemanticSearchTool()
        context = ToolContext(project_root=Path("/tmp"), semantic_search=None)

        result = tool.execute(context, query="find auth")

        assert result.success is True  # NOT False!
        assert "find_exact_text" in result.output
        assert result.metadata.get("unavailable") is True

    def test_not_indexed_returns_success_true(self):
        """When not indexed, returns success=True with guidance."""
        mock_provider = Mock()
        mock_provider.is_indexed.return_value = False

        tool = SemanticSearchTool()
        context = ToolContext(
            project_root=Path("/tmp"),
            semantic_search=mock_provider,
        )

        result = tool.execute(context, query="find auth")

        assert result.success is True
        assert "not ready" in result.output.lower()
```

# END Extended Scope 

---

## Overview

Expose the existing semantic search infrastructure (`src/context/semantic/`) as an agent tool.
The core functionality is complete - this plan covers only the thin tool wrapper and DI wiring.

---

## Current State

### What Exists

1. **SemanticSearchProtocol** (`src/context/protocols.py:638-717`)
   - Full protocol definition with `search()`, `index_files()`, `is_indexed()`, `clear_index()`

2. **LanceDBSearchProvider** (`src/context/semantic/provider.py:111-931`)
   - Hybrid search (vector + full-text)
   - Incremental indexing with change detection
   - Configurable ranking via `ResultRankerProtocol`
   - Returns `SearchResult` with chunks, scores, token usage

3. **SemanticSearchInitializer** (`src/context/semantic/initializer.py`)
   - Background thread initialization for heavy dependencies
   - Non-blocking startup pattern

4. **Tool Infrastructure** (`src/agent_tools/tools/`)
   - `ToolBase` base class with parameter validation
   - `ToolContext` dataclass for shared resources
   - `ToolRegistry` for registration and schema generation

### What's Missing

- `SemanticSearchTool` class
- DI wiring to inject `SemanticSearchProtocol` into `ToolContext`
- Registration in `ToolRegistry.create_default()`

---

## Design Decisions

### 1. Dependency Injection Strategy

**Decision: Extend ToolContext with optional semantic_search field**

```python
@dataclass
class ToolContext:
    project_root: Path
    dry_run: bool = False
    config: Optional["AgentConfig"] = None
    orchestrator: Optional[MemoryProvider] = None
    semantic_search: Optional[SemanticSearchProtocol] = None  # NEW
```

**Rationale:**
- Follows existing pattern (`orchestrator` is already optional)
- No new abstractions needed
- Tool gracefully degrades when `semantic_search is None`
- Easy to inject mocks for testing

**Alternatives Considered:**
- Service locator pattern - Rejected (hidden dependencies, harder to test)
- Lazy instantiation in tool - Rejected (violates DI principle, hard to test)

### 2. Tool Availability

**Decision: Tool always registered, returns helpful error when unavailable**

When `context.semantic_search is None`:
```
Semantic search is not available. The index may not be initialized yet.
Run with --semantic-search flag or wait for background initialization.
```

**Rationale:**
- Consistent tool discovery (always appears in tool list)
- Clear error message guides user
- No conditional registration logic

### 3. Output Format

**Decision: Match existing search_code tool output style**

```
Found 5 relevant code chunks:

src/auth/login.py:45-67 (score: 0.89)
  def authenticate_user(username: str, password: str) -> User:
      """Authenticate user with username/password."""
      ...

src/auth/session.py:12-34 (score: 0.82)
  class SessionManager:
      """Manages user sessions with token refresh."""
      ...

[Token budget: 2450/4000]
```

**Rationale:**
- Familiar format for agents already using `search_code`
- Shows file path, line range, score, and preview
- Token budget visibility for context management

---

## Implementation

### Phase 1: Extend ToolContext

**File:** `src/agent_tools/tools/base.py`

```python
@dataclass
class ToolContext:
    project_root: Path
    dry_run: bool = False
    config: Optional["AgentConfig"] = None
    orchestrator: Optional[MemoryProvider] = None
    semantic_search: Optional["SemanticSearchProtocol"] = None  # ADD
```

Add import at top (TYPE_CHECKING block):
```python
if TYPE_CHECKING:
    from ...agent_config import AgentConfig
    from ...context.protocols import SemanticSearchProtocol  # ADD
```

### Phase 2: Create SemanticSearchTool

**File:** `src/agent_tools/tools/semantic_search_tool.py` (NEW)

```python
"""
Semantic code search tool for the code agent.

Provides natural language search over the codebase using vector embeddings.
"""

from .base import ToolBase, ToolParameter, ToolResult, ToolContext


class SemanticSearchTool(ToolBase):
    """
    Search codebase using natural language queries.

    Uses vector embeddings to find semantically similar code,
    not just text matches. Useful for queries like:
    - "authentication and login logic"
    - "error handling patterns"
    - "database connection code"
    """

    @property
    def name(self) -> str:
        return "semantic_search"

    @property
    def description(self) -> str:
        return (
            "Search codebase using natural language. "
            "Finds semantically similar code, not just text matches."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                "query",
                str,
                "Natural language search query (e.g., 'authentication logic')",
                required=True,
            ),
            ToolParameter(
                "max_results",
                int,
                "Maximum number of results to return",
                required=False,
                default=10,
            ),
            ToolParameter(
                "max_tokens",
                int,
                "Maximum tokens for results (context budget)",
                required=False,
                default=4000,
            ),
        ]

    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        query = kwargs["query"]
        max_results = kwargs.get("max_results", 10)
        max_tokens = kwargs.get("max_tokens", 4000)

        # Check if semantic search is available
        if context.semantic_search is None:
            return ToolResult(
                success=False,
                output="",
                error=(
                    "Semantic search is not available. "
                    "The index may not be initialized yet or dependencies are missing."
                ),
            )

        # Check if index exists
        if not context.semantic_search.is_indexed():
            return ToolResult(
                success=False,
                output="",
                error=(
                    "Semantic search index not found. "
                    "The codebase needs to be indexed first."
                ),
            )

        try:
            result = context.semantic_search.search(
                query=query,
                max_results=max_results,
                max_tokens=max_tokens,
            )

            if not result.chunks:
                return ToolResult(
                    success=True,
                    output=f"No results found for: {query}",
                    metadata={"matches": 0, "query": query},
                )

            # Format output
            output = self._format_results(result, max_tokens)

            # Store in working memory if available
            if context.orchestrator:
                context.remember_search(
                    f"semantic: {query}",
                    [c["path"] for c in result.chunks],
                )

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "matches": len(result.chunks),
                    "query": query,
                    "tokens_used": result.tokens_used,
                    "limit_hit": result.limit_hit,
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Semantic search failed: {str(e)}",
            )

    def _format_results(self, result, max_tokens: int) -> str:
        """Format search results for display."""
        lines = [f"Found {len(result.chunks)} relevant code chunks:", ""]

        for chunk in result.chunks:
            path = chunk["path"]
            start, end = chunk["lines"]
            score = chunk.get("score", 0.0)
            content = chunk["content"]

            # Header with path, lines, score
            lines.append(f"{path}:{start}-{end} (score: {score:.2f})")

            # Content preview (indented, truncated)
            preview_lines = content.strip().split("\n")[:5]
            for line in preview_lines:
                lines.append(f"  {line[:100]}")
            if len(content.strip().split("\n")) > 5:
                lines.append("  ...")

            lines.append("")

        # Token budget footer
        lines.append(f"[Token budget: {result.tokens_used}/{max_tokens}]")

        if result.limit_hit:
            lines.append(f"[Results truncated: {result.limit_hit}]")

        return "\n".join(lines)
```

### Phase 3: Register Tool

**File:** `src/agent_tools/tools/registry.py`

Update `create_default()`:

```python
@classmethod
def create_default(cls) -> "ToolRegistry":
    from .file_tools import (...)
    from .git_tools import (...)
    from .search_tools import SearchCodeTool
    from .semantic_search_tool import SemanticSearchTool  # ADD

    registry = cls()

    # ... existing registrations ...

    # Register search tools
    registry.register(SearchCodeTool())
    registry.register(SemanticSearchTool())  # ADD

    return registry
```

### Phase 4: Wire Up Provider Injection

**File:** `src/agent/core.py` (around line 302)

Update `_create_default_tool_context()`:

```python
def _create_default_tool_context(self):
    """Create default tool context."""
    return ToolContext(
        project_root=self.project_root,
        dry_run=self.dry_run,
        config=self.config,
        orchestrator=self,
        semantic_search=self._get_semantic_search(),  # ADD
    )

def _get_semantic_search(self):
    """Get semantic search provider if available."""
    # Check if initializer exists and has completed
    if hasattr(self, '_semantic_initializer') and self._semantic_initializer:
        if self._semantic_initializer.is_complete():
            return self._semantic_initializer.get_result()
    return None
```

**Note:** The exact wiring depends on where `SemanticSearchInitializer` is instantiated in the codebase. This may require tracing through the agent initialization flow.

---

## Testing Strategy

### Unit Tests

**File:** `tests/agent_tools/test_semantic_search_tool.py` (NEW)

```python
"""Tests for SemanticSearchTool."""

import pytest
from pathlib import Path
from unittest.mock import Mock

from src.agent_tools.tools.semantic_search_tool import SemanticSearchTool
from src.agent_tools.tools.base import ToolContext
from src.context.protocols import SearchResult


class TestSemanticSearchTool:
    """Test SemanticSearchTool behavior."""

    @pytest.fixture
    def tool(self):
        return SemanticSearchTool()

    @pytest.fixture
    def mock_search_provider(self):
        """Create mock semantic search provider."""
        provider = Mock()
        provider.is_indexed.return_value = True
        provider.search.return_value = SearchResult(
            chunks=[
                {
                    "path": "src/auth.py",
                    "lines": (10, 25),
                    "content": "def login(user, pwd):\n    pass",
                    "score": 0.85,
                }
            ],
            tokens_used=150,
            limit_hit=None,
        )
        return provider

    @pytest.fixture
    def context_with_search(self, tmp_path, mock_search_provider):
        """Context with semantic search available."""
        return ToolContext(
            project_root=tmp_path,
            semantic_search=mock_search_provider,
        )

    @pytest.fixture
    def context_without_search(self, tmp_path):
        """Context without semantic search."""
        return ToolContext(
            project_root=tmp_path,
            semantic_search=None,
        )

    @pytest.mark.unit
    def test_search_returns_results(self, tool, context_with_search):
        """Successful search returns formatted results."""
        result = tool.execute(context_with_search, query="login")

        assert result.success is True
        assert "src/auth.py:10-25" in result.output
        assert "score: 0.85" in result.output
        assert result.metadata["matches"] == 1

    @pytest.mark.unit
    def test_search_unavailable_returns_error(self, tool, context_without_search):
        """Returns error when semantic search not available."""
        result = tool.execute(context_without_search, query="login")

        assert result.success is False
        assert "not available" in result.error.lower()

    @pytest.mark.unit
    def test_search_not_indexed_returns_error(self, tool, tmp_path):
        """Returns error when index doesn't exist."""
        mock_provider = Mock()
        mock_provider.is_indexed.return_value = False

        context = ToolContext(
            project_root=tmp_path,
            semantic_search=mock_provider,
        )

        result = tool.execute(context, query="login")

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.unit
    def test_empty_results_handled(self, tool, tmp_path):
        """Empty results return success with message."""
        mock_provider = Mock()
        mock_provider.is_indexed.return_value = True
        mock_provider.search.return_value = SearchResult(
            chunks=[],
            tokens_used=0,
            limit_hit=None,
        )

        context = ToolContext(
            project_root=tmp_path,
            semantic_search=mock_provider,
        )

        result = tool.execute(context, query="nonexistent")

        assert result.success is True
        assert "No results" in result.output

    @pytest.mark.unit
    def test_search_exception_handled(self, tool, tmp_path):
        """Exceptions are caught and returned as errors."""
        mock_provider = Mock()
        mock_provider.is_indexed.return_value = True
        mock_provider.search.side_effect = Exception("Database error")

        context = ToolContext(
            project_root=tmp_path,
            semantic_search=mock_provider,
        )

        result = tool.execute(context, query="test")

        assert result.success is False
        assert "Database error" in result.error
```

### Integration Tests

**File:** `tests/integration/test_semantic_search_tool_integration.py` (NEW)

```python
"""Integration tests for semantic search tool with real provider."""

import pytest
from pathlib import Path

from src.agent_tools.tools.semantic_search_tool import SemanticSearchTool
from src.agent_tools.tools.base import ToolContext
from src.context.semantic import LanceDBSearchProvider
from src.context.semantic.chunkers import CompositeCodeChunker
from src.context.semantic.config import SemanticIndexConfig


@pytest.mark.integration
@pytest.mark.slow
class TestSemanticSearchToolIntegration:
    """Integration tests with real semantic search provider."""

    @pytest.fixture
    def indexed_provider(self, tmp_path):
        """Create and index a real provider."""
        # Create test files
        (tmp_path / "auth.py").write_text('''
def authenticate(username: str, password: str) -> bool:
    """Authenticate user credentials."""
    return check_password(username, password)
''')

        chunker = CompositeCodeChunker()
        config = SemanticIndexConfig.for_testing()
        provider = LanceDBSearchProvider(
            project_path=tmp_path,
            chunker=chunker,
            config=config,
        )

        # Index files
        files = {"auth.py": (tmp_path / "auth.py").read_text()}
        provider.index_files(files)

        return provider

    def test_end_to_end_search(self, tmp_path, indexed_provider):
        """Full search flow with real provider."""
        tool = SemanticSearchTool()
        context = ToolContext(
            project_root=tmp_path,
            semantic_search=indexed_provider,
        )

        result = tool.execute(context, query="user authentication")

        assert result.success is True
        assert "auth.py" in result.output
        assert result.metadata["matches"] >= 1
```

---

## Files Changed Summary

| File | Change |
|------|--------|
| `src/agent_tools/tools/base.py` | Add `semantic_search` field to `ToolContext` |
| `src/agent_tools/tools/semantic_search_tool.py` | NEW - Tool implementation |
| `src/agent_tools/tools/registry.py` | Register `SemanticSearchTool` |
| `src/agent/core.py` | Wire up provider injection |
| `tests/agent_tools/test_semantic_search_tool.py` | NEW - Unit tests |
| `tests/integration/test_semantic_search_tool_integration.py` | NEW - Integration tests |

---

## Open Questions

1. **Initialization Timing:** Where exactly is `SemanticSearchInitializer` created? Need to trace the startup flow to find the right injection point.

2. **Auto-Indexing:** Should the tool trigger indexing if not indexed? Current design says no (returns error), but could add a `--index` flag.

3. **Re-ranking Config:** Should tool expose `RankingConfig` parameters? Current design uses defaults for simplicity.

---

## Acceptance Criteria

- [ ] `semantic_search` tool appears in tool list
- [ ] Returns helpful error when provider unavailable
- [ ] Returns helpful error when index doesn't exist
- [ ] Successful search returns formatted results with scores
- [ ] Token budget is respected and displayed
- [ ] Unit tests pass with mocked provider
- [ ] Integration test passes with real provider
- [ ] No regressions in existing tool tests
