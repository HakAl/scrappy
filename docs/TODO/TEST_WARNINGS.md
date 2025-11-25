# Test Warnings Report

---

## Implementation Plan

### Design Principles Applied

This plan follows the architectural principles from CLAUDE.md:

1. **Protocol-First Design**: The `ClarificationConfigProtocol` already exists; we use it
2. **Dependency Injection**: Test fixtures inject explicit config, avoiding warnings
3. **Single Responsibility**: Each fix addresses one concern
4. **Open/Closed**: No modification to core logic - just providing explicit configuration

---

### Phase 1: Quick Wins (Single-line fixes)

**Fix 1.1: Import Deprecation (1 file)**

File: `tests/task_router/test_task_router_pure_functions.py:13`

```python
# Before
from src.config.schema import ClarificationConfig

# After
from src.task_router.config import ClarificationConfig
```

**Fix 1.2: PytestCollectionWarning (1 file)**

File: `tests/agent/test_agent_components.py:14`

The class `TestAgentUI` is a test double, not a test class. Add the `__test__` attribute:

```python
class TestAgentUI:
    """Test double for AgentUIProtocol."""
    __test__ = False  # Prevent pytest from collecting this as a test class

    def __init__(self):
        ...
```

---

### Phase 2: Centralized Test Fixture for TaskRouter (Core fix)

**Rationale**: Instead of modifying 100+ individual test files, create a shared fixture in `tests/conftest.py` that provides a properly configured `TaskRouter`. Tests that need specific configurations can override.

**Fix 2.1: Add shared fixture to `tests/conftest.py`**

```python
from src.task_router.config import ClarificationConfig
from src.task_router import TaskRouter

@pytest.fixture
def default_clarification_config():
    """
    Provide explicit ClarificationConfig to suppress deprecation warnings.

    The default threshold changed from 0.65 to 0.7 in v2.0.
    By providing explicit config, we:
    1. Suppress the deprecation warning
    2. Make test behavior deterministic
    3. Document the expected threshold in tests
    """
    return ClarificationConfig(confidence_threshold=0.7, high_confidence_bypass=0.9)


@pytest.fixture
def task_router(default_clarification_config, mock_provider):
    """
    Pre-configured TaskRouter for tests.

    Uses explicit ClarificationConfig to avoid deprecation warnings.
    Tests needing custom config should create their own router.
    """
    return TaskRouter(
        orchestrator=None,
        verbose=False,
        clarification_config=default_clarification_config,
    )
```

**Fix 2.2: Update test files to use the fixture**

For files with pytest fixtures (e.g., `test_task_router.py`):

```python
# Before
@pytest.fixture
def router():
    return TaskRouter(orchestrator=None, verbose=False)

# After - use the conftest fixture directly, or:
@pytest.fixture
def router(default_clarification_config):
    return TaskRouter(
        orchestrator=None,
        verbose=False,
        clarification_config=default_clarification_config,
    )
```

For files with direct instantiation:

```python
# Before
router = TaskRouter(orchestrator=None, verbose=False)

# After
from src.task_router.config import ClarificationConfig
config = ClarificationConfig()
router = TaskRouter(orchestrator=None, verbose=False, clarification_config=config)
```

**Fix 2.3: Update `task_router_handler.py` (production code)**

File: `src/cli/task_router_handler.py:118`

The handler creates routers without explicit config. Fix by injecting config:

```python
# In _create_default_router method
from src.task_router.config import ClarificationConfig

return TaskRouter(
    orchestrator=self.orchestrator,
    project_root=self.project_root,
    auto_confirm_direct=self.auto_confirm,
    verbose=True,
    output_handler=CLIIOOutputHandler(self.io),
    input_handler=input_adapter,
    intent_clarifier=InteractiveClarifier(io=input_adapter),
    clarification_config=ClarificationConfig(),  # Add explicit config
)
```

---

### Phase 3: Resource Warning Fix

**Fix 3.1: Proper logging handler cleanup**

File: `scrappy.py:51`

The logging setup creates a FileHandler without cleanup. Options:

**Option A: Use atexit for cleanup (Recommended)**

```python
import atexit
import logging
from pathlib import Path

log_file = Path.cwd() / ".scrappy" / "debug.log"
log_file.parent.mkdir(parents=True, exist_ok=True)

# Create handler explicitly so we can close it
file_handler = logging.FileHandler(log_file, mode='w')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(
    logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
)

logging.basicConfig(
    level=logging.DEBUG,
    handlers=[file_handler, logging.StreamHandler()]
)

# Register cleanup
atexit.register(file_handler.close)
```


---

### Affected Files Summary

| File | Change Type | Fix |
|------|-------------|-----|
| `tests/conftest.py` | Add fixture | `default_clarification_config`, `task_router` |
| `tests/task_router/test_task_router_pure_functions.py` | Update import | Line 13 |
| `tests/agent/test_agent_components.py` | Add attribute | `__test__ = False` |
| `src/cli/task_router_handler.py` | Add parameter | `clarification_config=ClarificationConfig()` |
| `scrappy.py` | Refactor logging | Use explicit handler with atexit cleanup |
| `tests/cli/test_cli_handlers.py` | Update fixtures | Use `default_clarification_config` |
| `tests/cli/test_cli_interactive.py` | Update fixtures | Use `default_clarification_config` |
| `tests/cli/test_validator_integration.py` | Update fixtures | Use `default_clarification_config` |
| `tests/integration/test_cli_flows.py` | Update fixtures | Use `default_clarification_config` |
| `tests/task_router/test_task_router_io_injection.py` | Update fixtures | Use `default_clarification_config` |
| `tests/task_router/test_no_blocking_input.py` | Update instantiation | Add config parameter |
| `tests/task_router/test_task_classifier.py` | Update fixtures | Use `default_clarification_config` |
| `tests/task_router/test_task_router.py` | Update fixtures | Use `default_clarification_config` |
| `tests/task_router/test_task_router_dependency_injection.py` | Update instantiation | Add config parameter |
| `tests/test_error_recovery.py` | Update fixtures | Use `default_clarification_config` |

---

### Execution Order

1. Add `default_clarification_config` fixture to `tests/conftest.py`
2. Fix `tests/task_router/test_task_router_pure_functions.py` import
3. Fix `tests/agent/test_agent_components.py` with `__test__ = False`
4. Fix `src/cli/task_router_handler.py` production code
5. Update test files in order:
   - `tests/task_router/*.py` (direct TaskRouter usage)
   - `tests/cli/*.py` (uses handler)
   - `tests/integration/*.py`
   - `tests/test_error_recovery.py`
6. Fix `scrappy.py` logging
7. Run full test suite to verify: `python -m pytest tests/ -v`

---

### Verification

After implementation, run:

```bash
python -m pytest tests/ -v --tb=short 2>&1 | grep -E "(DeprecationWarning|ResourceWarning|PytestCollectionWarning)"
```

Expected output: No warnings (empty output).

---

## Summary

| Category | Count | Severity | Fix Effort |
|----------|-------|----------|------------|
| TaskRouter deprecation (confidence_threshold) | 100+ | Low | Easy - pass explicit `ClarificationConfig` |
| Import deprecation (ClarificationConfig) | 1 | Low | Easy - update import path |
| PytestCollectionWarning (TestAgentUI) | 1 | Low | Easy - rename class or remove `__init__` |
| ResourceWarning (unclosed file) | 1 | Medium | Easy - use context manager for log file |

**Total: ~129 warnings from 4 root causes**

---

## Detailed Breakdown

### 1. TaskRouter Deprecation Warning (100+ occurrences)

**Warning:**
```
DeprecationWarning: Default confidence_threshold changed from 0.65 to 0.7 in v2.0.
Pass explicit ClarificationConfig to suppress this warning.
```

**Source:** `src/cli/task_router_handler.py:118`

**Affected Test Files:**
- `tests/cli/test_cli_handlers.py` (9 warnings)
- `tests/cli/test_cli_interactive.py` (14 warnings)
- `tests/cli/test_validator_integration.py` (16 warnings)
- `tests/integration/test_cli_flows.py` (31 warnings)
- `tests/task_router/test_task_router_io_injection.py` (30 warnings)
- `tests/task_router/test_no_blocking_input.py` (3 warnings)
- `tests/task_router/test_task_classifier.py` (5 warnings)
- `tests/task_router/test_task_router.py` (7 warnings)
- `tests/task_router/test_task_router_dependency_injection.py` (8 warnings)
- `tests/test_error_recovery.py` (3 warnings)

**Fix:**
```python
# Before
router = TaskRouter(orchestrator=None, verbose=False)

# After
from src.task_router.config import ClarificationConfig
config = ClarificationConfig(confidence_threshold=0.7)
router = TaskRouter(orchestrator=None, verbose=False, clarification_config=config)
```

---

### 2. Import Deprecation Warning (1 occurrence)

**Warning:**
```
DeprecationWarning: Importing ClarificationConfig from src.config.schema is deprecated.
Import from src.task_router.config instead.
```

**Source:** `tests/task_router/test_task_router_pure_functions.py:13`

**Fix:**
```python
# Before
from src.config.schema import ClarificationConfig

# After
from src.task_router.config import ClarificationConfig
```

---

### 3. PytestCollectionWarning (1 occurrence)

**Warning:**
```
PytestCollectionWarning: cannot collect test class 'TestAgentUI' because it has a
__init__ constructor (from: tests/agent/test_agent_components.py)
```

**Source:** `tests/agent/test_agent_components.py:14`

**Fix Options:**
1. Remove the `__init__` constructor from `TestAgentUI`
2. Rename class to not start with `Test` (e.g., `AgentUIHelper`)
3. If it's not a test class, add `__test__ = False` attribute

---

### 4. ResourceWarning - Unclosed File (1 occurrence)

**Warning:**
```
ResourceWarning: unclosed file <_io.TextIOWrapper name='.scrappy/debug.log' mode='w' encoding='cp1252'>
```

**Source:** `scrappy.py:51` in `logging.basicConfig()`

**Triggered By:** `tests/test_unicode_encoding.py::test_utf8_environment_variables`

**Fix:**
```python
# Use a context manager or ensure file handle is properly closed
# Option 1: Use FileHandler with explicit close
handler = logging.FileHandler('.scrappy/debug.log', mode='w')
# ... ensure handler.close() is called on shutdown

# Option 2: Use atexit to clean up
import atexit
atexit.register(lambda: handler.close())
```

---

## Recommended Fix Priority

1. **Fix #2 (Import deprecation)** - Single line change, immediate fix
2. **Fix #3 (TestAgentUI)** - Quick fix, cleans up test collection
3. **Fix #1 (TaskRouter deprecation)** - Create a test fixture that provides configured router
4. **Fix #4 (ResourceWarning)** - Requires careful handling to not break logging

---

## Raw Warnings Output

```
================================================================ warnings summary ================================================================
tests\agent\test_agent_components.py:14
  C:\Users\anyth\MINE\dev\scrappy\tests\agent\test_agent_components.py:14: PytestCollectionWarning: cannot collect test class 'TestAgentUI' because it has a __init__ constructor (from: tests/agent/test_agent_components.py)
    class TestAgentUI:

tests\task_router\test_task_router_pure_functions.py:13
  C:\Users\anyth\MINE\dev\scrappy\tests\task_router\test_task_router_pure_functions.py:13: DeprecationWarning: Importing ClarificationConfig from src.config.schema is deprecated. Import from src.task_router.config instead.
    from src.config.schema import ClarificationConfig

tests/cli/test_cli_handlers.py: 9 warnings
tests/cli/test_cli_interactive.py: 14 warnings
tests/cli/test_validator_integration.py: 16 warnings
tests/integration/test_cli_flows.py: 31 warnings
tests/task_router/test_task_router_io_injection.py: 30 warnings
  C:\Users\anyth\MINE\dev\scrappy\src\cli\task_router_handler.py:118: DeprecationWarning: Default confidence_threshold changed from 0.65 to 0.7 in v2.0. Pass explicit ClarificationConfig to suppress this warning.
    return TaskRouter(

tests/task_router/test_no_blocking_input.py::TestTaskRouterInputHandler::test_task_router_accepts_input_handler
  C:\Users\anyth\MINE\dev\scrappy\tests\task_router\test_no_blocking_input.py:180: DeprecationWarning: Default confidence_threshold changed from 0.65 to 0.7 in v2.0. Pass explicit ClarificationConfig to suppress this warning.
    router = TaskRouter(input_handler=mock_input)

tests/task_router/test_no_blocking_input.py::TestTaskRouterInputHandler::test_task_router_creates_default_input_handler
  C:\Users\anyth\MINE\dev\scrappy\tests\task_router\test_no_blocking_input.py:189: DeprecationWarning: Default confidence_threshold changed from 0.65 to 0.7 in v2.0. Pass explicit ClarificationConfig to suppress this warning.
    router = TaskRouter()

tests/task_router/test_no_blocking_input.py::TestTaskRouterInputHandler::test_task_router_shares_input_handler_with_clarifier
  C:\Users\anyth\MINE\dev\scrappy\tests\task_router\test_no_blocking_input.py:197: DeprecationWarning: Default confidence_threshold changed from 0.65 to 0.7 in v2.0. Pass explicit ClarificationConfig to suppress this warning.
    router = TaskRouter()

tests/task_router/test_task_classifier.py::TestConfidenceScoring::test_confidence_affects_escalation
  C:\Users\anyth\MINE\dev\scrappy\tests\task_router\test_task_classifier.py:168: DeprecationWarning: Default confidence_threshold changed from 0.65 to 0.7 in v2.0. Pass explicit ClarificationConfig to suppress this warning.
    router = TaskRouter(orchestrator=None, verbose=False)

tests/task_router/test_task_classifier.py::TestIntentClarification::test_conflicting_intents_high_confidence_no_clarification
  C:\Users\anyth\MINE\dev\scrappy\tests\task_router\test_task_classifier.py:200: DeprecationWarning: Default confidence_threshold changed from 0.65 to 0.7 in v2.0. Pass explicit ClarificationConfig to suppress this warning.
    router = TaskRouter(orchestrator=None, verbose=False)

tests/task_router/test_task_classifier.py::TestIntentClarification::test_conflicting_intents_medium_confidence_needs_clarification
  C:\Users\anyth\MINE\dev\scrappy\tests\task_router\test_task_classifier.py:217: DeprecationWarning: Default confidence_threshold changed from 0.65 to 0.7 in v2.0. Pass explicit ClarificationConfig to suppress this warning.
    router = TaskRouter(orchestrator=None, verbose=False)

tests/task_router/test_task_classifier.py::TestIntentClarification::test_clear_intents_no_clarification
  C:\Users\anyth\MINE\dev\scrappy\tests\task_router\test_task_classifier.py:232: DeprecationWarning: Default confidence_threshold changed from 0.65 to 0.7 in v2.0. Pass explicit ClarificationConfig to suppress this warning.
    router = TaskRouter(orchestrator=None, verbose=False)

tests/task_router/test_task_classifier.py::TestIntentClarification::test_question_with_action_words_high_confidence
  C:\Users\anyth\MINE\dev\scrappy\tests\task_router\test_task_classifier.py:251: DeprecationWarning: Default confidence_threshold changed from 0.65 to 0.7 in v2.0. Pass explicit ClarificationConfig to suppress this warning.
    router = TaskRouter(orchestrator=None, verbose=False)

tests/task_router/test_task_router.py::TestConfidenceEscalation::test_low_confidence_research_with_action_word_escalates
tests/task_router/test_task_router.py::TestConfidenceEscalation::test_high_confidence_no_escalation
tests/task_router/test_task_router.py::TestConfidenceEscalation::test_escalation_updates_reasoning
  C:\Users\anyth\MINE\dev\scrappy\tests\task_router\test_task_router.py:19: DeprecationWarning: Default confidence_threshold changed from 0.65 to 0.7 in v2.0. Pass explicit ClarificationConfig to suppress this warning.
    return TaskRouter(orchestrator=None, verbose=False)

tests/task_router/test_task_router.py::TestIntentClarification::test_conflicting_intent_high_confidence_no_clarification
tests/task_router/test_task_router.py::TestIntentClarification::test_conflicting_intent_medium_confidence_needs_clarification
tests/task_router/test_task_router.py::TestIntentClarification::test_clear_action_no_clarification
tests/task_router/test_task_router.py::TestIntentClarification::test_clear_question_no_clarification
  C:\Users\anyth\MINE\dev\scrappy\tests\task_router\test_task_router.py:69: DeprecationWarning: Default confidence_threshold changed from 0.65 to 0.7 in v2.0. Pass explicit ClarificationConfig to suppress this warning.
    return TaskRouter(orchestrator=None, verbose=False)

tests/task_router/test_task_router_dependency_injection.py::TestTaskRouterDependencyInjection::test_accepts_custom_classifier
  C:\Users\anyth\MINE\dev\scrappy\tests\task_router\test_task_router_dependency_injection.py:44: DeprecationWarning: Default confidence_threshold changed from 0.65 to 0.7 in v2.0. Pass explicit ClarificationConfig to suppress this warning.
    router = TaskRouter(

tests/task_router/test_task_router_dependency_injection.py::TestTaskRouterDependencyInjection::test_accepts_custom_metrics_collector
  C:\Users\anyth\MINE\dev\scrappy\tests\task_router\test_task_router_dependency_injection.py:60: DeprecationWarning: Default confidence_threshold changed from 0.65 to 0.7 in v2.0. Pass explicit ClarificationConfig to suppress this warning.
    router = TaskRouter(

tests/task_router/test_task_router_dependency_injection.py::TestTaskRouterDependencyInjection::test_accepts_custom_provider_resolver
  C:\Users\anyth\MINE\dev\scrappy\tests\task_router\test_task_router_dependency_injection.py:76: DeprecationWarning: Default confidence_threshold changed from 0.65 to 0.7 in v2.0. Pass explicit ClarificationConfig to suppress this warning.
    router = TaskRouter(

tests/task_router/test_task_router_dependency_injection.py::TestInjectedClassifierIsUsed::test_classification_result_determines_strategy
  C:\Users\anyth\MINE\dev\scrappy\tests\task_router\test_task_router_dependency_injection.py:110: DeprecationWarning: Default confidence_threshold changed from 0.65 to 0.7 in v2.0. Pass explicit ClarificationConfig to suppress this warning.
    router = TaskRouter(

tests/task_router/test_task_router_dependency_injection.py::TestInjectedMetricsCollectorIsUsed::test_get_metrics_returns_from_injected_collector
  C:\Users\anyth\MINE\dev\scrappy\tests\task_router\test_task_router_dependency_injection.py:139: DeprecationWarning: Default confidence_threshold changed from 0.65 to 0.7 in v2.0. Pass explicit ClarificationConfig to suppress this warning.
    router = TaskRouter(

tests/task_router/test_task_router_dependency_injection.py::TestInjectedProviderResolverIsUsed::test_resolved_provider_appears_in_result_metadata
  C:\Users\anyth\MINE\dev\scrappy\tests\task_router\test_task_router_dependency_injection.py:165: DeprecationWarning: Default confidence_threshold changed from 0.65 to 0.7 in v2.0. Pass explicit ClarificationConfig to suppress this warning.
    router = TaskRouter(

tests/task_router/test_task_router_dependency_injection.py::TestAllDependenciesInjectedTogether::test_all_custom_dependencies_work_together
  C:\Users\anyth\MINE\dev\scrappy\tests\task_router\test_task_router_dependency_injection.py:205: DeprecationWarning: Default confidence_threshold changed from 0.65 to 0.7 in v2.0. Pass explicit ClarificationConfig to suppress this warning.
    router = TaskRouter(

tests/test_error_recovery.py::TestTaskRouterErrorHandling::test_router_handles_none_orchestrator
  C:\Users\anyth\MINE\dev\scrappy\tests\test_error_recovery.py:163: DeprecationWarning: Default confidence_threshold changed from 0.65 to 0.7 in v2.0. Pass explicit ClarificationConfig to suppress this warning.
    router = TaskRouter(orchestrator=None)

tests/test_error_recovery.py::TestTaskRouterErrorHandling::test_router_handles_conversation_without_orchestrator
tests/test_error_recovery.py::TestTaskRouterErrorHandling::test_router_metrics_with_failures
  C:\Users\anyth\MINE\dev\scrappy\tests\test_error_recovery.py:158: DeprecationWarning: Default confidence_threshold changed from 0.65 to 0.7 in v2.0. Pass explicit ClarificationConfig to suppress this warning.
    return TaskRouter(orchestrator=None, verbose=False)

tests/test_unicode_encoding.py::test_utf8_environment_variables
  C:\Users\anyth\MINE\dev\scrappy\scrappy.py:51: ResourceWarning: unclosed file <_io.TextIOWrapper name='C:\\Users\\anyth\\MINE\\dev\\scrappy\\.scrappy\\debug.log' mode='w' encoding='cp1252'>
    logging.basicConfig(
  Enable tracemalloc to get traceback where the object was allocated.
  See https://docs.pytest.org/en/stable/how-to/capture-warnings.html#resource-warnings for more info.

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
```
