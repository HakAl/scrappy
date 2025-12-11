# Conversation Persistence

## Problem
Users have amnesia between sessions. Scrappy forgets everything when closed.

## Solution Overview
SQLite-backed conversation storage with transparent persistence.

---

## Phase 1: MVP (Implement Now)

### Goal
"Scrappy remembers" - automatic, transparent persistence.

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
ConversationStore.get_recent(limit=50)
       |
       v
SessionContext._conversation_history = loaded_messages
```

### New Component: ConversationStore

Location: `src/scrappy/cli/conversation_store.py`

```python
class ConversationStore:
    """SQLite-backed conversation persistence."""

    def __init__(self, db_path: Path):
        self._conn = sqlite3.connect(db_path)
        self._init_schema()

    def add_message(self, role: str, content: str) -> int:
        """Insert message immediately. Returns message ID."""

    def get_recent(self, limit: int = 50) -> List[Dict[str, str]]:
        """Load last N messages for current project."""

    def clear(self) -> None:
        """Clear all messages for current project."""

    def get_stats(self) -> Dict[str, Any]:
        """Return message count, oldest/newest timestamps."""
```

### Schema
```sql
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_path TEXT NOT NULL,
    role TEXT NOT NULL,           -- 'user', 'assistant'
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_messages_project_time
    ON messages(project_path, created_at DESC);
```

### Integration Points

1. **SessionContext.__init__**
   - Accept `ConversationStore` dependency
   - Load recent messages on creation

2. **After each turn** (in interactive loop or task_router_handler)
   - Call `store.add_message(role, content)`

3. **Commands**
   - REMOVE: `/session save`, `/session toggle`, `/session load`
   - KEEP: `/session` (show stats), `/session clear` (wipe history)
   - ADD: `/history [n]` (show last n messages)

### Files to Modify
- [ ] NEW: `src/scrappy/cli/conversation_store.py`
- [ ] `src/scrappy/cli/session_context.py` - inject store, load on init
- [ ] `src/scrappy/cli/interactive.py` - add_message after each turn
- [ ] `src/scrappy/cli/persistence.py` - remove save/load/toggle, simplify
- [ ] `src/scrappy/cli/session.py` - update CLISessionManager
- [ ] NEW: `tests/cli/test_conversation_store.py`

### Migration
- Existing `.session.json` conversation_history: ignore (start fresh)
- Keep other session data (file_reads, etc.) in JSON for now

---

## Phase 2: Smart Recall (Future)

### Goal
For long conversations (500+ messages), let LLM retrieve relevant history on-demand.

### Architecture
```
Startup context (minimal):
  - Last 5 messages (immediate context)
  - System note: "Use recall_conversation tool for older context"

LLM needs older context:
  - Calls recall_conversation(query="auth decision")
  - Tool searches messages via FTS5
  - Returns relevant messages
  - LLM incorporates into response
```

### New Tool: recall_conversation

```python
class RecallConversationTool(BaseTool):
    """Search conversation history for relevant context."""

    name = "recall_conversation"
    description = "Search past conversation messages when you need context from earlier discussions"

    parameters = {
        "query": {
            "type": "string",
            "description": "What to search for in conversation history"
        },
        "last_n": {
            "type": "integer",
            "description": "Get last N messages instead of searching",
            "optional": True
        }
    }

    def execute(self, query: str = None, last_n: int = None) -> str:
        if last_n:
            messages = self.store.get_recent(limit=last_n)
        else:
            messages = self.store.search(query, limit=10)
        return self._format_messages(messages)
```

### Schema Addition (FTS5)
```sql
-- Full-text search virtual table
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
    USING fts5(content, content=messages, content_rowid=id);

-- Triggers to keep FTS in sync
CREATE TRIGGER messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;
```

### Search Method
```python
def search(self, query: str, limit: int = 10) -> List[Dict]:
    """Full-text search over conversation history."""
    sql = '''
        SELECT m.role, m.content, m.created_at
        FROM messages m
        JOIN messages_fts fts ON m.id = fts.rowid
        WHERE messages_fts MATCH ? AND m.project_path = ?
        ORDER BY rank
        LIMIT ?
    '''
    return self._conn.execute(sql, (query, self.project_path, limit)).fetchall()
```

### When to Implement
- When users report "scrappy forgot something from last week"
- When conversations regularly exceed 100+ messages
- When Phase 1 feels limiting

---

## Decision Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Storage | SQLite | Built-in, ACID, queryable, single file |
| Persistence | Immediate write | No data loss on crash |
| Startup load | Last 50 messages | Simple, covers most cases |
| Old messages | Keep forever | Disk is cheap, enables Phase 2 |
| Summarization | Skip for MVP | Complexity not worth it yet |
| Recall tool | Phase 2 | Cool but rabbit hole for MVP |
