<!-- todo -->

- Semantic LLM classification
- Add intent clarification mechanism

---
  Recommendations

  1. Configuration consolidation - Consider a RouterConfig dataclass for all thresholds/settings
  2. Pattern weight configuration - Allow runtime/file-based pattern weight adjustment
  3. Metrics persistence - Add optional persistence for MetricsCollector

  ---
  3. Fragile Pattern Matching

  Evidence:
  - Strategy pattern with pluggable ClassificationStrategy implementations
  - LLM-augmented classification for disambiguation
  - Intent clarification for ambiguous cases
  - Confidence scoring with escalation logic

  Remaining concerns:
  - Pattern weights still hardcoded in strategy classes
  - Could benefit from configurable patterns or learned weights

  Location: classification_strategies/*.py

  ---
  15. Configuration Scattered ⚠️ IMPROVED

  Evidence:
  - Router configuration centralized in constructor
  - Behavior switches on router instance:
    - clarify_on_low_confidence
    - confidence_threshold
    - escalate_on_low_confidence
    - use_llm_classification

  Remaining concerns:
  - Some thresholds hardcoded (e.g., 0.7 in pure_functions)
  - Pattern weights in strategy classes
  - Consider centralizing to a config object


# Task Router 

The Task Router is an intelligent dispatch system that:

1. **Classifies** user input by task type and complexity
2. **Selects** the optimal provider based on task requirements
3. **Routes** to the appropriate execution strategy
4. **Executes** with strategy-specific optimizations

This eliminates the overhead of running every task through a full agent loop while ensuring complex tasks still receive appropriate handling.

## Architecture

**Strategy Pattern:**
```
TaskClassifier
  └─ strategies: List[ClassificationStrategy]
       ├─ DirectCommandStrategy
       │    └─ patterns: List[(regex, weight, name)]
       ├─ CodeGenerationStrategy
       │    └─ patterns: List[(regex, weight, name)]
       ├─ ResearchStrategy
       │    └─ patterns: List[(regex, weight, name)]
       └─ ConversationStrategy
            └─ patterns: List[(regex, weight, name)]

  classify() method:
    - Call each strategy.evaluate(input)
    - Pick strategy with highest confidence
    - Generate metadata
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
  