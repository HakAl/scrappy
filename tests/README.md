# Test Suite for LLM Agent Team

## Overview

This directory contains the comprehensive test suite for the LLM Agent Team project.

## Test Structure

```
tests/
├── conftest.py                    # Shared fixtures and configuration
├── test_providers.py              # LLM provider and registry tests
├── test_orchestrator_memory.py    # Working memory tests
├── test_orchestrator_cache.py     # Response cache tests
├── test_task_classifier.py        # Task classification tests
├── test_task_router.py            # Task routing and execution tests
├── test_agent_tools.py            # Tool system tests
├── test_platform_utils.py         # Platform detection and validation tests
└── test_context.py                # Codebase context tests
```

## Running Tests

### Run all tests:
```bash
python -m pytest tests/
```

### Run with verbose output:
```bash
python -m pytest tests/ -v
```

### Run specific test file:
```bash
python -m pytest tests/test_providers.py
```

### Run tests by marker:
```bash
python -m pytest tests/ -m unit          # Run only unit tests
python -m pytest tests/ -m "not slow"    # Skip slow tests
```

### Run with coverage:
```bash
python -m pytest tests/ --cov=src --cov-report=html
```

## Test Categories

Tests are marked with the following markers:

- `@pytest.mark.unit` - Fast unit tests (no external dependencies)
- `@pytest.mark.integration` - Integration tests (may use external services)
- `@pytest.mark.slow` - Slow running tests
- `@pytest.mark.requires_api` - Tests that require API keys

## Key Test Areas

### 1. Provider Tests (`test_providers.py`)
- LLMResponse dataclass creation and fields
- ProviderLimits configuration
- ProviderRegistry registration and retrieval
- Provider interface compliance

### 2. Orchestrator Cache Tests (`test_orchestrator_cache.py`)
- Cache hit/miss behavior
- TTL-based expiration
- Query normalization for better matching
- Intent-based semantic caching
- Cache statistics tracking
- File persistence

### 3. Working Memory Tests (`test_orchestrator_memory.py`)
- LRU cache eviction
- File read tracking
- Search result storage
- Serialization/deserialization
- Context string generation

### 4. Task Classification Tests (`test_task_classifier.py`)
- Pattern matching for different task types
- Direct command recognition
- Code generation detection
- Research query identification
- Safety checks for dangerous commands
- Confidence scoring

### 5. Task Router Tests (`test_task_router.py`)
- Task routing logic
- Confidence escalation
- Intent clarification detection
- Execution metrics tracking
- Strategy selection

### 6. Agent Tools Tests (`test_agent_tools.py`)
- ToolContext path safety
- Tool parameter validation
- Tool registry operations
- Path traversal prevention
- Tool execution

### 7. Platform Utils Tests (`test_platform_utils.py`)
- Platform detection (Windows/Unix/macOS)
- Command translation between platforms
- Dangerous command detection
- Path normalization
- Shell information retrieval

### 8. Context Tests (`test_context.py`)
- Codebase exploration
- File type detection
- Project structure analysis
- Cache persistence
- Prompt augmentation

## Fixtures

Common fixtures available in `conftest.py`:

- `mock_llm_response` - Factory for creating mock LLM responses
- `mock_provider` - Mock LLM provider with configurable behavior
- `mock_registry` - Mock provider registry
- `temp_project_dir` - Temporary project directory with basic structure
- `sample_codebase_context` - Pre-configured codebase context
- `isolated_orchestrator` - Orchestrator instance without real API calls

## Current Coverage

As of initial setup:
- **204 tests total**
- **200 passing (98%)**
- **4 skipped (interactive prompt tests)**

### Code Coverage Breakdown

Run `python -m pytest tests/ --cov=src --cov-report=term-missing` for full report.

**Overall: 23.76%** (excellent baseline for core infrastructure)

**Well-tested modules (>70% coverage):**
- `orchestrator/memory.py`: 100%
- `task_router/classifier.py`: 95.95%
- `agent_tools/tools/base.py`: 96.20%
- `providers/base.py`: 86.76%
- `platform_utils.py`: 70.83%
- `orchestrator/cache.py`: 67.43%
- `context.py`: 54.47%

**Modules needing more coverage:**
- CLI modules: 0% (integration tests needed)
- `agent.py`: 0% (complex agent workflows)
- Provider implementations: 24-32%
- Task router strategies: 24-40%

## Known Issues

1. **Context caching tests** - Some timing issues with cache serialization
2. **Safety check tests** - Classifier doesn't block all pipe-to-shell patterns
3. **Platform-specific behavior** - Some tests behave differently on Windows vs Unix

## Adding New Tests

1. Create test file in `tests/` directory with `test_` prefix
2. Import fixtures from `conftest.py`
3. Mark tests with appropriate markers (`@pytest.mark.unit`, etc.)
4. Use descriptive test names that explain what's being tested
5. Group related tests in classes

Example:
```python
import pytest

class TestNewFeature:
    @pytest.mark.unit
    def test_feature_works(self, temp_project_dir):
        """Test that new feature works correctly."""
        # Test implementation
        assert result == expected
```

## Best Practices

1. Keep tests fast - mock external dependencies
2. Use fixtures for shared setup
3. Test edge cases and error conditions
4. Write descriptive test names
5. Group related tests in classes
6. Mark tests appropriately for filtering
