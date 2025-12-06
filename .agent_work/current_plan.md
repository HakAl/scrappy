# Semantic Search UX - Aggressive Integration Plan

**Status**: PRERELEASE - Clean Breaks Over Shims
**Approach**: Backend COMPLETE - This is an ACTIVATION task with refactoring

---

## Pre-Implementation Checklist

- [ ] Run existing tests: `python -m pytest tests/context/ -v`
- [ ] Verify dependencies in pyproject.toml (lancedb, fastembed, fasteners)

---

## Step 1: Define Index State Protocols

**File**: `src/scrappy/context/protocols.py`

**Action**: ADD these definitions after line 515 (after RankingConfig):

```python
from enum import Enum

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
    FULL_INDEX = "full"
    INCREMENTAL_UPDATE = "incremental"
    SKIP = "skip"


@runtime_checkable
class IndexStateProtocol(Protocol):
    """Single responsibility: Persist and retrieve index state."""

    def load(self) -> Optional[IndexState]: ...
    def save(self, state: IndexState) -> None: ...
    def clear(self) -> None: ...


@runtime_checkable
class IndexingDecisionProtocol(Protocol):
    """Single responsibility: Decide what indexing action to take."""

    def decide(
        self,
        saved_state: Optional[IndexState],
        current_metrics: ChangeMetrics,
    ) -> IndexingDecision: ...

    def should_show_progress(self, metrics: ChangeMetrics) -> bool: ...
```

---

## Step 2: Extend SemanticIndexConfig with Thresholds

**File**: `src/scrappy/context/semantic/config.py`

**Action**: ADD threshold fields to SemanticIndexConfig dataclass (after line 45):

```python
    # Chunk estimation (for progress decisions)
    avg_chunk_bytes: int = 400

    # Progress thresholds
    show_progress_chunks: int = 20
    max_index_age_days: int = 7
    reindex_chunk_change_percent: float = 0.25
```

---

## Step 3: Create LanceDBIndexStateManager

**File**: `src/scrappy/context/semantic/state.py` (CREATE NEW)

**Action**: CREATE this file:

```python
"""
Index state persistence using LanceDB metadata table.

Single Responsibility: Persist and retrieve index state.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from ..protocols import IndexState

logger = logging.getLogger(__name__)


class LanceDBIndexStateManager:
    """
    Stores index state in LanceDB metadata table.

    Uses a dedicated table (_index_meta) to store state atomically
    with the index, preventing split-brain issues.
    """

    META_TABLE = "_index_meta"

    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._db = None

    def _get_db(self):
        """Lazy load LanceDB connection."""
        if self._db is None:
            import lancedb
            self._db = lancedb.connect(str(self._db_path))
        return self._db

    def load(self) -> Optional[IndexState]:
        """Load state from LanceDB metadata table."""
        try:
            db = self._get_db()
            if self.META_TABLE not in db.table_names():
                return None

            table = db.open_table(self.META_TABLE)
            rows = table.to_pandas()
            if rows.empty:
                return None

            row = rows.iloc[0]
            return IndexState(
                last_indexed=datetime.fromisoformat(row["last_indexed"]),
                total_chunks=int(row["total_chunks"]),
                total_files=int(row["total_files"]),
                index_version=str(row["index_version"]),
                file_hashes=eval(row["file_hashes"]) if row["file_hashes"] else {},
            )
        except Exception as e:
            logger.warning(f"Failed to load index state: {e}")
            return None

    def save(self, state: IndexState) -> None:
        """Save state to LanceDB metadata table."""
        try:
            db = self._get_db()

            data = [{
                "last_indexed": state.last_indexed.isoformat(),
                "total_chunks": state.total_chunks,
                "total_files": state.total_files,
                "index_version": state.index_version,
                "file_hashes": repr(state.file_hashes),
            }]

            if self.META_TABLE in db.table_names():
                db.drop_table(self.META_TABLE)

            db.create_table(self.META_TABLE, data)
            logger.debug(f"Saved index state: {state.total_files} files, {state.total_chunks} chunks")
        except Exception as e:
            logger.warning(f"Failed to save index state: {e}")

    def clear(self) -> None:
        """Clear stored state."""
        try:
            db = self._get_db()
            if self.META_TABLE in db.table_names():
                db.drop_table(self.META_TABLE)
        except Exception as e:
            logger.warning(f"Failed to clear index state: {e}")


class NullIndexStateManager:
    """No-op state manager for testing."""

    def load(self) -> None:
        return None

    def save(self, state: IndexState) -> None:
        pass

    def clear(self) -> None:
        pass
```

---

## Step 4: Create ThresholdDecisionMaker

**File**: `src/scrappy/context/semantic/decision.py` (CREATE NEW)

**Action**: CREATE this file:

```python
"""
Indexing decision logic based on configurable thresholds.

Single Responsibility: Decide what indexing action to take.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from ..protocols import IndexState, ChangeMetrics, IndexingDecision
from .config import SemanticIndexConfig

logger = logging.getLogger(__name__)


class ThresholdDecisionMaker:
    """
    Decides indexing action based on configurable thresholds.

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
        if saved_state is None:
            logger.info("No previous index - full index required")
            return IndexingDecision.FULL_INDEX

        # Check age
        age = datetime.now() - saved_state.last_indexed
        max_age = timedelta(days=self._config.max_index_age_days)
        if age > max_age:
            logger.info(f"Index is {age.days} days old - full re-index required")
            return IndexingDecision.FULL_INDEX

        # Check change percentage
        if saved_state.total_chunks > 0:
            change_ratio = current_metrics.estimated_chunks / saved_state.total_chunks
            if change_ratio > self._config.reindex_chunk_change_percent:
                logger.info(f"Chunk change ratio {change_ratio:.2f} exceeds threshold - full re-index")
                return IndexingDecision.FULL_INDEX

        # Check if any changes
        total_changes = (
            current_metrics.new_files +
            current_metrics.modified_files +
            current_metrics.deleted_files
        )
        if total_changes == 0:
            logger.debug("No changes detected - skipping indexing")
            return IndexingDecision.SKIP

        logger.info(f"Incremental update: {total_changes} files changed")
        return IndexingDecision.INCREMENTAL_UPDATE

    def should_show_progress(self, metrics: ChangeMetrics) -> bool:
        """Whether to show progress UI for this operation."""
        return metrics.estimated_chunks >= self._config.show_progress_chunks


class NullDecisionMaker:
    """Always returns FULL_INDEX for testing."""

    def decide(
        self,
        saved_state: Optional[IndexState],
        current_metrics: ChangeMetrics,
    ) -> IndexingDecision:
        return IndexingDecision.FULL_INDEX

    def should_show_progress(self, metrics: ChangeMetrics) -> bool:
        return True
```

---

## Step 5: Create ChangeMetricsCalculator

**File**: `src/scrappy/context/semantic/metrics.py` (CREATE NEW)

**Action**: CREATE this file:

```python
"""
Change metrics calculation for indexing decisions.

Single Responsibility: Compute change metrics from file state.
"""

import logging
from typing import Optional, Dict

from ..protocols import IndexState, ChangeMetrics
from .config import SemanticIndexConfig

logger = logging.getLogger(__name__)


class ChangeMetricsCalculator:
    """
    Calculates what changed since last index.

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
            total_size = sum(current_files.values())
            return ChangeMetrics(
                new_files=len(current_files),
                modified_files=0,
                deleted_files=0,
                estimated_chunks=self._estimate_chunks(total_size),
                total_bytes_changed=total_size,
            )

        current_paths = set(current_hashes.keys())
        saved_paths = set(saved_state.file_hashes.keys())

        new_files = current_paths - saved_paths
        deleted_files = saved_paths - current_paths

        modified_files = set()
        for path in current_paths & saved_paths:
            if current_hashes[path] != saved_state.file_hashes.get(path):
                modified_files.add(path)

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

---

## Step 6: Add StatusBarProgressReporter

**File**: `src/scrappy/infrastructure/progress.py`

**Action**: ADD after LoggingProgressReporter class (around line 250):

```python
class StatusBarProgressReporter:
    """
    Updates status bar with progress. For visible operations.

    Uses callback pattern for TUI integration.
    """

    def __init__(self, callback: Callable[[str, int, int], None]):
        """
        Args:
            callback: Function taking (description, current, total)
        """
        self._callback = callback
        self._start_time: Optional[float] = None

    def start(self, description: str, total: Optional[int] = None) -> None:
        self._start_time = time.time()
        self._callback(description, 0, total or 0)

    def update(self, current: Optional[int] = None, description: Optional[str] = None) -> None:
        if self._callback:
            self._callback(description or "", current or 0, 0)

    def complete(self, message: str = "Complete") -> None:
        if self._callback:
            self._callback(message, 0, 0)

    def error(self, message: str) -> None:
        if self._callback:
            self._callback(f"Error: {message}", 0, 0)

    def get_elapsed(self) -> float:
        if self._start_time is None:
            return 0.0
        return time.time() - self._start_time
```

---

## Step 7: Fix ProgressIndicator Elapsed Time

**File**: `src/scrappy/cli/textual_app.py`

**Action**: MODIFY ProgressIndicator class (lines 189-237):

```python
class ProgressIndicator:
    """Shows indexing/processing progress in the status bar."""

    def __init__(self) -> None:
        self._progress: int = 0
        self._total: int = 0
        self._message: str = ""
        self._active: bool = False
        self._start_time: Optional[float] = None  # ADD THIS
        self._widget: Optional[Horizontal] = None
        self._label: Optional[Label] = None
        self._bar: Optional[ProgressBar] = None

    # ... existing properties ...

    def start(self, message: str, total: int = 0) -> None:  # ADD THIS METHOD
        """Start progress tracking."""
        self._start_time = time.time()
        self._message = message
        self._total = total
        self._progress = 0
        self._active = True
        self.update_widget()

    def get_elapsed(self) -> float:  # ADD THIS METHOD
        """Get elapsed time in seconds."""
        if self._start_time is None:
            return 0.0
        return time.time() - self._start_time

    def update(self, progress: int, total: int, message: str) -> None:
        self._progress = progress
        self._total = total
        self._message = message
        self._active = True
        if self._start_time is None:  # ADD THIS
            self._start_time = time.time()
        self.update_widget()
```

Also ADD at top of file: `import time`

---

## Step 8: Refactor SemanticSearchManager - Inject Dependencies

**File**: `src/scrappy/context/semantic_manager.py`

**Action**: MODIFY __init__ to accept new dependencies (lines 57-84):

```python
def __init__(
    self,
    project_path: Path,
    initializer: Optional[BackgroundInitializerProtocol] = None,
    event_queue: Optional[EventQueueProtocol] = None,
    io: Optional['CLIIOProtocol'] = None,
    config: Optional['SemanticIndexConfig'] = None,  # ADD
    state_manager: Optional['IndexStateProtocol'] = None,  # ADD
    decision_maker: Optional['IndexingDecisionProtocol'] = None,  # ADD
):
    # ... existing code ...
    self._config = config  # ADD
    self._state_manager = state_manager  # ADD
    self._decision_maker = decision_maker  # ADD
```

**Action**: ADD import at top:

```python
from .semantic.config import SemanticIndexConfig
from .protocols import IndexStateProtocol, IndexingDecisionProtocol
```

---

## Step 9: DELETE Commented Code Block in Factory

**File**: `src/scrappy/orchestrator/factory.py`

**Action**: DELETE lines 228-242 (the TODO-wrapped commented code):

```python
        # TODO:
        # TODO:
        # TODO:  initialize semantic search
        # if self.enable_semantic_search:
        #     try:
        #         from ..context.semantic.initializer import SemanticSearchInitializer
        #         initializer = SemanticSearchInitializer(context.project_path)
        #         context._semantic_initializer = initializer
        #         context.start_background_initialization()
        #     except ImportError:
        #         # Semantic search dependencies not available
        #         pass
        # TODO:
        # TODO:
        # TODO:
```

---

## Step 10: Implement Semantic Search Integration in Factory

**File**: `src/scrappy/orchestrator/factory.py`

**Action**: REPLACE deleted code with proper DI wiring in `create_codebase_context()`:

```python
def create_codebase_context(self) -> ContextProvider:
    """Create default codebase context."""
    context = CodebaseContext(self.project_path)

    if self.enable_semantic_search:
        self._setup_semantic_search(context)

    return context

def _setup_semantic_search(self, context: 'CodebaseContext') -> None:
    """Wire up semantic search with proper DI."""
    try:
        from ..context.semantic.state import LanceDBIndexStateManager
        from ..context.semantic.decision import ThresholdDecisionMaker
        from ..context.semantic.metrics import ChangeMetricsCalculator
        from ..context.semantic.config import SemanticIndexConfig
        from ..context.semantic_manager import SemanticSearchManager
        from ..context.semantic.initializer import SemanticSearchInitializer

        config = SemanticIndexConfig.from_memory_adaptive()
        db_path = self.project_path / config.db_dir_name

        state_manager = LanceDBIndexStateManager(db_path)
        decision_maker = ThresholdDecisionMaker(config)

        manager = SemanticSearchManager(
            project_path=self.project_path,
            config=config,
            state_manager=state_manager,
            decision_maker=decision_maker,
        )

        context._semantic_manager = manager
        manager.start_background_init()

    except ImportError as e:
        logger.debug(f"Semantic search dependencies not available: {e}")
```

**Action**: ADD import at top:

```python
import logging
logger = logging.getLogger(__name__)
```

---

## Step 11: Enable Semantic Search by Default

**File**: `src/scrappy/orchestrator/factory.py`

**Action**: CHANGE line 103:

FROM: `enable_semantic_search: bool = False,`
TO: `enable_semantic_search: bool = True,`

---

## Step 12: Update Callers - Commands Stay Disabled

**File**: `src/scrappy/cli/commands.py`

**Action**: NO CHANGES NEEDED - one-off commands correctly have `enable_semantic_search=False`

---

## Step 13: Write Tests for New Components

**File**: `tests/context/test_index_state_manager.py` (CREATE NEW)

Test round-trip persistence of IndexState.

**File**: `tests/context/test_decision_maker.py` (CREATE NEW)

Test decision logic for all scenarios:
- No previous state -> FULL_INDEX
- Old index -> FULL_INDEX
- High change ratio -> FULL_INDEX
- Small changes -> INCREMENTAL_UPDATE
- No changes -> SKIP

**File**: `tests/context/test_change_metrics.py` (CREATE NEW)

Test metrics calculation:
- First run (no saved state)
- With saved state and changes
- With no changes

---

## Step 14: Verify Integration

**Action**: Run full test suite:

```bash
python -m pytest tests/ -v
```

**Action**: Manual test:

1. Launch CLI on project without prior index
2. Verify status shows "Indexing: X/Y chunks"
3. Exit and relaunch
4. Verify silent startup (index exists, no changes)
5. Modify a file, relaunch
6. Verify incremental update behavior

---

## Files Summary

| File | Action | Description |
|------|--------|-------------|
| `context/protocols.py` | MODIFY | Add IndexState, ChangeMetrics, IndexingDecision, protocols |
| `context/semantic/config.py` | MODIFY | Add threshold fields |
| `context/semantic/state.py` | CREATE | LanceDBIndexStateManager |
| `context/semantic/decision.py` | CREATE | ThresholdDecisionMaker |
| `context/semantic/metrics.py` | CREATE | ChangeMetricsCalculator |
| `infrastructure/progress.py` | MODIFY | Add StatusBarProgressReporter |
| `cli/textual_app.py` | MODIFY | Fix ProgressIndicator elapsed time |
| `context/semantic_manager.py` | MODIFY | Accept injected dependencies |
| `orchestrator/factory.py` | MODIFY | DELETE commented code, ADD proper DI wiring, CHANGE default to True |
| `tests/context/test_index_state_manager.py` | CREATE | State persistence tests |
| `tests/context/test_decision_maker.py` | CREATE | Decision logic tests |
| `tests/context/test_change_metrics.py` | CREATE | Metrics calculation tests |

---

## Code to DELETE (No Deprecation)

1. **factory.py:228-242** - Commented TODO block (replaced with proper implementation)

---

## Callers to UPDATE (No Adapters)

1. **factory.py** - `create_codebase_context()` now calls `_setup_semantic_search()`
2. **semantic_manager.py** - `__init__` accepts new optional parameters (backward compatible)

---

## Out of Scope (Per Plan)

- Semantic search tool for agents (separate task)
- Search results UI/display
- User configuration of thresholds
- Index repair/rebuild commands
- Periodic re-indexing (Phase 5 - optional)

#EOF
