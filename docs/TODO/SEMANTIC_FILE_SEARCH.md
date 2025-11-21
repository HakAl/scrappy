# Existing Integration Status -- POC Verified with -- scripts/test_semantic_search.py

src/context/protocols.py, line 406
```python

# --- Semantic Search Data Classes ---

@dataclass
class CodeChunk:
    """Represents a chunk of code with line range."""
    start_line: int
    end_line: int
    file_path: Optional[str] = None


@dataclass
class SearchResult:
    """Result from semantic search."""
    chunks: List[Dict[str, Any]]  # [{path, lines: (start, end), content, score}]
    tokens_used: int
    limit_hit: Optional[str] = None  # 'token_limit' | None


# --- Semantic Search Protocols ---

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

    Example:
        def chunk_file(chunker: CodeChunkerProtocol, content: str) -> List[CodeChunk]:
            return chunker.chunk("example.py", content)
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

    Example:
        def search_code(search: SemanticSearchProtocol, query: str) -> SearchResult:
            if search.is_indexed():
                return search.search(query)
            return SearchResult(chunks=[], tokens_used=0)
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
src/context/code_chunker.py
src/context/semantic/embeddings.py
src/context/semantic/initializer.py
src/context/semantic/provider.py

Architecture Now Properly Integrated:

  ┌─────────────────────────────────────────────────┐
  │          BackgroundInitializerProtocol          │
  │  (infrastructure/protocols.py)                  │
  │  - start()                                      │
  │  - is_complete()                                │
  │  - get_status()                                 │
  │  - get_result()                                 │
  └────────────────┬────────────────────────────────┘
                   │ implements
                   ▼
  ┌─────────────────────────────────────────────────┐
  │       SemanticSearchInitializer                 │
  │  (context/semantic/initializer.py)              │
  │  - Loads FastEmbed/LanceDB in background        │
  │  - Thread-safe status updates                   │
  │  - Returns SemanticSearchProtocol when ready    │
  └────────────────┬────────────────────────────────┘
                   │ injected into
                   ▼
  ┌─────────────────────────────────────────────────┐
  │            CodebaseContext                      │
  │  (context/codebase_context.py)                  │
  │  - start_background_initialization()            │
  │  - is_semantic_search_ready()                   │
  │  - get_semantic_initialization_status()         │
  │  - explore() auto-uses when ready               │
  └─────────────────────────────────────────────────┘

  Demo Scripts Available:

  # Full integration demo with Rich progress
  python scripts/demo_integration.py

  # Original POC (still works)
  python scripts/test_semantic_search.py



[//]: # (TODO)

# P0

Finish semantic search integration -- partial implementation outlined above

Potential integration strategy for desired UX

Required Features
    - loads in background on app start with rich progress
    - progress displayed clearly to user
    - progress display goes away shortly after complete


# P1

--------------------------------------------------------
Don't index: htmlcov, temp, cache, everything
--------------------------------------------------------

"Trust Git first, fall back to regex, check for binary last" is the correct hierarchy for a developer tool.

### 1. The "Substring Match" Bug (Critical)
Your current regexes are too loose.
```python
r"build", r"dist", r"target"
```
**The problem:** These are searching purely for substrings.
*   `r"build"` will skip `src/builders.py`.
*   `r"dist"` will skip `src/distributed_systems.py`.
*   `r"target"` will skip `src/utils/retargeting.ts`.

**The Fix:**
You need to match these either as **directories** or **exact filenames**, not arbitrary substrings. The cleanest way in your `_should_skip` helper is to check path *parts*, or use stricter regex boundaries.

**Revised Regex Strategy:**
Update the regexes to match path separators or boundaries.
```python
# Match "dist" only if it appears as a complete folder name or file name
r"(^|/)dist(/|$)", r"(^|/)build(/|$)", r"(^|/)node_modules(/|$)"
```
*Or, clearer but slightly more Python code:* leave regexes for extensions (`\.pyc$`) and use a set for directory names.

### 2. The "Fall-back" Security Risk
```python
candidates = self._list_files_git() or self._list_files_plain()
```
If `git ls-files` fails (e.g., a corrupt git index, or git isn't installed), you silently fall back to `_list_files_plain`.
**The Risk:** If a user has a `secret.key` file that is ignored via `.gitignore`, and the git command fails, your tool falls back to the regex list. Since `secret.key` isn't in your hardcoded regex list, **it gets indexed**.

**The Fix:**
Only fall back if `path` is **not** a git repository. If it *is* a git repo but the command fails, you should probably warn/abort rather than ignoring the `.gitignore`.

```python
def _crawl_filesystem(self) -> dict[str, str]:
    is_git = (self._project_path / ".git").exists()
    candidates = set()
    
    if self.filter_config.respect_gitignore and is_git:
        candidates = self._list_files_git()
        # If git repo exists but returns empty/fails, DO NOT fall back 
        # unless you really trust your regex list to catch secrets.
        if not candidates: 
             # logic to decide if we fall back or warn
             pass 
    else:
        candidates = self._list_files_plain()
    
    # ... rest of function
```

### 3. The "Memory Bomb" (Large Files)
You are doing `path.read_text()`. If the repo contains a 2GB `server.log` or a minified JS bundle that isn't in `.gitignore`, your process will crash or hang.

**The Fix:**
Add a simple size check before reading.

```python
MAX_FILE_SIZE = 1024 * 1024 * 5  # 5MB limit

# ... inside the loop
stat = path.stat()
if stat.st_size > MAX_FILE_SIZE:
    logger.debug(f"Skipping large file: {rel} ({stat.st_size} bytes)")
    continue
```

---

### Example Code

Example regex boundaries and adds the size limit.

```python
from dataclasses import dataclass, field
import re
import subprocess
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

@dataclass
class IndexFilterConfig:
    # Mixed strategy: 
    # 1. Exact directory/file matches (safer than regex for names like "build")
    # 2. Regex for extensions/patterns
    
    ignore_names: set[str] = field(default_factory=lambda: {
        "__pycache__", "node_modules", ".git", ".svn", ".hg", 
        ".idea", ".vscode", ".DS_Store", "Thumbs.db",
        "dist", "build", "target", "venv", ".venv", ".env"
    })
    
    ignore_extensions: list[str] = field(default_factory=lambda: (
        r"\.py[cod]$", r"\.so$", r"\.dylib$", r"\.dll$", r"\.exe$", 
        r"\.bin$", r"\.jpe?g$", r"\.png$", r"\.gif$", r"\.svg$", r"\.ico$",
        r"\.lock$", r"package-lock\.json$", r"yarn\.lock$", 
    ))

    respect_gitignore: bool = True
    include_untracked: bool = False
    max_file_size_bytes: int = 5 * 1024 * 1024  # 5MB

    def __post_init__(self):
        self._compiled_ext = [re.compile(p, re.I) for p in self.ignore_extensions]

    def should_skip(self, path: Path, root: Path) -> bool:
        """
        Checks if path should be skipped based on static rules.
        path: absolute path
        root: project root
        """
        rel = path.relative_to(root)
        
        # 1. Check path parts against denied directory/file names
        # This prevents "dist" matching "distributed_systems.py"
        if any(part in self.ignore_names for part in rel.parts):
            return True
            
        # 2. Check regex extensions on the filename
        filename = path.name
        if any(r.search(filename) for r in self._compiled_ext):
            return True
            
        return False
```

---
--------------------------------------------------------
Token estimator still drifts on minified / Unicode files
--------------------------------------------------------
`len(content)/3` is fine for normal source, but collapses on:
- minified JS (1 char ≈ 1 token)  
- files with emoji or CJK comments (1 glyph ≈ 2–3 tokens).

Cheap improvement: keep a running **tiktoken** counter once you are within 20 % of the budget:

```python
import tiktoken
enc = tiktoken.get_encoding("cl100k_base")
...
if used_tokens + cost > max_tokens * 0.8:          # 80 % trigger
    cost = len(enc.encode(content))
    if used_tokens + cost > max_tokens:
        ...
```

You only pay for the exact count on the last few chunks.

---
--------------------------------------------------------
Hash collision safety
--------------------------------------------------------
MD5 is fine for change detection, but if you ever expose `content_hash` to the user (e.g. for de-duplication UI) move to Blake3 or SHA-256 to avoid “but MD5 is broken” conversations.  One-line change, zero perf hit for code-base sizes.

---
--------------------------------------------------------
FTS “replace=True” blocks readers
--------------------------------------------------------
Re-building the FTS index locks the table for ~100–400 ms per 10 k rows.  
LanceDB ≥ 0.6 lets you build incrementally:

```python
table.create_fts_index("content", replace=False)
```

Do it once after the **first** batch and never again; deletes are automatically handled.  Readers stay lock-free.
---

# P2
--------------------------------------------------------
HNSW instead of IVF-PQ for < 1 M rows
--------------------------------------------------------
IVF-PQ is fastest for > 1 M vectors, but for the usual 50 k–200 k code-chunk data set HNSW gives *lower* latency and better recall.  One-liner:

```python
table.create_index(
    index_type="HNSW",
    metric="cosine",
    m=32,
    ef_construction=150,
    replace=True
)
```