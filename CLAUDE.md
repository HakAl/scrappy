# Claude Code Guidelines

**IMPORTANT: ALWAYS USE TDD. TESTS FIRST, THEN CODE!**

**CRITICAL: Demonstrate expected behavior of all new features in tests that fail. When tests exist, write code to satisfy the tests, then verify new code with tests.**

**CRITICAL: Never use emojis or special characters in code.**

## Test Quality Policy

**CRITICAL: Write tests that prove features work and provide confidence for changes.**

### What Makes a Good Test

Tests must demonstrate functionality and serve as guardrails for refactoring:

1. **Test behavior, not implementation** - Verify what the code does, not how it does it internally
2. **Cover edge cases and failure modes** - Happy path alone is insufficient; test boundaries, errors, and invalid inputs
3. **Prove the feature works** - Tests should fail when requirements break, not when implementation details change
4. **Enable confident refactoring** - If you can't refactor without breaking tests, the tests are testing the wrong things

### Red Flags (Avoid These)

- Tests that mock everything and verify mock calls instead of outcomes
- Tests that only cover the happy path
- Tests that break when you refactor but behavior stays the same
- Tests that pass when actual functionality is broken
- High coverage numbers with no real safety guarantees

### Writing Tests

When adding or modifying functionality:

1. **Start with edge cases** - What inputs break this? What are the boundaries?
2. **Test failure modes** - How should this behave when things go wrong?
3. **Verify observable outcomes** - Assert on return values, state changes, side effects users care about
4. **Ask: "Does this test give me confidence?"** - If not, rewrite it

### Commands

```bash
# Useful mocks!
tests\helpers.py

# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_<module>.py -v

# Run with coverage (use as a guide, not a target)
python -m pytest tests/ --cov=src --cov-report=term-missing
```

### Coverage Note

Coverage metrics are informational only. High coverage with poor tests provides false confidence. Focus on test quality: meaningful assertions, edge case coverage, and behavior verification.
