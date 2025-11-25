# Failing Tests Summary

## Overview

35 tests failing across 4 test files. Root causes identified below.

---

## 1. test_rate_limit_recovery.py (8 failures)

**Error:** `TypeError: keys must be str, int, float, bool or None, not MagicMock`

**Root Cause:** The test fixture mocks `chat_async` but the code now uses sync `chat()` method.

**Location:** `tests/rate_limiting/test_rate_limit_recovery.py:69-129`

**Details:**
- The `mock_orchestrator` fixture sets up `mock_cerebras_instance.chat_async = AsyncMock()`
- But `RetryOrchestrator.execute_with_retry_sync()` calls `provider.chat()` (sync), not `chat_async()`
- Since `chat` is not mocked, it returns a MagicMock
- `response.model` becomes a MagicMock
- `rate_tracker.record_request()` tries to use this as a dict key
- JSON serialization fails when saving to disk

**Quick Fix:** Add `mock_instance.chat = MagicMock()` for each provider and set `chat.return_value = mock_response` in tests.

**Architectural Analysis:**

The mock mismatch reveals a deeper problem: there is no explicit `ProviderProtocol` defining whether providers expose `chat()`, `chat_async()`, or both. Tests were written against implementation details rather than a defined interface.

**Proper Fix:**
1. Define a `ProviderProtocol` that explicitly specifies the expected interface
2. Update production code to conform to the protocol
3. Write tests against the protocol, not implementation

This prevents future drift between tests and implementation.

**Affected Tests:**
- test_successful_request_no_fallback
- test_retry_on_rate_limit_then_success
- test_fallback_to_next_provider_on_rate_limit
- test_multiple_fallbacks_until_success
- test_all_providers_rate_limited_raises_error
- test_non_rate_limit_error_not_retried
- test_auto_fallback_disabled
- test_task_history_tracks_fallback

---

## 2. test_task_router_refactored.py (3 failures)

**Error:** `AssertionError: assert 'RESEARCH' in ''` (empty stdout)

**Root Cause:** `ConsoleOutputHandler` requires an `io` parameter to produce output, but tests don't provide one.

**Location:** `src/task_router/output_handler.py:76-134`

**Details:**
- `ConsoleOutputHandler.__init__(self, io: Optional['CLIIOProtocol'] = None)`
- If `io` is None, all log methods return early: `if not self._io: return`
- Tests create `ConsoleOutputHandler()` without providing `io`
- No output is produced, so `capsys.readouterr().out` is empty

**Quick Fix:** Either:
1. Provide a mock `io` object that implements `CLIIOProtocol`
2. Or modify tests to use `BufferOutputHandler` instead (which works without io)

**Architectural Analysis:**

The pattern `if not self._io: return` is a **silent failure anti-pattern**. The class accepts invalid state and silently does nothing. This violates fail-fast principles and makes debugging difficult.

**Proper Fix Options:**
1. **Make `io` required** - If the handler cannot function without it, do not make it optional. Raise `TypeError` if not provided.
2. **Use Null Object pattern** - Provide a `NullIO` implementation that explicitly does nothing, rather than scattering null checks throughout methods.
3. **Constructor validation** - If `io` is optional for some use cases, validate and raise `ValueError` with a clear message when methods that require it are called.

Using `BufferOutputHandler` in tests sidesteps testing `ConsoleOutputHandler` behavior entirely.

**Affected Tests:**
- test_console_output_handler_prints_to_stdout
- test_console_output_handler_logs_provider_selection
- test_console_output_handler_logs_execution_start

---

## 3. test_task_router_rich.py (16 failures)

**Error:** `TypeError: RichOutputHandler.__init__() got an unexpected keyword argument 'console'`

**Root Cause:** `RichOutputHandler` signature changed - it now takes `io` parameter, not `console`.

**Location:** `src/task_router/output_handler.py:345-362`

**Details:**
- Current signature: `def __init__(self, io: "CLIIOProtocol"):`
- Tests call: `handler = RichOutputHandler(console=console)`
- The `console` kwarg is no longer accepted

**Quick Fix:** Update tests to provide an `io` parameter that wraps the console.

**Architectural Analysis:**

This is a breaking API change that was not coordinated with tests. This reveals a process issue:
- API changes should be documented
- Tests should be updated in the same commit as API changes
- Consider backward compatibility during transitions

**Process Improvement:**
When changing constructor signatures:
1. Update all call sites in the same commit
2. If gradual migration is needed, accept both parameters temporarily with a deprecation warning
3. Document breaking changes in a CHANGELOG

**Affected Tests:**
All 16 tests in `TestRichOutputHandlerClassification`, `TestRichOutputHandlerProvider`, `TestRichOutputHandlerStrategy`, `TestRichOutputHandlerInfo`, `TestRichOutputHandlerIntegration`.

---

## 4. test_interactive_rich.py (8 failures)

### 4a. TestWelcomeBannerPanel (5 failures)

**Error:** `AttributeError: 'NoneType' object has no attribute 'post_renderable'`

**Root Cause:** `render_welcome_banner()` calls `io.output_sink.post_renderable(panel)` but `output_sink` is None.

**Location:** `src/cli/interactive_banner.py:68`

**Details:**
- The test creates `UnifiedIO(console=console)`
- But `UnifiedIO.output_sink` is None unless a Textual app is running
- Line 68: `io.output_sink.post_renderable(panel)` - fails because `output_sink` is None

**Quick Fix Options:**
1. Make `render_welcome_banner()` check if `output_sink` exists before calling it
2. Or mock `output_sink` in tests
3. Or use a different code path for non-Textual output

**Architectural Analysis:**

This is a critical architectural smell. The code assumes `output_sink` exists without verifying. The proposed quick fixes all mask the underlying problem.

**SOLID Violations:**
- **Liskov Substitution** - A `UnifiedIO` without `output_sink` cannot substitute for one with it. Methods that require `output_sink` will fail unpredictably.
- **Interface Segregation** - `UnifiedIO` has methods that only work in some configurations. Clients cannot know which methods are safe to call.

**Proper Fix:**
1. **Split interfaces** - Create separate protocols for IO with and without renderable output capability
2. **Fail fast** - If `render_welcome_banner` requires renderable output, require a type that guarantees it at compile time
3. **Type-safe configuration** - Use different IO implementations for Textual vs non-Textual contexts, not optional attributes

Example:
```python
class RenderableIOProtocol(Protocol):
    def post_renderable(self, renderable: Any) -> None: ...

def render_welcome_banner(io: RenderableIOProtocol) -> None:
    # Type system guarantees post_renderable exists
```

**Affected Tests:**
- test_welcome_banner_uses_panel_component
- test_welcome_banner_contains_ascii_art
- test_welcome_banner_shows_quick_commands
- test_welcome_banner_panel_has_border_style
- test_welcome_banner_shows_mode_statuses

### 4b. TestPlanTaskTreeDisplay (3 failures)

**Error:** `NameError: name 'title' is not defined`

**Root Cause:** Bug in `show_plan_tree()` - uses undefined variable `title`.

**Location:** `src/cli/display_rich.py:270`

**Details:**
- Line 270: `io.echo(f"\n{title}:")` - `title` is never defined
- Should probably be `goal` or `tree_title`

**Fix:** Replace `title` with `goal` on line 270.

**Architectural Analysis:**

This is a straightforward bug, not a design issue. Fix immediately.

**Affected Tests:**
- test_plan_displays_as_tree
- test_plan_tree_shows_task_status
- test_plan_tree_highlights_current_task

---

## Summary Table

| File | Failures | Root Cause | Quick Fix | Proper Fix |
|------|----------|------------|-----------|------------|
| test_rate_limit_recovery.py | 8 | Mock `chat` not `chat_async` | Add `chat` mock | Define ProviderProtocol |
| test_task_router_refactored.py | 3 | Missing `io` parameter | Mock io or use BufferOutputHandler | Make io required or use Null Object |
| test_task_router_rich.py | 16 | Wrong constructor arg | Change kwarg name | Coordinate API changes with tests |
| test_interactive_rich.py | 5 | `output_sink` is None | Add null check | Split interface, fail fast |
| test_interactive_rich.py | 3 | Undefined `title` variable | Change to `goal` | Same (this is correct) |

---

## Fix Priority

### Immediate (Bug Fix)
- `display_rich.py:270` - change `title` to `goal` (1 line) - This is an actual bug in production code

### Quick Fixes (Get Tests Passing)
- `test_task_router_rich.py` - change `console=` to `io=` (16 tests, same fix)
- `test_rate_limit_recovery.py` - add `chat` mock alongside `chat_async`
- `test_task_router_refactored.py` - provide mock io
- `interactive_banner.py` - add null check for `output_sink`

### Proper Fixes (Technical Debt)
These require more effort but address root causes:

1. **Define ProviderProtocol** - Establish explicit contract for provider interface
2. **Fix ConsoleOutputHandler** - Make `io` required or implement Null Object pattern
3. **Split UnifiedIO interfaces** - Separate capabilities into focused protocols
4. **Process improvement** - Update tests in same commit as API changes

---

## Recommendations

The quick fixes will get tests passing but accumulate technical debt. Consider:

1. **For time pressure:** Apply quick fixes, create follow-up tickets for proper fixes
2. **For quality:** Fix the `title` bug immediately, then address architectural issues before other quick fixes
3. **Minimum viable:** At least define protocols for new code going forward, even if existing code uses quick fixes

---

# Implementation Plan: Proper Architectural Fixes

## Overview

This plan addresses the root causes of test failures by fixing architectural issues rather than applying band-aids. The codebase already has a solid protocol foundation (40+ protocols defined), but inconsistent application.

**Guiding Principles:**
- Protocol-first design (define interface before implementation)
- Fail-fast (no silent failures)
- Single Responsibility (focused interfaces)
- Dependency Injection (all dependencies injectable)

---

## Phase 0: Immediate Bug Fix

**File:** `src/cli/display_rich.py:270`

**Change:** Replace undefined `title` with `goal`

**Risk:** None - straightforward bug fix
**Tests Fixed:** 3

---

## Phase 1: Define ProviderProtocol

**Problem:** `LLMProvider` is an ABC, tests mock implementation details (`chat_async`) instead of interface.

**Current State:**
```python
# src/providers/base.py
class LLMProvider(ABC):
    @abstractmethod
    def chat(self, ...) -> LLMResponse: ...

    def chat_async(self, ...) -> LLMResponse:  # Default implementation wraps sync
        return asyncio.run(...)
```

**Target State:**
```python
# src/providers/protocols.py (NEW FILE)
from typing import Protocol, Optional, List
from .base import LLMResponse, ModelInfo, ProviderLimits

@runtime_checkable
class ProviderProtocol(Protocol):
    """Contract for LLM provider implementations."""

    @property
    def name(self) -> str: ...

    @property
    def available_models(self) -> List[str]: ...

    @property
    def default_model(self) -> str: ...

    def chat(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs
    ) -> LLMResponse: ...

    def get_limits(self, model: Optional[str] = None) -> ProviderLimits: ...

    def is_available(self) -> bool: ...


@runtime_checkable
class AsyncProviderProtocol(ProviderProtocol, Protocol):
    """Extended protocol for providers with native async support."""

    async def chat_async(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs
    ) -> LLMResponse: ...
```

**Implementation Steps:**

1. Create `src/providers/protocols.py` with `ProviderProtocol` and `AsyncProviderProtocol`
2. Update `src/providers/__init__.py` to export protocols
3. Update type hints in orchestrator to use `ProviderProtocol` instead of `LLMProvider`
4. Update test fixtures to mock against protocol, not implementation
5. Keep `LLMProvider` ABC as base class (implementations extend ABC, consumers depend on Protocol)

**Files Changed:**
- `src/providers/protocols.py` (new)
- `src/providers/__init__.py`
- `src/orchestrator/protocols.py` (update imports)
- `tests/rate_limiting/test_rate_limit_recovery.py`

**Tests Fixed:** 8

---

## Phase 2: Fix OutputHandler Architecture

**Problem:** `ConsoleOutputHandler` silently fails when `io` is None.

**Current State:**
```python
class ConsoleOutputHandler(OutputHandlerInterface):
    def __init__(self, io: Optional['CLIIOProtocol'] = None):
        self._io = io

    def log_classification(self, ...):
        if not self._io:  # Silent failure!
            return
        self._io.echo(...)
```

**Target State - Option A (Make Required):**
```python
class ConsoleOutputHandler(OutputHandlerInterface):
    def __init__(self, io: 'CLIIOProtocol'):  # Required, not optional
        if io is None:
            raise TypeError("ConsoleOutputHandler requires an io instance")
        self._io = io
```

**Target State - Option B (Null Object Pattern):**
```python
# src/task_router/output_handler.py

class NullIO:
    """Null object that satisfies CLIIOProtocol but does nothing."""
    def echo(self, *args, **kwargs) -> None: pass
    def secho(self, *args, **kwargs) -> None: pass
    # ... other methods

class ConsoleOutputHandler(OutputHandlerInterface):
    def __init__(self, io: Optional['CLIIOProtocol'] = None):
        self._io = io or NullIO()  # Never None internally

    def log_classification(self, ...):
        # No null check needed - _io is always valid
        self._io.echo(...)
```

**Recommended:** Option A for ConsoleOutputHandler (fail fast), keep `NullOutputHandler` for silent mode.

**Implementation Steps:**

1. Make `io` required in `ConsoleOutputHandler.__init__`
2. Update existing call sites to provide io
3. For tests, create `MockIO` test double in `tests/helpers.py`
4. Update tests to use `MockIO`

**Files Changed:**
- `src/task_router/output_handler.py`
- `tests/task_router/test_task_router_refactored.py`
- `tests/helpers.py` (add MockIO)

**Tests Fixed:** 3

---

## Phase 3: Fix RichOutputHandler API

**Problem:** Constructor signature changed without coordinating with tests.

**Current State:**
```python
class RichOutputHandler:
    def __init__(self, io: "CLIIOProtocol"):  # Changed from console=
```

**Implementation Steps:**

1. Update all test files to use `io=` parameter
2. Create helper function in tests for constructing handlers with proper mocks

**Files Changed:**
- `tests/task_router/test_task_router_rich.py`

**Tests Fixed:** 16

---

## Phase 4: Split UnifiedIO Capabilities

**Problem:** `UnifiedIO` has optional `output_sink` but methods assume it exists.

**Current State:**
```python
class UnifiedIO:
    def __init__(self, console=None, output_sink=None):
        self.output_sink = output_sink  # Can be None

# src/cli/interactive_banner.py:68
io.output_sink.post_renderable(panel)  # Crashes if output_sink is None
```

**Analysis:**

Looking at the existing protocols in `src/cli/protocols.py`:
- `OutputSink` - already defined, good
- `CLIIOProtocol` - basic IO operations
- `RichOutputProtocol` - Rich-specific operations
- `UnifiedIOProtocol` - combines both

The issue is that `UnifiedIO` implements `UnifiedIOProtocol` but not all instances have renderable output capability.

**Target State:**

```python
# src/cli/protocols.py - Add new protocol

@runtime_checkable
class RenderableOutputProtocol(Protocol):
    """Protocol for IO that can post Rich renderables."""

    @property
    def output_sink(self) -> OutputSink: ...

    def post_renderable(self, obj: "RenderableType") -> None: ...


# src/cli/interactive_banner.py - Update function signature
def render_welcome_banner(io: RenderableOutputProtocol) -> Panel:
    """Render welcome banner. Requires renderable output support."""
    panel = create_welcome_panel()
    io.post_renderable(panel)
    return panel


# Alternative: Guard at runtime with clear error
def render_welcome_banner(io: UnifiedIOProtocol) -> Panel:
    """Render welcome banner."""
    if not hasattr(io, 'output_sink') or io.output_sink is None:
        raise RuntimeError(
            "render_welcome_banner requires UnifiedIO with output_sink. "
            "Use UnifiedIO(output_sink=adapter) for TUI mode."
        )
    panel = create_welcome_panel()
    io.output_sink.post_renderable(panel)
    return panel
```

**Implementation Steps:**

1. Add `RenderableOutputProtocol` to `src/cli/protocols.py`
2. Update `render_welcome_banner` to either:
   - Accept `RenderableOutputProtocol` type (compile-time safety)
   - Or add runtime check with clear error message (fail-fast)
3. Update tests to provide proper mock with `output_sink`

**Files Changed:**
- `src/cli/protocols.py`
- `src/cli/interactive_banner.py`
- `tests/cli/test_interactive_rich.py`

**Tests Fixed:** 5

---

## Phase 5: Test Infrastructure Updates

**Problem:** Tests lack proper test doubles for protocols.

**Implementation Steps:**

Add to `tests/helpers.py`:

```python
# Test doubles for protocols

class MockIO:
    """Test double for CLIIOProtocol."""
    def __init__(self):
        self.output: List[str] = []

    def echo(self, message: str = "", **kwargs) -> None:
        self.output.append(message)

    def secho(self, message: str, **kwargs) -> None:
        self.output.append(message)

    # ... other methods


class MockOutputSink:
    """Test double for OutputSink."""
    def __init__(self):
        self.outputs: List[str] = []
        self.renderables: List[Any] = []

    def post_output(self, content: str) -> None:
        self.outputs.append(content)

    def post_renderable(self, obj: Any) -> None:
        self.renderables.append(obj)


class MockProvider:
    """Test double for ProviderProtocol."""
    def __init__(
        self,
        name: str = "mock",
        response: Optional[LLMResponse] = None,
        error: Optional[Exception] = None
    ):
        self._name = name
        self._response = response or LLMResponse(content="mock response", ...)
        self._error = error
        self.calls: List[Dict] = []

    @property
    def name(self) -> str:
        return self._name

    def chat(self, prompt: str, **kwargs) -> LLMResponse:
        self.calls.append({"prompt": prompt, **kwargs})
        if self._error:
            raise self._error
        return self._response
```

**Files Changed:**
- `tests/helpers.py`

---

## Execution Order

| Step | Phase | Description | Tests Fixed | Risk |
|------|-------|-------------|-------------|------|
| 1 | 0 | Fix `title` bug | 3 | None |
| 2 | 3 | Fix test kwarg `console=` to `io=` | 16 | Low |
| 3 | 5 | Add test doubles to helpers.py | 0 | None |
| 4 | 2 | Make ConsoleOutputHandler.io required | 3 | Medium |
| 5 | 1 | Create ProviderProtocol | 8 | Medium |
| 6 | 4 | Add RenderableOutputProtocol | 5 | Medium |

**Total Tests Fixed:** 35

---

## Validation Checklist

After each phase, verify:

- [ ] All affected tests pass
- [ ] No new type errors (run mypy if configured)
- [ ] No regressions in unrelated tests
- [ ] Protocols are `@runtime_checkable` for isinstance checks
- [ ] Test doubles in helpers.py match protocol signatures

---

## Future Considerations

Once these fixes are complete, consider:

1. **Consolidate Output Systems** - Multiple parallel output abstractions exist:
   - `OutputHandlerInterface` (task_router)
   - `OutputInterface` (cli/output.py)
   - `OutputSink` (cli/protocols.py)
   - `ConsoleOutput/NullOutput` (orchestrator/output.py)

   These could be unified under a single hierarchy.

2. **Complete ABC to Protocol Migration** - Some modules still use ABC where Protocol would be better for structural typing.

3. **Add Protocol Conformance Tests** - Tests that verify implementations satisfy their protocols.
