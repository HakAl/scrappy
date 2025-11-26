## Future Enhancements

WARNING: Ignoring invalid distribution ~crappy-dev (C:\Python313\Lib\site-packages)
remove built in display truncation

- [ ] Learning from user patterns
- [ ] Provider performance tracking
- [ ] Automatic strategy tuning based on success rates
- [ ] Batch task optimization
- [ ] Streaming execution support
- [ ] Cost-aware provider selection
- [ ] Rate limit awareness in routing decisions


-------------------------

  - Batch processing - Run overnight analysis jobs
  - CI/CD integration - Automated code review, documentation generation
  - RAG pipeline - Use local embeddings for semantic search


---

## Cache / Config Files

### Advice on "Cache File Names"
Follow the **Standard Directory Structure** so you don't litter their home folder.

**The "Scrappy" Way (Simple):**
Just use `~/.scrappy/`. It’s easy to find and delete.

**The "Pro" Way (XDG Standards):**
Use a library like `platformdirs` to put the cache where the OS expects it (e.g., `~/.cache/scrappy` on Linux, `~/Library/Caches/scrappy` on Mac).

**The Migration Strategy:**
If you have users (or yourself) with the old `.llm_agent_team` folder, add a tiny migration check at startup:

```python
from pathlib import Path
import shutil

OLD_DIR = Path.home() / ".llm_agent_team"
NEW_DIR = Path.home() / ".scrappy"

def migrate_legacy_data():
    if OLD_DIR.exists() and not NEW_DIR.exists():
        print("Migrating legacy data to .scrappy/...")
        shutil.move(str(OLD_DIR), str(NEW_DIR))
```

### 3. Cache Naming Convention
For the actual files inside the cache, avoid generic names like `cache.json` which grow infinitely.

**Recommended Structure:**
```text
~/.scrappy/
  ├── config.json          # API keys (if not env vars)
  ├── history/             # Chat logs
  │   ├── 2025-11-18_14-30_fix-auth.jsonl
  │   └── 2025-11-19_09-00_add-tests.jsonl
  └── semantic_cache/      # The "Brain"
      ├── index.faiss      # Vector store (if you add RAG)
      └── db.sqlite        # Key-Value store of (PromptHash -> Response)
```

*   **Why SQLite?** It's one file, it handles concurrent writes (mostly), and it's faster than parsing a massive JSON file every time the CLI starts.

---


### The "Holy Grail" of LLM Testing: `VCR.py`
You mentioned "making everything testable." The biggest pain point with testing agents is that LLMs are non-deterministic and expensive. You don't want your test suite to cost $5 every time you run it.

*   **The Solution:** Use **`pytest-recording`** (a wrapper around `VCR.py`).
*   **How it works:**
    1.  Run your test once with the `--record-mode=once` flag.
    2.  It makes the *real* API call to Groq/Gemini and saves the JSON response to a YAML file (a "cassette").
    3.  Future test runs intercept the HTTP request and instantly return the saved YAML response.
*   **Why this is huge:** It makes your tests **fast** (milliseconds instead of seconds), **free** (no API usage), and **deterministic** (the model always "says" the same thing).

```bash
pip install pytest-recording
```

```python
# tests/test_agent.py
import pytest

@pytest.mark.vcr() # This decorator magically mocks the network call
def test_agent_refactor_logic():
    agent = Agent()
    # This will hit the API the first time, then use the cassette forever
    result = agent.ask("Refactor this function") 
    assert "def" in result
```

### 2. Implementing the "Daily Standup" (Code Snippet)
Since you liked the standup idea, here is the logic to implement it efficiently. The trick is to not dump the *entire* diff (which might break context limits), but to summarize file-by-file.

**The Logic:**
1.  Get list of changed files in last 24h.
2.  Get `git diff` for each file.
3.  If diff > 100 lines, just send the file name and "Large changes".
4.  Send to your **cheapest** model (Groq Llama-3-8b is perfect here).

**Draft Implementation:**
```python
import subprocess
from rich.console import Console
from rich.markdown import Markdown

console = Console()

def get_standup():
    # 1. Get raw diff from yesterday
    diff = subprocess.check_output(
        ["git", "diff", "--since=yesterday", "HEAD"]
    ).decode("utf-8")
    
    if not diff:
        return "No work done yesterday! 🏖️"

    # 2. Prompt the "Cheap" Model (Groq/Cerebras)
    prompt = f"""
    You are a Developer Team Lead. Summarize the following git diffs into a 
    Daily Standup format. Be concise. Group by feature/bug.
    
    DIFF:
    {diff[:6000]}  # Truncate to avoid context errors
    """
    
    # Call your existing orchestration layer here
    summary = agent_team.route_request(prompt, model="fast") 
    
    # 3. Render beautiful output
    console.print(Markdown(summary))
```



