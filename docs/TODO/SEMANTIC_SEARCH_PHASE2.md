# New Features and Fixes

### The Priority Queue (The Logic)
This is the easiest win. You modify your file collector to sort the list before handing it to the embedder.
EG:
Modify your file walker to yield files in this specific order:
1.  **`README.md`** (Priority 0): The agent needs this to answer "What does this repo do?".
2.  **`src/**/*.py` (or `.js`, etc)** (Priority 1): The actual logic.
3.  **`docs/*.md`** (Priority 2): Detailed explanations.
4.  **`tests/`** (Priority 3): Specific implementation details.
```python
# pseudo_code_indexer.py
from pathlib import Path

EXAMPLE_SOURCE_EXTENSIONS = {'.py', '.js', '.ts', '.go', '.rs', '.java', '.c', '.cpp'}

def get_prioritized_files(root_dir):
    all_files = list(scandir_recursive(root_dir)) # Your existing file walker
    
    high_priority = []
    low_priority = []
    
    for f in all_files:
        if Path(f).suffix in SOURCE_EXTENSIONS:
            high_priority.append(f)
        else:
            # Docs, tests, config files go here
            low_priority.append(f)
            
    # Yield high priority first!
    return high_priority + low_priority
```

**Why this helps:**
The moment the `high_priority` batch finishes, your agent can answer coding questions. It doesn't have to wait for `docs/` or `tests/` to finish to be useful for the immediate task.

---

### "Lazy" Check
Since you use LanceDB, the data persists on disk. **You should almost never re-index the whole codebase on startup.**

"Diff Check" before you call `FastEmbed`.

**The Workflow:**
1.  **On Startup:** Query LanceDB for all existing filenames and their `last_modified` timestamp.
2.  **Scan Files:** Walk the OS file system.
3.  **Compare:**
    *   If file is **New**: Add to `to_embed` list.
    *   If file **mtime > db_mtime**: Add to `to_embed` list (it changed).
    *   If file **mtime == db_mtime**: **SKIP IT.**

**Implementation Sketch:**

```python
import os
import lancedb

def sync_index(root_dir, table):
    # 1. Get current DB state (Fast because LanceDB is columnar)
    # Assuming schema: [filename, vector, last_modified]
    existing_files = table.search().select(["filename", "last_modified"]).to_pandas()
    db_state = dict(zip(existing_files['filename'], existing_files['last_modified']))
    
    to_embed = []
    
    # 2. Check OS state
    for file_path in get_prioritized_files(root_dir):
        current_mtime = os.path.getmtime(file_path)
        
        # If file is new OR modified since last index
        if file_path not in db_state or current_mtime > db_state[file_path]:
            to_embed.append((file_path, current_mtime))
            
    # 3. Only run FastEmbed on the delta
    if to_embed:
        print(f"Indexing {len(to_embed)} new/changed files...")
        process_batch(to_embed) # Your embedding logic
    else:
        print("Index up to date. Ready instantly.")
```

---

### Exclude "Noise" inside Tests

You asked if you should exclude tests. **Don't exclude the test logic, but DO exclude the test data.**

Test directories are often full of large static files that choke embeddings but provide zero logic context.

Add these patterns to your ignore list (or check for them):
*   `__snapshots__/` (Jest/Vitest snapshots are massive JSON/Text blobs).
*   `*.snap`
*   `test/fixtures/` (Often contain large static dummy data).
*   `test/data/`
*   `*.json` (Inside test folders specifically).

**Why:** A single 5MB JSON fixture file takes longer to embed than 50 Python source files. Cutting these gives you the speed benefit you were looking for without losing the "how to write a test" context.

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

---

Expose Key User-Facing Settings 
Add a semantic_search section to CLIConfig with only the settings users might actually want to tune:

  semantic_search:
    enabled: true                    # Enable/disable semantic search
    db_dir_name: ".scrappy/lancedb"  # Where to store the index
    max_text_length: 512             # Max chars per chunk (affects search quality)
    fts_rebuild_threshold: 100       # When to rebuild full-text index