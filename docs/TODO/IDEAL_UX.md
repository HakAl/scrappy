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
