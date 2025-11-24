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

---


# P0 - Finish semantic search integration

[//]: # (TODO)

# P0

Finish semantic search integration

Required Features
    - index lancedb when model is ready -- finished
    - progress displayed clearly to user
    - progress display goes away shortly after complete

Current status:
- Need to organize content so progress isn't drawn over user input

## Root Cause Analysis

**Issue 1: Progress Never Hides**
Location: `src/infrastructure/progress.py:61-87`

The `RichProgressReporter.complete()` and `error()` methods have a critical bug:
```python
def complete(self, message: str = "Complete") -> None:
    if self._status:
        self._status.stop()  # Spinner stops
        self._status = None
        # Print completion message that stays visible  <-- BUG!
        if self._console:
            self._console.print(f"[green]{message}[/green]")  # Permanent message
```

The `console.print()` call (lines 73, 87) leaves a **permanent message** that never disappears.
This violates the transient requirement.

**Issue 2: Progress Interferes with User Input**
- Progress outputs to stderr via `Console(stderr=True)` (line 42)
- User prompt uses `io.prompt()` on stdout
- Both write to same terminal causing visual interference
- No layout management to separate display regions
- Rich's `Status` API doesn't prevent overlap with concurrent output

## Implementation Plan

### Step 1: Fix Permanent Message Bug

**File:** `src/infrastructure/progress.py`

Replace `console.print()` with transient status updates:

```python
import time

def complete(self, message: str = "Complete") -> None:
    """Mark progress as complete and clean up display (transiently)."""
    if self._status:
        # Show completion in status (not print!)
        self._status.update(f"[green]✓ {message}[/green]")
        time.sleep(0.5)  # Display briefly
        self._status.stop()  # Then disappear completely
        self._status = None

def error(self, message: str) -> None:
    """Report an error and clean up display (transiently)."""
    if self._status:
        # Show error in status (not print!)
        self._status.update(f"[red]✗ Error: {message}[/red]")
        time.sleep(1.0)  # Show errors longer
        self._status.stop()  # Then disappear completely
        self._status = None
```

**Why this works:**
- Status updates are transient by nature
- `status.stop()` clears the entire status line
- No permanent messages left on screen
- Meets P0 requirement: "progress goes away shortly after complete"

### Step 2: Prevent Input Interference with Live Display

**Problem:** `Console.status()` can overlap with `io.prompt()` output.

**Solution:** Use `rich.live.Live` for dedicated non-scrolling display area.

**File:** `src/infrastructure/progress.py`

Add new `LiveProgressReporter` class:

```python
import time
from typing import Optional
from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text

class LiveProgressReporter:
    """
    Progress reporter using Rich Live display.

    Live display creates a dedicated area that updates in-place without
    scrolling or interfering with user input prompts.

    Implements ProgressReporterProtocol.
    """

    def __init__(self):
        """Initialize Live progress reporter."""
        self._live = None
        self._console = None

    def start(self, description: str, total: Optional[int] = None) -> None:
        """
        Start Live progress display.

        Args:
            description: Operation description
            total: Total items (unused for spinner display)
        """
        try:
            self._console = Console(stderr=True)
            renderable = Spinner("dots", text=Text(description, style="cyan"))

            # Live display updates in-place, doesn't scroll
            # transient=True makes it disappear when stopped
            self._live = Live(
                renderable,
                console=self._console,
                transient=True,
                refresh_per_second=10
            )
            self._live.start()

        except ImportError:
            self._live = None

    def update(self, current: Optional[int] = None, description: Optional[str] = None) -> None:
        """
        Update progress display.

        Args:
            current: Current count (unused)
            description: Updated description
        """
        if self._live and description:
            renderable = Spinner("dots", text=Text(description, style="cyan"))
            self._live.update(renderable)

    def complete(self, message: str = "Complete") -> None:
        """
        Show completion and hide.

        Args:
            message: Completion message
        """
        if self._live:
            # Show completion briefly
            self._live.update(Text(f"✓ {message}", style="green"))
            time.sleep(0.5)
            # Then disappear (transient=True)
            self._live.stop()
            self._live = None

    def error(self, message: str) -> None:
        """
        Show error and hide.

        Args:
            message: Error message
        """
        if self._live:
            # Show error longer
            self._live.update(Text(f"✗ Error: {message}", style="red"))
            time.sleep(1.0)
            # Then disappear
            self._live.stop()
            self._live = None
```

**Why Live is better:**
- Updates in-place without scrolling
- Doesn't interfere with concurrent stdout/stderr output
- Built-in `transient=True` support
- Thread-safe updates
- Better refresh control

### Step 3: Update CodebaseContext

**File:** `src/context/codebase_context.py:625-626`

```python
# OLD
from ..infrastructure.progress import RichProgressReporter, NullProgressReporter
progress = RichProgressReporter()

# NEW
from ..infrastructure.progress import LiveProgressReporter, NullProgressReporter
progress = LiveProgressReporter()
```

### Step 4: Update CLI Startup Progress

**File:** `src/cli/core.py:216-278`

Replace `_show_semantic_search_progress()` implementation:

```python
def _show_semantic_search_progress(self):
    """
    Display semantic search initialization progress with Rich Live.

    Uses Live display for non-interfering, transient progress updates.
    """
    import time

    # Check if initialization in progress
    status = self.orchestrator.context.get_semantic_initialization_status()
    if not status or self.orchestrator.context.is_semantic_search_ready():
        return

    try:
        from rich.console import Console
        from rich.live import Live
        from rich.spinner import Spinner
        from rich.text import Text

        console = Console(stderr=True)

        with Live(
            Spinner("dots", text=Text("Loading semantic search...", style="cyan")),
            console=console,
            transient=True,
            refresh_per_second=10
        ) as live:
            max_wait_seconds = 2.0
            start_time = time.time()

            while not self.orchestrator.context.is_semantic_search_ready():
                # Check timeout
                if time.time() - start_time > max_wait_seconds:
                    live.update(
                        Spinner("dots", text=Text(
                            "Semantic search loading in background...",
                            style="yellow"
                        ))
                    )
                    time.sleep(0.3)
                    break

                # Update status
                current_status = self.orchestrator.context.get_semantic_initialization_status()
                if current_status and current_status != "Not started":
                    live.update(
                        Spinner("dots", text=Text(current_status, style="cyan"))
                    )

                time.sleep(0.1)

            # Show completion if ready
            if self.orchestrator.context.is_semantic_search_ready():
                live.update(Text("✓ Semantic search ready", style="green"))
                time.sleep(0.3)
                # Disappears on context exit due to transient=True

    except ImportError:
        # Fallback for missing Rich
        if not self.orchestrator.context.is_semantic_search_ready():
            status = self.orchestrator.context.get_semantic_initialization_status()
            if status:
                self.io.secho(f"Semantic search: {status}", fg="cyan")
```

## Testing Plan

**Test 1: Progress Updates During Indexing**
```bash
# Start CLI, trigger semantic indexing
python -m scrappy
# Verify:
# - Progress spinner appears
# - Status text updates with batch numbers
# - Updates are smooth, no flickering
```

**Test 2: Progress Auto-Hide**
```bash
# After indexing completes
# Verify:
# - Completion message shows briefly (0.5s)
# - Progress disappears completely
# - No permanent messages left
# - Prompt is clean
```

**Test 3: No Input Interference**
```bash
# While indexing runs in background
# Verify:
# - Can type at prompt without visual corruption
# - Progress doesn't overwrite prompt
# - Progress stays in dedicated area
```

**Test 4: Error Handling**
```bash
# Trigger indexing error (e.g., corrupt file)
# Verify:
# - Error message shows in red
# - Displays for 1 second
# - Then disappears
# - Progress cleans up properly
```

## Success Criteria

- ✅ Progress updates visibly during operations (Live.update() works)
- ✅ Progress doesn't overlap user input (Live manages display area)
- ✅ Progress auto-hides 0.5s after completion (transient + sleep)
- ✅ No permanent messages left on screen (no console.print())
- ✅ Works with background thread initialization (Live is thread-safe)
- ✅ Degrades gracefully if Rich unavailable (ImportError fallback)

## Files to Modify

1. `src/infrastructure/progress.py`
   - Fix `RichProgressReporter.complete()` and `.error()` (remove console.print)
   - Add new `LiveProgressReporter` class

2. `src/context/codebase_context.py`
   - Line 625-626: Change to `LiveProgressReporter()`

3. `src/cli/core.py`
   - Lines 216-278: Rewrite `_show_semantic_search_progress()` to use Live

---

# P1
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