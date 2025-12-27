# Smolagents Library Research

**Bead**: scrappy-pf9
**Status**: Complete
**Date**: 2025-12-25

## Overview

Smolagents is HuggingFace's lightweight agent library that enables:
- Code-based agents that write Python to solve tasks
- Tool-calling agents with structured JSON output
- LiteLLM integration for 100+ providers
- Multi-agent orchestration
- Minimal dependencies ("barebones" design)

## Key Concepts

### Two Agent Types

**CodeAgent** - Writes and executes Python code:
```python
from smolagents import CodeAgent, LiteLLMModel

model = LiteLLMModel(model_id="groq/llama3-8b-8192")
agent = CodeAgent(tools=[], model=model, add_base_tools=True)

# Agent writes Python code to solve tasks
agent.run("What is the 118th Fibonacci number?")
# Agent generates: result = fib(118); print(result)
```

**ToolCallingAgent** - Outputs structured tool calls (no code execution):
```python
from smolagents import ToolCallingAgent, LiteLLMModel

model = LiteLLMModel(model_id="anthropic/claude-3-5-sonnet-latest")
agent = ToolCallingAgent(tools=[], model=model)

# Agent outputs JSON tool calls
agent.run("Search for Python tutorials")
# Agent outputs: {"tool": "web_search", "args": {"query": "Python tutorials"}}
```

### LiteLLM Integration

```python
from smolagents import LiteLLMModel

# Supports all LiteLLM providers
model = LiteLLMModel(
    model_id="groq/llama3-8b-8192",  # or "anthropic/claude-3", "openai/gpt-4", etc.
    temperature=0.2,
    max_tokens=1000,
    requests_per_minute=60  # Rate limiting
)
```

### Tool Definition

```python
from smolagents import tool

@tool
def search_codebase(query: str) -> str:
    """Search the codebase for relevant files.

    Args:
        query: The search query

    Returns:
        Search results as formatted string
    """
    # Implementation
    return f"Found files matching: {query}"

agent = CodeAgent(tools=[search_codebase], model=model)
```

### Multi-Agent Systems

```python
from smolagents import CodeAgent, LiteLLMModel

# Create specialized agents
web_agent = CodeAgent(
    tools=[web_search_tool],
    model=model,
    name="web_researcher"
)

# Manager agent orchestrates sub-agents
manager_agent = CodeAgent(
    tools=[],
    model=model,
    managed_agents=[web_agent],
    additional_authorized_imports=["pandas", "numpy"]
)

manager_agent.run("Research and analyze Python web frameworks")
```

### Gradio UI Integration

```python
from smolagents import CodeAgent, GradioUI

agent = CodeAgent(tools=[image_generation_tool], model=model)
GradioUI(agent).launch()  # Interactive web interface
```

## Comparison with Scrappy's Agent

| Aspect | Smolagents | Scrappy CodeAgent |
|--------|------------|-------------------|
| Paradigm | Code generation | Tool calling |
| Safety | Sandboxed Python exec | Human-in-the-loop |
| Tools | Decorator-based | Registry pattern |
| UI | Gradio built-in | Rich CLI / Textual TUI |
| State | Minimal | Full conversation state |
| Checkpointing | None | Git-based |
| Providers | LiteLLM | LiteLLM |

### Key Architectural Difference

**Smolagents**: LLM writes Python code, agent executes it
```python
# LLM generates:
result = search_docs("authentication")
files = list_directory("src/auth")
print(f"Found {len(files)} files")
```

**Scrappy**: LLM outputs JSON tool calls, agent executes tools
```json
{
  "thought": "I need to find authentication files",
  "action": "search_code",
  "parameters": {"pattern": "authentication"},
  "is_complete": false
}
```

## Scrappy Code Replacement Analysis

### Could Smolagents Replace?

**CodeAgent pattern**: No.
- Scrappy's safety model requires human confirmation
- Code execution is too risky for Scrappy's use case
- Scrappy needs granular tool-level control

**ToolCallingAgent pattern**: Partial overlap.
- Similar to Scrappy's JSON-based tool calling
- Less mature than Scrappy's implementation
- Missing: safety checks, duplicate detection, checkpointing

### Potential Integration Points

1. **Research Sub-Agent**: Use CodeAgent for compute-heavy research tasks
```python
# Scrappy could spawn a smolagents CodeAgent for specific tasks
research_agent = CodeAgent(
    tools=[search_tool, read_file_tool],
    model=LiteLLMModel(model_id="groq/llama3-8b-8192"),
)
# Use for tasks where code execution is appropriate
```

2. **Multi-Agent Orchestration**: Smolagents' `managed_agents` pattern
```python
# Could be useful for future multi-agent features
manager = CodeAgent(
    managed_agents=[code_agent, research_agent, test_agent]
)
```

## Potential Savings

| Component | Smolagents Replacement | Realistic? |
|-----------|------------------------|------------|
| agent_loop.py (1018 lines) | CodeAgent | No - different paradigm |
| action_executor.py (518 lines) | Built-in | No - missing safety |
| tool_runner.py (106 lines) | @tool decorator | Partial - 50 lines |
| response_parser.py (555 lines) | Built-in | No - different format |

**Realistic savings**: ~50-100 lines for tool registration only.

Smolagents doesn't solve Scrappy's actual problems:
- Structured LLM output parsing (use Instructor)
- State machine patterns (use Burr)
- Prompt optimization (use DSPy)

## Unique Value of Smolagents

What smolagents does well:
1. **Code execution paradigm** - LLM writes code, not tool calls
2. **Minimal overhead** - "Barebones" library design
3. **Multi-agent** - Built-in agent orchestration
4. **Gradio UI** - Quick prototyping interface

What Scrappy already does better:
1. **Safety** - Human-in-the-loop, confirmation flows
2. **Observability** - Audit logging, checkpointing
3. **Robustness** - Error handling, retry logic, duplicate detection
4. **UI** - Rich CLI and Textual TUI

## Risks and Considerations

1. **Different paradigm**: Code execution vs tool calling
2. **Safety model**: Smolagents assumes sandboxed execution is safe
3. **Maturity**: Newer library, less battle-tested
4. **Overlap**: Doesn't solve the problems Instructor/DSPy solve
5. **Migration**: Would require fundamental architecture change

## Recommendation

**Do not adopt smolagents** for core agent infrastructure.

Reasons:
1. **Wrong paradigm** - Scrappy uses tool calling, not code execution
2. **Missing safety** - No human-in-the-loop patterns
3. **Limited benefit** - Only helps with tool registration (~50 lines)
4. **Different philosophy** - Smolagents trusts LLM-generated code

**Potential future use**:
- Research sub-agents for compute tasks
- Prototyping new agent patterns
- Multi-agent orchestration experiments

For Scrappy's actual needs:
- **Structured outputs**: Use Instructor (~790 lines savings)
- **State management**: Consider Burr for checkpointing
- **Prompt patterns**: Consider DSPy for optimization

## Conclusion

Smolagents is an interesting library for code-executing agents, but it's a poor fit for Scrappy because:

1. Scrappy's safety-first design requires human confirmation
2. Tool calling (not code execution) is Scrappy's core pattern
3. The library doesn't address Scrappy's actual pain points

**Recommendation**: Skip smolagents. Focus on Instructor for immediate code reduction.

## Sources

- [Smolagents GitHub](https://github.com/huggingface/smolagents)
- [Smolagents Documentation](https://huggingface.co/docs/smolagents)
- [HuggingFace Agents Course](https://huggingface.co/learn/agents-course)
