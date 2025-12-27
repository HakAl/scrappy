# Instructor Integration Plan

**Bead**: scrappy-5ap
**Status**: Draft
**Date**: 2025-12-25

## Problem

`json_extractor.py` (259 lines) is brittle and fails ~5% of the time with:
- Markdown code block parsing
- Truncated JSON recovery
- Brace matching edge cases
- 6 different failure modes

## Solution

Replace with Instructor library. LLMs return validated Pydantic models directly.

## What Changes

| File | Current | After |
|------|---------|-------|
| `json_extractor.py` | 259 lines | Delete |
| `response_parser.py` | 555 lines | ~50 lines |
| `router.py` (LLM section) | ~50 lines | ~15 lines |

**Total reduction**: ~790 lines

---

## Architecture

### Protocol First

```python
from typing import Protocol, Type, TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

class StructuredOutputProvider(Protocol):
    """Contract for structured LLM responses."""

    def create(
        self,
        response_model: Type[T],
        messages: list[dict],
        max_retries: int = 2,
    ) -> T:
        """Return validated Pydantic model from LLM."""
        ...
```

### Adapter Implementation

```python
import instructor

class InstructorAdapter:
    """Implements StructuredOutputProvider using Instructor."""

    def __init__(self, provider: str):
        self._client = instructor.from_provider(provider)

    def create(
        self,
        response_model: Type[T],
        messages: list[dict],
        max_retries: int = 2,
    ) -> T:
        return self._client.chat.completions.create(
            response_model=response_model,
            messages=messages,
            max_retries=max_retries,
        )
```

### Response Models

```python
from pydantic import BaseModel, Field
from enum import Enum

class TaskType(str, Enum):
    QUESTION = "question"
    CODE_CHANGE = "code_change"
    RESEARCH = "research"

class TaskClassification(BaseModel):
    """Classify user intent."""
    task_type: TaskType
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str

class AgentAction(BaseModel):
    """Next action for agent to take."""
    thought: str
    tool: str
    parameters: dict
```

---

## Test Strategy

### Test Double

```python
class MockStructuredProvider:
    """Test double - NO real API calls."""

    def __init__(self):
        self.responses: dict[str, BaseModel] = {}
        self.calls: list[tuple] = []

    def set_response(self, model_name: str, response: BaseModel):
        self.responses[model_name] = response

    def create(
        self,
        response_model: Type[T],
        messages: list[dict],
        max_retries: int = 2,
    ) -> T:
        self.calls.append((response_model, messages))
        return self.responses[response_model.__name__]
```

### Example Test

```python
def test_classifies_question_correctly():
    mock = MockStructuredProvider()
    mock.set_response("TaskClassification", TaskClassification(
        task_type=TaskType.QUESTION,
        confidence=0.95,
        reasoning="User asking about function behavior",
    ))

    router = TaskRouter(structured_provider=mock)
    result = router.classify("what does this function do?")

    assert result.task_type == TaskType.QUESTION
    assert len(mock.calls) == 1
```

---

## Error Handling

```python
from pydantic import ValidationError

class StructuredOutputError(Exception):
    """Failed to get structured output from LLM."""
    pass

def classify_task(
    input: str,
    provider: StructuredOutputProvider,
) -> TaskClassification | None:
    """Classify with error handling."""
    try:
        return provider.create(
            response_model=TaskClassification,
            messages=[{"role": "user", "content": input}],
            max_retries=2,
        )
    except ValidationError as e:
        logger.warning(f"LLM returned invalid structure: {e}")
        return None  # Caller uses fallback
    except Exception as e:
        logger.error(f"Provider failed: {e}")
        return None
```

---

## Migration Plan

### Step 1: Add Alongside (Day 1)

```python
# Keep existing code, add new adapter
class LegacyParser:
    """Current implementation - keep during migration."""
    ...

class InstructorParser:
    """New implementation."""
    ...
```

### Step 2: Feature Flag (Day 1)

```python
def get_parser(use_instructor: bool = False) -> Parser:
    if use_instructor:
        return InstructorParser(provider="groq/llama3-8b-8192")
    return LegacyParser()
```

### Step 3: Test Both (Day 2)

Run both parsers, log differences, verify Instructor works.

### Step 4: Switch Default (Day 3)

```python
def get_parser(use_instructor: bool = True) -> Parser:  # Flipped
    ...
```

### Step 5: Delete Legacy (Day 4)

After 24h stable, delete `json_extractor.py` and legacy code.

---

## Implementation Checklist

- [ ] Add dependency: `pip install "instructor[litellm]"`
- [ ] Create `src/scrappy/llm/structured.py`:
  - [ ] `StructuredOutputProvider` protocol
  - [ ] `InstructorAdapter` implementation
  - [ ] `MockStructuredProvider` test double
- [ ] Create `src/scrappy/llm/models.py`:
  - [ ] `TaskClassification` model
  - [ ] `AgentAction` model
- [ ] Add tests (NO real API calls)
- [ ] Add feature flag
- [ ] Run both parsers in parallel, log differences
- [ ] Switch default after validation
- [ ] Delete `json_extractor.py`
- [ ] Simplify `response_parser.py`

---

## Success Metric

| Metric | Current | Target |
|--------|---------|--------|
| JSON parse failures | ~5% | <0.5% |

---

## Timeline

**4 days total**

---

## What We're NOT Doing

These were considered and rejected as premature:

- **Model routing** - Use one quality model. Add routing if cost becomes a problem.
- **Self-validation (Judge)** - Users validate output. Adds latency for unclear benefit.
- **Prompt optimization (DSPy)** - No training data or evidence prompts are the bottleneck.
- **State machines (Burr)** - No complex stateful workflows exist.
- **Test config detection** - Users can specify test commands directly.

Add these later if they become actual problems.

---

## Dependencies

```
instructor[litellm]>=1.0.0
```

No other new dependencies.
