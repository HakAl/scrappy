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
