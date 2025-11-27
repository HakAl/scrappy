This is a classic case of **Feature Envy** and **Scope Creep**. Your `CodebaseContext` started as a coordination layer (a Facade), but the semantic search integration forced it to understand *how* to initialize models, *how* to batch files for indexing, and *how* to manage background threads.

Here is the architectural fix: **Extract the Semantic Search Lifecycle to a dedicated manager.**

`CodebaseContext` should remain a **Facade**. It should ask for a search result, but it shouldn't know about batch sizes, loading states, or progress bars.

Here is the suggested refactoring plan:

### 1. The Plan: "Extract Class" Refactoring
We will move approximately 150 lines of code (initialization, indexing loop, progress reporting) into a new class: `SemanticSearchManager`.

### 2. The New Component (`semantic_manager.py`)
This class takes ownership of the complex state machine you built (Init -> Wait -> Index -> Ready).

```python
# codebase/context/semantic_manager.py
import logging
from typing import Optional, Callable
from ..infrastructure.protocols import BackgroundInitializerProtocol

logger = logging.getLogger(__name__)

class SemanticSearchManager:
    """
    Encapsulates the lifecycle, loading, and indexing logic for Semantic Search.
    """
    def __init__(
        self, 
        initializer: Optional[BackgroundInitializerProtocol],
        file_collector
    ):
        self._initializer = initializer
        self._file_collector = file_collector
        self._search_provider = None
        self._progress_callback: Optional[Callable[[str], None]] = None
        
        # Hook up the callback immediately if initializer exists
        if self._initializer:
            self._initializer.wait_with_callback(self._on_ready)

    def start(self):
        """Non-blocking start."""
        if self._initializer:
            self._initializer.start()

    def set_progress_callback(self, callback):
        self._progress_callback = callback

    def is_ready(self) -> bool:
        return self._search_provider is not None

    def search(self, query: str, max_tokens: int):
        """Delegates to provider if ready, returns None if not."""
        if not self.is_ready():
            return None
        return self._search_provider.search(query, max_tokens=max_tokens)

    def _on_ready(self, success: bool, result, error) -> None:
        if success and result:
            self._search_provider = result
            self._trigger_indexing()
        elif error:
            logger.error(f"Semantic search failed to load: {error}")

    def _trigger_indexing(self):
        """
        The complex batching logic from your original class goes here.
        """
        if not self._file_collector or not self._search_provider:
            return

        try:
            self._notify("Starting batched indexing...")
            # ... [Insert the 50 lines of batching/indexing logic here] ...
            self._notify("Indexing complete.")
        except Exception as e:
            logger.error(f"Indexing failed: {e}")
            self._search_provider = None # Fail safe

    def _notify(self, msg: str):
        if self._progress_callback:
            self._progress_callback(msg)
```

### 3. The Cleaned `CodebaseContext`
Now `CodebaseContext` returns to being a high-level coordinator. It aggregates results from `FileScanner`, `GitReader`, and now `SemanticManager`.

```python
# codebase/context/codebase_context.py

# ... imports ...
from .semantic_manager import SemanticSearchManager

class CodebaseContext:
    def __init__(
        self,
        project_path: Optional[str] = None,
        # ... other dependencies ...
        semantic_manager: Optional[SemanticSearchManager] = None, 
    ):
        self.project_path = Path(project_path or ".").resolve()
        
        # Dependency Injection or Default Factory
        self.semantic = semantic_manager or self._create_semantic_manager()
        
        # ... standard init ...

    def start_background_initialization(self):
        """Delegate to manager."""
        self.semantic.start()

    def get_relevant_context(self, query: str, max_tokens: int = 4000) -> str:
        """
        Much cleaner: Try semantic, fallback to keyword.
        """
        if not self.is_explored():
            return ""

        # 1. Try Semantic (Delegated)
        search_result = self.semantic.search(query, max_tokens)
        if search_result and search_result.chunks:
            return self._format_search_result(search_result)

        # 2. Fallback to Keyword (Local logic)
        logger.debug("Falling back to keyword-based context")
        return self._get_keyword_context(query)

    def _create_semantic_manager(self) -> SemanticSearchManager:
        # Factory logic to wire up the sub-dependencies
        initializer = self._create_default_semantic_initializer()
        collector = self._create_default_file_collector()
        return SemanticSearchManager(initializer, collector)

    # ... The rest of the class is just Prompt Formatting & caching ...
```

### 4. Further Refactoring Suggestions

If the class is still too big after extracting the Semantic Manager, apply the **Strategy Pattern** to the remaining logic:

#### A. Extract Prompt Formatting
The `augment_prompt`, `generate_summary`, and `_format_search_result` methods are purely string manipulation. They don't need to live on the object that holds the Git history or File Index.

Create a `ContextFormatter`:
```python
class ContextFormatter:
    def format_context(self, context_data: dict, query: str) -> str:
        # Logic to combine structure, git, and semantic results
        pass

    def format_summary(self, structure: dict, git_info: dict) -> str:
        # Logic to build the summary prompt
        pass
```

#### B. Flatten the Factory Methods
You have 7 generic `_create_default_X` methods. This is arguably unnecessary noise in the main class.
*   **Suggestion:** Move these into a standalone `ContextFactory` or `ContextBuilder` class.
*   **Usage:** `context = ContextBuilder.for_path("./my_project").with_defaults().build()`

### Summary of Benefits

1.  **Encapsulation:** The `CodebaseContext` no longer needs to import `RichProgressReporter` or know what a "batch size" is.
2.  **Testability:** You can now test `SemanticSearchManager` in isolation (mocking the file collector and initializer) without creating a full Project structure.
3.  **Readability:** The `CodebaseContext` becomes a readable API surface again: "Initialize -> Explore -> Get Context".