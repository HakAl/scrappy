# Pydantic-AI Library Research

**Bead**: scrappy-vle
**Status**: Complete
**Date**: 2025-12-25

## Overview

Pydantic-AI is a type-safe agent framework built on Pydantic, designed for building AI applications with:
- Strong typing and validation via Pydantic models
- Dependency injection for testability
- Tool registration via decorators
- Streaming support
- Multi-provider support with FallbackModel

## Key Concepts

### Agent Definition with Dependency Injection

```python
from dataclasses import dataclass
from pydantic_ai import Agent, RunContext

@dataclass
class AgentDeps:
    """Dependencies injected into agent tools."""
    project_root: str
    config: dict
    orchestrator: Any

agent = Agent(
    'groq:llama3-8b-8192',
    deps_type=AgentDeps,
    system_prompt="You are a helpful assistant.",
)
```

### Tool Registration

```python
@agent.tool
async def read_file(ctx: RunContext[AgentDeps], path: str) -> str:
    """Read a file from the project."""
    full_path = Path(ctx.deps.project_root) / path
    return full_path.read_text()

@agent.tool
async def list_directory(ctx: RunContext[AgentDeps], path: str = ".") -> list[str]:
    """List files in a directory."""
    full_path = Path(ctx.deps.project_root) / path
    return [f.name for f in full_path.iterdir()]
```

### Structured Output

```python
from pydantic import BaseModel

class TaskClassification(BaseModel):
    task_type: str
    confidence: float
    reasoning: str

classify_agent = Agent(
    'groq:llama3-8b-8192',
    output_type=TaskClassification,
    system_prompt="Classify user tasks into categories.",
)

result = classify_agent.run_sync("create a new file")
# result.output is TaskClassification instance
```

### FallbackModel for Multi-Provider

```python
from pydantic_ai.models import FallbackModel

model = FallbackModel(
    'groq:llama3-8b-8192',
    'cerebras:llama3.1-8b',
    'openai:gpt-4o-mini',
)

agent = Agent(model, deps_type=AgentDeps)
# Automatically falls back if rate limited
```

### Streaming Support

```python
async with agent.run_stream("Generate a summary") as result:
    async for chunk in result.stream_text():
        print(chunk, end='', flush=True)
```

## Scrappy Code Replacement Analysis

### 1. CodeAgent (core.py - 723 lines)

**Current Pattern**:
```python
class CodeAgent:
    def __init__(
        self,
        orchestrator: Union[OrchestratorAdapter, object],
        project_path: Optional[str] = None,
        config: Optional[AgentConfig] = None,
        tool_registry: Optional[ToolRegistryProtocol] = None,
        # ... 15+ injectable dependencies
    ):
        # Complex initialization with factory methods for defaults
```

**Pydantic-AI Pattern**:
```python
@dataclass
class ScrappyDeps:
    orchestrator: OrchestratorAdapter
    project_root: Path
    config: AgentConfig
    file_system: FileSystemProtocol
    audit_logger: AuditLoggerProtocol

agent = Agent(
    FallbackModel('groq:llama3-8b-8192', 'cerebras:llama3.1-8b'),
    deps_type=ScrappyDeps,
    system_prompt=lambda ctx: build_system_prompt(ctx.deps),
)

@agent.tool
async def read_file(ctx: RunContext[ScrappyDeps], path: str) -> str:
    """Read file from project."""
    full_path = ctx.deps.project_root / path
    return ctx.deps.file_system.read(str(full_path))
```

**Assessment**: Partial fit. Pydantic-AI simplifies tool registration but Scrappy's complex initialization (UI, safety, checkpointing) would remain.

### 2. Tool Registry Pattern (tool_runner.py - 106 lines)

**Current Pattern**:
```python
class ToolRunner:
    def __init__(self, tool_registry: ToolRegistryProtocol, ...):
        self.tools = {}
        for tool in self.tool_registry.list_all():
            def make_tool_wrapper(t):
                return lambda **kwargs: t.execute(self.tool_context, **kwargs)
            self.tools[tool.name] = make_tool_wrapper(tool)

    def run_tool(self, tool_name: str, parameters: Dict[str, Any]) -> ToolResult:
        return self.tools[tool_name](**parameters)
```

**Pydantic-AI Pattern**:
```python
# Tools are decorated on the agent - no registry needed
@agent.tool
async def search_code(ctx: RunContext[ScrappyDeps], pattern: str) -> str:
    """Search codebase for pattern."""
    return do_search(ctx.deps.project_root, pattern)

# Agent handles tool resolution automatically
```

**Savings**: ~106 lines, simpler mental model

### 3. ActionExecutor (action_executor.py - 518 lines)

**Current Pattern**:
- Orchestrates: Safety check -> Duplicate detection -> Tool execution -> Result
- Manual confirmation flow with allow-all mode
- Diff preview for write operations
- Batch execution support

**Pydantic-AI Comparison**:
- No built-in safety/confirmation layer
- No duplicate detection
- No batch execution concept

**Assessment**: Poor fit. ActionExecutor's value is in safety orchestration, not tool calling. Pydantic-AI doesn't help here.

### 4. Provider Selection (provider_strategy.py)

**Current Pattern**:
```python
class DynamicProviderStrategy:
    def get_planner(self) -> Optional[str]:
        return self.orchestrator.get_best_provider(prefer_quality=True)

    def get_executor(self) -> Optional[str]:
        return self.orchestrator.get_best_provider(prefer_quality=False)
```

**Pydantic-AI Pattern**:
```python
from pydantic_ai.models import FallbackModel

# Built-in fallback on rate limits
model = FallbackModel(
    'groq:llama3-8b-8192',
    'cerebras:llama3.1-8b',
    'openai:gpt-4o-mini',
)
```

**Assessment**: Good fit for basic fallback, but Scrappy's dynamic selection (quality vs speed, rate-limit-aware) is more sophisticated.

## Overlap with Instructor

| Feature | Instructor | Pydantic-AI | Best For |
|---------|------------|-------------|----------|
| Structured outputs | Core focus | Supported | Instructor (more mature) |
| Validation retries | Built-in | Built-in | Either |
| Tool registration | N/A | Core focus | Pydantic-AI |
| Dependency injection | N/A | Core focus | Pydantic-AI |
| Streaming | Limited | Full support | Pydantic-AI |
| Provider fallback | Via LiteLLM | FallbackModel | Either |
| Complexity | Minimal | Higher | Instructor for simple cases |

**Recommendation**: Use Instructor for structured LLM outputs (classification, extraction). Use Pydantic-AI only if building new agent abstractions.

## Potential Savings Summary

| Component | Current Lines | With Pydantic-AI | Realistic Savings |
|-----------|---------------|------------------|-------------------|
| Tool registration (ToolRunner) | 106 | ~20 | ~86 |
| Tool context patterns | ~50 | ~10 | ~40 |
| Provider fallback | ~100 | ~20 | ~80 |
| **Subtotal (realistic)** | ~256 | ~50 | **~206 lines** |

**Note**: CodeAgent and ActionExecutor savings are minimal because their value is in orchestration (safety, UI, checkpointing), not tool calling.

## Integration Patterns

### Hybrid Approach (Recommended)

Use Pydantic-AI for tool-heavy sub-agents, keep existing orchestration:

```python
from pydantic_ai import Agent, RunContext
from dataclasses import dataclass

@dataclass
class ResearchDeps:
    project_root: Path
    semantic_search: SemanticSearchProtocol

# Research sub-agent with Pydantic-AI
research_agent = Agent(
    'groq:llama3-8b-8192',
    deps_type=ResearchDeps,
)

@research_agent.tool
async def search_codebase(ctx: RunContext[ResearchDeps], query: str) -> str:
    """Search codebase semantically."""
    results = ctx.deps.semantic_search.search(query, limit=10)
    return format_search_results(results)

@research_agent.tool
async def read_file(ctx: RunContext[ResearchDeps], path: str) -> str:
    """Read file contents."""
    return (ctx.deps.project_root / path).read_text()

# Use from existing CodeAgent
class CodeAgent:
    def __init__(self, ...):
        self._research_agent = research_agent

    async def run_research(self, query: str) -> str:
        deps = ResearchDeps(
            project_root=self.project_root,
            semantic_search=self.semantic_search,
        )
        result = await self._research_agent.run(query, deps=deps)
        return result.output
```

### Testing Benefits

Pydantic-AI's dependency injection simplifies testing:

```python
def test_research_agent():
    """Test research agent with mock dependencies."""
    mock_search = MockSemanticSearch()
    mock_search.add_result("auth", "src/auth/login.py:45")

    deps = ResearchDeps(
        project_root=Path("/tmp/test"),
        semantic_search=mock_search,
    )

    result = research_agent.run_sync("find auth code", deps=deps)
    assert "login.py" in result.output
```

## Risks and Considerations

1. **Learning Curve**: Different mental model from traditional agent patterns
2. **Async-First**: Pydantic-AI is async-first; Scrappy uses sync patterns
3. **Maturity**: Newer library (2024), less battle-tested than Instructor
4. **Overlap**: Significant overlap with Instructor for structured outputs
5. **Partial Adoption**: Only helps with tool registration, not orchestration

## Recommendation

**Limited Adoption**:

1. **Use Instructor instead** for structured LLM outputs (classification, extraction)
   - More mature, simpler API, better LiteLLM integration
   - Already evaluated and recommended for 790+ lines of savings

2. **Consider Pydantic-AI for new sub-agents** if building:
   - Research-focused agents with many tools
   - Tool-heavy workflows where decorator pattern helps
   - New agent types that don't need existing safety/UI infrastructure

3. **Don't migrate existing agent infrastructure**:
   - CodeAgent, ActionExecutor, AgentLoop work well
   - Their value is orchestration, not tool calling
   - Migration cost exceeds benefits

## Conclusion

Pydantic-AI offers elegant tool registration and dependency injection, but overlaps heavily with Instructor for structured outputs. For Scrappy:

- **Best Use**: New tool-heavy sub-agents
- **Avoid**: Migrating existing orchestration code
- **Alternative**: Use Instructor for structured outputs (recommended)

The decorator-based tool registration is cleaner than manual registry, but Scrappy's complex safety/UI/checkpointing infrastructure means the core agent code would remain regardless.
