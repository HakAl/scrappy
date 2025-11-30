# Session Management

Sessions persist conversation history, working memory, and state between CLI invocations.

## Architecture

```
src/orchestrator/
  session.py    # SessionManager implementation
  memory.py     # WorkingMemory (file reads, searches, git ops, discoveries)
  protocols.py  # SessionProtocol definition

src/cli/
  session.py    # CLISessionManager (CLI-specific)
  persistence.py # Session command handlers
```

## Session Data

A session contains:

```python
{
    "file_reads": {
        "src/main.py": {
            "content": "...",
            "timestamp": "2025-11-15T10:30:00",
            "lines": 150
        }
    },
    "search_results": [...],      # Recent code searches (last 10)
    "git_operations": [...],      # Recent git commands (last 10)
    "discoveries": [...],         # Key findings
    "conversation_history": [     # Chat messages
        {"role": "user", "content": "..."},
        {"role": "assistant", "content": "..."}
    ],
    "task_history": [...],        # Task execution history
    "saved_at": "2025-11-15T10:35:00",
    "session_start": "2025-11-15T10:00:00"
}
```

## Session Storage

Sessions are stored as a single file:

```
.scrappy/
  session.json    # Single session file per project
```

Note: Only one session per project is supported. The session file is overwritten on each save.

## Session Operations

### Save Session

```python
from src.orchestrator import AgentOrchestrator

orch = AgentOrchestrator()

# Save current session (includes working memory + conversation)
orch.save_session(conversation_history)
```

### Load Session

```python
# Load saved session
result = orch.load_session()
# Returns: {files, searches, git_ops, discoveries, tasks, conversation}
```

### Clear Session

```python
# Delete saved session file
orch.clear_session()
```

## CLI Integration

### Auto-save on Exit

By default, sessions are saved when exiting with `/quit`:

```bash
scrappy  # Start interactive mode
# ... conversation ...
/quit    # Session auto-saved
```

Disable with `--no-save`:

```bash
scrappy --no-save
```

Note: Ctrl+C does NOT trigger auto-save. Use `/quit` to save.

### Resume Session

Resume from last session:

```bash
scrappy --resume
# or
scrappy -r
```

### Interactive Commands

```
/session            # Show session info and status
/session save       # Save current session
/session load       # Load saved session
/session clear      # Delete saved session file
/session toggle     # Toggle auto-save on/off
```

## Working Memory

The session includes "working memory" that tracks context during your session:

### What's Tracked

- **File Reads** - Files read by agent, cached with content and metadata
- **Search Results** - Code search queries and results (LRU, last 10)
- **Git Operations** - Git command outputs (LRU, last 10)
- **Discoveries** - Key findings with location metadata

### Cache Limits

```python
max_file_cache: int = 20      # LRU eviction for files
max_search_results: int = 10  # Rolling window
max_git_operations: int = 10  # Rolling window
```

### Clearing Working Memory

Clear in-memory working memory without affecting saved session:

```
/context clearmem
```

## Testing

Use mock storage for testing:

```python
class MockSessionManager:
    def __init__(self):
        self._session = None

    def save_session(self, conversation):
        self._session = {"conversation": conversation}

    def load_session(self):
        return self._session


def test_session_roundtrip():
    manager = MockSessionManager()
    manager.save_session([{"role": "user", "content": "test"}])
    loaded = manager.load_session()
    assert loaded["conversation"][0]["content"] == "test"
```

## Limitations

- **Single session per project** - No multi-session support or session IDs
- **No encryption** - Session data stored in plaintext JSON
- **Ephemeral on interrupt** - Ctrl+C doesn't save (must use `/quit`)
- **LRU eviction** - Only recent files/searches/git ops are kept
