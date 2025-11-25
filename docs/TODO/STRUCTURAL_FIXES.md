
## 1. Consolidate Output Systems

Multiple parallel output abstractions exist with overlapping responsibilities:

### Current State

| System | Location | Type | Methods | Purpose |
|--------|----------|------|---------|---------|
| **OutputHandlerInterface** | `src/task_router/output_handler.py:36` | ABC | `log_classification`, `log_provider_selection`, `log_execution_start`, `log_info` | Task router logging |
| **OutputInterface** | `src/cli/output.py:40` | ABC | `print`, `style`, `prompt`, `confirm` | CLI library abstraction (Rich/Click) |
| **OutputSink** | `src/cli/protocols.py:18` | Protocol | `post_output`, `post_renderable` | TUI message queue routing |
| **OutputInterface** | `src/orchestrator/protocols.py:614` | Protocol | `info`, `warn`, `error`, `success` | Operational logging |

### Problems

1. **Name Collision**: Two different `OutputInterface` classes exist:
   - `src/cli/output.py:40` - CLI library abstraction
   - `src/orchestrator/protocols.py:614` - Operational logging

2. **Adapter Complexity**: Multiple bridge classes exist:
   - `OrchestratorOutputAdapter` (textual_interactive.py) - orchestrator -> OutputSink
   - `CLIIOOutputHandler` (task_router/output_handler.py) - CLIIOProtocol -> OutputHandlerInterface
   - `OutputSinkAdapter` (unified_io.py) - UnifiedIO -> OutputSink

3. **Inconsistent Abstraction Levels**:
   - OutputHandlerInterface: Domain-specific (classification, provider selection)
   - CLI OutputInterface: Library-specific (Rich vs Click)
   - OutputSink: Transport-specific (queue-based for Textual)
   - Orchestrator OutputInterface: Message-level (info/warn/error)

### Recommended Refactoring

**Step 1: Rename to avoid collision**
```python
# cli/output.py
class FormattedOutputInterface(ABC):  # was OutputInterface
    ...

# orchestrator/protocols.py
class OperationalOutputProtocol(Protocol):  # was OutputInterface
    ...
```

**Step 2: Extract common base protocol**
```python
# protocols/output.py (new file)
class BaseOutputProtocol(Protocol):
    """Core output contract - message-level logging."""
    def info(self, message: str) -> None: ...
    def warn(self, message: str) -> None: ...
    def error(self, message: str) -> None: ...
    def success(self, message: str) -> None: ...
```

**Step 3: Build hierarchy**
```python
class FormattedOutputProtocol(BaseOutputProtocol, Protocol):
    """Adds styled output and user interaction."""
    def print(self, text: str, color: str | None = None, bold: bool = False) -> None: ...
    def style(self, text: str, color: str | None = None, bold: bool = False) -> str: ...
    def prompt(self, text: str, default: str = "") -> str: ...
    def confirm(self, text: str, default: bool = False) -> bool: ...

class RichRenderableProtocol(Protocol):
    """Rich-specific rendering for TUI mode."""
    def post_output(self, content: str) -> None: ...
    def post_renderable(self, obj: RenderableType) -> None: ...
```

**Step 4: Consolidate adapters**
- Merge bridge classes into a single `OutputBridge` that routes based on mode
- Remove redundant adapter layers

### Implementation Files to Modify

| File | Change |
|------|--------|
| `src/cli/output.py` | Rename `OutputInterface` -> `FormattedOutputInterface` |
| `src/orchestrator/protocols.py` | Rename `OutputInterface` -> `OperationalOutputProtocol` |
| `src/protocols/output.py` | Create new file with `BaseOutputProtocol` |
| `src/cli/protocols.py` | Have `OutputSink` extend `BaseOutputProtocol` |
| `src/task_router/output_handler.py` | Migrate ABC -> Protocol |
| `src/cli/unified_io.py` | Simplify `OutputSinkAdapter` |
| `src/cli/textual_interactive.py` | Simplify `OrchestratorOutputAdapter` |

---

## 2. Complete ABC to Protocol Migration

### ABCs That Should Be Protocols

| Priority | File | Class | Line | Why Convert |
|----------|------|-------|------|-------------|
| CRITICAL | `src/task_router/intent_clarifier.py` | `IntentClarifierInterface` | 21 | Already deprecated - docstring says use Protocol |
| HIGH | `src/task_router/output_handler.py` | `OutputHandlerInterface` | 36 | Pure interface, no concrete logic, 6 implementations |
| HIGH | `src/agent/response_parser.py` | `ResponseParser` | 26 | Single method interface, 3 implementations |
| HIGH | `src/task_router/strategies/base.py` | `ExecutionStrategy` | 172 | Pure contract, no concrete logic |
| MEDIUM | `src/cli/output.py` | `OutputInterface` | 40 | Pure contract, helper methods can be standalone |
| MEDIUM | `src/providers/base.py` | `LLMProvider` | 167 | Core contract with some helpers - could split |
| MEDIUM | `src/agent_tools/tools/base.py` | `Tool` | 101 | Mix of contract and helpers - could split |
| LOW | `src/task_router/classification_strategy.py` | `ClassificationStrategy` | 33 | Has concrete utility methods |

### Dead Import to Clean Up

- `src/agent_tools/formatters/output_formatter.py:7` - Imports `ABC, abstractmethod` but uses Protocol instead

### Conversion Pattern

**Before (ABC):**
```python
from abc import ABC, abstractmethod

class ResponseParser(ABC):
    @abstractmethod
    def parse(self, response_text: str) -> ParseResult:
        pass
```

**After (Protocol):**
```python
from typing import Protocol

class ResponseParserProtocol(Protocol):
    """Protocol for response parsing."""
    def parse(self, response_text: str) -> ParseResult: ...
```

### For ABCs with Concrete Methods

Split into Protocol + base implementation:

```python
# Protocol defines the contract
class ToolProtocol(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def description(self) -> str: ...
    @property
    def parameters(self) -> list[ToolParameter]: ...
    def execute(self, context: ToolContext, **kwargs) -> ToolResult: ...

# Base class provides shared utilities (not required to inherit)
class ToolBase:
    """Optional base class with helper methods."""
    def parameters_schema(self) -> dict: ...
    def validate(self, **kwargs) -> list[str]: ...
    def get_signature(self) -> str: ...
```

---

## 3. Add Protocol Conformance Tests

### Current Test Coverage

The codebase has 52+ Protocol definitions with varying test coverage:

| Area | Protocols | Tested | Coverage |
|------|-----------|--------|----------|
| Task Router | 10 | 9 | 90% |
| Infrastructure | 7 | 6 | 86% |
| Agent | 12 | 11 | 92% |
| Orchestrator | 10 | 10 | 100% |
| CLI | 8 | 8 | 100% |
| Context | 7 | 7 | 100% |

### Missing Protocol Conformance Tests

Current tests verify behavior but don't explicitly verify protocol conformance. Need to add:

```python
# tests/test_protocol_conformance.py

from typing import runtime_checkable, Protocol, get_type_hints
import pytest

def assert_implements_protocol(implementation: type, protocol: type) -> None:
    """Verify a class implements all protocol methods with correct signatures."""
    protocol_hints = get_type_hints(protocol)
    impl_hints = get_type_hints(implementation)

    for method_name in protocol_hints:
        assert hasattr(implementation, method_name), \
            f"{implementation.__name__} missing {method_name}"
        # Additional signature checks...

class TestOutputProtocolConformance:
    def test_console_output_implements_protocol(self):
        from src.orchestrator.output import ConsoleOutput
        from src.orchestrator.protocols import OutputInterface
        assert_implements_protocol(ConsoleOutput, OutputInterface)

    def test_null_output_implements_protocol(self):
        from src.orchestrator.output import NullOutput
        from src.orchestrator.protocols import OutputInterface
        assert_implements_protocol(NullOutput, OutputInterface)

class TestCacheProtocolConformance:
    def test_response_cache_implements_protocol(self):
        from src.orchestrator.cache import ResponseCache
        from src.orchestrator.protocols import CacheProtocol
        assert_implements_protocol(ResponseCache, CacheProtocol)
```

### Protocols Needing Explicit Conformance Tests

| Protocol | Implementations to Test |
|----------|------------------------|
| `CacheProtocol` | ResponseCache, InMemoryCache |
| `FileSystemProtocol` | RealFileSystem, InMemoryFileSystem |
| `RateLimitTrackerProtocol` | RateLimitTracker |
| `SessionManagerProtocol` | SessionManager, InMemorySessionManager |
| `ProviderSelectorProtocol` | ProviderSelector |
| `ToolRegistryProtocol` | ToolRegistry |
| `ResponseParserProtocol` | JSONResponseParser, NativeToolCallParser, UnifiedResponseParser |

### Runtime Checkable Protocols

For protocols marked `@runtime_checkable`, add isinstance checks:

```python
def test_textual_adapter_is_output_sink():
    from src.cli.textual_app import TextualOutputAdapter
    from src.cli.protocols import OutputSink

    adapter = TextualOutputAdapter(queue.Queue())
    assert isinstance(adapter, OutputSink)
```

### Test File Organization

```
tests/
  protocol_conformance/
    __init__.py
    test_output_conformance.py      # All output protocol implementations
    test_cache_conformance.py       # Cache implementations
    test_filesystem_conformance.py  # FileSystem implementations
    test_provider_conformance.py    # Provider protocol implementations
    conftest.py                     # Shared fixtures and helpers
```

---

## Implementation Plan

This section provides a phased approach to implementing the structural fixes above. Each phase is independent and can be executed separately, though the order is recommended.

### Phase 1: Resolve Name Collisions (Low Risk, High Impact) - COMPLETED

**Goal:** Eliminate the `OutputInterface` name collision without breaking existing code.

**Status:** COMPLETED (2025-01-25)

**Tasks:**

1.1. **Rename CLI OutputInterface** - DONE
   - File: `src/cli/output.py`
   - Change: `OutputInterface` -> `FormattedOutputInterface`
   - Updated all class implementations (`TestOutput`, `RichOutput`, `ClickOutput`, `Output`)
   - Updated factory function return type

1.2. **Rename Orchestrator OutputInterface** - DONE
   - File: `src/orchestrator/protocols.py`
   - Change: `OutputInterface` -> `OperationalOutputProtocol`
   - Added backward compatibility aliases in:
     - `src/orchestrator/protocols.py`
     - `src/orchestrator/output.py`
     - `src/orchestrator/__init__.py`
     - `src/orchestrator/factory.py`
     - `src/orchestrator/status_reporter.py`
     - `src/orchestrator/context_coordinator.py`
   - Updated docstring in `src/cli/textual_interactive.py`

1.3. **Verify no remaining collisions** - DONE
   - All orchestrator output tests pass (39 tests)
   - All CLI tests pass
   - All imports work correctly
   - Backward compatibility maintained via `OutputInterface = OperationalOutputProtocol` aliases

**Actual Changes:** 8 files modified

---

### Phase 2: ABC to Protocol Migration (Critical Priority) - COMPLETED

**Goal:** Convert deprecated and pure-interface ABCs to Protocols.

**Status:** COMPLETED (2025-01-25)

**Tasks:**

2.1. **Remove deprecated IntentClarifierInterface** - DONE
   - Removed `IntentClarifierInterface` ABC from `src/task_router/intent_clarifier.py`
   - Updated `InteractiveClarifier`, `AutoClarifier`, `NullClarifier` to standalone classes
   - `IntentClarifierProtocol` already existed in `src/task_router/protocols.py`
   - Updated exports in `src/task_router/__init__.py`
   - Updated tests in `tests/task_router/test_intent_clarifier.py` (removed deprecation tests)

2.2. **Convert ResponseParser ABC to Protocol** - DONE
   - Removed `ResponseParser` ABC from `src/agent/response_parser.py`
   - Simplified `ResponseParserProtocol` in `src/agent/protocols.py` to minimal interface
   - Updated implementations to standalone classes:
     - `JSONResponseParser`
     - `NativeToolCallParser`
     - `UnifiedResponseParser`
   - Updated `src/agent/core.py` to use `ResponseParserProtocol` type annotation
   - Updated exports in `src/agent/__init__.py`

2.3. **Convert OutputHandlerInterface ABC to Protocol** - DONE
   - Removed `OutputHandlerInterface` ABC from `src/task_router/output_handler.py`
   - Created `OutputHandlerProtocol` in `src/task_router/protocols.py`
   - Updated 6 implementations to standalone classes:
     - `ConsoleOutputHandler`
     - `BufferOutputHandler`
     - `NullOutputHandler`
     - `FileOutputHandler`
     - `CLIIOOutputHandler`
     - `RichOutputHandler`
   - Updated `src/task_router/router.py` to use `OutputHandlerProtocol`
   - Updated exports in `src/task_router/__init__.py`

2.4. **Convert ExecutionStrategy ABC to Protocol** - DONE
   - Removed `ExecutionStrategy` ABC from `src/task_router/strategies/base.py`
   - Created `ExecutionStrategyProtocol` in `src/task_router/protocols.py`
   - Updated strategy implementations:
     - `DirectExecutor` - now standalone class
     - `ConversationExecutor` - now standalone class
     - `ProviderAwareStrategy` - remains as helper base class (not ABC)
     - `ResearchExecutor`, `AgentExecutor` - extend `ProviderAwareStrategy`
   - Updated `src/task_router/router.py` to use `ExecutionStrategyProtocol`
   - Updated exports in `src/task_router/__init__.py` and `src/task_router/strategies/__init__.py`

2.5. **Clean up dead import** - DONE
   - Removed `from abc import ABC, abstractmethod` from `src/agent_tools/formatters/output_formatter.py`

**Actual Changes:** 15 files modified

**Files Modified:**
- `src/task_router/intent_clarifier.py`
- `src/task_router/output_handler.py`
- `src/task_router/protocols.py`
- `src/task_router/router.py`
- `src/task_router/__init__.py`
- `src/task_router/strategies/base.py`
- `src/task_router/strategies/direct_executor.py`
- `src/task_router/strategies/conversation_executor.py`
- `src/task_router/strategies/__init__.py`
- `src/agent/response_parser.py`
- `src/agent/protocols.py`
- `src/agent/core.py`
- `src/agent/__init__.py`
- `src/agent_tools/formatters/output_formatter.py`
- `tests/task_router/test_intent_clarifier.py`

**Verification:**
- 479 tests passed
- All protocol conformance checks pass via `isinstance()` with `@runtime_checkable`
- All imports work correctly

---

### Phase 3: Split ABCs with Concrete Methods (Medium Priority) - COMPLETED

**Goal:** Separate interface contracts (Protocols) from shared implementations (base classes).

**Status:** COMPLETED (2025-01-25)

**Tasks:**

3.1. **Split LLMProvider** - DONE
   - File: `src/providers/base.py`
   - Created `LLMProviderProtocol` with minimal interface (name, available_models, default_model, chat, get_limits)
   - Created `LLMProviderBase` with shared utilities (chat_async, is_available, estimate_cost, chat_with_tools, etc.)
   - Added `LLMProvider = LLMProviderBase` backward compatibility alias
   - Updated `ProviderRegistry` to use `LLMProviderProtocol` for type hints
   - Updated `src/providers/__init__.py` to export new types
   - All provider implementations continue to work unchanged (extend LLMProviderBase via alias)

3.2. **Split Tool ABC** - DONE
   - File: `src/agent_tools/tools/base.py`
   - Created `ToolProtocol` with minimal interface (name, description, parameters, execute)
   - Created `ToolBase` with shared utilities (parameters_schema, validate, get_signature, get_full_description, __call__)
   - Added `Tool = ToolBase` backward compatibility alias
   - Updated `src/agent_tools/tools/__init__.py` to export new types
   - All tool implementations continue to work unchanged (extend ToolBase via alias)

3.3. **Split ClassificationStrategy ABC** - DONE
   - File: `src/task_router/classification_strategy.py`
   - Created `ClassificationStrategyProtocol` with minimal interface (task_type, evaluate)
   - Created `ClassificationStrategyBase` with shared evaluation logic (_init_patterns, evaluate, _generate_reasoning)
   - Added `ClassificationStrategy = ClassificationStrategyBase` backward compatibility alias
   - `PatternBasedStrategy` continues to extend `ClassificationStrategy` (via alias)
   - Updated `src/task_router/__init__.py` to export new types
   - All concrete strategies (ResearchStrategy, DirectCommandStrategy, etc.) work unchanged

**Actual Changes:** 8 files modified

**Files Modified:**
- `src/providers/base.py`
- `src/providers/__init__.py`
- `src/agent_tools/tools/base.py`
- `src/agent_tools/tools/__init__.py`
- `src/task_router/classification_strategy.py`
- `src/task_router/__init__.py`
- `tests/test_response_parser.py` (fixed import of removed ABC)

**Verification:**
- 3023 tests passed
- All protocol conformance checks pass via `isinstance()` with `@runtime_checkable`
- All imports work correctly
- Backward compatibility maintained via aliases

---

### Phase 4: Create Unified Output Protocol Hierarchy (Medium Priority)

**Goal:** Establish a clean protocol hierarchy for all output abstractions.

**Tasks:**

4.1. **Create base output protocol**
   - Create file: `src/protocols/output.py`
   - Define:
     ```python
     class BaseOutputProtocol(Protocol):
         def info(self, message: str) -> None: ...
         def warn(self, message: str) -> None: ...
         def error(self, message: str) -> None: ...
         def success(self, message: str) -> None: ...
     ```

4.2. **Create extended protocols**
   - In same file, add:
     ```python
     class FormattedOutputProtocol(BaseOutputProtocol, Protocol):
         def print(self, text: str, color: str | None = None, bold: bool = False) -> None: ...
         def style(self, text: str, color: str | None = None, bold: bool = False) -> str: ...
         def prompt(self, text: str, default: str = "") -> str: ...
         def confirm(self, text: str, default: bool = False) -> bool: ...

     class RichRenderableProtocol(Protocol):
         def post_output(self, content: str) -> None: ...
         def post_renderable(self, obj: RenderableType) -> None: ...
     ```

4.3. **Update existing implementations**
   - `src/orchestrator/output.py`: Implement `BaseOutputProtocol`
   - `src/cli/output.py`: Implement `FormattedOutputProtocol`
   - `src/cli/protocols.py`: `OutputSink` extends or is compatible with `RichRenderableProtocol`

4.4. **Consolidate adapters**
   - Create unified `OutputBridge` class
   - Deprecate: `OrchestratorOutputAdapter`, `OutputSinkAdapter` (or reduce to thin wrappers)
   - Route based on output mode (CLI/TUI/Test)

**Estimated Changes:** 8-12 files, ~300 lines modified

---

### Phase 5: Add Protocol Conformance Tests (High Priority)

**Goal:** Ensure all protocol implementations are explicitly tested for conformance.

**Tasks:**

5.1. **Create test infrastructure**
   - Create directory: `tests/protocol_conformance/`
   - Create: `tests/protocol_conformance/__init__.py`
   - Create: `tests/protocol_conformance/conftest.py` with helpers:
     ```python
     from typing import Protocol, get_type_hints
     import inspect

     def assert_implements_protocol(implementation: type, protocol: type) -> None:
         """Verify a class implements all protocol methods with correct signatures."""
         for name, method in inspect.getmembers(protocol, predicate=inspect.isfunction):
             if name.startswith('_'):
                 continue
             assert hasattr(implementation, name), f"{implementation.__name__} missing {name}"
             # Verify method signature compatibility
             proto_sig = inspect.signature(getattr(protocol, name))
             impl_sig = inspect.signature(getattr(implementation, name))
             # Compare parameters (simplified)
     ```

5.2. **Add output protocol conformance tests**
   - Create: `tests/protocol_conformance/test_output_conformance.py`
   - Test: `ConsoleOutput`, `NullOutput`, `CapturingOutput` against `OperationalOutputProtocol`
   - Test: `RichOutput`, `ClickOutput`, `TestOutput` against `FormattedOutputInterface`
   - Test: `TextualOutputAdapter` against `OutputSink`

5.3. **Add cache protocol conformance tests**
   - Create: `tests/protocol_conformance/test_cache_conformance.py`
   - Test: `ResponseCache` against `CacheProtocol`

5.4. **Add filesystem protocol conformance tests**
   - Create: `tests/protocol_conformance/test_filesystem_conformance.py`
   - Test: `RealFileSystem`, `InMemoryFileSystem` against `FileSystemProtocol`

5.5. **Add provider protocol conformance tests**
   - Create: `tests/protocol_conformance/test_provider_conformance.py`
   - Test all provider implementations against `LLMProviderProtocol`

5.6. **Add agent protocol conformance tests**
   - Create: `tests/protocol_conformance/test_agent_conformance.py`
   - Test: Response parsers, tool registry, prompt builder

5.7. **Add task router protocol conformance tests**
   - Create: `tests/protocol_conformance/test_task_router_conformance.py`
   - Test: Execution strategies, output handlers, classifiers

**Estimated Changes:** 7-10 new files, ~800 lines of tests

---

### Phase 6: Cleanup and Documentation (Low Priority)

**Goal:** Remove deprecated code and document the new architecture.

**Tasks:**

6.1. **Remove deprecated ABC classes**
   - After Phase 2 and 3, remove old ABC definitions that have been replaced
   - Ensure no remaining references

6.2. **Update imports across codebase**
   - Ensure all imports use new protocol names
   - Remove backward-compatibility aliases

6.3. **Update architecture documentation**
   - Document the new protocol hierarchy
   - Update any architecture diagrams

**Estimated Changes:** 5-10 files, ~100 lines modified

---

### Implementation Order Summary

| Phase | Description | Priority | Risk | Effort |
|-------|-------------|----------|------|--------|
| 1 | Resolve Name Collisions | High | Low | Small |
| 2 | ABC to Protocol Migration (Critical) | Critical | Medium | Medium |
| 3 | Split ABCs with Concrete Methods | Medium | Medium | Large |
| 4 | Unified Output Protocol Hierarchy | Medium | Medium | Medium |
| 5 | Protocol Conformance Tests | High | Low | Medium |
| 6 | Cleanup and Documentation | Low | Low | Small |

**Recommended Execution Order:** Phase 1 -> Phase 2 -> Phase 5 -> Phase 3 -> Phase 4 -> Phase 6

**Rationale:**
- Phase 1 is low-risk and immediately improves code clarity
- Phase 2 removes deprecated code and should happen early
- Phase 5 (tests) should come before major refactoring in Phase 3/4 to catch regressions
- Phase 3/4 are larger refactorings that benefit from test coverage
- Phase 6 is cleanup that happens after other changes stabilize

---

### Verification Checklist

After each phase, verify:

- [ ] All tests pass: `python -m pytest tests/ -v`
- [ ] No import errors: `python -c "import src"`
- [ ] Type checking passes (if using mypy): `mypy src/`
- [ ] No deprecated ABC usage warnings
- [ ] Protocol conformance tests pass (after Phase 5)
