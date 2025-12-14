# Task Router

The Task Router is an intelligent dispatch system that:

1. **Classifies** user input by task type and complexity
2. **Selects** the optimal model group based on task requirements
3. **Routes** to the appropriate execution strategy
4. **Executes** with strategy-specific optimizations

This eliminates the overhead of running every task through a full agent loop while ensuring complex tasks still receive appropriate handling.

## Architecture

**Strategy Pattern:**
```
TaskClassifier
  +-- strategies: List[ClassificationStrategy]
       +-- DirectCommandStrategy
       |    +-- patterns: List[(regex, weight, name)]
       +-- CodeGenerationStrategy
       |    +-- patterns: List[(regex, weight, name)]
       +-- ResearchStrategy
       |    +-- patterns: List[(regex, weight, name)]
       +-- ConversationStrategy
            +-- patterns: List[(regex, weight, name)]

  classify() method:
    - Call each strategy.evaluate(input)
    - Pick strategy with highest confidence
    - Generate metadata
```

## Model Group Selection

Instead of selecting individual providers, the router selects model groups:

| Group | Description | Used For |
|-------|-------------|----------|
| `fast` | 8B class models | Quick responses, high throughput |
| `quality` | 70B+ class models | Complex reasoning, code generation |

```python
def _suggest_model_group(task_type, complexity):
    if task_type == TaskType.DIRECT_COMMAND:
        return None  # No LLM needed

    if task_type == TaskType.CONVERSATION:
        return "fast"

    if task_type == TaskType.RESEARCH:
        return "fast"

    if task_type == TaskType.CODE_GENERATION:
        if complexity >= 7:
            return "quality"  # 70B model for complex tasks
        else:
            return "fast"     # 8B model for simpler code
```

## Benefits

### 1. Separation of Concerns
- Each strategy manages its own patterns
- Easy to understand what each strategy does
- No more giant pattern lists in one file

### 2. Testability
- Can test strategies independently
- Can mock/stub strategies for unit testing
- Easier to add tests for new patterns

### 3. Extensibility
- Add new strategies without modifying core classifier
- Can inject custom strategies via constructor:
  ```python
  custom_strategies = [
      DirectCommandStrategy(),
      CodeGenerationStrategy(),
      ResearchStrategy(),
      ConversationStrategy(),
      MyCustomStrategy(),  # Add custom strategy
  ]
  classifier = TaskClassifier(strategies=custom_strategies)
  ```
