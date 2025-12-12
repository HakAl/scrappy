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
