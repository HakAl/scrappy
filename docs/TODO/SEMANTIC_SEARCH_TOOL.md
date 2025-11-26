# Semantic Search Tool Implementation Plan

## Overview

Expose the existing semantic search infrastructure (`src/context/semantic/`) as an agent tool. The core functionality is complete - this plan covers only the thin tool wrapper and DI wiring.

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
