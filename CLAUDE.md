# Claude Code Guidelines

## Test Coverage Policy

**CRITICAL: Never decrease test coverage.**
**CRITICAL: Use emojis or special characters in code.**

When making changes to the codebase:

1. **Run tests before and after changes** to verify coverage is maintained or improved
2. **Add tests for new code** - all new functionality must have corresponding tests
3. **Maintain existing test coverage** - if modifying code, ensure tests still pass and coverage doesn't drop
4. **Fix failing tests** - never delete or skip tests to make CI pass; fix the underlying issue

### Commands

```bash
# Run all tests with coverage report
python -m pytest tests/ --cov=src --cov-report=term-missing

# Run specific test file
python -m pytest tests/test_<module>.py -v

# Check coverage for specific module
python -m pytest tests/ --cov=src.<module> --cov-report=term-missing
```

### Current Coverage Targets

- Rate Limiter: 94%+
- Task Router: 82%+
- Orchestrator Adapter: 94%+
- Groq Provider: 91%+
- Cohere Provider: 97%+

Aim to maintain or exceed these levels.
