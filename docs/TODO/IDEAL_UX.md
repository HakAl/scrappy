# PLAN REVIEW

This plan solves the single biggest friction point in local RAG: **The Indexing Latency vs. Freshness Trade-off.**

By moving from "Eager Consistency" (Index everything now) to "Lazy/Just-in-Time Consistency" (Index what I need now), 
you are aligning system resources with user intent.

Here is my architectural review of your **Smart Staleness Detection** plan, with a few "Senior Engineer"
optimizations to make the implementation easier and more robust.

---

### The Weak Link: `FileReferenceExtractor`

Phase 1 is the trickiest part. Users are lazy. They rarely type full paths.
*   *User Input:* "Why is the auth handler failing?"
*   *Actual File:* `src/users/authentication/handler.py`

**Regex won't catch that.**

#### Optimization: The "Fuzzy Path Matcher"
Instead of simple regex, load your file tree into a lightweight **Trie** or just a list of paths in memory (it's cheap).

When extracting:
1.  **Tokenize** the user query: `["why", "is", "auth", "handler", "failing"]`
2.  **Score** against paths:
    *   `src/users/authentication/handler.py` gets hits for "auth" (partial) and "handler" (exact).
    *   **Score:** High.
3.  **Threshold:** If score > X, add to `referenced_files`.

This solves Open Question #1 (Fuzzy Matching) by biasing towards "leaf nodes" (filenames) but allowing directory matches.

---

### ⚡ Optimization: The "Live Read" Bypass

You have an opportunity to make this even faster and smarter for the **Happy Path**.

If `FileReferenceExtractor` identifies `core.py`, and `core.py` is small (< 10kb):
**DO NOT RE-INDEX IT.**

**Just read it.**

Vector Search is a compression technique. It is lossy.
If you know exactly what file the user wants, and it fits in the context window:
1.  Read `core.py` from disk (0ms).
2.  Inject it directly into the System Prompt or Context.
3.  Skip the Vector DB entirely for that file.

**Revised Flow:**
```python
if file in referenced_files:
    if file_size < SMALL_FILE_THRESHOLD:
        # 1. LIVE CONTEXT INJECTION (The "God Mode")
        # Freshest possible data. No embedding latency. Perfect fidelity.
        context.add_file_content(file, read_from_disk(file))
    else:
        # 2. JIT RE-INDEXING (Your Plan)
        # File too big for raw context, need semantic search.
        if is_stale(file):
            reindex(file)
```

---

### Answers to Open Questions

#### 1. Fuzzy matching: How aggressive?
**Start Conservative.**
*   Match exact filenames (`auth.py`) and exact directory names (`auth/`).
*   Do *not* match partial substrings yet (`aut` -> `auth.py`). False positives will trigger unnecessary re-indexing, killing your latency wins.
*   *UX Fix:* If the user asks "How do I fix it?", prompt the bot to ask: *"Which file are you referring to?"* if it can't detect one.

#### 2. Threshold: How many files before we skip?
**Time-based, not count-based.**
*   Calculate `budget = 500ms`.
*   Estimate `cost_per_file = 100ms`.
*   `max_files = 5`.
*   If `referenced_files > 5`, trigger a **Background Re-index** and warn the user: *"Updating knowledge base for 12 files, this might take a moment..."*

#### 3. Background sync: Trigger after responding?
**YES.** absolutely.
*   The "General Question" scenario (Story 3) relies on the index being generally up-to-date.
*   Fire-and-forget a background thread *after* the LLM starts generating tokens (or after response completes).
*   Use a "debounce" (e.g., only sync if idle for 60s) to avoid eating CPU while the user is typing.

#### 4. Conversation memory: Track referenced files?
**Yes.** (Phase 4 item).
*   Add a `active_context_files` set to your `SessionContext`.
*   If User says "fix `core.py`", add `core.py` to the set.
*   Next prompt: "make it faster".
*   System checks `core.py` (from context) for staleness automatically.

---

### Summary
This is a sophisticated, high-value feature.
Implementing **Phase 1 (Extraction)** and **Phase 2 (Check)** is low risk.

I recommend implementing the **"Live Read Bypass"** immediately alongside this.
It saves you from writing complex re-indexing logic for 80% of use cases (small, specific files).

---

# Ideal UX: Smart Staleness Detection

## Vision

Instant responses for general queries. Minimal, targeted delays only when the user references stale files.

---

## User Stories

### Story 1: Referenced File is Stale
```
User: "how do I fix core.py?"

System (internal):
  1. Parse query -> extracts "core.py"
  2. Check staleness for core.py only (~5ms)
  3. core.py is stale -> reindex just core.py (~100ms)
  4. Proceed with semantic search

User experience: ~200ms delay (imperceptible)
```

### Story 2: Referenced File is Fresh
```
User: "how do I fix core.py?"

System (internal):
  1. Parse query -> extracts "core.py"
  2. Check staleness for core.py only (~5ms)
  3. core.py is fresh -> skip reindex
  4. Proceed with semantic search

User experience: no delay
```

### Story 3: General Question (No File Reference)
```
User: "what is dependency injection?"

System (internal):
  1. Parse query -> no file references
  2. Skip staleness check entirely
  3. Classify as GENERAL research
  4. Respond directly

User experience: no delay
```

### Story 4: Multiple Files Referenced
```
User: "how does auth.py call database.py?"

System (internal):
  1. Parse query -> extracts ["auth.py", "database.py"]
  2. Check staleness for both (~10ms)
  3. auth.py stale, database.py fresh
  4. Reindex only auth.py (~100ms)
  5. Proceed with semantic search

User experience: ~150ms delay (imperceptible)
```

---

## Implementation Strategy

### Phase 1: Query File Extraction

Extract file references from user query before classification.

```python
class FileReferenceExtractor:
    """Extract file paths mentioned in user queries."""

    def extract(self, query: str, file_index: dict) -> Set[str]:
        """
        Match query terms against known files.

        Examples:
            "fix core.py" -> {"src/core.py"}
            "how does auth work" -> {"src/auth.py", "src/auth/handler.py"}
            "what is REST" -> set()  # no file match
        """
        referenced = set()

        # Strategy 1: Exact filename match
        # "core.py" -> find all paths ending in core.py

        # Strategy 2: Stem match
        # "auth" -> find auth.py, auth/*.py

        # Strategy 3: Directory match
        # "task router" -> find task_router/*.py

        return referenced
```

### Phase 2: Targeted Staleness Check

New method on StalenessChecker for checking specific files only.

```python
class StalenessChecker:

    def check_files(self, files: Set[str]) -> Dict[str, bool]:
        """
        Check staleness for specific files only.

        Returns:
            Dict mapping file path -> is_stale boolean

        Performance: O(n) where n = len(files), not entire codebase
        """
        results = {}
        for file_path in files:
            stored = self._fingerprints.get(file_path)
            if stored is None:
                # New file, not in index
                results[file_path] = True
                continue

            current = self._get_current_fingerprint(file_path)
            results[file_path] = (current != stored)

        return results
```

### Phase 3: Prioritized Batch Reindexing

Reindex stale files first, then proceed without waiting for full reindex.

```python
class SemanticSearchManager:

    def reindex_priority_files(self, files: Set[str]) -> None:
        """
        Reindex specific files immediately (blocking but fast).

        Used for files referenced in current query.
        Full background reindex continues separately.
        """
        # Create collector for just these files
        collector = FilteredFileCollector(self._project_path, allowed_files=files)

        # Index synchronously (fast - only a few files)
        self.index_files(collector)
```

### Phase 4: Integrated Flow

Updated ResearchExecutor flow:

```python
def execute(self, task: ClassifiedTask) -> ExecutionResult:
    # Step 1: Extract file references from query
    extractor = FileReferenceExtractor()
    cached_index = self._get_cached_file_index()
    referenced_files = extractor.extract(task.original_input, cached_index)

    # Step 2: Check staleness for referenced files only
    if referenced_files:
        staleness = self._staleness_checker.check_files(referenced_files)
        stale_files = {f for f, is_stale in staleness.items() if is_stale}

        # Step 3: Reindex stale files first (fast - just a few files)
        if stale_files:
            self._semantic_manager.reindex_priority_files(stale_files)

    # Step 4: Classify and execute (now with fresh data for referenced files)
    classification = self._subclassifier.classify_with_matches(
        task.original_input, cached_index
    )
    # ... continue execution
```

---

## Performance Expectations

| Scenario | Current | After Phase 4 |
|----------|---------|---------------|
| General query | 30s block | 0ms |
| Query with fresh file | 30s block | ~10ms |
| Query with 1 stale file | 30s block | ~150ms |
| Query with 5 stale files | 30s block | ~500ms |

---

## Migration Path

1. **Now:** Never block (use cached data always)
2. **Phase 1:** Add file reference extraction
3. **Phase 2:** Add targeted staleness check
4. **Phase 3:** Add priority reindexing
5. **Phase 4:** Wire it all together

Each phase is independently valuable and testable.

---

## Open Questions

1. **Fuzzy matching:** How aggressive should file extraction be?
   - "auth" matches auth.py? auth/*.py? authentication.py?

2. **Threshold:** How many stale files before we skip and use cached?
   - 5 files? 10 files? Based on estimated reindex time?

3. **Background sync:** Should we trigger full reindex after responding?
   - Keeps index fresh for next query
   - But consumes resources

4. **Conversation memory:** Track all files referenced in session?
   - Enables smarter staleness checks across conversation
   - Memory overhead consideration
