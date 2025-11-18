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

  Critical Issues

  1. Poor Testability - Interactive I/O
  2. Massive Files - Single Responsibility Violation
  3. Fragile Pattern Matching
  4. Duplicated Code
  5. Complex JSON Parsing with No Error Recovery
  6. Mixed Concerns & God Objects
  7. Shallow Tests That Don't Prove Correctness

  Code Quality Issues

  8. Side Effects Everywhere
  9. No Validation
  10. Tight Coupling

  Test Quality Issues

  11. Tests Don't Follow TDD (violates CLAUDE.md)
  12. Over-reliance on Mocks Without Behavior Verification
  13. Skipped Tests Indicate Design Problems

  Architecture Issues

  14. No Clear Abstractions
  15. Configuration Scattered


  