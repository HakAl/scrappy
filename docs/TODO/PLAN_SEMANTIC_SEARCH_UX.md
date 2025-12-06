# Semantic Search UX Implementation Plan

## Overview

Enable semantic search with a polished user experience. The status bar is always visible, showing semantic search state.
Progress is shown for significant indexing operations based on estimated chunk count, not file count.

---

## Current State Analysis

### What Exists

1. **Complete Backend Implementation**
   - `LanceDBSearchProvider` (`context/semantic/provider.py`) - hybrid vector + FTS search
   - `SemanticSearchManager` (`context/semantic_manager.py`) - lifecycle coordination (needs refactor)
   - `SemanticSearchInitializer` (`context/semantic/initializer.py`) - background model loading
   - `SemanticFileCollector` (`context/semantic/file_collector.py`) - git-aware file collection
   - `CompositeCodeChunker` - AST-aware code chunking

2. **Status Bar Infrastructure**
   - `StatusBar` widget with component registration
   - `ProgressIndicator` component (progress/total/message)
   - `IndexingProgress` message routing
   - `TextualProgressReporter` for status updates

3. **Integration Points (Commented Out)**
   - `OrchestratorFactory.create_codebase_context()` lines 228-242 - disabled
   - `enable_semantic_search` parameter exists but defaults to False

4. **Storage Location**
   - LanceDB lives at `.scrappy/lancedb`
   - Index state will be stored as LanceDB metadata table

### Current Problems

1. **Status bar shows numbers but progress doesn't move** - values not propagating correctly
2. **Timer remains at 0** - no elapsed time tracking
3. **Status bar hidden/shown causes layout jank** - should always be visible
4. **Shown every time on load** - no persistence tracking for "initial index done"
5. **No threshold for "small updates"** - always runs full indexing
6. **SemanticSearchManager is a god class** - 6+ responsibilities, needs refactor

---

## Design Decisions

### Always-Visible Status Bar

The status bar is always visible with semantic search state:
- **Idle:** `"Semantic: ready"` (or minimal indicator)
- **Loading model:** `"Loading model..."`
- **Indexing:** `"Indexing: 42/128 chunks (3.2s)"`
- **Error:** `"Semantic: unavailable"`

This eliminates layout jank from show/hide transitions.

### Estimated Chunk Count Threshold

File count is a poor metric (1 file could be 10K lines). Use estimated chunk count instead:

```python
def estimate_chunks(file_sizes: List[int], avg_chunk_size: int = 500) -> int:
    """Estimate chunks from file sizes without reading content."""
    return sum(max(1, size // avg_chunk_size) for size in file_sizes)
```

Thresholds based on chunks:
- **< 20 chunks:** Silent update (no progress bar)
- **20-100 chunks:** Show progress bar
- **> 100 chunks:** Show progress bar with ETA

### Index State in LanceDB

Store index metadata as a LanceDB table (`_index_meta`) rather than separate JSON file:
- Keeps all semantic search state in one place
- Atomic with index updates
- No split-brain between state file and actual index

### Reporter Injection Pattern

Control progress visibility via reporter injection, not visibility flags:

```python
# At startup decision point
if decision == IndexingDecision.INCREMENTAL_UPDATE:
    reporter = LoggingProgressReporter()  # Silent
else:
    reporter = StatusBarProgressReporter(status_bar)  # Visible

manager.index_files(collector, progress_reporter=reporter)
```

---

## Implementation Plan

### Phase 0: Refactor SemanticSearchManager

**Goal:** Reduce SemanticSearchManager to coordination only. Extract state and decision logic.

#### 0.1 Define Protocols

**File:** `src/scrappy/context/protocols.py`

```python
@dataclass
class IndexState:
    """Persisted index metadata."""
    last_indexed: datetime
    total_chunks: int
    total_files: int
    index_version: str
    file_hashes: Dict[str, str]  # path -> content_hash


@dataclass
class ChangeMetrics:
    """Metrics about what changed since last index."""
    new_files: int
    modified_files: int
    deleted_files: int
    estimated_chunks: int
    total_bytes_changed: int


class IndexingDecision(Enum):
    FULL_INDEX = "full"           # First time or major changes
    INCREMENTAL_UPDATE = "incremental"  # Small changes
    SKIP = "skip"                 # No changes detected


class IndexStateProtocol(Protocol):
    """Single responsibility: Persist and retrieve index state."""

    def load(self) -> Optional[IndexState]: ...
    def save(self, state: IndexState) -> None: ...
    def clear(self) -> None: ...


class IndexingDecisionProtocol(Protocol):
    """Single responsibility: Decide what indexing action to take."""

    def decide(
        self,
        saved_state: Optional[IndexState],
        current_metrics: ChangeMetrics,
    ) -> IndexingDecision: ...
```

#### 0.2 Implement IndexStateManager

**File:** `src/scrappy/context/semantic/state.py`

```python
class LanceDBIndexStateManager:
    """
    Stores index state in LanceDB metadata table.

    Single Responsibility: Persist and retrieve index state.
    """

    META_TABLE = "_index_meta"

    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._db = None

    def load(self) -> Optional[IndexState]:
        """Load state from LanceDB metadata table."""
        ...

    def save(self, state: IndexState) -> None:
        """Save state to LanceDB metadata table."""
        ...

    def clear(self) -> None:
        """Clear stored state."""
        ...
```

#### 0.3 Extend SemanticIndexConfig

**File:** `src/scrappy/context/semantic/config.py`

Add threshold settings to existing config (keeps all semantic config in one place):

```python
@dataclass
class SemanticIndexConfig:
    # ... existing fields ...

    # Chunk estimation (for progress decisions)
    avg_chunk_bytes: int = 400  # Derived from max_text_length, slightly under

    # Progress thresholds
    show_progress_chunks: int = 20      # Show progress bar if estimated chunks exceed this
    max_index_age_days: int = 7         # Force full re-index if older than this
    reindex_chunk_change_percent: float = 0.25  # Force re-index if chunks change by this %
```

#### 0.4 Implement IndexingDecisionMaker

**File:** `src/scrappy/context/semantic/decision.py`

```python
class ThresholdDecisionMaker:
    """
    Decides indexing action based on configurable thresholds.

    Single Responsibility: Make indexing decisions.
    Uses SemanticIndexConfig for all threshold values.
    """

    def __init__(self, config: Optional[SemanticIndexConfig] = None):
        self._config = config or SemanticIndexConfig()

    def decide(
        self,
        saved_state: Optional[IndexState],
        current_metrics: ChangeMetrics,
    ) -> IndexingDecision:
        """
        Determine what indexing action to take.

        Returns FULL_INDEX if:
        - No previous index exists
        - Index is older than config.max_index_age_days
        - Chunk count changed by > config.reindex_chunk_change_percent

        Returns INCREMENTAL_UPDATE if:
        - Index exists and is recent
        - estimated_chunks > 0

        Returns SKIP if:
        - Index exists and no changes detected
        """
        ...

    def should_show_progress(self, metrics: ChangeMetrics) -> bool:
        """Whether to show progress UI for this operation."""
        return metrics.estimated_chunks >= self._config.show_progress_chunks
```

#### 0.5 Refactor SemanticSearchManager

**File:** `src/scrappy/context/semantic_manager.py`

Reduce to coordination only. Inject config for shared configuration:

```python
class SemanticSearchManager:
    """
    Coordinates semantic search lifecycle.

    Single Responsibility: Coordinate initialization, indexing, and search.
    Delegates state management and decision logic to injected dependencies.
    """

    def __init__(
        self,
        project_path: Path,
        config: Optional[SemanticIndexConfig] = None,
        initializer: Optional[BackgroundInitializerProtocol] = None,
        state_manager: Optional[IndexStateProtocol] = None,
        decision_maker: Optional[IndexingDecisionProtocol] = None,
        event_queue: Optional[EventQueueProtocol] = None,
    ):
        self._project_path = project_path
        self._config = config or SemanticIndexConfig()
        self._state_manager = state_manager  # Injected
        self._decision_maker = decision_maker  # Injected
        # ... rest of init
```

#### 0.6 Tests for Phase 0

- `test_index_state_manager.py` - state persistence round-trip
- `test_decision_maker.py` - decision logic for all scenarios
- `test_semantic_manager_refactored.py` - coordination with mocked dependencies

---

### Phase 1: Fix Status Bar Display

**Goal:** Status bar always visible, shows correct progress with elapsed time.

#### 1.1 Always-Visible Status Bar

**File:** `src/scrappy/cli/textual_app.py`

- Remove hide/show logic from StatusBar
- StatusBar always renders, shows current state
- Add semantic search state component:

```python
class SemanticStatusComponent:
    """Shows semantic search state in status bar."""

    def __init__(self):
        self._state = "initializing"
        self._progress = None
        self._elapsed = None

    def set_state(self, state: str) -> None:
        """Set state: 'ready', 'indexing', 'error'."""
        self._state = state

    def set_progress(self, current: int, total: int, elapsed: float) -> None:
        """Update indexing progress."""
        self._progress = (current, total)
        self._elapsed = elapsed

    def render(self) -> str:
        if self._state == "ready":
            return "Semantic: ready"
        elif self._state == "indexing" and self._progress:
            current, total = self._progress
            return f"Indexing: {current}/{total} ({self._elapsed:.1f}s)"
        elif self._state == "error":
            return "Semantic: unavailable"
        return "Semantic: loading..."
```

#### 1.2 Fix Progress Value Propagation

**File:** `src/scrappy/cli/textual_app.py`

- Ensure `ProgressBar.progress` receives correct 0.0-1.0 value
- Call widget refresh after updates

#### 1.3 Add Elapsed Time Tracking

**File:** `src/scrappy/cli/textual_app.py`

```python
class ProgressIndicator:
    def __init__(self):
        self._start_time: Optional[float] = None
        # ...

    def start(self, message: str, total: int = 0) -> None:
        self._start_time = time.time()
        # ...

    def get_elapsed(self) -> float:
        if self._start_time is None:
            return 0.0
        return time.time() - self._start_time
```

---

### Phase 2: Index State and Decision Logic

**Goal:** Persist index state, make smart decisions about when to re-index.

#### 2.1 Implement ChangeMetrics Calculator

**File:** `src/scrappy/context/semantic/metrics.py`

```python
class ChangeMetricsCalculator:
    """
    Calculates what changed since last index.

    Single Responsibility: Compute change metrics.
    Uses SemanticIndexConfig.avg_chunk_bytes for estimation.
    """

    def __init__(self, config: Optional[SemanticIndexConfig] = None):
        self._config = config or SemanticIndexConfig()

    def calculate(
        self,
        saved_state: Optional[IndexState],
        current_files: Dict[str, int],  # path -> size
        current_hashes: Dict[str, str],  # path -> hash
    ) -> ChangeMetrics:
        """
        Calculate change metrics by comparing current state to saved state.
        """
        if saved_state is None:
            # First run - everything is new
            total_size = sum(current_files.values())
            return ChangeMetrics(
                new_files=len(current_files),
                modified_files=0,
                deleted_files=0,
                estimated_chunks=self._estimate_chunks(total_size),
                total_bytes_changed=total_size,
            )

        # Compare hashes to find changes
        new_files = set(current_hashes.keys()) - set(saved_state.file_hashes.keys())
        deleted_files = set(saved_state.file_hashes.keys()) - set(current_hashes.keys())

        modified_files = set()
        for path, hash in current_hashes.items():
            if path in saved_state.file_hashes:
                if saved_state.file_hashes[path] != hash:
                    modified_files.add(path)

        # Estimate chunks from changed file sizes
        changed_size = sum(
            current_files.get(p, 0)
            for p in (new_files | modified_files)
        )

        return ChangeMetrics(
            new_files=len(new_files),
            modified_files=len(modified_files),
            deleted_files=len(deleted_files),
            estimated_chunks=self._estimate_chunks(changed_size),
            total_bytes_changed=changed_size,
        )

    def _estimate_chunks(self, total_bytes: int) -> int:
        if total_bytes <= 0:
            return 0
        return max(1, total_bytes // self._config.avg_chunk_bytes)
```

#### 2.2 Wire Up State Persistence

**File:** `src/scrappy/context/semantic/provider.py`

Add methods to save/load state after indexing:

```python
def save_index_state(self, state_manager: IndexStateProtocol) -> None:
    """Save current index state after successful indexing."""
    ...

def get_current_stats(self) -> Tuple[int, int]:
    """Return (total_chunks, total_files) from current index."""
    ...
```

---

### Phase 3: Reporter Injection for Progress Control

**Goal:** Control progress visibility via injected reporters, not flags.

#### 3.1 Define Reporter Variants

**File:** `src/scrappy/infrastructure/progress.py`

```python
class LoggingProgressReporter(ProgressReporterProtocol):
    """Logs progress but doesn't update UI. For silent operations."""

    def update(self, current: int = 0, total: int = 0, description: str = "") -> None:
        logger.debug(f"Progress: {description} ({current}/{total})")

    def complete(self, message: str = "") -> None:
        logger.debug(f"Complete: {message}")


class StatusBarProgressReporter(ProgressReporterProtocol):
    """Updates status bar with progress. For visible operations."""

    def __init__(self, callback: Callable[[str, int, int], None]):
        self._callback = callback

    def update(self, current: int = 0, total: int = 0, description: str = "") -> None:
        self._callback(description, current, total)
```

#### 3.2 Update SemanticSearchManager

**File:** `src/scrappy/context/semantic_manager.py`

Accept reporter as parameter:

```python
def index_files(
    self,
    file_collector: FileCollectorProtocol,
    progress_reporter: Optional[ProgressReporterProtocol] = None,
) -> None:
    """
    Index files for semantic search.

    Args:
        file_collector: Collector providing files to index
        progress_reporter: Reporter for progress updates (silent if None)
    """
    reporter = progress_reporter or NullProgressReporter()
    # Use reporter throughout indexing
```

---

### Phase 4: Enable Integration

**Goal:** Turn on semantic search with proper dependency injection.

#### 4.1 Update OrchestratorFactory

**File:** `src/scrappy/orchestrator/factory.py`

```python
def create_codebase_context(self) -> ContextProvider:
    context = CodebaseContext(self.project_path)

    if self.enable_semantic_search:
        # Create dependencies
        state_manager = LanceDBIndexStateManager(self._get_lancedb_path())
        decision_maker = ThresholdDecisionMaker()
        metrics_calc = ChangeMetricsCalculator()

        # Load state and calculate metrics
        saved_state = state_manager.load()
        current_metrics = metrics_calc.calculate(saved_state, ...)

        # Decide what to do
        decision = decision_maker.decide(saved_state, current_metrics)

        if decision != IndexingDecision.SKIP:
            # Choose reporter based on estimated work
            if decision_maker.should_show_progress(current_metrics):
                reporter = self._create_status_bar_reporter()
            else:
                reporter = LoggingProgressReporter()

            context.start_background_initialization(progress_reporter=reporter)

    return context
```

#### 4.2 Enable by Default

**File:** `src/scrappy/orchestrator/factory.py`

```python
enable_semantic_search: bool = True  # Changed from False
```

#### 4.3 Verify Dependencies

Ensure `lancedb` and `fastembed` are in main dependencies, not optional extras.

---

### Phase 5: Periodic Re-indexing (Optional)

**Goal:** Keep index fresh during long sessions.

#### 5.1 File Change Detection

**File:** `src/scrappy/context/semantic/file_collector.py`

```python
def get_changed_files(
    self,
    since_hashes: Dict[str, str],
) -> Tuple[List[str], List[str], List[str]]:
    """
    Return (new_files, modified_files, deleted_files).

    Compares current filesystem state against provided hashes.
    """
```

#### 5.2 Background Update Timer

**File:** `src/scrappy/context/semantic_manager.py`

```python
def schedule_periodic_update(self, interval_minutes: int = 30) -> None:
    """Schedule periodic index updates for long-running sessions."""
```

Lower priority - most sessions won't need this.

---

## Implementation Order

1. **Phase 0** (Refactor) - Extract state and decision logic
   - 0.1 Define protocols
   - 0.2 Implement IndexStateManager
   - 0.3 Extend SemanticIndexConfig with threshold settings
   - 0.4 Implement ThresholdDecisionMaker
   - 0.5 Refactor SemanticSearchManager
   - 0.6 Tests

2. **Phase 1** (Status Bar) - Always visible with correct progress
   - 1.1 Always-visible status bar
   - 1.2 Fix progress propagation
   - 1.3 Elapsed time tracking

3. **Phase 2** (State & Metrics) - Smart change detection
   - 2.1 ChangeMetricsCalculator
   - 2.2 Wire up state persistence

4. **Phase 3** (Reporter Injection) - Control visibility via DI
   - 3.1 Reporter variants
   - 3.2 Update SemanticSearchManager

5. **Phase 4** (Enable) - Turn it on
   - 4.1 Update factory with DI
   - 4.2 Enable by default
   - 4.3 Verify dependencies

6. **Phase 5** (Periodic) - Optional
   - 5.1 Change detection
   - 5.2 Background timer

---

## Testing Strategy

### Unit Tests

- `test_index_state_manager.py` - LanceDB state persistence
- `test_decision_maker.py` - all decision scenarios
- `test_change_metrics.py` - metric calculations
- `test_progress_reporters.py` - reporter behavior

### Integration Tests

- Full index flow with mocked dependencies
- State persistence round-trip
- Decision + indexing integration

### Manual Testing Scenarios

1. First launch on new project - shows progress bar
2. Second launch same project - silent or skip
3. Add large file, relaunch - shows progress
4. Add tiny file, relaunch - silent
5. Status bar always visible, no layout jank

---

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `context/protocols.py` | Modify | Add IndexState, ChangeMetrics, protocols |
| `context/semantic/state.py` | Create | LanceDBIndexStateManager |
| `context/semantic/decision.py` | Create | ThresholdDecisionMaker, IndexingThresholds |
| `context/semantic/metrics.py` | Create | ChangeMetricsCalculator |
| `context/semantic_manager.py` | Modify | Refactor to use injected dependencies |
| `infrastructure/progress.py` | Modify | Add LoggingProgressReporter, StatusBarProgressReporter |
| `cli/textual_app.py` | Modify | Always-visible status bar, SemanticStatusComponent |
| `orchestrator/factory.py` | Modify | Wire up DI, enable by default |

---

## Out of Scope

- Semantic search tool for agents (separate task)
- Search results UI/display
- User configuration of thresholds
- Index repair/rebuild commands
- Tool graceful degradation when index not ready (tool implementation concern)
