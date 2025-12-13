# Agent-Discovered Issues

This file logs issues discovered by agents during implementation sessions.

## Format
```
- Brief description (discovered while working on X)
```

## Issues

### Progress Reporting Architecture Issue
(Discovered while implementing Step 10: Fix Progress Value Propagation)

**Root Cause:** Dual progress reporting mechanisms causing numeric values to be lost.

**Current State:**
1. SemanticSearchManager uses ProgressReporterProtocol (has start/update/complete methods with numeric values)
2. CodebaseContext uses string-only callback: `Callable[[str], None]`
3. TextualApp posts IndexingProgress messages (supports numeric values)
4. But the bridge between them only passes string messages

**Flow:**
```
SemanticProvider.index_chunks()
  -> UnifiedIOProgressReporter.update(current=X, total=Y)  [HAS NUMBERS]
  -> io.secho(message)  [LOSES NUMBERS - only outputs text]
  -> _progress_callback(message)  [STRING ONLY]
  -> IndexingProgress(message=message)  [progress=0, total=0 by default]
  -> ProgressBar gets zeros, shows no progress
```

**Fix Required:**
- Use the ProgressReporterProtocol consistently instead of string callbacks

**Files Affected:**
- src/scrappy/cli/textual_app.py (created TextualProgressReporter but not injected)
- src/scrappy/context/codebase_context.py (string callback)
- src/scrappy/context/semantic_manager.py (creates own UnifiedIOProgressReporter)
- src/scrappy/infrastructure/progress.py (UnifiedIOProgressReporter ignores numeric values)

---

### TYPE_CHECKING Usage as Architectural Smell
(Discovered during Phase 2/3 architectural refactoring)

**Issue:** 30+ TYPE_CHECKING blocks remain in codebase, some masking design issues.

**Current State:**
- Most TYPE_CHECKING usage is for Python typing optimization (acceptable)
- Some blocks import concrete classes for type hints instead of protocols
- Examples:
  - cli/textual_app.py imports InteractiveMode under TYPE_CHECKING
  - cli/screens/main_screen.py imports InteractiveMode under TYPE_CHECKING
  - Various components import concrete types instead of protocols

**Root Cause:**
- Python's typing system encourages TYPE_CHECKING to avoid runtime overhead
- However, reliance on concrete types for hints indicates missing protocol abstractions
- In Java/statically-typed languages, this pattern wouldn't exist - you'd use interfaces

**Architectural Concern:**
- While not circular dependencies, TYPE_CHECKING blocks hide dependency complexity
- Components depend on concrete classes for typing instead of abstract protocols
- Makes dependency graph less explicit than it could be

**Potential Fix:**
- Extract protocols for all concrete types currently imported under TYPE_CHECKING
- Would require significant boilerplate but provide clearer dependency contracts
- Example: Create InteractiveModeProtocol instead of importing concrete InteractiveMode

**Priority:** LOW - Current design is valid Python; this is about architectural purity vs pragmatism

**Trade-off:**
- More protocols = clearer architecture, more boilerplate
- TYPE_CHECKING = less boilerplate, less explicit dependencies
- Current approach is idiomatic Python but less explicit than Java-style interfaces

---
