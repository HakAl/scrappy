# Semantic File Search Integration Plan

## Executive Summary

This plan integrates LanceDB semantic file search **seamlessly** into the existing CodebaseContext architecture. Users won't know it's there - context retrieval just gets better.

**Key Principle:** Protocol First, Implementation Second. Seamless Integration, Zero Breaking Changes.

**Integration Strategy:**
- `explore()` automatically indexes files for semantic search
- `get_relevant_context()` uses semantic search when available, falls back to keyword matching
- No opt-in, no CLI commands, no configuration needed
- Graceful degradation if LanceDB dependencies not installed

---

## Architecture Overview

### Current Flow (Before)

```
CodebaseContext.explore()
  ├─ _scan_files()           # Scan filesystem
  ├─ _analyze_structure()    # Detect project type
  ├─ _read_key_files()       # Read priority files
  └─ _get_git_history()      # Git metadata

CodebaseContext.get_relevant_context(query)
  └─ Keyword matching (simple, limited)
```

### New Flow (After)

```
CodebaseContext.explore()
  ├─ _scan_files()           # Scan filesystem
  ├─ _analyze_structure()    # Detect project type
  ├─ _read_key_files()       # Read priority files
  ├─ _get_git_history()      # Git metadata
  └─ _index_for_semantic_search()  # NEW: Build semantic index

CodebaseContext.get_relevant_context(query)
  ├─ Try semantic search (if available)
  └─ Fall back to keyword matching (if not)
```

**User-visible changes:** None. Context just gets better.

---

## Phase 1: Protocol Design (MANDATORY FIRST STEP)

### 1.1 Define Core Protocols

**File:** `src/context/protocols.py` (append to existing file)

Add these protocols following existing patterns:

```python
from typing import Protocol, List, Dict, Optional
from dataclasses import dataclass


# --- Data Classes ---

@dataclass
class CodeChunk:
    """Represents a chunk of code with line range."""
    start_line: int
    end_line: int
    file_path: Optional[str] = None


@dataclass
class SearchResult:
    """Result from semantic search."""
    chunks: List[Dict]  # [{path, lines: (start, end), content, score}]
    tokens_used: int
    limit_hit: Optional[str] = None  # 'token_limit' | None


# --- Protocols ---

@runtime_checkable
class CodeChunkerProtocol(Protocol):
    """
    Protocol for code chunking strategies.

    Abstracts code chunking to enable different strategies
    (semantic, line-based, AST-based) without changing consumers.

    Implementations:
    - SemanticCodeChunker: Semantic chunking with overlap
    - LineBasedChunker: Simple line-count chunking (future)
    - TestChunker: Fixed chunks for testing
    """

    def chunk(self, file_path: str, content: str) -> List[CodeChunk]:
        """
        Chunk code content into retrievable segments.

        Args:
            file_path: Path to the file being chunked
            content: File content to chunk

        Returns:
            List of CodeChunk objects with line ranges
        """
        ...


@runtime_checkable
class SemanticSearchProtocol(Protocol):
    """
    Protocol for semantic code search.

    Abstracts semantic search implementation to enable:
    - Swapping search backends (LanceDB, Pinecone, Chroma)
    - Testing with mock search results
    - Graceful degradation when not available

    Implementations:
    - LanceDBSearchProvider: Vector + FTS hybrid search
    - MockSearchProvider: Preset results for testing
    - NullSearchProvider: No-op for when dependencies unavailable
    """

    def index_files(self, files: Dict[str, str]) -> None:
        """
        Index files for semantic search.

        Args:
            files: Dict mapping file paths to content

        Raises:
            IndexingError: If indexing fails
        """
        ...

    def search(
        self,
        query: str,
        max_results: int = 25,
        max_tokens: int = 4000
    ) -> SearchResult:
        """
        Search indexed files semantically.

        Args:
            query: Search query
            max_results: Maximum results to return
            max_tokens: Token budget for results

        Returns:
            SearchResult with chunks and metadata
        """
        ...

    def is_indexed(self) -> bool:
        """
        Check if files have been indexed.

        Returns:
            True if index exists and is usable, False otherwise
        """
        ...

    def clear_index(self) -> None:
        """Clear the search index."""
        ...
```

**Why these protocols?**
- `CodeChunkerProtocol`: Swap chunking strategies without touching search code
- `SemanticSearchProtocol`: Swap search backends, test with mocks, graceful degradation

---

## Phase 2: Dependency Updates

### 2.1 Update pyproject.toml

**File:** `pyproject.toml`

Make LanceDB dependencies **optional** for graceful degradation:

```toml
[project.dependencies]
# ... existing required deps ...
groq = ">=0.4.0"
cohere = ">=5.0.0"
# ... etc ...

[project.optional-dependencies]
dev = [
    # ... existing dev deps ...
]

# NEW: Optional semantic search dependencies
semantic = [
    "lancedb>=0.5.0",
    "fastembed>=0.2.0",
    "fasteners>=0.19",
    "tantivy>=0.21.0; sys_platform != 'win32'",
    "tqdm>=4.65.0",
]

# Install with: pip install -e ".[semantic]"
```

### 2.2 Install Dependencies

```bash
# For users who want semantic search
pip install -e ".[semantic]"

# For users without semantic search
pip install -e .  # Still works, just uses keyword matching
```

---

## Phase 3: Implementation (Protocol-Compliant)

### 3.1 Implement CodeChunker

**File:** `src/context/code_chunker.py` (NEW)

```python
"""
Code chunking for semantic search.

Implements CodeChunkerProtocol with semantic overlap strategy.
"""

from typing import List
from .protocols import CodeChunk, CodeChunkerProtocol


class SemanticCodeChunker:
    """
    Chunks code with overlapping lines for better context.

    Implements CodeChunkerProtocol.

    Design decisions:
    - Overlap prevents context loss at chunk boundaries
    - Line-based chunking (not token-based) for simplicity
    - Configurable chunk size for different use cases
    """

    def __init__(
        self,
        chunk_size: int = 100,
        overlap: int = 3
    ):
        """
        Initialize chunker (NO I/O, just configuration).

        Args:
            chunk_size: Lines per chunk
            overlap: Overlapping lines between chunks

        Raises:
            ValueError: If overlap >= chunk_size
        """
        if overlap >= chunk_size:
            raise ValueError(f"Overlap ({overlap}) must be less than chunk_size ({chunk_size})")

        self._chunk_size = chunk_size
        self._overlap = overlap

    def chunk(self, file_path: str, content: str) -> List[CodeChunk]:
        """
        Chunk content with overlap.

        Example with chunk_size=10, overlap=3:
        - Chunk 1: lines 1-10
        - Chunk 2: lines 8-17 (3 line overlap)
        - Chunk 3: lines 15-24 (3 line overlap)

        Args:
            file_path: Path to file (for reference, not used)
            content: File content to chunk

        Returns:
            List of CodeChunk objects with line ranges
        """
        if not content.strip():
            return []

        lines = content.splitlines()
        chunks: List[CodeChunk] = []

        i = 0
        while i < len(lines):
            chunk_start = i + 1  # 1-indexed for human readability
            chunk_end = min(i + self._chunk_size, len(lines))

            chunks.append(CodeChunk(
                start_line=chunk_start,
                end_line=chunk_end,
                file_path=file_path
            ))

            # Move forward by (chunk_size - overlap)
            step = self._chunk_size - self._overlap
            i += step

        return chunks
```

### 3.2 Implement LanceDBSearchProvider

**File:** `src/context/lancedb_search_provider.py` (NEW)

```python
"""
LanceDB-based semantic search provider.

Implements SemanticSearchProtocol using LanceDB for vector storage
and hybrid search (vector + full-text).
"""

import os
import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Optional
from contextlib import contextmanager

import lancedb
import fasteners
from lancedb.pydantic import LanceModel, Vector
from lancedb.embeddings import get_registry

from .protocols import (
    CodeChunk,
    CodeChunkerProtocol,
    SemanticSearchProtocol,
    SearchResult
)

logger = logging.getLogger(__name__)

# --- Configuration Constants ---
DB_DIR_NAME = ".lancedb"
LOCK_FILE_NAME = "update.lock"
TABLE_NAME = "code_chunks"
EMBEDDING_MODEL = "jinaai/jina-embeddings-v2-base-code"
TOKEN_ESTIMATION_CHAR_RATIO = 3.0
BATCH_SIZE = 1000
MIN_CHUNK_SIZE = 20  # Skip very small chunks


class IndexingError(Exception):
    """Custom exception for user-facing indexing failures."""
    pass


# --- Setup Embedding Function ---
embedding_func = get_registry().get("fastembed").create(name=EMBEDDING_MODEL)


class CodeSchema(LanceModel):
    """Schema for storing code chunks with vector embeddings."""
    id: str                 # Composite: "path:start_line"
    file_path: str          # Normalized POSIX path
    start_line: int
    end_line: int
    content_hash: str       # MD5 hash for change detection
    content: str = embedding_func.SourceField()
    vector: Vector(embedding_func.ndims()) = embedding_func.VectorField()


class LanceDBSearchProvider:
    """
    LanceDB-based semantic search provider.

    Implements SemanticSearchProtocol using LanceDB for vector storage,
    hybrid search (vector + FTS), and incremental updates.

    Key features:
    - Incremental indexing (only updates changed files)
    - File locking (prevents race conditions)
    - Graceful error handling
    - Windows path normalization
    - Security (path traversal prevention)
    """

    def __init__(
        self,
        project_path: Path,
        chunker: CodeChunkerProtocol,
        db_dir_name: str = DB_DIR_NAME,
        lock_timeout: int = 300,  # 5 minutes (large repos need time)
    ):
        """
        Initialize search provider (NO I/O in constructor).

        Args:
            project_path: Project root path
            chunker: Code chunking strategy (INJECTED)
            db_dir_name: Database directory name
            lock_timeout: Lock acquisition timeout in seconds
        """
        self._project_path = project_path.resolve()
        self._chunker = chunker  # Injected dependency
        self._db_path = self._project_path / db_dir_name
        self._lock_path = self._db_path / LOCK_FILE_NAME
        self._lock_timeout = lock_timeout

        # Lazy initialization
        self._db = None

    def _ensure_db(self):
        """Lazy DB initialization (creates directory and connects)."""
        if self._db is None:
            self._db_path.mkdir(parents=True, exist_ok=True)
            self._db = lancedb.connect(self._db_path)

    # --- Helper: Path Normalization & Security ---

    def _normalize_path(self, raw_path: str) -> str:
        """
        Normalize paths to POSIX style and ensure within project root.

        Prevents path traversal attacks (e.g., "../../../etc/passwd").

        Args:
            raw_path: Raw path from user/filesystem

        Returns:
            Normalized POSIX path relative to project root

        Raises:
            ValueError: If path is outside project root
            IndexingError: If path is malformed
        """
        try:
            # Resolve handles symlinks and absolute paths
            full_path = (self._project_path / raw_path).resolve()
        except OSError as e:
            logger.error(f"Invalid path structure: {raw_path}")
            raise IndexingError(f"Path invalid: {raw_path}") from e

        # Security Check: Ensure file is actually inside the project
        if not full_path.is_relative_to(self._project_path):
            logger.warning(f"Security: Attempted access outside root: {raw_path}")
            raise ValueError(f"Security: File outside project root: {raw_path}")

        # Return POSIX path relative to root (e.g., "src/main.py")
        return full_path.relative_to(self._project_path).as_posix()

    def _compute_hash(self, text: str) -> str:
        """Fast hash for content change detection."""
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    # --- Helper: Safe Context Manager ---

    @contextmanager
    def _safe_db_context(self, timeout: Optional[int] = None):
        """
        Acquire file lock to prevent race conditions.

        Multiple CLI instances can't update index simultaneously.

        Args:
            timeout: Lock timeout in seconds (None = use default)

        Raises:
            IndexingError: If lock cannot be acquired
        """
        timeout = timeout or self._lock_timeout
        lock = fasteners.InterProcessLock(self._lock_path)
        got_lock = lock.acquire(blocking=True, timeout=timeout)

        if not got_lock:
            raise IndexingError(
                "Database locked by another process. "
                "Please wait or check for stuck processes."
            )

        try:
            yield
        except lancedb.db.LanceError as e:
            # Handle internal LanceDB corruption or errors
            raise IndexingError(f"Search engine error: {e}")
        finally:
            try:
                lock.release()
            except Exception:
                pass  # Best effort

    # --- Core: Indexing ---

    def index_files(self, files: Dict[str, str]) -> None:
        """
        Index files for semantic search (incremental updates).

        Implements SemanticSearchProtocol.

        Strategy:
        1. Snapshot current DB state (path -> hash)
        2. Diff against filesystem state
        3. Remove stale entries (deleted/modified files)
        4. Add new entries (new/modified files)
        5. Update FTS index

        Args:
            files: Dict mapping file paths to content

        Raises:
            IndexingError: If indexing fails
        """
        self._ensure_db()

        with self._safe_db_context():
            table_exists = TABLE_NAME in self._db.table_names()

            if not table_exists:
                self._create_and_populate(files)
                return

            table = self._db.open_table(TABLE_NAME)

            # 1. Snapshot current DB state (Path -> Hash)
            db_state = {}
            try:
                for batch in table.search().select(["file_path", "content_hash"]).to_batches():
                    df = batch.to_pandas()
                    for _, row in df.iterrows():
                        db_state[row["file_path"]] = row["content_hash"]
            except Exception:
                # Schema mismatch or corruption - rebuild
                logger.warning("Could not read existing index. Rebuilding...")
                self._create_and_populate(files)
                return

            # 2. Calculate Diff
            files_to_add = {}     # {path: content}
            paths_to_remove = []  # [path]

            # Check filesystem against DB
            for raw_path, content in files.items():
                try:
                    norm_path = self._normalize_path(raw_path)
                except ValueError:
                    continue  # Skip unsafe paths

                current_hash = self._compute_hash(content)

                # If new or modified
                if norm_path not in db_state or db_state[norm_path] != current_hash:
                    files_to_add[norm_path] = content
                    if norm_path in db_state:
                        paths_to_remove.append(norm_path)

            # Check DB against filesystem (detect deletions)
            fs_paths_set = set()
            for p in files:
                try:
                    fs_paths_set.add(self._normalize_path(p))
                except ValueError:
                    pass

            for db_path in db_state:
                if db_path not in fs_paths_set:
                    paths_to_remove.append(db_path)

            # 3. Apply Updates
            if not files_to_add and not paths_to_remove:
                logger.debug("Index is up to date")
                return

            logger.info(
                f"Updating index: +{len(files_to_add)} modified, "
                f"-{len(paths_to_remove)} deleted"
            )

            # Remove stale entries
            if paths_to_remove:
                table.delete("file_path IN (@paths)", {"paths": paths_to_remove})

            # Add new entries
            if files_to_add:
                self._add_files_in_batches(table, files_to_add)

                # Update FTS index
                # replace=True is expensive but ensures consistency
                table.create_fts_index("content", replace=True)

            table.cleanup_old_versions()

    def _create_and_populate(self, files: Dict[str, str]):
        """Create table from scratch."""
        # Drop if exists
        if TABLE_NAME in self._db.table_names():
            self._db.drop_table(TABLE_NAME)

        table = self._db.create_table(TABLE_NAME, schema=CodeSchema)

        # Normalize keys
        valid_files = {}
        for k, v in files.items():
            try:
                valid_files[self._normalize_path(k)] = v
            except ValueError:
                pass

        self._add_files_in_batches(table, valid_files)
        table.create_fts_index("content", replace=True)

    def _add_files_in_batches(self, table, files: Dict[str, str]):
        """Chunk content and add to DB in batches (memory efficient)."""
        batch = []

        for norm_path, content in files.items():
            try:
                chunks = self._chunker.chunk(norm_path, content)
                lines = content.splitlines()
                file_hash = self._compute_hash(content)

                for chunk in chunks:
                    chunk_text = '\n'.join(lines[chunk.start_line - 1:chunk.end_line])

                    # Skip very small chunks (noise)
                    if len(chunk_text) < MIN_CHUNK_SIZE:
                        continue

                    batch.append({
                        "id": f"{norm_path}:{chunk.start_line}",
                        "file_path": norm_path,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                        "content_hash": file_hash,
                        "content": chunk_text,
                    })

                    if len(batch) >= BATCH_SIZE:
                        table.add(batch)
                        batch = []

            except Exception as e:
                logger.error(f"Failed to chunk/index file {norm_path}: {e}")

        if batch:
            table.add(batch)

    # --- Core: Retrieval ---

    def search(
        self,
        query: str,
        max_results: int = 25,
        max_tokens: int = 4000
    ) -> SearchResult:
        """
        Search indexed files semantically.

        Implements SemanticSearchProtocol.

        Uses hybrid search: vector similarity + full-text search.
        Falls back to vector-only if FTS fails.

        Args:
            query: Search query
            max_results: Maximum results to return
            max_tokens: Token budget for results

        Returns:
            SearchResult with chunks and metadata
        """
        if not self.is_indexed():
            return SearchResult(chunks=[], tokens_used=0, limit_hit=None)

        table = self._db.open_table(TABLE_NAME)

        # Hybrid Search: Vector (semantic) + FTS (keyword)
        try:
            results = (
                table.search(query, query_type="hybrid")
                .limit(max_results)
                .to_list()
            )
        except Exception as e:
            # Fallback if FTS index broken or missing
            logger.warning(f"Hybrid search failed ({e}), falling back to vector search")
            results = table.search(query, query_type="vector").limit(max_results).to_list()

        final_chunks = []
        used_tokens = 0
        limit_hit = None

        # Deduplication: (file_path, start_line)
        seen_chunks = set()

        for row in results:
            chunk_id = (row['file_path'], row['start_line'])
            if chunk_id in seen_chunks:
                continue

            content = row['content']
            # Rough token estimation
            cost = int(len(content) / TOKEN_ESTIMATION_CHAR_RATIO)

            if used_tokens + cost > max_tokens:
                limit_hit = 'token_limit'
                break

            final_chunks.append({
                'path': row['file_path'],
                'lines': (row['start_line'], row['end_line']),
                'content': content,
                'score': row.get('_score', 0.0)
            })
            used_tokens += cost
            seen_chunks.add(chunk_id)

        return SearchResult(
            chunks=final_chunks,
            tokens_used=used_tokens,
            limit_hit=limit_hit
        )

    def is_indexed(self) -> bool:
        """
        Check if files have been indexed.

        Implements SemanticSearchProtocol.

        Returns:
            True if index exists and is usable
        """
        try:
            self._ensure_db()
            return TABLE_NAME in self._db.table_names()
        except Exception:
            return False

    def clear_index(self) -> None:
        """
        Clear the search index.

        Implements SemanticSearchProtocol.
        """
        self._ensure_db()
        with self._safe_db_context():
            if TABLE_NAME in self._db.table_names():
                self._db.drop_table(TABLE_NAME)
```

### 3.3 Update CodebaseContext (Seamless Integration)

**File:** `src/context/codebase_context.py`

Add semantic search support with graceful degradation:

```python
# Add to imports at top of file
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# In CodebaseContext class:

class CodebaseContext:
    def __init__(
        self,
        project_path: Optional[str] = None,
        file_scanner: Optional[FileScanner] = None,
        cache: Optional[ContextCache] = None,
        platform_detector: Optional[PlatformDetector] = None,
        git_history_reader: Optional[GitHistoryReader] = None,
        project_detector: Optional[ProjectDetector] = None,
        auto_load_cache: bool = False,
        # NEW: Optional semantic search injection
        semantic_search: Optional['SemanticSearchProtocol'] = None,
    ):
        """
        Initialize codebase context.

        Args:
            ... existing args ...
            semantic_search: Optional semantic search provider.
                           If None, will auto-create if dependencies available.
        """
        # ... existing initialization ...

        # NEW: Semantic search (created by factory if not injected)
        self._semantic_search = semantic_search or self._create_default_semantic_search()

    def _create_default_semantic_search(self) -> Optional['SemanticSearchProtocol']:
        """
        Create default semantic search if dependencies available.

        Gracefully returns None if LanceDB not installed.

        Returns:
            SemanticSearchProtocol instance or None
        """
        try:
            from .code_chunker import SemanticCodeChunker
            from .lancedb_search_provider import LanceDBSearchProvider

            chunker = SemanticCodeChunker(chunk_size=100, overlap=3)
            return LanceDBSearchProvider(self.project_path, chunker)
        except ImportError as e:
            logger.debug(f"Semantic search not available: {e}")
            return None
        except Exception as e:
            logger.warning(f"Failed to initialize semantic search: {e}")
            return None

    def explore(self, force: bool = False) -> dict:
        """
        Explore the codebase and build context.

        Now includes semantic indexing if available.

        Args:
            force: Force re-exploration even if cache exists

        Returns:
            Dict with exploration results
        """
        if self.is_explored() and not force:
            return {
                'status': 'cached',
                'explored_at': self.explored_at.isoformat(),
                'summary': self.summary
            }

        # Scan for source files
        self.file_index = self._scan_files()

        # Analyze structure
        self.structure = self._analyze_structure()

        # Read key files
        self.key_files = self._read_key_files()

        # Get git history if available
        if self.structure.get('has_git'):
            self.git_history = self._get_git_history()

        # NEW: Index for semantic search if available
        if self._semantic_search:
            self._index_for_semantic_search()

        # Mark exploration time
        self.explored_at = datetime.now()

        # Save to cache
        self._save_cache()

        return {
            'status': 'explored',
            'explored_at': self.explored_at.isoformat(),
            'total_files': self.structure.get('total_files', 0),
            'file_types': self.structure.get('by_type', {}),
            'directories': self.structure.get('directories', []),
            'has_git_history': bool(self.git_history),
            'semantic_search_enabled': self._semantic_search is not None,
        }

    def _index_for_semantic_search(self):
        """
        Index files for semantic search (called during explore).

        Gracefully handles errors - semantic search becomes unavailable on failure.
        """
        try:
            logger.info("Indexing files for semantic search...")

            # Collect file contents
            files = {}
            for file_type, file_list in self.file_index.items():
                for file_path in file_list:
                    full_path = self.project_path / file_path
                    try:
                        content = full_path.read_text(encoding='utf-8', errors='ignore')
                        files[file_path] = content
                    except Exception as e:
                        logger.debug(f"Skipping {file_path}: {e}")

            # Index files
            self._semantic_search.index_files(files)
            logger.info(f"Indexed {len(files)} files for semantic search")

        except Exception as e:
            logger.warning(f"Semantic indexing failed: {e}")
            # Gracefully degrade - disable semantic search
            self._semantic_search = None

    def get_relevant_context(self, query: str, max_tokens: int = 4000) -> str:
        """
        Get context relevant to a specific query.

        Now uses semantic search if available, with fallback to keyword matching.

        Args:
            query: The query to find relevant context for
            max_tokens: Maximum tokens to return (for semantic search)

        Returns:
            Relevant context string
        """
        if not self.is_explored():
            return ""

        # Try semantic search first
        if self._semantic_search and self._semantic_search.is_indexed():
            try:
                result = self._semantic_search.search(query, max_tokens=max_tokens)
                if result.chunks:
                    logger.debug(f"Using semantic search ({len(result.chunks)} chunks)")
                    return self._format_search_result(result)
            except Exception as e:
                logger.warning(f"Semantic search failed, falling back to keyword: {e}")

        # Fall back to keyword matching (existing logic)
        logger.debug("Using keyword-based context")
        return self._get_keyword_context(query)

    def _format_search_result(self, result: 'SearchResult') -> str:
        """
        Format search result into context string.

        Args:
            result: SearchResult from semantic search

        Returns:
            Formatted context string
        """
        if not result.chunks:
            return ""

        parts = []
        for chunk in result.chunks:
            header = f"--- {chunk['path']} (lines {chunk['lines'][0]}-{chunk['lines'][1]}) ---"
            parts.append(f"{header}\n{chunk['content']}\n")

        return "\n".join(parts)

    def _get_keyword_context(self, query: str) -> str:
        """
        Get context using keyword matching (existing behavior).

        This is the ORIGINAL get_relevant_context logic, extracted
        for clarity and to enable fallback.

        Args:
            query: Search query

        Returns:
            Context string based on keyword matching
        """
        # Simple keyword-based relevance (existing logic)
        query_lower = query.lower()
        relevant_parts = []

        # Always include summary
        if self.summary:
            relevant_parts.append(f"Project: {self.summary}")

        # Check for file-specific keywords
        if any(word in query_lower for word in ['file', 'module', 'class', 'function', 'import']):
            py_files = self.file_index.get('python', [])[:10]
            if py_files:
                relevant_parts.append("Key Python files:\n" + "\n".join(f"  {f}" for f in py_files))

        # Check for config-related queries
        if any(word in query_lower for word in ['config', 'setup', 'install', 'dependency', 'require']):
            if 'requirements.txt' in self.key_files:
                from .config_loader import get_truncation_defaults
                defaults = get_truncation_defaults()
                deps = self.key_files['requirements.txt'][:defaults['error_message']]
                relevant_parts.append(f"Dependencies:\n{deps}")

        # Check for architecture queries
        if any(word in query_lower for word in ['architecture', 'structure', 'organize', 'pattern']):
            dirs = self.structure.get('directories', [])
            if dirs:
                relevant_parts.append(f"Project directories: {', '.join(dirs)}")

        return "\n\n".join(relevant_parts)
```

---

## Phase 4: Testing (TDD Approach)

### 4.1 Test CodeChunker

**File:** `tests/context/test_code_chunker.py` (NEW)

```python
"""
Tests for code chunking.

Following TDD: Test behavior, not implementation.
"""

import pytest
from src.context.code_chunker import SemanticCodeChunker


def test_chunks_empty_content():
    """Chunker handles empty content gracefully."""
    chunker = SemanticCodeChunker(chunk_size=10, overlap=2)
    chunks = chunker.chunk("test.py", "")
    assert chunks == []


def test_chunks_whitespace_only():
    """Chunker handles whitespace-only content."""
    chunker = SemanticCodeChunker(chunk_size=10, overlap=2)
    chunks = chunker.chunk("test.py", "   \n\n   \n")
    assert chunks == []


def test_chunks_single_small_file():
    """Chunker creates single chunk for small files."""
    chunker = SemanticCodeChunker(chunk_size=100, overlap=3)
    content = "\n".join([f"line {i}" for i in range(10)])

    chunks = chunker.chunk("test.py", content)

    assert len(chunks) == 1
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 10


def test_chunks_with_overlap():
    """Chunker creates overlapping chunks for context."""
    chunker = SemanticCodeChunker(chunk_size=10, overlap=3)
    content = "\n".join([f"line {i}" for i in range(30)])

    chunks = chunker.chunk("test.py", content)

    # Should have multiple chunks
    assert len(chunks) >= 3

    # Chunks should overlap by 3 lines
    for i in range(len(chunks) - 1):
        # Next chunk should start before current ends
        overlap = chunks[i].end_line - chunks[i + 1].start_line + 1
        assert overlap == 3 or overlap == chunks[i].end_line - chunks[i].start_line + 1


def test_rejects_invalid_overlap():
    """Chunker validates overlap < chunk_size."""
    with pytest.raises(ValueError, match="must be less than chunk_size"):
        SemanticCodeChunker(chunk_size=10, overlap=10)

    with pytest.raises(ValueError):
        SemanticCodeChunker(chunk_size=5, overlap=20)


def test_chunk_boundaries():
    """Chunker respects exact boundaries."""
    chunker = SemanticCodeChunker(chunk_size=5, overlap=1)
    content = "\n".join([f"line {i}" for i in range(1, 11)])  # 10 lines

    chunks = chunker.chunk("test.py", content)

    # First chunk should be lines 1-5
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 5

    # Second chunk should be lines 5-9 (1 line overlap)
    assert chunks[1].start_line == 5
    assert chunks[1].end_line == 9
```

### 4.2 Test LanceDB Provider

**File:** `tests/context/test_lancedb_provider.py` (NEW)

```python
"""
Tests for LanceDB semantic search.

Tests BEHAVIOR (indexing, search, updates), not implementation details.
"""

import pytest
import shutil
from pathlib import Path
from src.context.lancedb_search_provider import LanceDBSearchProvider
from src.context.code_chunker import SemanticCodeChunker


@pytest.fixture
def provider(tmp_path):
    """Create search provider with temp directory."""
    chunker = SemanticCodeChunker(chunk_size=100, overlap=3)
    provider = LanceDBSearchProvider(tmp_path, chunker)

    yield provider

    # Cleanup
    db_path = tmp_path / ".lancedb"
    if db_path.exists():
        shutil.rmtree(db_path)


def test_empty_search_returns_empty(provider):
    """Search on empty index returns no results."""
    result = provider.search("test query")

    assert result.chunks == []
    assert result.tokens_used == 0
    assert result.limit_hit is None


def test_is_indexed_returns_false_when_empty(provider):
    """is_indexed() returns False before indexing."""
    assert provider.is_indexed() is False


def test_indexes_and_retrieves_content(provider):
    """End-to-end: index files and retrieve via search."""
    files = {
        "main.py": "def hello():\n    print('Hello world')\n",
        "utils.py": "def add(a, b):\n    return a + b\n"
    }

    provider.index_files(files)

    assert provider.is_indexed() is True

    result = provider.search("hello")

    assert len(result.chunks) > 0
    assert result.tokens_used > 0

    # Should find main.py content
    found_hello = any("hello" in c['content'].lower() for c in result.chunks)
    assert found_hello


def test_incremental_update_removes_old_version(provider):
    """Incremental update replaces old file version."""
    # Index v1
    files = {"test.py": "def old_function():\n    pass\n"}
    provider.index_files(files)

    result = provider.search("old_function")
    assert len(result.chunks) > 0

    # Update to v2
    files["test.py"] = "def new_function():\n    pass\n"
    provider.index_files(files)

    # Search should find new, not old
    result = provider.search("new_function")
    assert len(result.chunks) > 0

    result_old = provider.search("old_function")
    assert len(result_old.chunks) == 0


def test_handles_file_deletion(provider):
    """Index update removes deleted files."""
    # Index two files
    files = {
        "keep.py": "def keep_this():\n    pass\n",
        "delete.py": "def delete_this():\n    pass\n"
    }
    provider.index_files(files)

    # Search finds both
    result = provider.search("keep_this")
    assert len(result.chunks) > 0
    result = provider.search("delete_this")
    assert len(result.chunks) > 0

    # Update index without delete.py
    files_updated = {"keep.py": "def keep_this():\n    pass\n"}
    provider.index_files(files_updated)

    # Should still find keep.py
    result = provider.search("keep_this")
    assert len(result.chunks) > 0

    # Should NOT find delete.py
    result = provider.search("delete_this")
    assert len(result.chunks) == 0


def test_handles_nasty_filenames(provider):
    """Handles special characters in filenames."""
    nasty_files = {
        "space in name.py": "print('space')",
        "dir/with/forward.py": "print('forward')",
        "weird'quote.py": "print('quote')",
        "utf8_🚀.py": "print('rocket')",
    }

    # Should index without crashing
    provider.index_files(nasty_files)

    # Should retrieve Unicode file
    result = provider.search("rocket", max_tokens=1000)
    assert len(result.chunks) > 0
    found = any("utf8_🚀.py" in c['path'] for c in result.chunks)
    assert found


def test_security_prevents_path_traversal(provider, tmp_path):
    """Prevents indexing files outside project root."""
    # Create file outside project root
    outside_file = tmp_path.parent / "secret.txt"
    outside_file.write_text("secret data")

    # Attempt path traversal
    nasty_input = {"../secret.txt": "secret content"}

    # Should not crash, should skip file
    provider.index_files(nasty_input)

    # Should not find secret content
    result = provider.search("secret")
    assert len(result.chunks) == 0


def test_respects_token_limit(provider):
    """Search respects max_tokens parameter."""
    # Create large file
    large_content = "\n".join([f"line {i} with some content here" for i in range(1000)])
    files = {"large.py": large_content}

    provider.index_files(files)

    # Search with small token limit
    result = provider.search("line", max_tokens=100)

    # Should respect token limit
    assert result.tokens_used <= 100
    # Should hit limit
    assert result.limit_hit == 'token_limit'


def test_clear_index_removes_all_data(provider):
    """clear_index() removes all indexed data."""
    files = {"test.py": "def foo():\n    pass\n"}
    provider.index_files(files)

    assert provider.is_indexed() is True

    provider.clear_index()

    assert provider.is_indexed() is False

    result = provider.search("foo")
    assert len(result.chunks) == 0
```

### 4.3 Integration Test

**File:** `tests/integration/test_semantic_search_integration.py` (NEW)

```python
"""
Integration tests for semantic search with CodebaseContext.

Tests end-to-end behavior across multiple components.
"""

import pytest
from pathlib import Path
from src.context import CodebaseContext


def test_semantic_context_retrieval_end_to_end(tmp_path):
    """End-to-end: explore codebase, semantic search works automatically."""
    # Create test files
    (tmp_path / "auth.py").write_text(
        "def authenticate_user(username, password):\n"
        "    '''Authenticate a user with credentials.'''\n"
        "    return validate_credentials(username, password)\n"
    )
    (tmp_path / "email.py").write_text(
        "def validate_email(email):\n"
        "    '''Check if email is valid.'''\n"
        "    return '@' in email\n"
    )

    # Create context (semantic search auto-created if available)
    context = CodebaseContext(str(tmp_path))

    # Explore codebase (should auto-index)
    result = context.explore()

    # If semantic search is available, should be indicated
    # (gracefully handles if LanceDB not installed)
    if result.get('semantic_search_enabled'):
        # Get context for authentication query
        context_str = context.get_relevant_context("user authentication")

        # Should find relevant content
        assert "authenticate_user" in context_str or "auth.py" in context_str
        assert len(context_str) > 0
    else:
        # Semantic search not available (LanceDB not installed)
        # Should fall back to keyword matching
        context_str = context.get_relevant_context("authentication")
        # Keyword matching may or may not find it - that's OK
        assert isinstance(context_str, str)


def test_graceful_degradation_without_lancedb(tmp_path, monkeypatch):
    """Context works without LanceDB (graceful degradation)."""
    # Simulate LanceDB not available
    import sys
    if 'lancedb' in sys.modules:
        monkeypatch.setitem(sys.modules, 'lancedb', None)

    # Create context - should not crash
    context = CodebaseContext(str(tmp_path))

    # Explore should work
    result = context.explore()
    assert result['status'] == 'explored'

    # get_relevant_context should fall back to keyword
    context_str = context.get_relevant_context("test")
    assert isinstance(context_str, str)  # Should return something, not crash
```

---

## Phase 5: Documentation

### 5.1 Update README

**File:** `README.md`

Add section explaining semantic search (user-facing):

```markdown
## Codebase Context Awareness

Scrappy automatically understands your codebase and provides relevant context to the LLM.

### Automatic Semantic Search

When you run `scrappy`, it automatically:
1. Scans your project files
2. Indexes code for semantic search (if dependencies installed)
3. Uses AI to find relevant code for your queries

**No configuration needed** - it just works.

### Optional: Install Semantic Search

For enhanced context retrieval:

\`\`\`bash
pip install -e ".[semantic]"
\`\`\`

This installs LanceDB for vector-based semantic search. Without it, scrappy falls back to keyword matching (still works fine).

### How It Works

- **First run:** Indexes your codebase (may take 30-60 seconds for large projects)
- **Subsequent runs:** Updates only changed files (fast)
- **Query time:** Finds relevant code chunks using AI embeddings
- **Automatic:** No manual indexing commands needed
```

### 5.2 Architecture Documentation

**File:** `docs/ARCHITECTURE.md`

Add section on semantic search architecture:

```markdown
## Semantic Search Architecture

### Components

1. **CodeChunkerProtocol** (`src/context/protocols.py`)
   - Abstracts chunking strategies
   - Implementation: `SemanticCodeChunker`

2. **SemanticSearchProtocol** (`src/context/protocols.py`)
   - Abstracts search backends
   - Implementation: `LanceDBSearchProvider`

3. **CodebaseContext** (`src/context/codebase_context.py`)
   - Integrates semantic search seamlessly
   - Falls back to keyword matching gracefully

### Data Flow

\`\`\`
User runs CLI
    ↓
CodebaseContext.explore()
    ├─ Scan files
    ├─ Analyze structure
    ├─ Read key files
    └─ Index for semantic search (NEW)
        ├─ Chunk files (CodeChunker)
        └─ Build vector index (LanceDBSearchProvider)

User asks question
    ↓
CodebaseContext.get_relevant_context(query)
    ├─ Try semantic search
    │   ├─ Vector similarity
    │   └─ Hybrid ranking
    └─ Fall back to keyword (if semantic unavailable)
        └─ Return context
\`\`\`

### Design Decisions

**Protocol-First:** All components have protocols for swappability
**Graceful Degradation:** Works without LanceDB installed
**Incremental Updates:** Only re-indexes changed files
**Zero Configuration:** Automatic integration, no user action needed
```

---

## Implementation Checklist

Following CLAUDE.md principles:

### Architecture
- [ ] Protocols defined before implementations
- [ ] Each class has single responsibility (chunker, indexer, context separate)
- [ ] SOLID principles followed
- [ ] No god classes (all < 300 lines)
- [ ] Clear separation of concerns

### Dependency Injection
- [ ] All dependencies in constructor parameters (chunker injected into provider)
- [ ] Dependencies are protocols, not concrete classes
- [ ] No side effects in constructors (lazy DB initialization)
- [ ] No direct file/network access in constructors
- [ ] Defaults via factory methods (`_create_default_semantic_search`)

### Testing
- [ ] Tests prove features work (indexing, search, updates)
- [ ] Edge cases covered (empty, special chars, path traversal)
- [ ] Error conditions tested (graceful degradation)
- [ ] Minimal mocking (only external dependencies)
- [ ] Tests fail when features break
- [ ] Can refactor without breaking tests

### Code Quality
- [ ] No code duplication
- [ ] Meaningful names
- [ ] Functions < 50 lines
- [ ] Classes < 300 lines
- [ ] Type hints on all functions
- [ ] No magic numbers (all in constants)

---

## Success Criteria

1. **Seamless Integration**
   - `explore()` automatically indexes
   - `get_relevant_context()` automatically uses semantic search
   - No user action required

2. **Graceful Degradation**
   - Works without LanceDB (falls back to keyword)
   - Handles indexing errors gracefully
   - Never crashes user workflow

3. **Maintains Architecture**
   - All protocols defined
   - Full dependency injection
   - All tests pass

4. **Performance**
   - Incremental updates (not full re-index)
   - < 5s for 1000 files
   - Respects token budgets

---

## Implementation Order

1. **Phase 1:** Define protocols in `protocols.py`
2. **Phase 2:** Update `pyproject.toml` with optional dependencies
3. **Phase 3:** Implement `SemanticCodeChunker`
4. **Phase 4:** Implement `LanceDBSearchProvider`
5. **Phase 5:** Update `CodebaseContext` integration
6. **Phase 6:** Write tests (TDD - can do alongside implementation)
7. **Phase 7:** Update documentation

**Total estimate:** No time estimates (per CLAUDE.md). Focus on one phase at a time.

---

## Ready to Start?

The plan is complete and aligned with your architecture. Semantic search will be transparent to users - just better context retrieval.

**Next step:** Implement Phase 1 (Protocol definitions)?
