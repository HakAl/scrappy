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
Massive Files - Single Responsibility command_router.py
 Command Router Decomposition Plan

 Strategy: Command Registry Pattern

 Replace 30+ elif branches with dictionary-based dispatch

 Implementation Steps

 1. Create handler methods for each command:
   - _handle_exit(args) - quit/exit/q
   - _handle_help(args), _handle_status(args), etc. - display commands
   - _handle_plan(args), _handle_reason(args), _handle_agent(args) - task commands
   - _handle_smart(args) - smart query with toggle logic
   - _handle_auto(args) - auto-route with subcommands
   - _handle_clear(args), _handle_autoexec(args), _handle_multiline(args) - state commands
 2. Build command registry in __init__:
 self._command_registry = {
     "/quit": self._handle_exit,
     "/exit": self._handle_exit,
     "/help": self._handle_help,
     # ... all commands
 }
 3. Simplify route() to ~30 lines:
   - Validate command (keep existing)
   - Lookup handler in registry
   - Call handler with args
   - Handle unknown commands
 4. Write tests first (TDD):
   - Test registry dispatch works
   - Test each handler method independently
   - Test unknown command handling

 Result

 - route(): 231 lines → ~30 lines
 - Clear separation of concerns
 - Easy to add/modify commands
 - Each handler independently testable
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
