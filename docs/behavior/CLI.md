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
Side Effects, Validation, Coupling
can you research the task and create a plan to fix?


help with a plan to decompose?
create a plan to fix?
start with tests?
implement
---


  ---
  8-10: Side Effects, Validation, Coupling

  - Tight coupling: InteractiveMode syncs 5 state attributes from CommandRouter

  ---
  14-15: Architecture Issues

  - CLI handlers access orchestrator.context.project_path, agent.planner, etc. directly
  - Configuration split between src/cli/config/ and inline in validators.py:124-145

  ---
  7. Shallow Tests

  Example from test_cli_command_router.py:46-55:
  router.display.show_help.assert_called_once()  # Only verifies call
  # Never checks that help content was actually correct
  
  ---
  11-13: Test Quality Issues

  - 15 skipped tests across 5 files
  - Tests mention TDD in docstrings but coverage gaps suggest post-hoc writing

  Better pattern from test_cli_input_handler.py:24-31:
  result = handler.read_multiline_input()
  assert result == "hello world"  # Verifies actual behavior

  ---
