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

  - router.py:158-186 - _clarify_intent() uses input() directly, making it impossible to test without user
  interaction
  - This is why 4 tests are skipped in the test file (lines 47, 219, 257, 312)
  - Violates dependency inversion principle

  2. Massive Files - Single Responsibility Violation

  - strategies.py: 1,145 lines - should be split into separate files per strategy
  - router.py: 725 lines - too many responsibilities (routing, classification, metrics, UI, provider resolution)
  - classifier.py: 436 lines - acceptable but patterns are scattered

  3. Fragile Pattern Matching

  - classifier.py:56-152 - Hundreds of hardcoded regex patterns that overlap and conflict
  - Pattern-based classification is brittle and requires constant maintenance
  - No priority system when multiple patterns match

  4. Duplicated Code

  - route() and route_with_provider() consolidated into single route() method with optional provider parameter
  - Provider resolution logic scattered across multiple methods

  5. Complex JSON Parsing with No Error Recovery

  - router.py:296-318 - Multiple nested tries to extract JSON from LLM responses
  - strategies.py:440-496 - Similar fragile parsing in ResearchExecutor
  - Uses regex to extract JSON instead of proper parsing

  6. Mixed Concerns & God Objects

  - TaskRouter does: classification, execution, metrics, UI prompts, provider resolution, hooks
  - ResearchExecutor does: tool setup, file resolution, auto-exploration, tool execution, prompt building

  7. Shallow Tests That Don't Prove Correctness

  Examples from test_task_router.py:
  - Line 26: Just checks router is not None - trivial
  - Line 36: Just checks result has attributes - doesn't verify behavior
  - Line 332: "Test that pip commands are recognized" - doesn't test what happens when executed
  - Tests focus on implementation details, not behavior

  Code Quality Issues

  8. Side Effects Everywhere

  - Methods print directly to stdout (should use logging or return messages)
  - State mutations scattered throughout
  - Hard to reason about behavior

  9. No Validation

  - Parameters not validated before use
  - No guard clauses for edge cases
  - Silent failures (catching broad exceptions and continuing)

  10. Tight Coupling

  - Strategies tightly coupled to orchestrator implementation details
  - Hard dependencies make testing difficult
  - Can't swap implementations easily

  Test Quality Issues

  11. Tests Don't Follow TDD (violates CLAUDE.md)

  - Tests written after code (evident from shallow assertions)
  - Don't demonstrate expected behavior
  - Don't test edge cases or failure modes
  - High line count (1,446 lines) but low quality

  12. Over-reliance on Mocks Without Behavior Verification

  - Example line 200-207: Creates mock but doesn't verify it's called correctly
  - Testing that mocks exist, not that behavior is correct

  13. Skipped Tests Indicate Design Problems

  - 4 skipped tests all cite "interactive prompts"
  - This means the production code has untestable design

  Architecture Issues

  14. No Clear Abstractions

  - Business logic mixed with infrastructure
  - No separation between pure functions and side effects
  - Domain objects are anemic (just data containers)

  15. Configuration Scattered

  - Settings spread across multiple classes
  - No single source of truth for configuration
  - Hard to understand what can be configured

  
  Recommended Fix Strategy

 
we're working to improve src\task_router the next task is: 
Improve Architecture - Pure functions - Separate calculation from side effects
can you research the problem and begin writing tests for the change?


  Phase 5: Improve Architecture

  4. Pure functions - Separate calculation from side effects
