# DSPy Library Research

**Bead**: scrappy-bat
**Status**: Complete
**Date**: 2025-12-25

## Overview

DSPy is a framework for programming language models using declarative signatures instead of prompt engineering. It enables:
- Defining prompts as typed input/output signatures
- Automatic prompt optimization via compilation
- Modular composition (ChainOfThought, ReAct, etc.)
- Provider-agnostic patterns via LiteLLM

## Key Concepts

### Signatures - Declarative Prompts

```python
import dspy

# Simple signature - just input/output fields
summarize = dspy.ChainOfThought('document -> summary')

# Class-based signature with descriptions
class TaskClassification(dspy.Signature):
    """Classify the user's task type based on their request."""

    user_input: str = dspy.InputField(desc="The user's request or query")
    task_type: str = dspy.OutputField(desc="RESEARCH|CODE_GENERATION|DIRECT_COMMAND|CONVERSATION")
    confidence: float = dspy.OutputField(desc="Confidence score from 0.0 to 1.0")
    reasoning: str = dspy.OutputField(desc="Brief explanation of the classification")
```

### LiteLLM Integration

```python
import dspy

# Configure with any LiteLLM-compatible provider
lm = dspy.LM('groq/llama3-8b-8192', temperature=0.7)
dspy.configure(lm=lm)

# Or use multiple models
fast_lm = dspy.LM('cerebras/llama3.1-8b', max_tokens=500)
quality_lm = dspy.LM('groq/llama-3.1-70b-versatile', max_tokens=2000)

# Switch at runtime
dspy.configure(lm=fast_lm)  # For quick tasks
dspy.configure(lm=quality_lm)  # For complex tasks
```

### Built-in Modules

**ChainOfThought** - Step-by-step reasoning:
```python
cot = dspy.ChainOfThought('question -> answer')
response = cot(question="What files handle authentication?")
print(response.reasoning)  # Step-by-step thinking
print(response.answer)     # Final answer
```

**ReAct** - Tool-using agents:
```python
def search_code(query: str) -> str:
    """Search codebase for relevant code."""
    return search_results

def read_file(path: str) -> str:
    """Read file contents."""
    return file_contents

react = dspy.ReAct(
    signature="question -> answer",
    tools=[search_code, read_file],
    max_iters=5
)
```

**Predict** - Simple completion:
```python
classify = dspy.Predict(TaskClassification)
result = classify(user_input="create a new file")
```

### Optimization and Compilation

```python
from dspy.teleprompt import BootstrapFewShot, MIPROv2

# Define a metric
def accuracy_metric(example, prediction, trace=None):
    return example.expected_type == prediction.task_type

# Bootstrap few-shot examples
optimizer = BootstrapFewShot(
    metric=accuracy_metric,
    max_bootstrapped_demos=4,
    max_labeled_demos=8
)
optimized = optimizer.compile(classifier, trainset=training_data)

# Or use MIPROv2 for heavy optimization
tp = MIPROv2(metric=accuracy_metric, auto="medium")
optimized = tp.compile(classifier, trainset=training_data)

# Save optimized program
optimized.save("optimized_classifier.json")
```

## Scrappy Code Replacement Candidates

### 1. Task Classification (`task_router/classifier.py` + `router.py`)

**Current Implementation** (~400 lines):
- Rule-based pattern matching
- LLM fallback for low confidence
- Manual JSON parsing
- String-to-enum mapping

**DSPy Replacement**:
```python
import dspy
from enum import Enum

class TaskType(str, Enum):
    RESEARCH = "RESEARCH"
    CODE_GENERATION = "CODE_GENERATION"
    DIRECT_COMMAND = "DIRECT_COMMAND"
    CONVERSATION = "CONVERSATION"

class ClassifyTask(dspy.Signature):
    """Classify user task into execution category."""

    user_input: str = dspy.InputField()
    task_type: TaskType = dspy.OutputField()
    confidence: float = dspy.OutputField()
    reasoning: str = dspy.OutputField()

class TaskClassifier(dspy.Module):
    def __init__(self):
        self.classify = dspy.ChainOfThought(ClassifyTask)

    def forward(self, user_input: str):
        return self.classify(user_input=user_input)

# Usage
classifier = TaskClassifier()
result = classifier(user_input="create a requirements.txt file")
# result.task_type -> TaskType.CODE_GENERATION
# result.confidence -> 0.95
# result.reasoning -> "User wants to create a file, which is a code generation task"
```

**Benefits**:
- Type-safe enums (no string mapping)
- Automatic validation
- Built-in reasoning trace
- Can be optimized with training data

### 2. Research Prompt Builder (`cli/research_prompt_builder.py`)

**Current Implementation** (134 lines):
- Manual string formatting
- Classification context injection
- Research results formatting

**DSPy Replacement**:
```python
class ResearchQuery(dspy.Signature):
    """Answer questions about a codebase using research findings."""

    query: str = dspy.InputField(desc="User's original question")
    classification: str = dspy.InputField(desc="Query classification context")
    research_results: str = dspy.InputField(desc="Research findings from codebase")
    answer: str = dspy.OutputField(desc="Specific, accurate answer with file citations")

class CodebaseResearcher(dspy.Module):
    def __init__(self):
        self.respond = dspy.ChainOfThought(ResearchQuery)

    def forward(self, query, classification, research_results):
        return self.respond(
            query=query,
            classification=classification,
            research_results=research_results
        )
```

### 3. Prompt Factory (`prompts/factory.py`)

**Current Implementation** (200 lines):
- Mode-specific prompts (chat, agent, research)
- Manual section composition
- String interpolation

**DSPy Replacement**:
```python
# Chat mode - simple
class ChatResponse(dspy.Signature):
    """Answer questions directly and concisely."""
    question: str = dspy.InputField()
    answer: str = dspy.OutputField()

# Agent mode - with reasoning
class AgentTask(dspy.Signature):
    """Complete coding task using available tools."""
    task: str = dspy.InputField()
    platform: str = dspy.InputField()
    available_tools: str = dspy.InputField()
    thought: str = dspy.OutputField(desc="Current reasoning about the task")
    action: str = dspy.OutputField(desc="Tool to use or 'complete'")
    parameters: dict = dspy.OutputField(desc="Tool parameters")

# Research mode - with codebase context
class ResearchTask(dspy.Signature):
    """Research codebase to answer question."""
    query: str = dspy.InputField()
    context: str = dspy.InputField()
    findings: str = dspy.OutputField()
    confidence: str = dspy.OutputField()
```

### 4. LLM Classification in Router (`task_router/router.py:234-345`)

**Current Implementation** (~110 lines):
- Manual system prompt construction
- JSON extraction and parsing
- Error handling and retries

**DSPy Replacement**:
```python
class SemanticClassifier(dspy.Module):
    """LLM-based semantic classification for ambiguous tasks."""

    def __init__(self):
        self.classify = dspy.ChainOfThought(ClassifyTask)

    def forward(self, user_input: str, rule_classification: str, rule_confidence: float):
        # DSPy handles the prompt, parsing, and retries
        return self.classify(
            user_input=user_input,
            # Can add rule-based hints as additional context
        )

# Usage in router
if rule_confidence < 0.7:
    result = semantic_classifier(
        user_input=user_input,
        rule_classification=classified.task_type.value,
        rule_confidence=classified.confidence
    )
```

## Potential Code Reduction

| File | Current Lines | After DSPy | Savings |
|------|---------------|------------|---------|
| `task_router/classifier.py` | 375 | ~100 | ~275 |
| `task_router/router.py` (LLM section) | ~110 | ~30 | ~80 |
| `cli/research_prompt_builder.py` | 134 | ~50 | ~84 |
| `prompts/factory.py` | 200 | ~80 | ~120 |
| **Total** | ~819 | ~260 | **~559 lines** |

## Optimization Potential

DSPy's compilation features could significantly improve Scrappy:

### Training Data Collection
```python
# Collect examples during normal usage
training_examples = [
    dspy.Example(user_input="create a file", task_type="CODE_GENERATION", confidence=0.95),
    dspy.Example(user_input="what does this function do", task_type="RESEARCH", confidence=0.9),
    # ... more examples
]
```

### Automatic Prompt Optimization
```python
# Optimize classifier with real usage data
optimizer = dspy.BootstrapFewShot(metric=accuracy_metric, max_bootstrapped_demos=8)
optimized_classifier = optimizer.compile(TaskClassifier(), trainset=training_examples)

# Save and load optimized prompts
optimized_classifier.save("prompts/optimized_classifier.json")
```

### A/B Testing Different Optimizations
```python
# Compare different optimization strategies
light_optimized = MIPROv2(auto="light").compile(classifier, trainset=data)
heavy_optimized = MIPROv2(auto="heavy").compile(classifier, trainset=data)

# Evaluate and choose best
evaluate(light_optimized, devset=test_data)
evaluate(heavy_optimized, devset=test_data)
```

## Integration with Other Libraries

| Library | Integration Point |
|---------|-------------------|
| Instructor | DSPy's typed outputs complement Instructor's validation |
| Burr | DSPy modules can be Burr actions |
| LiteLLM | DSPy uses LiteLLM internally for provider routing |
| Pydantic | DSPy signatures work with Pydantic types |

## Risks and Considerations

1. **Learning Curve**: Different mental model from traditional prompting
2. **Debugging**: Compiled prompts may be harder to debug
3. **Migration Effort**: Significant refactoring of prompt logic
4. **Provider Compatibility**: Some free tier providers may have issues with complex prompts
5. **Overhead**: Additional abstraction layer

## Recommendation

**Gradual Adoption Strategy**:

1. **Phase 1**: Use for new classification features
   - Task classification refinement
   - Intent clarification
   - New research handlers

2. **Phase 2**: Replace research prompt builder
   - Most isolated component
   - Clear input/output signature
   - Easy to test

3. **Phase 3**: Refactor prompt factory
   - Convert to DSPy signatures
   - Maintain backward compatibility
   - Enable optimization

4. **Phase 4**: Add prompt optimization
   - Collect training data from usage
   - Run periodic optimization
   - A/B test improvements

## Example: Full Classification Pipeline

```python
import dspy
from enum import Enum
from typing import Optional

class TaskType(str, Enum):
    RESEARCH = "RESEARCH"
    CODE_GENERATION = "CODE_GENERATION"
    DIRECT_COMMAND = "DIRECT_COMMAND"
    CONVERSATION = "CONVERSATION"

class ClassifyTask(dspy.Signature):
    """Classify user request into task type with confidence."""
    user_input: str = dspy.InputField()
    task_type: TaskType = dspy.OutputField()
    confidence: float = dspy.OutputField()
    reasoning: str = dspy.OutputField()
    suggested_provider: Optional[str] = dspy.OutputField()

class ScrappyClassifier(dspy.Module):
    def __init__(self):
        self.classify = dspy.ChainOfThought(ClassifyTask)

    def forward(self, user_input: str):
        result = self.classify(user_input=user_input)

        # Post-processing: suggest provider based on task type
        if result.task_type == TaskType.CODE_GENERATION and result.confidence < 0.7:
            result.suggested_provider = "quality"  # Use stronger model
        else:
            result.suggested_provider = "fast"

        return result

# Configure and use
dspy.configure(lm=dspy.LM('groq/llama3-8b-8192'))
classifier = ScrappyClassifier()

# Optimize with training data
optimizer = dspy.BootstrapFewShot(metric=lambda e, p, t: e.task_type == p.task_type)
optimized = optimizer.compile(classifier, trainset=training_examples)
optimized.save("scrappy_classifier.json")
```

## Conclusion

DSPy offers a powerful paradigm shift from prompt engineering to prompt programming. Key benefits:

- **Type Safety**: Signatures enforce structure
- **Optimization**: Automatic prompt improvement
- **Modularity**: Composable components
- **Testing**: Clear input/output contracts

Best suited for:
- Classification tasks with clear input/output
- Research pipelines with multi-step reasoning
- Any prompt that would benefit from optimization

Not recommended for:
- Simple, static prompts
- Highly dynamic prompt generation
- Low-latency requirements (optimization overhead)
