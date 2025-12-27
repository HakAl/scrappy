# Instructor Library Research

**Bead**: scrappy-eyq
**Status**: Complete
**Date**: 2025-12-25

## Overview

Instructor is a library for structured LLM outputs using Pydantic models. It provides automatic validation, retry mechanisms, and clean integration with multiple providers including LiteLLM.

## Key Integration Patterns

### LiteLLM Integration

```python
import instructor
from pydantic import BaseModel

# Direct provider string (supports Groq, Cerebras, etc.)
client = instructor.from_provider("groq/llama3-8b-8192")
client = instructor.from_provider("cerebras/llama3.1-70b")

# Or via LiteLLM for unified interface
client = instructor.from_provider("litellm/gpt-3.5-turbo")
```

**Key Finding**: Instructor supports Scrappy's free tier providers natively:
- `instructor.from_provider("groq/llama3-8b-8192")`
- `instructor.from_provider("cerebras/llama3.1-70b")`

### Structured Output Example

```python
from pydantic import BaseModel, Field

class TaskClassification(BaseModel):
    task_type: str = Field(description="RESEARCH|CODE_GENERATION|DIRECT_COMMAND|CONVERSATION")
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str

# Automatic validation and retry
result = client.chat.completions.create(
    response_model=TaskClassification,
    messages=[{"role": "user", "content": "Classify: create a new file"}],
    max_retries=3,
)
# result is a validated TaskClassification instance
```

## Custom Code Replacement Candidates

### 1. JSONExtractor (259 lines) - `task_router/json_extractor.py`

**Current Approach**:
- Manual extraction from markdown code blocks
- Python bool/None conversion (`True` -> `true`)
- Brace matching for malformed JSON
- Multiple fallback strategies

**Instructor Replacement**:
```python
# Current: 259 lines of parsing code
json_str = extractor.extract(llm_response)
json_str = extractor.fix_json(json_str)
data = json.loads(json_str)

# With Instructor: ~5 lines
class ClassificationResult(BaseModel):
    task_type: str
    confidence: float
    reasoning: str

result = client.chat.completions.create(
    response_model=ClassificationResult,
    messages=[...],
)
# `result` is already validated, typed, and structured
```

**Savings**: ~250 lines, eliminates JSON parsing edge cases

### 2. Response Parser (555 lines) - `agent/response_parser.py`

**Current Approach**:
- JSONResponseParser with 6 fallback strategies:
  - Direct parse
  - Python bool conversion
  - Triple-quote fix
  - Brace matching
  - Truncated JSON recovery
  - Regex extraction
- NativeToolCallParser for tool calls
- UnifiedResponseParser router

**Instructor Replacement**:
```python
from pydantic import BaseModel
from typing import Optional

class AgentAction(BaseModel):
    thought: str
    action: str
    parameters: dict
    is_complete: bool = False
    result: Optional[str] = None

# Replace entire parser with:
response = client.chat.completions.create(
    response_model=AgentAction,
    messages=[...],
    max_retries=2,
)
```

**Savings**: ~500 lines, automatic retry on validation failure

### 3. LLM Classification in Router (50+ lines) - `task_router/router.py`

**Current Approach** (lines 234-345):
- Manual system prompt for classification
- JSON extraction with `parse_llm_classification_response()`
- String-to-enum mapping
- Confidence threshold logic

**Instructor Replacement**:
```python
from enum import Enum

class TaskType(str, Enum):
    RESEARCH = "RESEARCH"
    CODE_GENERATION = "CODE_GENERATION"
    DIRECT_COMMAND = "DIRECT_COMMAND"
    CONVERSATION = "CONVERSATION"

class LLMClassification(BaseModel):
    task_type: TaskType
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str

# Clean, type-safe classification
result = client.chat.completions.create(
    response_model=LLMClassification,
    messages=[
        {"role": "system", "content": "Classify the user's task..."},
        {"role": "user", "content": f"Classify: {user_input}"}
    ],
)
# result.task_type is already a TaskType enum
```

**Savings**: ~40 lines, type-safe enum handling

## Provider Compatibility

| Provider | Native Support | Via LiteLLM | Notes |
|----------|----------------|-------------|-------|
| Groq | `groq/llama3-8b-8192` | Yes | Free tier friendly |
| Cerebras | `cerebras/llama3.1-70b` | Yes | Free tier friendly |
| OpenAI | `openai/gpt-4` | Yes | Full support |
| Anthropic | `anthropic/claude-3` | Yes | Full support |
| Gemini | `genai/gemini-1.5-flash` | Yes | Full support |
| Ollama | `ollama/llama3` | Yes | Local models |

## Retry & Validation Features

### Built-in Retry
```python
client = instructor.from_provider("groq/llama3-8b-8192")

# Automatic retry on validation failure
result = client.chat.completions.create(
    response_model=MyModel,
    messages=[...],
    max_retries=3,  # Retries with error context sent back to LLM
)
```

### Custom Validators
```python
from pydantic import field_validator

class ValidatedOutput(BaseModel):
    age: int

    @field_validator('age')
    def validate_age(cls, v):
        if v < 0 or v > 150:
            raise ValueError('Age must be between 0 and 150')
        return v
```

### Tenacity Integration
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=1, max=60)
)
def robust_extraction(text: str) -> UserInfo:
    return client.chat.completions.create(
        response_model=UserInfo,
        messages=[{"role": "user", "content": text}]
    )
```

## Potential Savings Summary

| File | Current Lines | After Instructor | Savings |
|------|---------------|------------------|---------|
| json_extractor.py | 259 | ~10 | ~250 |
| response_parser.py | 555 | ~50 | ~500 |
| router.py (LLM classification) | ~50 | ~15 | ~35 |
| **Total** | ~864 | ~75 | **~790 lines** |

## Risks & Considerations

1. **Dependency Addition**: Adds instructor as dependency (lightweight, actively maintained)
2. **Migration Path**: Can adopt incrementally - start with new features
3. **Provider Quirks**: Some free tier providers may have lower compliance with structured output
4. **Performance**: Minimal overhead - Pydantic validation is fast

## Recommendation

**Adopt Instructor** for new structured output needs. Migration path:

1. **Phase 1**: Use for new classification/extraction features
2. **Phase 2**: Replace `json_extractor.py` (cleanest win)
3. **Phase 3**: Replace `response_parser.py` (biggest savings)
4. **Phase 4**: Refactor router LLM classification

## Integration Example for Scrappy

```python
# src/scrappy/llm/structured.py
import instructor
from pydantic import BaseModel, Field
from typing import Optional
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

class AgentAction(BaseModel):
    thought: str
    action: str
    parameters: dict = Field(default_factory=dict)
    is_complete: bool = False
    result: Optional[str] = None

def create_instructor_client(model: str = "groq/llama3-8b-8192"):
    """Create Instructor client for structured outputs."""
    return instructor.from_provider(model)

# Usage in task router:
def classify_with_instructor(client, user_input: str) -> TaskClassification:
    return client.chat.completions.create(
        response_model=TaskClassification,
        messages=[
            {"role": "system", "content": "Classify the user's task..."},
            {"role": "user", "content": user_input}
        ],
        max_retries=2,
    )
```

## Next Steps

1. Add instructor dependency: `pip install "instructor[litellm]"`
2. Create `src/scrappy/llm/structured.py` with base models
3. Start with task classification use case
4. Monitor provider compatibility in production
