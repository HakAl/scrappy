# Mirascope Library Research

**Bead**: scrappy-94j
**Status**: Complete
**Date**: 2025-12-25

## Overview

Mirascope is a lightweight LLM toolkit that provides:
- Provider-agnostic LLM calls with unified interface
- Structured outputs via Pydantic models
- Tools and function calling
- Native Python/Pydantic approach (no custom abstractions)
- Support for OpenAI, Anthropic, Groq, Gemini, Cohere, LiteLLM, Azure, Bedrock

## Key Concepts

### Decorator-Based LLM Calls

```python
from mirascope import llm
from pydantic import BaseModel

class Book(BaseModel):
    title: str
    author: str

@llm.call(provider="openai", model="gpt-4o-mini", response_model=Book)
def extract_book(text: str) -> str:
    return f"Extract {text}"

book = extract_book("The Name of the Wind by Patrick Rothfuss")
assert isinstance(book, Book)
```

### Provider Support

```python
from mirascope import llm

# OpenAI
@llm.call(provider="openai", model="gpt-4o-mini")
def openai_call(text: str) -> str:
    return text

# Anthropic
@llm.call(provider="anthropic", model="claude-3-5-sonnet")
def anthropic_call(text: str) -> str:
    return text

# Groq (free tier friendly)
@llm.call(provider="groq", model="llama3-8b-8192")
def groq_call(text: str) -> str:
    return text

# LiteLLM for any provider
@llm.call(provider="litellm", model="groq/llama3-8b-8192")
def litellm_call(text: str) -> str:
    return text
```

### Structured Outputs

```python
from mirascope import llm
from pydantic import BaseModel, Field
from enum import Enum

class TaskType(str, Enum):
    RESEARCH = "RESEARCH"
    CODE_GENERATION = "CODE_GENERATION"
    DIRECT_COMMAND = "DIRECT_COMMAND"
    CONVERSATION = "CONVERSATION"

class TaskClassification(BaseModel):
    task_type: TaskType
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str

@llm.call(provider="groq", model="llama3-8b-8192", response_model=TaskClassification)
def classify_task(user_input: str) -> str:
    return f"Classify this user request: {user_input}"

result = classify_task("create a new file")
# result is TaskClassification instance
```

### Tools and Function Calling

```python
from mirascope import llm
from mirascope.tools import Tool

class SearchTool(Tool):
    """Search the codebase for patterns."""
    pattern: str

    def call(self) -> str:
        # Execute search
        return f"Found matches for {self.pattern}"

@llm.call(provider="openai", model="gpt-4o-mini", tools=[SearchTool])
def agent_with_tools(query: str) -> str:
    return f"Help with: {query}"
```

## Comparison with Instructor

| Feature | Mirascope | Instructor |
|---------|-----------|------------|
| Structured outputs | Yes (Pydantic) | Yes (Pydantic) |
| Provider support | Many built-in | Via LiteLLM |
| Tool/function calling | Yes | Limited |
| Chaining | Yes | No |
| Retry logic | Yes | Yes |
| Complexity | Moderate | Minimal |
| Learning curve | Low | Very low |

**Key Difference**: Mirascope has wider scope (tools, chaining, agents) while Instructor focuses purely on structured outputs. For Scrappy's needs (structured classification outputs), Instructor is simpler.

## Scrappy Code Replacement Analysis

### 1. JSON Extractor (json_extractor.py - 259 lines)

**Current**: Manual JSON extraction with fallbacks
**Mirascope**:
```python
@llm.call(provider="groq", model="llama3-8b-8192", response_model=TaskClassification)
def classify(user_input: str) -> str:
    return f"Classify: {user_input}"
```

**Savings**: ~250 lines (same as Instructor)

### 2. Response Parser (response_parser.py - 555 lines)

**Current**: 6 fallback strategies for JSON parsing
**Mirascope**:
```python
class AgentResponse(BaseModel):
    thought: str
    action: str
    parameters: dict
    is_complete: bool = False

@llm.call(provider="groq", model="llama3-8b-8192", response_model=AgentResponse)
def get_agent_response(context: str) -> str:
    return context
```

**Savings**: ~500 lines (same as Instructor)

### 3. LLM Classification in Router (~50 lines)

**Savings**: ~35 lines (same as Instructor)

## Potential Savings Summary

| Component | Current Lines | With Mirascope | Savings |
|-----------|---------------|----------------|---------|
| json_extractor.py | 259 | ~10 | ~250 |
| response_parser.py | 555 | ~50 | ~500 |
| Router LLM classification | ~50 | ~15 | ~35 |
| **Total** | ~864 | ~75 | **~790 lines** |

**Note**: Savings are identical to Instructor because both solve the same problem (structured LLM outputs).

## Mirascope vs Instructor for Scrappy

| Consideration | Mirascope | Instructor | Winner |
|---------------|-----------|------------|--------|
| Simplicity | Decorators + classes | Simple wrapper | Instructor |
| Maturity | Newer (2024) | Established | Instructor |
| Documentation | Good | Excellent | Instructor |
| LiteLLM integration | Native provider | `from_provider()` | Tie |
| Extra features | Tools, chaining | None | Mirascope |
| Scrappy needs | Overkill | Perfect fit | Instructor |

## Unique Value of Mirascope

Mirascope's advantages over Instructor:
1. **Built-in tool support** - Could simplify tool definitions
2. **Chaining** - Multi-step LLM workflows
3. **Provider-specific features** - Access to native APIs
4. **Agent patterns** - Higher-level agent abstractions

However, Scrappy already has:
- Tool registry system (works well)
- Agent loop (complex, tested)
- Provider abstraction (via LiteLLM)

Mirascope would add value only if building new agent types from scratch.

## Risks and Considerations

1. **Overlap with Instructor**: Same structured output benefits, more complexity
2. **Learning curve**: Decorator patterns, tool classes
3. **Dependency**: Additional library to maintain
4. **Migration cost**: No advantage over Instructor for existing code

## Recommendation

**Do not adopt Mirascope**. Use Instructor instead because:

1. **Simpler API** - Instructor is more focused, less to learn
2. **Same benefits** - Both solve structured outputs equally well
3. **Better fit** - Instructor's minimalism matches Scrappy's needs
4. **Established** - More battle-tested, better documentation

Mirascope would be a good choice if:
- Starting a new project from scratch
- Need built-in tool calling abstractions
- Want to avoid building custom agent infrastructure

For Scrappy's case (existing agent infrastructure, need structured outputs only), Instructor is the clear winner.

## Conclusion

Mirascope is a capable library with broader scope than Instructor, but for Scrappy's specific needs (structured LLM outputs for classification and response parsing), Instructor provides the same benefits with less complexity.

**Recommendation**: Skip Mirascope, adopt Instructor for ~790 lines of code reduction.

## Sources

- [Mirascope GitHub](https://github.com/Mirascope/mirascope)
- [Mirascope Documentation](https://mirascope.com/docs)
- [Mirascope vs LangChain Comparison](https://mirascope.com/blog/langchain-alternatives)
