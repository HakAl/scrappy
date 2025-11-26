# Session Management

Sessions persist conversation history, context, and state between CLI invocations.

## Architecture

```
src/orchestrator/
  session.py    # SessionManager implementation
  protocols.py  # SessionProtocol definition

src/cli/
  session.py    # CLISessionManager (CLI-specific)
```

## Session Data

A session contains:

```python
@dataclass
class Session:
    id: str
    created_at: datetime
    messages: List[Dict]           # Conversation history
    context: Optional[Dict]        # Codebase context snapshot
    provider_states: Dict          # Provider-specific state
    metadata: Dict                 # Custom metadata
```

## Session Storage

Sessions are stored in `.scrappy/sessions/`:

```
.scrappy/
  sessions/
    session_abc123.json
    session_def456.json
    latest.json -> session_abc123.json
```

## Session Operations

### Save Session

```python
from src.orchestrator.session import SessionManager

session_manager = SessionManager(storage_path=".scrappy/sessions")

# Save current session
session_id = session_manager.save(
    messages=conversation_history,
    context=codebase_context,
)
```

### Resume Session

```python
# Resume latest session
session = session_manager.load_latest()

# Resume specific session
session = session_manager.load(session_id="abc123")
```

### List Sessions

```python
sessions = session_manager.list_sessions()
for s in sessions:
    print(f"{s.id}: {s.created_at}")
```

## CLI Integration

### Auto-save on Exit

By default, sessions are saved when exiting interactive mode:

```bash
scrappy  # Start interactive mode
# ... conversation ...
# Session auto-saved on exit
```

Disable with `--no-save`:

```bash
scrappy --no-save
```

### Resume Session

Resume from last session:

```bash
scrappy --resume
# or
scrappy -r
```

### Interactive Commands

```
/session            # Show session info
/session save       # Save current session
/session load       # Load a session
/session list       # List available sessions
/session clear      # Clear current session
```

## Session Protocol

```python
class SessionProtocol(Protocol):
    def save(
        self,
        messages: List[Dict],
        context: Optional[Dict] = None,
        metadata: Optional[Dict] = None,
    ) -> str: ...

    def load(self, session_id: str) -> Session: ...
    def load_latest(self) -> Optional[Session]: ...
    def list_sessions(self) -> List[SessionInfo]: ...
    def delete(self, session_id: str) -> bool: ...
```

## Message Format

Messages follow the standard chat format:

```python
messages = [
    {"role": "user", "content": "What does this function do?"},
    {"role": "assistant", "content": "This function calculates..."},
    {"role": "user", "content": "Can you improve it?"},
]
```

## Context Snapshots

Sessions can store a snapshot of codebase context:

```python
context = {
    "project_type": "python",
    "platform": "windows",
    "files_indexed": 150,
    "relevant_files": ["src/main.py", "src/utils.py"],
}

session_manager.save(messages=messages, context=context)
```

This allows the session to restore context even if files have changed.

## Testing

Use mock storage for testing:

```python
class MockSessionStorage:
    def __init__(self):
        self._sessions = {}

    def save(self, session: Session) -> str:
        self._sessions[session.id] = session
        return session.id

    def load(self, session_id: str) -> Session:
        return self._sessions.get(session_id)


def test_session_roundtrip():
    storage = MockSessionStorage()
    manager = SessionManager(storage=storage)

    session_id = manager.save(messages=[{"role": "user", "content": "test"}])
    loaded = manager.load(session_id)

    assert loaded.messages[0]["content"] == "test"
```

## Session Cleanup

Old sessions can be cleaned up:

```python
# Delete sessions older than 7 days
session_manager.cleanup(max_age_days=7)

# Keep only N most recent sessions
session_manager.cleanup(keep_count=10)
```
