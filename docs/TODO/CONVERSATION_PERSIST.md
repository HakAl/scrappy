# Conversation Persistence

## Problem
Scrappy has amnesia between chats. Scrappy forgets everything.

## Solution Overview
SQLite-backed conversation storage with transparent persistence.

---

## Phase 1: MVP (Implement Now) -- COMPLETE

### Goal
"Scrappy remembers" - automatic, transparent persistence.

### Scope Decisions
| Item | Decision | Rationale |
|------|----------|-----------|
| Tool calls | Schema ready, usage deferred to Phase 1.5 | Avoids migrations; Phase 1 stores user/assistant only |
| Token budget | Yes (not message count) | Prevents context stuffing with large outputs |
| Stale separator | Yes (UI only) | Simple UX improvement |
| ANSI stripping | Yes | Prevent garbage in history |
| System prompts | Never store | App state, not conversation state; inject live on startup |
| System message injection | Defer to Phase 1.5 | Adds complexity |

### Architecture
```
User sends message
       |
       v
SessionContext.add_message()
       |
       +---> In-memory list (existing)
       +---> ConversationStore.add_message() (NEW - immediate write)

On startup:
       |
       v
ConversationStore.get_recent(token_budget=8000)
       |
       +---> Check staleness (last message > 4 hours?)
       |          |
       |          +---> Yes: Show "--- Previous session (Dec 10) ---"
       |
       v
SessionContext._conversation_history = loaded_messages
```

### New Component: ConversationStore

Location: `src/scrappy/cli/conversation_store.py`

Database Location: `{project_root}/.scrappy/conversations.db`
Config Location: `{project_root}/.scrappy/config.json`

### Project Identity

Projects are identified by UUID, not path. This survives renames, moves, and symlink variations.

```python
# .scrappy/config.json
{
    "project_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

```python
def get_or_create_project_id(scrappy_dir: Path) -> str:
    """Load existing project ID or generate new one.

    Args:
        scrappy_dir: Path to .scrappy/ directory

    Returns:
        UUID string for this project
    """
    config_file = scrappy_dir / "config.json"

    if config_file.exists():
        with open(config_file) as f:
            return json.load(f)["project_id"]

    # First run - generate new UUID
    project_id = str(uuid.uuid4())
    scrappy_dir.mkdir(parents=True, exist_ok=True)
    with open(config_file, "w") as f:
        json.dump({"project_id": project_id}, f)

    return project_id
```

```python
class ConversationStoreProtocol(Protocol):
    """Protocol for conversation persistence."""

    def add_message(self, role: str, content: str) -> int: ...
    def get_recent(self, token_budget: int = 8000) -> List[Dict[str, str]]: ...
    def get_last_message_time(self) -> Optional[datetime]: ...
    def clear(self) -> None: ...
    def get_stats(self) -> Dict[str, Any]: ...
    def close(self) -> None: ...


class ConversationStore:
    """SQLite-backed conversation persistence.

    IMPORTANT: Use the create() factory method, not __init__ directly.
    """

    def __init__(self, conn: sqlite3.Connection, project_id: str):
        """Assign dependencies only. No I/O here.

        Args:
            conn: Already-opened SQLite connection.
            project_id: UUID string identifying this project.
        """
        self._conn = conn
        self._project_id = project_id

    @classmethod
    def create(cls, scrappy_dir: Path) -> "ConversationStore":
        """Factory method that handles I/O and initialization.

        Args:
            scrappy_dir: Path to .scrappy/ directory in project root.

        Returns:
            Initialized ConversationStore ready for use.
        """
        # Ensure .scrappy directory exists
        scrappy_dir.mkdir(parents=True, exist_ok=True)

        # Get or create project UUID
        project_id = get_or_create_project_id(scrappy_dir)

        # Open database with WAL mode for crash safety
        db_path = scrappy_dir / "conversations.db"
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL;")

        store = cls(conn, project_id)
        store._init_schema()
        return store

    def add_message(self, role: str, content: str) -> int:
        """Insert message immediately. Returns message ID.

        Content is stripped of ANSI codes before storage.
        Only stores 'user' and 'assistant' roles.
        Skips 'system' (app state, not conversation state).
        Skips 'tool' (deferred to Phase 1.5).

        Phase 1 implementation (explicit NULLs for future columns):
            cursor = self._conn.execute('''
                INSERT INTO messages (project_id, role, content, tool_calls, tool_call_id)
                VALUES (?, ?, ?, NULL, NULL)
            ''', (self._project_id, role, strip_ansi(content)))
            self._conn.commit()
            return cursor.lastrowid
        """

    def get_recent(self, token_budget: int = 8000) -> List[Dict[str, str]]:
        """Load messages up to token budget for current project.

        Works backwards from newest, accumulating until budget hit.
        Uses len(content) // 3 as token estimate (conservative for code).
        Always includes at least the most recent message, even if it
        exceeds the budget.

        IMPORTANT: Never split atomic turn boundaries.
        - Phase 1: User/assistant pairs are atomic (can split between pairs)
        - Phase 1.5: Tool call sequences are atomic:
            [assistant w/tool_calls] -> [tool results...] -> [assistant response]
          Must include all or none of a tool call sequence.

        Edge cases:
        - If only a user message exists (no assistant response), include it.
        - If conversation is empty, return empty list.
        - If budget would split a tool sequence, exclude the entire sequence.
        """

    def get_last_message_time(self) -> Optional[datetime]:
        """Get timestamp of most recent message (for staleness check).

        Returns UTC datetime for consistent timezone handling.
        """

    def clear(self) -> None:
        """Clear all messages for current project."""

    def get_stats(self) -> Dict[str, Any]:
        """Return message count, token estimate, oldest/newest timestamps."""

    def close(self) -> None:
        """Close the database connection. Call on shutdown."""
        self._conn.close()
```

### Known Limitations

- **Token estimation is approximate**: `len(content) // 3` is conservative for code-heavy content (code has more small tokens than prose). Better to load slightly less context than overflow. Consider `tiktoken` for accuracy in future.
- **Atomic turn boundaries** (Phase 1.5): Token budget must respect tool call sequences. A tool call and its results are atomic - cutting between them confuses the LLM. This may result in loading slightly under budget to avoid splitting sequences.

### Schema
```sql
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,     -- UUID from .scrappy/config.json
    role TEXT NOT NULL,           -- 'user', 'assistant', 'tool' (Phase 1.5)
    content TEXT,                 -- Nullable for tool-call-only messages
    tool_calls TEXT,              -- JSON string, Phase 1.5 (nullable)
    tool_call_id TEXT,            -- For role='tool' messages, Phase 1.5 (nullable)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP  -- UTC (SQLite default)
);

CREATE INDEX IF NOT EXISTS idx_messages_project_time
    ON messages(project_id, created_at DESC);

-- Schema versioning for future migrations
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);
INSERT OR IGNORE INTO schema_version (version) VALUES (1);
```

**Design choice:** Schema includes Phase 1.5 columns upfront (nullable) to avoid migrations. Phase 1 ignores them; Phase 1.5 starts populating them.

**Note:** `CURRENT_TIMESTAMP` in SQLite is always UTC, which matches our timezone handling strategy.

### ANSI Stripping Utility
```python
import re

# Handles SGR (colors/styles), cursor movement, and OSC sequences
ANSI_PATTERN = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]|\x1b\].*?\x07|\x1b[PX^_].*?\x1b\\')

def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text before storage."""
    return ANSI_PATTERN.sub('', text)
```

### Stale Session Detection
```python
from datetime import datetime, timedelta, timezone

STALE_THRESHOLD = timedelta(hours=4)

def check_session_staleness(last_message_time: datetime) -> bool:
    """Returns True if session is stale (> 4 hours since last message).

    IMPORTANT: last_message_time must be UTC (as returned by get_last_message_time).
    """
    if last_message_time is None:
        return False
    now_utc = datetime.now(timezone.utc)
    # Ensure last_message_time is timezone-aware
    if last_message_time.tzinfo is None:
        last_message_time = last_message_time.replace(tzinfo=timezone.utc)
    return now_utc - last_message_time > STALE_THRESHOLD

def format_stale_separator(last_time: datetime) -> str:
    """Format the visual separator for stale sessions.

    Converts UTC time to local time for display.
    """
    local_time = last_time.replace(tzinfo=timezone.utc).astimezone()
    return f"--- Previous session ({local_time.strftime('%b %d, %I:%M %p')}) ---"
```

### Integration Points

1. **SessionContext.__init__**
   - Accept `ConversationStore` dependency
   - Load recent messages (token-budgeted) on creation
   - Check staleness, set flag for UI separator

2. **After each turn** (in interactive loop or task_router_handler)
   - Call `store.add_message(role, strip_ansi(content))`
   - Only for role in ('user', 'assistant')

3. **CLI startup** (in interactive.py)
   - If session is stale, print separator before first prompt

4. **Commands**
   - REMOVE: `/session save`, `/session toggle`, `/session load`
   - KEEP: `/session` (show stats), `/session clear` (wipe history)
   - ADD: `/history [n]` (show last n messages)

### Error Handling

**Database Errors:**
- **Corrupted database**: Log warning, create fresh database, continue (lose history but don't crash)
- **Disk full on write**: Log error, skip persistence, continue with in-memory only
- **Permission denied**: Log error at startup, disable persistence for session

**Graceful Degradation:**
```python
class ConversationStore:
    def add_message(self, role: str, content: str) -> int:
        try:
            # ... insert logic ...
        except sqlite3.Error as e:
            logger.warning(f"Failed to persist message: {e}")
            return -1  # Indicate failure but don't crash

    @classmethod
    def create(cls, db_path: Path, project_path: Path) -> Optional["ConversationStore"]:
        try:
            # ... creation logic ...
        except (sqlite3.Error, OSError) as e:
            logger.warning(f"Could not initialize conversation store: {e}")
            return None  # Caller handles None (no persistence)
```

### Files to Modify
- [ ] NEW: `src/scrappy/cli/conversation_store.py` (includes `get_or_create_project_id`)
- [ ] NEW: `tests/cli/test_conversation_store.py`
- [ ] `src/scrappy/cli/session_context.py` - inject store, load on init
- [ ] `src/scrappy/cli/interactive.py` - add_message after each turn, stale separator
- [ ] `src/scrappy/cli/persistence.py` - remove save/load/toggle, simplify
- [ ] `src/scrappy/cli/session.py` - update CLISessionManager
- [ ] `.gitignore` - add `.scrappy/` directory

### Migration
- Existing `.session.json` conversation_history: ignore (start fresh)
- Keep other session data (file_reads, etc.) in JSON for now

---

## Phase 1.5: Tool Call Fidelity (Near-term) -- 

### Problem
Modern LLMs use structured tool calling:
1. **Assistant:** Sends `tool_calls` (array of name + args)
2. **Tool:** Sends `role: tool`, `tool_call_id`, and `content` (result)

If we flatten to plain text, LLM loses chain-of-thought connection and may:
- Hallucinate that it hasn't run the tool yet
- Get confused by formatting

### Schema

No schema changes needed - Phase 1 schema already includes `tool_calls`, `tool_call_id`, and nullable `content`.

### Updated add_message
```python
def add_message(self, message: Dict[str, Any]) -> int:
    """
    Accepts a full message dict (standard LLM format).
    Handles extracting tool_calls and content.
    """
    role = message.get("role")
    content = message.get("content")
    if content:
        content = strip_ansi(content)

    tool_calls = json.dumps(message.get("tool_calls")) if message.get("tool_calls") else None
    tool_call_id = message.get("tool_call_id")

    self._conn.execute("""
        INSERT INTO messages (project_id, role, content, tool_calls, tool_call_id)
        VALUES (?, ?, ?, ?, ?)
    """, (self._project_id, role, content, tool_calls, tool_call_id))
    self._conn.commit()
```

### System Message for Stale Context
When session is stale (> 4 hours), inject system message:
```python
def get_stale_context_message() -> Dict[str, str]:
    return {
        "role": "system",
        "content": "Note: The following conversation happened in a previous session. The user may be starting a new workflow."
    }
```

---

## Phase 2: Smart Recall (Future)

### Goal
For long conversations (500+ messages), let LLM retrieve relevant history on-demand.FTS5 for Exact Recall

For queries like "what was that curl command?":
```sql
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
    USING fts5(content, content=messages, content_rowid=id);

CREATE TRIGGER messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;
```


### Architecture: Episodic Memory
```
Short-term Memory (Active Context):
  - Loaded from SQLite (last ~20 messages / 4k tokens)

Long-term Memory (RAG):
  - Passive RAG (Existing): Codebase, docs
  - Episodic RAG (New): Past conversations
```

### Vector Pollution Risk
**Problem:** Dumping conversation history into existing codebase RAG degrades results.
- User asks: "How does UserAuth work?"
- Bad RAG: Returns chat message "I hate UserAuth, it's broken"
- Good RAG: Returns UserAuth class definition

**Solution:** Separate namespace for conversation history.
```
collection: codebase_knowledge   (high authority)
collection: episodic_memory      (context, lower authority)
```

### Memory Consolidation Service
```python
class MemoryConsolidator:
    """Embeds finished conversations into vector DB."""

    def embed_conversation(self):
        # 1. Read unindexed messages from SQLite
        # 2. Group into logical chunks (User Q + Assistant A pairs)
        # 3. Embed and insert into Vector DB (namespace: 'episodic_memory')
        # 4. Mark as indexed in SQLite (add 'indexed_at' column)
```

### Schema Addition (SQLite marker)
```sql
ALTER TABLE messages ADD COLUMN indexed_at TIMESTAMP;  -- When embedded to vector DB
```

### Hybrid Search Tool
```python
class RecallConversationTool(BaseTool):
    """Search conversation history for relevant context."""

    name = "recall_conversation"
    description = "Search past conversation messages when you need context from earlier discussions"

    def execute(self, query: str = None, last_n: int = None) -> str:
        if last_n:
            # Direct SQLite fetch
            messages = self.store.get_recent(limit=last_n)
        else:
            # Hybrid: Vector (semantic) + optional FTS5 (exact)
            vector_results = self.vector_db.search(query, namespace='episodic_memory')
            # Optionally merge with FTS5 for exact matches
            return self._format_results(vector_results)
```

---

## Decision Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Storage | SQLite | Built-in, ACID, queryable, single file |
| Persistence | Immediate write | No data loss on crash |
| Journal mode | WAL | Better crash safety and concurrent reads |
| Startup load | Token budget (8k) | Prevents context stuffing |
| Message types (MVP) | User/assistant only | Simplicity; tool calls in Phase 1.5 |
| System prompts | Never store | App state changes between versions; inject live |
| Stale detection | 4 hour threshold | Balance between continuity and fresh starts |
| Timezone handling | UTC everywhere | Consistent staleness checks across timezones |
| Project identity | UUID in .scrappy/config.json | Survives renames/moves; no path edge cases |
| Constructor pattern | Factory method | No I/O in __init__ per CLAUDE.md; DI-friendly |
| Protocol-first | Yes | Enables testing with doubles; per CLAUDE.md |
| UI separator | Yes (MVP) | Simple, good UX |
| System message | Phase 1.5 | Adds complexity |
| ANSI stripping | Yes (MVP) | Prevent garbage in LLM context |
| Error handling | Graceful degradation | DB errors log warning, don't crash |
| Tool call columns | Include in Phase 1 schema | Avoids migrations; Phase 1 ignores, Phase 1.5 uses |
| Tool call fidelity | Phase 1.5 | Important but adds code complexity |
| Atomic turn boundaries | Yes (Phase 1.5) | Never split tool call sequences; LLM needs complete context |
| Episodic memory | Phase 2 | Cool but rabbit hole for MVP |
| Vector namespace | Phase 2 | Prevents pollution of codebase RAG |
| Hybrid search | Phase 2 | Best of both worlds |

---

## Implementation Checklist

### Phase 1 (MVP)
- [ ] Create `ConversationStoreProtocol` and `ConversationStore` class
- [ ] Implement `create()` factory method with WAL mode
- [ ] Implement `get_or_create_project_id()` for UUID-based project identity
- [ ] Implement token-budgeted `get_recent()` with edge case handling
- [ ] Implement ANSI stripping utility (full escape sequence coverage)
- [ ] Implement stale session detection with UTC timezone handling
- [ ] Implement graceful error handling (degraded mode on DB errors)
- [ ] Inject `ConversationStore` into `SessionContext`
- [ ] Wire `add_message()` into interactive loop
- [ ] Add stale separator to CLI startup
- [ ] Remove `/session save|load|toggle` commands
- [ ] Update `/session` to show SQLite stats
- [ ] Add `/history [n]` command
- [ ] Add `.scrappy/` to `.gitignore`
- [ ] Write tests for `ConversationStore`
- [ ] Write tests for `get_or_create_project_id()`
- [ ] Write tests for ANSI stripping utility
- [ ] Write tests for staleness detection
- [ ] Test project rename preserves history (UUID survives move)
- [ ] Manual testing of full flow

### Phase 1.5 (Tool Fidelity)
- [x] Update `add_message()` to populate `tool_calls`, `tool_call_id` columns
- [x] Update `get_recent()` to reconstruct tool call structure
- [x] Implement atomic turn boundaries (never split tool call sequences)
- [x] Add system message injection for stale sessions (function defined, integration deferred)
- [x] Test with actual tool-using conversations (unit tests cover scenarios)
- [x] Test token budget edge case: budget lands mid-tool-sequence

### Phase 2 (Episodic Memory)
- [ ] Create `episodic_memory` namespace in vector DB
- [ ] Build `MemoryConsolidator` service
- [ ] Add `indexed_at` column to messages
- [ ] Create `RecallConversationTool`
- [ ] Optionally add FTS5 for exact search
- [ ] Test hybrid search quality
