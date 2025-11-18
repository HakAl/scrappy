Task Router Assessment
:

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

  - router.py:410-502 and router.py:503-602 - route() and route_with_provider() have ~80% code duplication
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

 


  Phase 4: Remove Code Duplication

  1. Consolidate routing methods - Single route() method that accepts options
  2. Extract common provider logic - Single source of truth
  3. Reuse JSON parsing - One robust implementation

  Phase 5: Improve Architecture

  1. Define clear interfaces - Expand protocol classes
  2. Dependency injection - Pass all dependencies explicitly
  3. Immutable domain objects - Make ClassifiedTask immutable
  4. Pure functions - Separate calculation from side effects
