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
Massive Files - Single Responsibility validators.py
Proposed Decomposition: validators/ Package

  src/cli/validators/
      __init__.py       # Re-exports for backward compatibility (~30 lines)
      base.py           # ValidationError, shared patterns (~50 lines)
      command.py        # Command validation domain (~120 lines)
      path.py           # Path validation domain (~160 lines)
      provider.py       # Provider validation domain (~110 lines)

  Module Details:

  base.py - Shared infrastructure
  - ValidationError exception
  - Shared regex patterns (CONTROL_CHARS_PATTERN, NEWLINE_PATTERN)

  command.py - Command validation
  - CommandValidationResult dataclass
  - VALID_COMMANDS set
  - MAX_COMMAND_LENGTH constant
  - validate_command() function

  path.py - Path validation
  - PathValidationResult dataclass
  - Path constants (MAX_PATH_LENGTH, MAX_PATH_COMPONENT_LENGTH)
  - Path patterns (WINDOWS_INVALID_CHARS, GLOB_CHARS_PATTERN)
  - validate_path() function

  provider.py - Provider validation
  - ProviderValidationResult dataclass
  - VALID_PROVIDERS set
  - MAX_PROVIDER_LENGTH constant
  - validate_provider() function

  __init__.py - Backward compatibility
  from .base import ValidationError
  from .command import CommandValidationResult, validate_command, VALID_COMMANDS
  from .path import PathValidationResult, validate_path
  from .provider import ProviderValidationResult, validate_provider, VALID_PROVIDERS

  __all__ = [
      'ValidationError',
      'CommandValidationResult', 'validate_command', 'VALID_COMMANDS',
      'PathValidationResult', 'validate_path',
      'ProviderValidationResult', 'validate_provider', 'VALID_PROVIDERS',
  ]
can you research the task and start with tests?


help with a plan to decompose?
start with tests?
implement
---


  ---
  2. Massive Files - Single Responsibility

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
