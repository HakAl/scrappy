# Semantic Search Phase 2 - Implementation Plan

This document provides a detailed implementation plan for the features outlined in `SEMANTIC_SEARCH_PHASE2.md`, with architectural considerations following SOLID principles.

---

## Executive Summary

The Phase 2 enhancements fall into three categories:

| Category | Features | Priority |
|----------|----------|----------|
| **Performance** | Priority Queue, FTS Incremental | High |
| **Quality** | Test Noise Exclusion, Deleted File Cleanup, Search Result Ranking | High |
| **Architecture** | Intelligent Chunking (AST-aware), User Config Exposure | Medium |

---

## Feature 1: Priority Queue File Collection

### Current State
`SemanticFileCollector` in `src/context/semantic/file_collector.py` uses git-aware collection but does not prioritize files by type.

### Design

**New Protocol:**
```python
# In src/context/protocols.py
class FilePrioritizerProtocol(Protocol):
    """Assigns priority to files for indexing order."""

    def get_priority(self, file_path: Path) -> int:
        """Return priority (0 = highest, higher = lower priority)."""
        ...

    def sort_by_priority(self, files: List[Path]) -> List[Path]:
        """Sort files by priority (highest first)."""
        ...
```

**Implementation:**
```python
# New file: src/context/semantic/file_prioritizer.py

@dataclass
class FilePriorityConfig:
    """Configuration for file prioritization."""
    source_extensions: FrozenSet[str] = frozenset({
        '.py', '.js', '.ts', '.tsx', '.go', '.rs', '.java', '.c', '.cpp', '.h'
    })
    readme_patterns: FrozenSet[str] = frozenset({'readme.md', 'readme.rst', 'readme.txt'})
    docs_patterns: FrozenSet[str] = frozenset({'docs/', 'documentation/'})
    test_patterns: FrozenSet[str] = frozenset({'test/', 'tests/', 'spec/', '__tests__/'})

class DefaultFilePrioritizer:
    """Prioritizes files for indexing: README > Source > Docs > Tests > Other."""

    PRIORITY_README = 0
    PRIORITY_SOURCE = 1
    PRIORITY_DOCS = 2
    PRIORITY_TESTS = 3
    PRIORITY_OTHER = 4

    def __init__(self, config: Optional[FilePriorityConfig] = None):
        self._config = config or FilePriorityConfig()

    def get_priority(self, file_path: Path) -> int:
        name_lower = file_path.name.lower()
        path_str = str(file_path).lower().replace('\\', '/')

        # Priority 0: README files
        if name_lower in self._config.readme_patterns:
            return self.PRIORITY_README

        # Priority 3: Test files (check before source to catch test/*.py)
        if any(pattern in path_str for pattern in self._config.test_patterns):
            return self.PRIORITY_TESTS

        # Priority 1: Source code
        if file_path.suffix.lower() in self._config.source_extensions:
            return self.PRIORITY_SOURCE

        # Priority 2: Documentation
        if any(pattern in path_str for pattern in self._config.docs_patterns):
            return self.PRIORITY_DOCS

        return self.PRIORITY_OTHER

    def sort_by_priority(self, files: List[Path]) -> List[Path]:
        return sorted(files, key=self.get_priority)
```

### Integration Point
Modify `SemanticFileCollector` to accept optional `FilePrioritizerProtocol`:

```python
class SemanticFileCollector:
    def __init__(
        self,
        root_dir: Path,
        filter_config: Optional[IndexFilterConfig] = None,
        prioritizer: Optional[FilePrioritizerProtocol] = None,  # NEW
    ):
        self._prioritizer = prioritizer or DefaultFilePrioritizer()

    def collect_files_batched(self, batch_size: int = 50) -> Generator[...]:
        files = self._collect_file_paths()
        prioritized = self._prioritizer.sort_by_priority(files)
        # ... rest of batching logic
```

### Test Strategy
- Test priority assignment for each file type
- Test sorting produces correct order
- Test integration with file collector
- Test custom config overrides defaults

---

## Feature 2: Lazy/Incremental Indexing (Diff Check)

### Current State
`LanceDBSearchProvider` already has incremental indexing! See `_get_file_diffs()` method at line ~280. It:
- Queries existing file paths and content hashes
- Compares against current files
- Identifies new, modified, and deleted files

**However:** It uses `content_hash` (MD5 of content), not `mtime`. This is actually **better** because:
- Detects actual content changes (not just touch)
- Works across systems with different time resolutions
- More reliable than mtime

### Recommended Enhancement
The current implementation is solid. The TODO suggestion to use `mtime` is a premature optimization. Content hashing is more accurate and the performance difference is negligible for codebases < 100k files.

**Optional Enhancement:** Add mtime as a fast-path check:
```python
def _should_check_content(self, file_path: Path, db_mtime: float) -> bool:
    """Fast-path: skip content hash if mtime unchanged."""
    current_mtime = file_path.stat().st_mtime
    return current_mtime > db_mtime
```

This requires adding `last_modified: float` to the schema - a breaking change requiring migration.

### Recommendation
**No immediate action needed.** Current implementation is correct and performant. Document this in the codebase.

---

## Feature 3: Test Noise Exclusion

### Current State
`IndexFilterConfig` in `src/context/semantic/file_collector.py` has `ignore_names` but lacks test-specific noise patterns.

### Design

**Extend IndexFilterConfig:**
```python
@dataclass
class IndexFilterConfig:
    # ... existing fields ...

    # NEW: Test data exclusion patterns
    test_noise_patterns: FrozenSet[str] = frozenset({
        '__snapshots__/',
        'snapshots/',
        'fixtures/',
        'test/data/',
        'tests/data/',
        'test/fixtures/',
        'tests/fixtures/',
        'testdata/',
        '__mocks__/',
    })

    test_noise_extensions: FrozenSet[str] = frozenset({
        '.snap',
        '.snapshot',
    })

    # Large JSON files in test directories
    skip_large_json_in_tests: bool = True
    large_json_threshold_bytes: int = 50_000  # 50KB
```

**Update _should_include_file():**
```python
def _should_include_file(self, file_path: Path, ...) -> bool:
    path_str = str(file_path).lower().replace('\\', '/')

    # Check test noise patterns
    if any(pattern in path_str for pattern in self._config.test_noise_patterns):
        return False

    # Check test noise extensions
    if file_path.suffix.lower() in self._config.test_noise_extensions:
        return False

    # Large JSON in test directories
    if self._config.skip_large_json_in_tests:
        if file_path.suffix.lower() == '.json':
            if any(p in path_str for p in ('test/', 'tests/', 'spec/')):
                if file_path.stat().st_size > self._config.large_json_threshold_bytes:
                    return False

    # ... existing checks ...
```

### Test Strategy
- Test snapshot directory exclusion
- Test fixture directory exclusion
- Test .snap file exclusion
- Test large JSON exclusion with threshold
- Test that test code (not data) is still included

---

## Feature 4: Deleted File Cleanup

### Current State
`LanceDBSearchProvider.index_files()` has deletion detection logic at lines 362-374, but it only runs when `is_batch=False`. During batched indexing (the common case for large codebases), stale entries from deleted files accumulate in the index.

```python
# Current behavior - deletion detection SKIPPED during batched indexing
if not is_batch:
    # ... deletion detection logic ...
    for db_path in db_state:
        if db_path not in fs_paths_set:
            paths_to_remove.append(db_path)
```

### Problem
When using `collect_files_batched()`, each batch calls `index_files(batch, is_batch=True)`. Deleted files are never detected because no single batch contains the full file set.

### Design

**New Protocol Method:**
```python
# In src/context/protocols.py - extend SemanticSearchProtocol
class SemanticSearchProtocol(Protocol):
    # ... existing methods ...

    def cleanup_deleted_files(self, current_files: Set[str]) -> int:
        """
        Remove index entries for files that no longer exist.

        Args:
            current_files: Set of normalized file paths that currently exist

        Returns:
            Number of stale entries removed
        """
        ...
```

**Implementation in LanceDBSearchProvider:**
```python
def cleanup_deleted_files(self, current_files: Set[str]) -> int:
    """
    Remove stale entries for deleted files.

    Should be called AFTER batched indexing completes with the full
    set of currently-existing file paths.

    Args:
        current_files: Set of normalized POSIX paths that exist

    Returns:
        Number of entries removed
    """
    if not self.is_indexed():
        return 0

    self._ensure_db()

    with self._safe_db_context():
        table = self._db.open_table(TABLE_NAME)

        # Get all indexed file paths
        indexed_paths = set()
        for batch in table.search().select(["file_path"]).to_batches():
            df = batch.to_pandas()
            indexed_paths.update(df["file_path"].tolist())

        # Find stale paths (in DB but not in current files)
        stale_paths = indexed_paths - current_files

        if not stale_paths:
            logger.debug("No stale entries to clean up")
            return 0

        logger.info(f"Removing {len(stale_paths)} stale file entries")

        # Delete in batches to avoid huge SQL statements
        BATCH_SIZE = 100
        removed = 0
        stale_list = list(stale_paths)

        for i in range(0, len(stale_list), BATCH_SIZE):
            batch = stale_list[i:i + BATCH_SIZE]
            paths_sql = ", ".join(f"'{p}'" for p in batch)
            table.delete(f"file_path IN ({paths_sql})")
            removed += len(batch)

        table.cleanup_old_versions()
        return removed
```

**Integration with Batched Indexing:**
```python
# In the calling code (e.g., CodebaseContext or CLI)
collector = SemanticFileCollector(project_path)
all_paths: Set[str] = set()

# Phase 1: Index in batches
for batch in collector.collect_files_batched(batch_size=50):
    normalized_batch = {normalize_path(p): content for p, content in batch.items()}
    all_paths.update(normalized_batch.keys())
    search_provider.index_files(normalized_batch, is_batch=True)

# Phase 2: Clean up deleted files
removed = search_provider.cleanup_deleted_files(all_paths)
logger.info(f"Cleaned up {removed} deleted file entries")
```

### Alternative: Track Indexed Paths Internally
Could also track paths during `index_files()` and provide a `finalize_batch()` method:

```python
class LanceDBSearchProvider:
    def __init__(self, ...):
        self._batch_indexed_paths: Set[str] = set()

    def index_files(self, files: Dict[str, str], is_batch: bool = False) -> None:
        # ... existing logic ...
        if is_batch:
            self._batch_indexed_paths.update(normalized_paths)

    def finalize_batch_indexing(self) -> int:
        """Call after all batches to clean up deleted files."""
        if not self._batch_indexed_paths:
            return 0
        removed = self.cleanup_deleted_files(self._batch_indexed_paths)
        self._batch_indexed_paths.clear()
        return removed
```

### Test Strategy
- Test cleanup removes entries for deleted files
- Test cleanup preserves entries for existing files
- Test cleanup with empty current_files set
- Test cleanup with no stale entries (no-op)
- Test batch deletion (SQL statement size limits)
- Test integration with batched indexing workflow

---

## Feature 5: Search Result Ranking

### Current State
`LanceDBSearchProvider.search()` uses LanceDB's hybrid search which combines vector similarity and FTS scores, but the fusion strategy is opaque and may not be optimal for code search.

```python
# Current implementation - relies on LanceDB's default fusion
results = (
    table.search(query_vector, query_type="hybrid")
    .text(query)
    .limit(max_results)
    .to_list()
)
```

### Problem
- No control over vector vs. FTS score weighting
- No boost for exact matches or file path matches
- No recency or file importance signals
- Results ordered by opaque `_score` field

### Design

**New Protocol:**
```python
# In src/context/protocols.py
@dataclass
class ScoredChunk:
    """A chunk with detailed scoring breakdown."""
    file_path: str
    start_line: int
    end_line: int
    content: str
    vector_score: float      # Semantic similarity (0-1)
    fts_score: float         # Keyword match score (0-1)
    final_score: float       # Combined/weighted score
    match_details: Dict[str, Any] = field(default_factory=dict)


class ResultRankerProtocol(Protocol):
    """Ranks and scores search results."""

    def rank(
        self,
        query: str,
        candidates: List[ScoredChunk],
        config: Optional["RankingConfig"] = None,
    ) -> List[ScoredChunk]:
        """
        Re-rank candidates based on multiple signals.

        Args:
            query: Original search query
            candidates: Raw results from search backend
            config: Ranking configuration

        Returns:
            Re-ranked list of chunks (highest score first)
        """
        ...
```

**Ranking Configuration:**
```python
@dataclass
class RankingConfig:
    """Configuration for result ranking."""
    vector_weight: float = 0.6       # Weight for semantic similarity
    fts_weight: float = 0.3          # Weight for keyword matches
    exact_match_boost: float = 0.5   # Boost for exact query substring
    path_match_boost: float = 0.2    # Boost if query terms in file path
    recency_weight: float = 0.0      # Future: boost recently modified files
```

**Implementation:**
```python
# New file: src/context/semantic/ranker.py

class DefaultResultRanker:
    """
    Re-ranks search results with configurable scoring.

    Scoring formula:
        final_score = (vector_score * vector_weight) +
                      (fts_score * fts_weight) +
                      exact_match_boost (if applicable) +
                      path_match_boost (if applicable)
    """

    def __init__(self, config: Optional[RankingConfig] = None):
        self._config = config or RankingConfig()

    def rank(
        self,
        query: str,
        candidates: List[ScoredChunk],
        config: Optional[RankingConfig] = None,
    ) -> List[ScoredChunk]:
        cfg = config or self._config
        query_lower = query.lower()
        query_terms = set(query_lower.split())

        for chunk in candidates:
            # Base score from vector + FTS
            base_score = (
                chunk.vector_score * cfg.vector_weight +
                chunk.fts_score * cfg.fts_weight
            )

            # Exact match boost
            exact_boost = 0.0
            if query_lower in chunk.content.lower():
                exact_boost = cfg.exact_match_boost
                chunk.match_details["exact_match"] = True

            # Path match boost (query terms appear in file path)
            path_boost = 0.0
            path_lower = chunk.file_path.lower()
            matching_terms = [t for t in query_terms if t in path_lower]
            if matching_terms:
                path_boost = cfg.path_match_boost * (len(matching_terms) / len(query_terms))
                chunk.match_details["path_matches"] = matching_terms

            chunk.final_score = base_score + exact_boost + path_boost

        # Sort by final score (descending)
        return sorted(candidates, key=lambda c: c.final_score, reverse=True)
```

**Integration with LanceDBSearchProvider:**
```python
class LanceDBSearchProvider:
    def __init__(
        self,
        # ... existing params ...
        ranker: Optional[ResultRankerProtocol] = None,
    ):
        self._ranker = ranker or DefaultResultRanker()

    def search(
        self,
        query: str,
        max_results: int = 25,
        max_tokens: int = 4000,
        ranking_config: Optional[RankingConfig] = None,
    ) -> SearchResult:
        # ... existing search logic ...

        # Convert raw results to ScoredChunk
        candidates = []
        for row in results:
            candidates.append(ScoredChunk(
                file_path=row["file_path"],
                start_line=row["start_line"],
                end_line=row["end_line"],
                content=row["content"],
                vector_score=row.get("_distance", 0.0),  # LanceDB distance
                fts_score=row.get("_score", 0.0),        # FTS score if available
                final_score=0.0,  # Will be set by ranker
            ))

        # Re-rank
        ranked = self._ranker.rank(query, candidates, ranking_config)

        # Apply token budget and build result
        # ... rest of existing logic ...
```

### Future Enhancements
- **Recency signal:** Track file modification time, boost recently changed files
- **Frequency signal:** Boost files that appear in multiple queries (hot files)
- **User feedback:** Learn from click-through data (which results users actually use)

### Test Strategy
- Test default ranking preserves relative order when scores are similar
- Test exact match boost increases score
- Test path match boost with partial matches
- Test configurable weights produce expected rankings
- Test edge cases (empty query, no matches)

---

## Feature 6: FTS Incremental Index

### Current State
`_maybe_rebuild_fts()` uses `replace=True` which can lock readers:
```python
self._table.create_fts_index("content", replace=True)
```

### Design

**Update _maybe_rebuild_fts():**
```python
def _maybe_rebuild_fts(self, chunks_added: int, force: bool = False) -> None:
    if not force and chunks_added < self._config.fts_rebuild_threshold:
        return

    try:
        # Check if FTS index exists
        # LanceDB >= 0.6: create_fts_index with replace=False is incremental
        self._table.create_fts_index("content", replace=False)
    except Exception as e:
        if "already exists" in str(e).lower():
            # Index exists, incremental update not needed
            pass
        else:
            logger.warning(f"FTS index creation failed: {e}")
```

### Version Check
Verify LanceDB version supports incremental FTS:
```python
def _supports_incremental_fts(self) -> bool:
    import lancedb
    version = tuple(map(int, lancedb.__version__.split('.')[:2]))
    return version >= (0, 6)
```

### Test Strategy
- Test FTS creation on empty table
- Test FTS with replace=False on existing index
- Test concurrent read during FTS update (if possible)

---

## Feature 7: Intelligent Code Chunking (AST-Aware)

### Current State
`SemanticCodeChunker` uses naive line-based chunking with fixed overlap:

```python
class SemanticCodeChunker:
    def __init__(self, chunk_size: int = 250, overlap: int = 30):
        ...

    def chunk(self, file_path: str, content: str) -> List[CodeChunk]:
        # Chunks every N lines regardless of code structure
        while i < len(lines):
            chunk_start = i + 1
            chunk_end = min(i + self._chunk_size, len(lines))
            # ... creates chunk ...
            i += self._chunk_size - self._overlap
```

### Problem
- Chunks split functions/classes mid-definition
- A 60-line function might be split across 2+ chunks, losing context
- Import blocks, docstrings, and function bodies all treated the same
- Overlap is wasteful when natural boundaries exist

### Design

**Extended Protocol:**
```python
# In src/context/protocols.py
@dataclass
class CodeChunk:
    start_line: int
    end_line: int
    file_path: Optional[str] = None
    chunk_type: Optional[str] = None  # NEW: "function", "class", "module", "block"
    name: Optional[str] = None        # NEW: "MyClass.my_method", "helper_func"


class CodeChunkerProtocol(Protocol):
    def chunk(self, file_path: str, content: str) -> List[CodeChunk]:
        """Chunk code content into retrievable segments."""
        ...

    def supports_language(self, file_extension: str) -> bool:
        """Check if chunker has language-specific support for this extension."""
        ...
```

**Strategy Pattern for Language Support:**
```python
# New file: src/context/semantic/chunkers/__init__.py

class ChunkingStrategyProtocol(Protocol):
    """Language-specific chunking strategy."""

    def chunk(self, content: str, file_path: str) -> List[CodeChunk]:
        """Chunk content using language-aware boundaries."""
        ...

    @property
    def supported_extensions(self) -> Set[str]:
        """File extensions this strategy handles."""
        ...
```

**Python AST-Based Chunker:**
```python
# New file: src/context/semantic/chunkers/python_chunker.py

import ast
from typing import List, Set

class PythonASTChunker:
    """
    Chunks Python code using AST boundaries.

    Strategy:
    1. Parse AST to find top-level definitions (functions, classes)
    2. Each function/method becomes a chunk (if under max_lines)
    3. Large functions are split at logical points (nested functions, decorators)
    4. Imports and module docstring become a "preamble" chunk
    5. Fall back to line-based for unparseable code
    """

    def __init__(
        self,
        max_chunk_lines: int = 100,
        min_chunk_lines: int = 5,
        include_preamble: bool = True,
    ):
        self._max_lines = max_chunk_lines
        self._min_lines = min_chunk_lines
        self._include_preamble = include_preamble

    @property
    def supported_extensions(self) -> Set[str]:
        return {".py", ".pyi"}

    def chunk(self, content: str, file_path: str) -> List[CodeChunk]:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            # Fall back to line-based chunking
            return self._fallback_chunk(content, file_path)

        chunks = []
        lines = content.splitlines()

        # Extract preamble (imports, module docstring)
        if self._include_preamble:
            preamble_end = self._find_preamble_end(tree)
            if preamble_end > 0:
                chunks.append(CodeChunk(
                    start_line=1,
                    end_line=preamble_end,
                    file_path=file_path,
                    chunk_type="preamble",
                    name="imports",
                ))

        # Process top-level definitions
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                chunks.extend(self._chunk_function(node, file_path, lines))
            elif isinstance(node, ast.ClassDef):
                chunks.extend(self._chunk_class(node, file_path, lines))

        return chunks if chunks else self._fallback_chunk(content, file_path)

    def _chunk_function(self, node: ast.FunctionDef, file_path: str, lines: List[str]) -> List[CodeChunk]:
        """Chunk a function definition."""
        start = node.lineno
        end = node.end_lineno or start

        # If function fits in max_lines, keep as single chunk
        if (end - start + 1) <= self._max_lines:
            return [CodeChunk(
                start_line=start,
                end_line=end,
                file_path=file_path,
                chunk_type="function",
                name=node.name,
            )]

        # Large function: split at nested definitions or logical points
        return self._split_large_block(node, file_path, lines, "function", node.name)

    def _chunk_class(self, node: ast.ClassDef, file_path: str, lines: List[str]) -> List[CodeChunk]:
        """Chunk a class definition - each method becomes a chunk."""
        chunks = []

        # Class header + docstring
        class_start = node.lineno
        first_method = None
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                first_method = child
                break

        header_end = (first_method.lineno - 1) if first_method else (node.end_lineno or class_start)

        if header_end > class_start:
            chunks.append(CodeChunk(
                start_line=class_start,
                end_line=min(header_end, class_start + 20),  # Cap header size
                file_path=file_path,
                chunk_type="class",
                name=node.name,
            ))

        # Each method as separate chunk
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_chunks = self._chunk_function(child, file_path, lines)
                for mc in method_chunks:
                    mc.name = f"{node.name}.{mc.name}"  # Qualify with class name
                chunks.extend(method_chunks)

        return chunks

    def _find_preamble_end(self, tree: ast.Module) -> int:
        """Find where imports/docstring end and definitions begin."""
        preamble_end = 0
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                preamble_end = node.end_lineno or node.lineno
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                # Module docstring
                preamble_end = node.end_lineno or node.lineno
            else:
                break
        return preamble_end

    def _fallback_chunk(self, content: str, file_path: str) -> List[CodeChunk]:
        """Line-based fallback for unparseable code."""
        from ..code_chunker import SemanticCodeChunker
        fallback = SemanticCodeChunker(chunk_size=60, overlap=15)
        return fallback.chunk(file_path, content)
```

**Composite Chunker (Main Entry Point):**
```python
# New file: src/context/semantic/chunkers/composite_chunker.py

class CompositeCodeChunker:
    """
    Routes files to language-specific chunkers.

    Falls back to line-based chunking for unsupported languages.
    """

    def __init__(
        self,
        strategies: Optional[Dict[str, ChunkingStrategyProtocol]] = None,
        fallback_chunk_size: int = 60,
        fallback_overlap: int = 15,
    ):
        self._strategies = strategies or self._default_strategies()
        self._fallback = SemanticCodeChunker(
            chunk_size=fallback_chunk_size,
            overlap=fallback_overlap,
        )

        # Build extension -> strategy mapping
        self._ext_map: Dict[str, ChunkingStrategyProtocol] = {}
        for strategy in self._strategies.values():
            for ext in strategy.supported_extensions:
                self._ext_map[ext] = strategy

    def _default_strategies(self) -> Dict[str, ChunkingStrategyProtocol]:
        return {
            "python": PythonASTChunker(),
            # Future: "javascript": JavaScriptChunker(),
            # Future: "typescript": TypeScriptChunker(),
        }

    def chunk(self, file_path: str, content: str) -> List[CodeChunk]:
        ext = Path(file_path).suffix.lower()

        if ext in self._ext_map:
            return self._ext_map[ext].chunk(content, file_path)

        return self._fallback.chunk(file_path, content)

    def supports_language(self, file_extension: str) -> bool:
        return file_extension.lower() in self._ext_map
```

### Integration
Replace `SemanticCodeChunker` with `CompositeCodeChunker` in the initializer:

```python
# In src/context/semantic/initializer.py
def _initialize(self) -> LanceDBSearchProvider:
    chunker = CompositeCodeChunker()  # Instead of SemanticCodeChunker
    return LanceDBSearchProvider(
        project_path=self._project_path,
        chunker=chunker,
        config=SemanticIndexConfig(db_dir_name=".scrappy/lancedb"),
    )
```

### Future Language Support
The strategy pattern makes adding new languages straightforward:

```python
# JavaScript/TypeScript (using tree-sitter or acorn)
class JavaScriptChunker:
    supported_extensions = {".js", ".jsx", ".ts", ".tsx"}
    # Parse with tree-sitter, chunk at function/class boundaries

# Go
class GoChunker:
    supported_extensions = {".go"}
    # Parse with go/ast or tree-sitter

# Rust
class RustChunker:
    supported_extensions = {".rs"}
    # Parse with tree-sitter-rust
```

### Test Strategy
- Test Python function chunking (single chunk for small functions)
- Test Python class chunking (header + methods)
- Test large function splitting
- Test syntax error fallback to line-based
- Test preamble extraction (imports, docstring)
- Test composite router selects correct strategy
- Test unsupported extension uses fallback
- Test chunk names are qualified (ClassName.method_name)

---

## Feature 8: User-Facing Configuration

### Current State
Configuration is programmatic via `SemanticIndexConfig`. No user-facing config file support.

### Design

**Extend CLIConfig (if exists) or create new config section:**
```yaml
# In .scrappy/config.yaml or similar

semantic_search:
  enabled: true
  db_dir_name: ".scrappy/lancedb"
  max_text_length: 512
  fts_rebuild_threshold: 100

  # Advanced (optional)
  batch_size: 256
  super_batch_size: 2048
  vector_index_type: "auto"  # auto, hnsw, ivf_pq

  # File filtering
  ignore_patterns:
    - "__snapshots__/"
    - "*.snap"
    - "fixtures/"
```

**Config Loader:**
```python
# In src/config/semantic_config.py

def load_semantic_config(config_path: Optional[Path] = None) -> SemanticIndexConfig:
    """Load semantic search config from file or defaults."""
    if config_path is None:
        config_path = Path.cwd() / ".scrappy" / "config.yaml"

    if not config_path.exists():
        return SemanticIndexConfig()

    with open(config_path) as f:
        data = yaml.safe_load(f)

    semantic_data = data.get("semantic_search", {})
    return SemanticIndexConfig(
        batch_size=semantic_data.get("batch_size", 256),
        max_text_length=semantic_data.get("max_text_length", 512),
        # ... map other fields
    )
```

### Test Strategy
- Test default config loading
- Test custom config file parsing
- Test invalid config handling
- Test config validation

---

## Implementation Order

### Phase 2.1: Quick Wins (< 1 day each) - COMPLETED

1. **Test Noise Exclusion** - Extend IndexFilterConfig - DONE
   - Low risk, immediate benefit
   - No new protocols needed
   - Effort: 2-4 hours
   - **Implementation:** Added `test_noise_patterns`, `test_noise_extensions`, `skip_large_json_in_tests`, and `large_json_threshold_bytes` to `IndexFilterConfig`. Updated `should_skip_by_path()` and added `should_skip_large_json_in_tests()`. 10 tests added.

2. **FTS Incremental** - Update replace=False - DONE
   - Small change
   - Verify LanceDB version
   - Effort: 1-2 hours
   - **Implementation:** Updated `_maybe_rebuild_fts()` to try `replace=False` first, with fallback to `replace=True`. Gracefully handles "already exists" errors. 3 tests added.

3. **Deleted File Cleanup** - Add cleanup_deleted_files method - DONE
   - Straightforward implementation
   - Extends existing protocol
   - Effort: 3-4 hours
   - **Implementation:** Added `cleanup_deleted_files()` to `SemanticSearchProtocol` and `LanceDBSearchProvider`. Batches deletions (100 per batch), escapes SQL, cleans up old versions. 6 tests added.

### Phase 2.2: Medium Effort (1-2 days each) - COMPLETED

4. **Priority Queue** - New protocol and implementation - DONE
   - New file: `file_prioritizer.py`
   - Modify `SemanticFileCollector`
   - Full test coverage
   - Effort: 1 day
   - **Implementation:** Added `FilePrioritizerProtocol` to `protocols.py`. Created `DefaultFilePrioritizer` with priority levels: README (0) > Source (1) > Docs (2) > Tests (3) > Other (4). Integrated into `SemanticFileCollector` with dependency injection. 25 tests added.

5. **Search Result Ranking** - New ranker protocol and implementation - DONE
   - New file: `ranker.py`
   - New data classes for scoring
   - Inject into provider
   - Effort: 1-2 days
   - **Implementation:** Added `ResultRankerProtocol`, `ScoredChunk`, and `RankingConfig` to `protocols.py`. Created `DefaultResultRanker` with weighted scoring (vector + FTS), exact match boost, and path match boost. Created `PassthroughRanker` for testing. Integrated into `LanceDBSearchProvider` with optional ranker injection. 21 tests added.

### Phase 2.3: Larger Changes (3-5 days each)

6. **Intelligent Chunking** - AST-aware code chunking
   - New `chunkers/` subpackage
   - Python AST implementation
   - Composite router pattern
   - Effort: 3-4 days

7. **User Config** - Config file support
   - Config loading/validation
   - Documentation
   - Migration from programmatic config
   - Effort: 2-3 days

---

## Architecture Diagram

```
                      +-------------------+
                      |   User Config     |
                      | (.scrappy/config) |
                      +--------+----------+
                               |
                               v
  +------------------+   +-----+------+   +-------------------+
  | FilePrioritizer  |-->|  File      |-->| SemanticFile      |
  | Protocol         |   | Collector  |   | Collector         |
  +------------------+   +------------+   +-------------------+
                                                 |
                                                 v
  +------------------+   +------------+   +-----+-------------+
  | Composite        |-->|  LanceDB   |-->| cleanup_deleted   |
  | CodeChunker      |   | Provider   |   | _files()          |
  +--------+---------+   +-----+------+   +-------------------+
           |                   |
           v                   v
  +--------+---------+   +-----+-------------+
  | PythonASTChunker |   | ResultRanker      |
  | (+ future langs) |   | Protocol          |
  +------------------+   +-------------------+
                               |
                               v
                      +--------+----------+
                      | Ranked Search     |
                      | Results           |
                      +-------------------+
```

---

## Testing Requirements

Each feature requires:

1. **Unit tests** - Protocol implementations in isolation
2. **Integration tests** - With real LanceDB (use temp directories)
3. **Mock tests** - Using test doubles from `tests/helpers.py`

**Test Isolation:** All tests must use injected dependencies. No real API calls, no real file system access outside temp directories.

**New Test Doubles Needed:**
- `MockResultRanker` - Returns candidates unchanged or with preset scores
- `MockChunkingStrategy` - Returns preset chunks for testing composite router

---

## Dependencies

| Feature | New Dependencies |
|---------|-----------------|
| Test Noise Exclusion | None |
| FTS Incremental | None (LanceDB >= 0.6 recommended) |
| Deleted File Cleanup | None |
| Priority Queue | None |
| Search Result Ranking | None |
| Intelligent Chunking | None (uses stdlib `ast` for Python) |
| User Config | `pyyaml` (likely already present) |

---

## Risk Assessment

| Feature | Risk | Mitigation |
|---------|------|------------|
| Test Noise | Low | Can be disabled via config |
| FTS Incremental | Low | Version check, fallback to replace=True |
| Deleted File Cleanup | Low | Explicit call, doesn't change default behavior |
| Priority Queue | Low | Non-breaking, additive |
| Search Result Ranking | Medium | Default ranker preserves existing behavior |
| Intelligent Chunking | Medium | Fallback to line-based for parse errors |
| User Config | Low | Backwards-compatible defaults |

---

## Success Metrics

1. **Test Noise:** 10-30% reduction in index size for test-heavy projects
2. **Priority Queue:** First useful results available 50% faster on large codebases
3. **Deleted File Cleanup:** Zero stale entries after batched re-indexing
4. **Search Result Ranking:** Improved relevance (qualitative, measure via user feedback)
5. **Intelligent Chunking:** Functions/classes returned as complete units (not split)
6. **User Config:** Users can tune settings without code changes
