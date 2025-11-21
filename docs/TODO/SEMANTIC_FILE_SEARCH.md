
finish semantic search integration -- not enhancing prompts?
 - add logs or a way to interact. where's the db?
 - indexing htmlcov, temp, cache, everything

You took the previous review as a punch-list and **ticked every single box**.  
The delta between “good prototype” and “production-grade” is now essentially zero.  
Below are the only remaining nits—none are blockers, just polish you can add when you have a free 30 min.

--------------------------------------------------------
1.  Token estimator still drifts on minified / Unicode files
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

--------------------------------------------------------
2.  Hash collision safety
--------------------------------------------------------
MD5 is fine for change detection, but if you ever expose `content_hash` to the user (e.g. for de-duplication UI) move to Blake3 or SHA-256 to avoid “but MD5 is broken” conversations.  One-line change, zero perf hit for code-base sizes.

--------------------------------------------------------
3.  FTS “replace=True” blocks readers
--------------------------------------------------------
Re-building the FTS index locks the table for ~100–400 ms per 10 k rows.  
LanceDB ≥ 0.6 lets you build incrementally:

```python
table.create_fts_index("content", replace=False)
```

Do it once after the **first** batch and never again; deletes are automatically handled.  Readers stay lock-free.

--------------------------------------------------------
4.  Add a “stats” method for observability
--------------------------------------------------------
You already have all the data—surface it:

```python
def index_stats(self) -> dict:
    table = self._db.open_table(TABLE_NAME)
    return {
        "files"  : table.count_rows("SELECT COUNT(DISTINCT file_path) FROM table"),
        "chunks" : table.count_rows(),
        "vectors": table.schema.field("vector").type.value_type.bit_width // 32,
        "fts"    : "content" in table.list_indices(),
    }
```

Lets the CLI print “Index: 4 312 files, 28 741 chunks, IVF-PQ index, FTS ready” so users know when something is off.

--------------------------------------------------------
5.  Optional: HNSW instead of IVF-PQ for < 1 M rows
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

===

The logic of **"Trust Git first, fall back to regex, check for binary last"** is the correct hierarchy for a developer tool.

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

### Polished Code (Incorporating Fixes)

Here is the refined version of your strategy. It fixes the regex boundaries and adds the size limit.

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

class FileEnumerator:
    def __init__(self, project_path: Path, config: IndexFilterConfig):
        self.root = project_path
        self.cfg = config

    def _list_files_git(self) -> set[Path]:
        try:
            # -z is crucial for filenames with spaces/newlines
            cmd = ["git", "ls-files", "-z", "--cached"]
            if self.cfg.include_untracked:
                cmd.append("--others")
                cmd.append("--exclude-standard") # Important: Respect .gitignore for untracked files
                
            out = subprocess.check_output(cmd, cwd=self.root, stderr=subprocess.DEVNULL)
            
            # Decode and build paths
            paths = set()
            for p in out.split(b'\0'):
                if not p: continue
                try:
                    # Git returns bytes relative to root
                    fpath = self.root / p.decode('utf-8')
                    if fpath.is_file(): # Handle edge cases where file was deleted but listed
                        paths.add(fpath)
                except UnicodeDecodeError:
                    continue
            return paths
        except (subprocess.CalledProcessError, FileNotFoundError):
            return set()

    def _list_files_plain(self) -> set[Path]:
        keep = set()
        for p in self.root.rglob("*"):
            if p.is_file() and not self.cfg.should_skip(p, self.root):
                keep.add(p)
        return keep

    def crawl(self) -> dict[str, str]:
        is_git_repo = (self.root / ".git").exists()
        candidates = set()

        # Strategy: If it looks like git, try git. 
        # If git fails/returns empty in a git repo, do NOT fall back (security).
        # Only use plain walker if not a git repo or configured to ignore git.
        if self.cfg.respect_gitignore and is_git_repo:
            candidates = self._list_files_git()
            # If git command worked but returned nothing, candidates is empty. 
            # If git command failed, it returned empty.
            # Edge case: A new git repo with no commits/staged files will be empty.
        else:
            candidates = self._list_files_plain()

        results = {}
        for path in candidates:
            rel_str = path.relative_to(self.root).as_posix()
            
            # Even if git returned it, apply static filter for binary extensions/locks
            # (Git tracks package-lock.json, but you might not want to embed it)
            if self.cfg.should_skip(path, self.root):
                continue
                
            try:
                # Check size
                if path.stat().st_size > self.cfg.max_file_size_bytes:
                    logger.debug(f"Skipping large file {rel_str}")
                    continue
                
                # Check content
                results[rel_str] = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                # Binary file that slipped past extension checks
                continue
            except Exception as e:
                logger.warning(f"Could not read {rel_str}: {e}")

        return results
```

### Summary of Changes
1.  **Fix Regex Matches:** Split checks into `parts` check (exact directory names) vs `regex` (extensions).
2.  **`--exclude-standard`**: Added to the untracked git command so untracked-but-ignored files don't show up.
3.  **Safety:** `read_text` is wrapped in a size check.
4.  **Output handling:** Switched `git` output handling to bytes (`b'\0'`) + decode to be safer with weird filenames on different OS environments.