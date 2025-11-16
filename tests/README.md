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

As of latest update:
- **312 tests total**
- **308 passing (98.7%)**
- **4 skipped (interactive prompt tests)**

### Code Coverage Breakdown

Run `python -m pytest tests/ --cov=src --cov-report=term-missing` for full report.

**Overall: 32.83%** (improved from 23.76% baseline)

**Well-tested modules (>70% coverage):**
- `orchestrator/memory.py`: 100%
- `agent_tools/tools/__init__.py`: 100%
- `agent_tools/__init__.py`: 100%
- `orchestrator/__init__.py`: 100%
- `providers/__init__.py`: 100%
- `task_router/__init__.py`: 100%
- `cli/__init__.py`: 100%
- `agent_tools/tools/base.py`: 96.20%
- `task_router/classifier.py`: 95.95%
- `cli/commands.py`: 90.00%
- `providers/base.py`: 86.76%
- `agent_tools/tools/registry.py`: 80.77%
- `platform_utils.py`: 73.96%
- `providers/cohere_provider.py`: 72.46%
- `orchestrator/cache.py`: 70.86%

**Improved modules:**
- `providers/groq_provider.py`: 58.90%
- `orchestrator_adapter.py`: 55.67%
- `context.py`: 54.47%
- `providers/cerebras_provider.py`: 48.54%
- `providers/gemini_provider.py`: 47.34%
- `task_router/router.py`: 40.81%
- `intent_classifier.py`: 38.33%
- `orchestrator/rate_limiter.py`: 36.21%

**Modules needing more coverage:**
- CLI modules: 5-23% (functional tests needed)
- `agent.py`: ~30% (complex agent workflows)
- Task router strategies: 24.53%
- Orchestrator core: 18.21%

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
