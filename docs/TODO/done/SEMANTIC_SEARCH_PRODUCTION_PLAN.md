# Semantic Search: POC to Production Implementation Plan

## Executive Summary

The current POC in `src/context/semantic/` is functional but needs architectural improvements and performance optimizations to be production-ready. This plan addresses the optimizations documented in `SPEED.md` while ensuring the code follows SOLID principles and the project's architectural guidelines.

---

## Implementation Status

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 1: Bug Fixes | COMPLETE | Bugs were false positives - code was already correct |
| Phase 2: Performance | COMPLETE | Config, super-batch, conditional FTS implemented |
| Phase 3: Architecture | COMPLETE | EmbeddingFunctionProtocol added, DI for embedding_func |
| Phase 4: Observability | COMPLETE | IndexingMetrics, progress reporting added |
| Phase 5: Testing | COMPLETE | 49 tests total (5 new for embedding injection) |

---

## What Was Implemented (Phase 2)

### New Files Created
- `src/context/semantic/config.py` - `SemanticIndexConfig` dataclass
- `tests/context/test_semantic_config.py` - 23 tests
- `tests/context/test_semantic_provider.py` - 21 tests

### Changes to `provider.py`
- Added `IndexingMetrics` dataclass for observability
- Updated constructor to accept `SemanticIndexConfig`
- Replaced `_add_files_in_batches` with super-batch processing
- Added `_process_super_batch` method
- Added `_maybe_rebuild_fts` for conditional FTS rebuild

### Configuration Defaults (in `SemanticIndexConfig`)
- `batch_size=256` (was 64)
- `max_text_length=512` (was 2000)
- `super_batch_size=2048` (memory safety)
- `fts_rebuild_threshold=100` (conditional rebuild)

---

## Current State Analysis

### What We Have (Production-Ready)

1. **`provider.py`** - `LanceDBSearchProvider`
   - Super-batch processing for memory safety
   - Conditional FTS rebuild (skips when < 100 chunks added)
   - Full DI via `SemanticIndexConfig`
   - Returns `IndexingMetrics` with timing data

2. **`config.py`** - `SemanticIndexConfig`
   - All tuning parameters injectable
   - Factory methods: `from_memory_adaptive()`, `for_testing()`

3. **`embeddings.py`** - `EmbedFunction` (117 lines)
   - Clean singleton pattern for model caching
   - Already uses 256 batch size in `embed()` call

4. **`file_collector.py`** - `SemanticFileCollector` (469 lines)
   - Well-designed with git integration and batched collection
   - Follows protocols properly

5. **`initializer.py`** - `SemanticSearchInitializer` (267 lines)
   - Background loading works correctly
   - Uses threading properly

6. **`code_chunker.py`** - `SemanticCodeChunker` (82 lines)
   - Simple, effective line-based chunking with overlap

### Protocols Defined (in `context/protocols.py`)
- `SemanticSearchProtocol` - search provider contract
- `CodeChunkerProtocol` - chunker contract
- `FileCollectorProtocol` - file collection contract

---

## Remaining Work

### Architecture (Phase 3 - COMPLETE)
1. **EmbeddingFunctionProtocol** - Added to `src/context/protocols.py`
2. **Provider DI** - `LanceDBSearchProvider` now accepts optional `embedding_func` parameter
3. **Tests** - 5 new tests for embedding function injection

---

## Implementation Plan

### Phase 1: Bug Fixes and Critical Issues

#### 1.1 Fix Deletion Logic Bug
**File:** `src/context/semantic/provider.py`

The `paths_to_remove` list is populated but deletions only happen when files are modified (line 333-334), not when files are actually deleted from the filesystem.

```python
# Current (buggy): Only removes when file is MODIFIED
if norm_path in db_state:
    paths_to_remove.append(norm_path)

# Missing: Already handled in lines 346-348 but both use same paths_to_remove list
```

**Fix:** The deletion detection (lines 336-348) is correct, but need to verify the deletion actually executes for all cases.

#### 1.2 Verify Search Query Embedding
**File:** `src/context/semantic/provider.py:570`

```python
# Current: Using index [0] on generator - may fail
query_vector = self._embedding_func.generate_embeddings([query])[0]
```

**Fix:** Ensure this properly materializes the generator result.

---

### Phase 2: Performance Optimizations (from SPEED.md)

#### 2.1 Create Configuration Dataclass
**New File:** `src/context/semantic/config.py`

```python
@dataclass
class SemanticIndexConfig:
    """Configuration for semantic search indexing."""

    # Embedding settings
    batch_size: int = 256          # Chunks per embedding batch
    max_text_length: int = 512     # BGE-small optimal context
    min_chunk_size: int = 20       # Skip tiny chunks

    # Memory safety
    super_batch_size: int = 2048   # Max chunks before DB flush

    # FTS settings
    fts_rebuild_threshold: int = 100  # Min chunks before FTS rebuild

    # Database settings
    db_dir_name: str = ".scrappy/lancedb"
    lock_timeout: int = 300

    @classmethod
    def from_memory_adaptive(cls) -> "SemanticIndexConfig":
        """Create config adaptive to available RAM."""
        try:
            import psutil
            available_gb = psutil.virtual_memory().available / (1024**3)
            super_batch = min(2048, int(available_gb * 400))
        except ImportError:
            super_batch = 1024  # Conservative default
        return cls(super_batch_size=super_batch)
```

#### 2.2 Implement Super-Batch Processing
**File:** `src/context/semantic/provider.py`

Replace `_add_files_in_batches` with optimized version:

```python
def _add_files_optimized(self, table, files: Dict[str, str]) -> None:
    """Add files with super-batch processing for memory safety."""
    config = self._config  # Injected SemanticIndexConfig

    all_chunks = []
    total_added = 0

    for norm_path, content in files.items():
        chunks = self._chunker.chunk(norm_path, content)
        lines = content.splitlines()
        file_hash = self._compute_hash(content)

        for chunk in chunks:
            chunk_text = self._extract_chunk_text(lines, chunk)
            if len(chunk_text) < config.min_chunk_size:
                continue

            all_chunks.append({
                "id": f"{norm_path}:{chunk.start_line}",
                "file_path": norm_path,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "content_hash": file_hash,
                "content": chunk_text[:config.max_text_length],
            })

            # Memory safety: flush when super-batch is full
            if len(all_chunks) >= config.super_batch_size:
                self._process_super_batch(table, all_chunks)
                total_added += len(all_chunks)
                all_chunks = []

    # Final flush
    if all_chunks:
        self._process_super_batch(table, all_chunks)
        total_added += len(all_chunks)

    return total_added

def _process_super_batch(self, table, chunks: List[Dict]) -> None:
    """Process a super-batch: embed and insert."""
    texts = [c["content"] for c in chunks]
    embeddings = list(self._embedding_func.generate_embeddings(texts))

    for chunk, embedding in zip(chunks, embeddings):
        chunk["vector"] = embedding

    # Insert in DB-optimal batches
    DB_BATCH_SIZE = 1000
    for i in range(0, len(chunks), DB_BATCH_SIZE):
        table.add(chunks[i:i + DB_BATCH_SIZE])
```

#### 2.3 Conditional FTS Rebuild
**File:** `src/context/semantic/provider.py`

```python
def _maybe_rebuild_fts(self, table, chunks_added: int) -> None:
    """Only rebuild FTS when significant data added."""
    if chunks_added < self._config.fts_rebuild_threshold:
        logger.debug(f"Skipping FTS rebuild ({chunks_added} < {self._config.fts_rebuild_threshold})")
        return

    try:
        if table.count_rows() > 0:
            table.create_fts_index("content", replace=True)
    except Exception as e:
        logger.warning(f"FTS rebuild failed: {e}")
```

---

### Phase 3: Protocol-First Architecture

#### 3.1 Define EmbeddingFunctionProtocol
**File:** `src/context/protocols.py`

```python
@runtime_checkable
class EmbeddingFunctionProtocol(Protocol):
    """Protocol for embedding generation."""

    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for texts."""
        ...

    def ndims(self) -> int:
        """Return embedding dimensionality."""
        ...
```

#### 3.2 Update Provider Constructor
**File:** `src/context/semantic/provider.py`

```python
def __init__(
    self,
    project_path: Path,
    chunker: CodeChunkerProtocol,
    config: Optional[SemanticIndexConfig] = None,
    embedding_func: Optional[EmbeddingFunctionProtocol] = None,
    progress_reporter: Optional[ProgressReporterProtocol] = None,
):
    """
    Initialize search provider (NO I/O in constructor).

    Args:
        project_path: Project root path
        chunker: Code chunking strategy (INJECTED)
        config: Index configuration (INJECTED, defaults provided)
        embedding_func: Embedding function (INJECTED, lazy-loaded if None)
        progress_reporter: Progress reporter (INJECTED)
    """
    self._project_path = project_path.resolve()
    self._chunker = chunker
    self._config = config or SemanticIndexConfig()
    self._embedding_func_factory = embedding_func  # May be None for lazy load
    # ... rest unchanged
```

---

### Phase 4: Observability and Metrics

#### 4.1 Add Timing Instrumentation
**File:** `src/context/semantic/provider.py`

```python
@dataclass
class IndexingMetrics:
    """Metrics from an indexing operation."""
    files_processed: int = 0
    chunks_added: int = 0
    chunks_skipped: int = 0
    embedding_time_seconds: float = 0.0
    db_write_time_seconds: float = 0.0
    total_time_seconds: float = 0.0
    chunks_per_second: float = 0.0

def index_files(self, files: Dict[str, str], is_batch: bool = False) -> IndexingMetrics:
    """Index files and return metrics."""
    start = time.time()
    metrics = IndexingMetrics()
    # ... implementation ...
    metrics.total_time_seconds = time.time() - start
    metrics.chunks_per_second = metrics.chunks_added / max(metrics.embedding_time_seconds, 0.001)
    return metrics
```

#### 4.2 Progress Reporting Integration
**File:** `src/context/semantic/provider.py`

```python
def _add_files_optimized(self, table, files: Dict[str, str]) -> int:
    total_files = len(files)

    for idx, (norm_path, content) in enumerate(files.items()):
        # Report progress
        self._progress.update(
            current=idx + 1,
            total=total_files,
            message=f"Indexing {norm_path}"
        )
        # ... rest of processing
```

---

### Phase 5: Testing Strategy

#### 5.1 Unit Tests for New Components

**File:** `tests/context/test_semantic_config.py`
- Test `SemanticIndexConfig` defaults
- Test `from_memory_adaptive()` factory
- Test validation (if any)

**File:** `tests/context/test_semantic_provider_optimized.py`
- Test super-batch memory capping
- Test FTS conditional rebuild
- Test deletion logic fix
- Test metrics collection

#### 5.2 Integration Tests

**File:** `tests/context/test_semantic_integration.py`
- End-to-end indexing and search
- Large repository simulation (memory safety)
- Concurrent access (file locking)

#### 5.3 Test Doubles

**File:** `tests/helpers/semantic_doubles.py`

```python
class MockEmbeddingFunction:
    """Test double for EmbeddingFunctionProtocol."""

    def __init__(self, dims: int = 384):
        self._dims = dims
        self.call_count = 0

    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        self.call_count += 1
        return [[0.1] * self._dims for _ in texts]

    def ndims(self) -> int:
        return self._dims


class MockChunker:
    """Test double for CodeChunkerProtocol."""

    def chunk(self, file_path: str, content: str) -> List[CodeChunk]:
        lines = content.splitlines()
        return [CodeChunk(start_line=1, end_line=len(lines), file_path=file_path)]
```

---

### Phase 6: Environment Optimizations (Optional)

#### 6.1 Document ONNX Environment Variables
**File:** `docs/SEMANTIC_SEARCH.md`

```markdown
## Performance Tuning

Set these environment variables for optimal embedding performance:

```bash
# ONNX Runtime optimizations
export OMP_NUM_THREADS=8                      # Match your CPU cores
export OMP_WAIT_POLICY=PASSIVE               # Better for throughput
export ONNXRUNTIME_EXECUTION_MODE=SEQUENTIAL # Recommended for batching

# Python optimizations
export PYTHONOPTIMIZE=1                      # Disable debug mode
```
```

#### 6.2 Add Threading Configuration to EmbedFunction
**File:** `src/context/semantic/embeddings.py`

```python
def _get_or_create_model() -> TextEmbedding:
    global _CACHED_MODEL
    if _CACHED_MODEL is None:
        # Configure ONNX threading for optimal performance
        import os
        cpu_count = os.cpu_count() or 4
        os.environ.setdefault('OMP_NUM_THREADS', str(cpu_count))

        _CACHED_MODEL = TextEmbedding(
            model_name="BAAI/bge-small-en-v1.5",
        )
    return _CACHED_MODEL
```

---

## Implementation Order

### Sprint 1: Critical Fixes - COMPLETE
1. ~~Fix deletion logic bug~~ - Was false positive, code already correct
2. ~~Fix query embedding generator handling~~ - Was false positive, code already correct
3. ~~Add basic tests for existing functionality~~ - Done

### Sprint 2: Performance Core - COMPLETE
1. ~~Create `SemanticIndexConfig` dataclass~~ - Done (`src/context/semantic/config.py`)
2. ~~Implement super-batch processing with memory cap~~ - Done
3. ~~Implement conditional FTS rebuild~~ - Done (`_maybe_rebuild_fts`)
4. ~~Update batch size to 256, text length to 512~~ - Done (in config defaults)

### Sprint 3: Architecture Cleanup - COMPLETE
1. ~~Define `EmbeddingFunctionProtocol`~~ - Done (in `src/context/protocols.py`)
2. ~~Refactor provider constructor for full DI~~ - Done (accepts `SemanticIndexConfig` and `embedding_func`)
3. ~~Add test doubles for protocols~~ - Done (`MockChunker`, `MockEmbeddingFunction`)
4. ~~Add tests for embedding injection~~ - Done (5 new tests)

### Sprint 4: Observability - COMPLETE
1. ~~Add `IndexingMetrics` dataclass~~ - Done
2. ~~Integrate progress reporting~~ - Done (in `_add_files_in_batches`)
3. ~~Add timing instrumentation~~ - Done (embed_time, db_time, total_time)

### Sprint 5: Testing and Documentation - COMPLETE
1. ~~Comprehensive unit tests~~ - Done (44 new tests)
2. ~~Integration tests with mock embeddings~~ - Done
3. Document environment optimizations - See below

---

## Expected Outcomes

### Performance Improvements
- **Indexing Speed:** 2-3x faster (based on SPEED.md results: 465s -> 198s)
- **Memory Safety:** Capped at ~800MB RAM usage regardless of repo size
- **FTS Overhead:** Reduced by skipping unnecessary rebuilds

### Architecture Improvements
- Full dependency injection for testability
- Protocol-first design for all components
- Configurable via dataclass (no magic constants)

### Observability
- Metrics from every indexing operation
- Progress reporting for UI integration
- Timing data for performance monitoring

---

## Files to Modify

| File | Changes |
|------|---------|
| `src/context/semantic/provider.py` | Super-batch, FTS optimization, deletion fix, metrics |
| `src/context/semantic/embeddings.py` | Environment config (optional) |
| `src/context/semantic/config.py` | **NEW** - Configuration dataclass |
| `src/context/protocols.py` | Add `EmbeddingFunctionProtocol` |
| `tests/context/test_semantic_provider.py` | **NEW** - Provider tests |
| `tests/helpers/semantic_doubles.py` | **NEW** - Test doubles |
| `docs/SEMANTIC_SEARCH.md` | **NEW** - Environment docs |

---

## Risk Mitigation

### Memory Safety
- Super-batch size adaptive to available RAM
- Tested with large repos (10k+ files)

### Backward Compatibility
- All changes backward compatible
- Existing API unchanged (metrics return is optional)

### Dependency Risks
- psutil is optional (graceful fallback)
- FastEmbed/LanceDB versions pinned in requirements

---

## Success Criteria

1. Indexing 10,000 chunks in < 120 seconds (vs ~465s currently)
2. Memory usage capped at 1GB for any repo size
3. All existing tests pass
4. New tests cover edge cases (OOM prevention, deletion, FTS skip)
5. Full protocol compliance for DI/testing
