

# Async Threading Solution for Loading Heavy Model


## Current Analysis

`SemanticSearchInitializer` is designed to handle background initialization,
but there might be some issues with how it's integrated with the `LanceDBSearchProvider`.
The key is to ensure the embedding model loads in the background thread during initialization,
not when first using the search functionality.

## Solution

```python
# In your main application code or wherever you initialize the semantic search

import threading
from pathlib import Path
from context.semantic.initializer import SemanticSearchInitializer

# Create the initializer
semantic_initializer = SemanticSearchInitializer(project_path=Path("."))

# Start the background initialization (non-blocking)
semantic_initializer.start()

# You can check the status later
def check_semantic_search_status():
    if semantic_initializer.is_complete():
        search_provider = semantic_initializer.get_result()
        if search_provider:
            print("Semantic search is ready!")
            # Now you can use search_provider.index_files() or search_provider.search()
        else:
            error = semantic_initializer.get_error()
            print(f"Semantic search initialization failed: {error}")
    else:
        status = semantic_initializer.get_status()
        print(f"Semantic search status: {status}")
        # Check again later

# You could use a timer to periodically check the status
threading.Timer(5.0, check_semantic_search_status).start()
```


### 1. Update `SemanticSearchInitializer._initialize_semantic_search()`

```python
def _initialize_semantic_search(self) -> None:
    """
    Internal method to initialize semantic search in background thread.

    This is the actual heavy lifting that happens in the background.
    """
    try:
        logger.debug("Starting semantic search initialization in background")

        # Import heavy dependencies here (in background thread)
        from ..code_chunker import SemanticCodeChunker
        from .provider import LanceDBSearchProvider

        with self._lock:
            self._status = "Loading embedding model..."

        # Create chunker (lightweight)
        chunker = SemanticCodeChunker(chunk_size=100, overlap=3)

        # Create LanceDB provider (triggers FastEmbed model download if needed)
        with self._lock:
            self._status = "Initializing vector database..."

        search_provider = LanceDBSearchProvider(
            self._project_path,
            chunker,
            db_dir_name=".scrappy/lancedb"
        )

        # Trigger model loading in background by ensuring schema is ready
        # This downloads/loads the FastEmbed model NOW (in background)
        # instead of blocking later during index_files()
        with self._lock:
            self._status = "Loading embedding model (this may take 10-30s)..."

        # Ensure DB is created first
        search_provider._ensure_db()
        
        # Now load the embedding model by accessing the embedding function
        # This is the critical step that loads the heavy model in the background
        search_provider._ensure_schema()  # This will call _create_embedding_func()
        
        # Additional step to ensure the model is fully loaded
        # Generate a dummy embedding to trigger model initialization if needed
        try:
            if search_provider._embedding_func:
                # This will trigger the actual model loading if not already done
                _ = search_provider._embedding_func.generate_embeddings(["test"])
                logger.debug("Embedding model is fully loaded")
        except Exception as e:
            logger.warning(f"Error during test embedding generation: {e}")

        with self._lock:
            self._result = search_provider
            self._status = "Complete"
            self._complete = True

        logger.debug("Semantic search initialized successfully in background")

    except ImportError as e:
        with self._lock:
            self._error = e
            self._status = f"Failed: Missing dependencies ({e})"
            self._complete = True
        logger.debug(f"Semantic search not available: {e}")

    except Exception as e:
        with self._lock:
            self._error = e
            self._status = f"Failed: {e}"
            self._complete = True
        logger.warning(f"Failed to initialize semantic search: {e}")
```

### 2. Update `LanceDBSearchProvider._ensure_schema()` to ensure the model is fully loaded

```python
def _ensure_schema(self):
    """
    Lazy schema initialization (creates embedding func and schema).

    Raises:
        IndexingError: If fastembed is not available or initialization fails
    """
    if self._code_schema is None:
        try:
            logger.debug("Initializing embedding function (may take 10-30s on first use)...")
            self._embedding_func = _create_embedding_func()
            
            # Ensure the model is fully loaded by generating a test embedding
            # This ensures the heavy model loading happens here, not later
            try:
                _ = self._embedding_func.generate_embeddings(["test"])
                logger.debug("Embedding model is fully loaded")
            except Exception as e:
                logger.warning(f"Error during test embedding generation: {e}")
            
            self._code_schema = _create_code_schema(self._embedding_func)
            logger.debug("Embedding function initialized")
        except Exception as e:
            raise IndexingError(
                f"Failed to initialize embedding function. "
                f"Make sure semantic search dependencies are installed: "
                f"pip install fastembed lancedb. "
                f"Error: {e}"
            ) from e
```

### 3. Add a method to `SemanticSearchInitializer` to wait for completion with a callback

```python
def wait_with_callback(self, callback, timeout: Optional[float] = None) -> None:
    """
    Wait for initialization to complete and call a callback when done.
    
    This is useful for integrating with UI frameworks that use callbacks.
    
    Args:
        callback: Function to call when initialization is complete
        timeout: Maximum seconds to wait (None = wait forever)
    """
    def wait_thread():
        completed = self.wait_for_completion(timeout=timeout)
        callback(completed, self.get_result(), self.get_error())
    
    thread = threading.Thread(target=wait_thread)
    thread.daemon = True
    thread.start()
```

## Usage Example

Here's how you would use this in your application:

```python
# In your application initialization code
from context.semantic.initializer import SemanticSearchInitializer

def on_semantic_search_ready(completed, search_provider, error):
    if completed and search_provider:
        print("Semantic search is ready!")
        # Now you can use search_provider.index_files() or search_provider.search()
        # For example:
        files_to_index = {"file1.py": "content1", "file2.py": "content2"}
        search_provider.index_files(files_to_index)
        
        # Or perform a search
        results = search_provider.search("query")
        print(f"Found {len(results.chunks)} results")
    else:
        print(f"Semantic search initialization failed: {error}")

# Create and start the initializer
semantic_initializer = SemanticSearchInitializer(project_path=Path("."))
semantic_initializer.start()

# Set up a callback to be notified when initialization is complete
semantic_initializer.wait_with_callback(on_semantic_search_ready, timeout=60.0)

# Your application can continue running without blocking
```

## Key Points

1. The heavy model loading happens in `SemanticSearchInitializer._initialize_semantic_search()` in a background thread.
2. We explicitly trigger the model loading by calling `_ensure_schema()` and generating a test embedding.
3. The UI won't freeze because the heavy initialization happens in the background thread.
4. The application can check the status or use callbacks to know when the semantic search is ready.

This approach ensures that the heavy model is loaded in the background thread during initialization, not when first using the search functionality, preventing UI freezing during startup.