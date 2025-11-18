### Issues

<!-- todo -- Assess code / tests / maintainability -->

- multiline input broken (copy / paste)
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
**RED**

we're working to improve src\cli the next task is: 
Type Safety & Documentation - Add Docstrings
 - Document all public methods
 - Document side effects explicitly
 - Document state changes
  Phase 3 - Infrastructure (~30 methods)
  - cache_manager.py, rate_limiter.py, persistence.py
  - task_router_handler.py, error_recovery.py, exceptions.py
can you research the task and implement?

**GREEN**

we completed the red phase of the task: 

**REFACTOR**

we created:

they're fully tested and ready for integration in src/. can you complete the refactor phase of TDD?

---
CLI Refactoring

 Phase 6: Type Safety & Documentation

 6.2 Add Docstrings

 - Document all public methods
 - Document side effects explicitly
 - Document state changes



  Phase 4 - Utilities/Config (~10-20 items)
  - utils/*.py, config/*.py, validators.py, protocols.py, types.py