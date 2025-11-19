# CLI

**The Good**

  1. CLIIOProtocol abstraction - Clean dependency injection
  2. MockIO and ConfigurableTestOrchestrator - Excellent test helpers
  3. validators.py - Comprehensive validation with dataclass results
  4. src/cli/config/ - Well-organized configuration
  5. error_recovery.py - Sophisticated patterns (CircuitBreaker, retry, fallback)
  6. Docstrings - Good documentation throughout


### Issues

<!-- todo -- Assess code / tests / maintainability -->

- multiline input (copy / paste)
- user choices stored in history (y, Y, n, N, 1, 2, 3, etc)
- Verbose ALTS warning: Google Cloud ALTS credentials warning on every run
- Interactive-Only CLI: Can't pipe commands, no programmatic API, no --command flag
- Windows Unicode Incompatibility: Emoji characters crash on Windows (cp1252)
- Missing API Key Warning: Shows [X] but continues (not blocking, just noisy)

<!-- new features -->

- Diff preview
 - Structured output validation - Pydantic schemas for LLM responses
 - Streaming responses - Token-by-token generation for better UX
 
<!-- maintainence -->
  1. Add # type: ignore[no-redef] to fallback imports in except blocks
  2. Consider using a common imports module to avoid the try/except pattern
  3. Fix the codebase.py Path vs str type issues
  4. Add type stubs for external dependencies (types-PyYAML, etc.)

---


we're working to improve src\cli the next task is: 
Massive Files - Single Responsibility - error_recovery.py 
 Create a new error_recovery/ package with focused modules:

  src/cli/error_recovery/
      __init__.py          (~40 lines)  - Re-exports for backward compatibility
      retry.py             (~100 lines) - retry_operation, safe_operation_with_recovery
      fallback.py          (~120 lines) - with_fallback, fallback_providers, graceful_degrade
      circuit_breaker.py   (~120 lines) - CircuitBreaker class
      context.py           (~380 lines) - All error context managers

  Key Points

  1. Backward compatibility: __init__.py re-exports all public APIs so existing imports like from
  src.cli.error_recovery import retry_operation continue to work
  2. Each module has one reason to change:
    - retry.py - Changes to retry timing/strategy
    - fallback.py - Changes to fallback selection logic
    - circuit_breaker.py - Changes to circuit breaker behavior
    - context.py - Changes to context manager behavior
  3. Context managers stay together (380 lines) because they're tightly coupled - _RetryableErrorContext and
  _SimpleErrorContext are implementations selected by error_recovery_context(). Could be split further later if
  needed.
  4. Tests require no changes - all existing imports will still work
can you research the task and start with tests?

help with a plan to decompose?
start with tests?
implement

 The file has 5 distinct responsibilities that can be cleanly separated:
 
  ---
  Decomposition Plan

  Create a new error_recovery/ package with focused modules:

  src/cli/error_recovery/
      __init__.py          (~40 lines)  - Re-exports for backward compatibility
      retry.py             (~100 lines) - retry_operation, safe_operation_with_recovery
      fallback.py          (~120 lines) - with_fallback, fallback_providers, graceful_degrade
      circuit_breaker.py   (~120 lines) - CircuitBreaker class
      context.py           (~380 lines) - All error context managers

  Key Points

  1. Backward compatibility: __init__.py re-exports all public APIs so existing imports like from
  src.cli.error_recovery import retry_operation continue to work
  2. Each module has one reason to change:
    - retry.py - Changes to retry timing/strategy
    - fallback.py - Changes to fallback selection logic
    - circuit_breaker.py - Changes to circuit breaker behavior
    - context.py - Changes to context manager behavior
  3. Context managers stay together (380 lines) because they're tightly coupled - _RetryableErrorContext and
  _SimpleErrorContext are implementations selected by error_recovery_context(). Could be split further later if
  needed.
  4. Tests require no changes - all existing imports will still work


  ---
  2. Massive Files - Single Responsibility

  - error_recovery.py - 710 lines
  - validators.py - 512 lines
  - command_router.py - route() method is 192 lines with 30+ elif branches

  ---
  3-6: Pattern Matching, Duplication, JSON, God Objects

  - Fragile patterns: 25+ regex patterns in config/patterns.py with limited edge case tests
  - Duplicated imports: Try/except fallback pattern in ~10 files
  - JSON risk: No error handling around json.dumps() in logging.py:182
  - God object: smart_query.smart_query() handles 9 different concerns in one method

  ---
  7. Shallow Tests

  Example from test_cli_command_router.py:46-55:
  router.display.show_help.assert_called_once()  # Only verifies call
  # Never checks that help content was actually correct

  Better pattern from test_cli_input_handler.py:24-31:
  result = handler.read_multiline_input()
  assert result == "hello world"  # Verifies actual behavior

  ---
  8-10: Side Effects, Validation, Coupling

  - Global state: _loggers, _global_io, _global_level in logging.py
  - Validation inconsistent: Some inline checks should use validators.py
  - Tight coupling: InteractiveMode syncs 5 state attributes from CommandRouter

  ---
  11-13: Test Quality Issues

  - 15 skipped tests across 5 files
  - Tests mention TDD in docstrings but coverage gaps suggest post-hoc writing

  ---
  14-15: Architecture Issues

  - CLI handlers access orchestrator.context.project_path, agent.planner, etc. directly
  - Configuration split between src/cli/config/ and inline in validators.py:124-145


  ---
  Priority Fixes

  1. Convert direct click calls to use io parameter in display.py, tasks.py, smart_query.py
  2. Split CommandRouter.route() into command-specific handlers or a dispatch table
  3. Add behavior assertions to tests - verify outputs, not just mock calls
  4. Consolidate configuration into src/cli/config/
  5. Add JSON error handling in logging.py
