# Conversation Persistence

## Problem
Users have amnesia between sessions. Scrappy forgets everything when closed.

## Solution Overview
SQLite-backed conversation storage with transparent persistence.

---

## Phase 1: MVP (Implement Now)

### Goal
"Scrappy remembers" - automatic, transparent persistence.

### Scope Decisions
| Item | Decision | Rationale |
|------|----------|-----------|
| Tool calls | Skip (user/assistant text only) | Simplicity; LLM can re-run tools if needed |
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

```python
class ConversationStore:
    """SQLite-backed conversation persistence."""

    def __init__(self, db_path: Path, project_path: Path):
        self._conn = sqlite3.connect(db_path)
        self._project_path = str(project_path)
        self._init_schema()

    def add_message(self, role: str, content: str) -> int:
        """Insert message immediately. Returns message ID.

        Content is stripped of ANSI codes before storage.
        Only stores 'user' and 'assistant' roles.
        Skips 'system' (app state, not conversation state).
        Skips 'tool' (deferred to Phase 1.5).
        """

    def get_recent(self, token_budget: int = 8000) -> List[Dict[str, str]]:
        """Load messages up to token budget for current project.

        Works backwards from newest, accumulating until budget hit.
        Uses len(content) // 4 as token estimate.
        Always includes at least the most recent user/assistant pair.
        """

    def get_last_message_time(self) -> Optional[datetime]:
        """Get timestamp of most recent message (for staleness check)."""

    def clear(self) -> None:
        """Clear all messages for current project."""

    def get_stats(self) -> Dict[str, Any]:
        """Return message count, token estimate, oldest/newest timestamps."""
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

### ANSI Stripping Utility
```python
import re

ANSI_PATTERN = re.compile(r'\x1b\[[0-9;]*m')

def strip_ansi(text: str) -> str:
    """Remove ANSI color codes from text before storage."""
    return ANSI_PATTERN.sub('', text)
```

### Stale Session Detection
```python
from datetime import datetime, timedelta

STALE_THRESHOLD = timedelta(hours=4)

def check_session_staleness(last_message_time: datetime) -> bool:
    """Returns True if session is stale (> 4 hours since last message)."""
    if last_message_time is None:
        return False
    return datetime.now() - last_message_time > STALE_THRESHOLD

def format_stale_separator(last_time: datetime) -> str:
    """Format the visual separator for stale sessions."""
    return f"--- Previous session ({last_time.strftime('%b %d, %I:%M %p')}) ---"
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

### Files to Modify
- [ ] NEW: `src/scrappy/cli/conversation_store.py`
- [ ] NEW: `tests/cli/test_conversation_store.py`
- [ ] `src/scrappy/cli/session_context.py` - inject store, load on init
- [ ] `src/scrappy/cli/interactive.py` - add_message after each turn, stale separator
- [ ] `src/scrappy/cli/persistence.py` - remove save/load/toggle, simplify
- [ ] `src/scrappy/cli/session.py` - update CLISessionManager

### Migration
- Existing `.session.json` conversation_history: ignore (start fresh)
- Keep other session data (file_reads, etc.) in JSON for now

---

## Phase 1.5: Tool Call Fidelity (Near-term)

### Problem
Modern LLMs use structured tool calling:
1. **Assistant:** Sends `tool_calls` (array of name + args)
2. **Tool:** Sends `role: tool`, `tool_call_id`, and `content` (result)

If we flatten to plain text, LLM loses chain-of-thought connection and may:
- Hallucinate that it hasn't run the tool yet
- Get confused by formatting

### Schema Update
```sql
-- Add columns to existing messages table
ALTER TABLE messages ADD COLUMN tool_calls TEXT;      -- JSON string (if assistant)
ALTER TABLE messages ADD COLUMN tool_call_id TEXT;    -- String (if role is 'tool')
ALTER TABLE messages ALTER COLUMN content DROP NOT NULL;  -- Can be null for tool-only
```

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
        INSERT INTO messages (project_path, role, content, tool_calls, tool_call_id)
        VALUES (?, ?, ?, ?, ?)
    """, (self._project_path, role, content, tool_calls, tool_call_id))
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
For long conversations (500+ messages), let LLM retrieve relevant history on-demand.

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

### Optional: FTS5 for Exact Recall
For queries like "what was that curl command?":
```sql
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
    USING fts5(content, content=messages, content_rowid=id);

CREATE TRIGGER messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;
```

### When to Implement Phase 2
- Users report "scrappy forgot something from last week"
- Conversations regularly exceed 100+ messages
- Phase 1 feels limiting

---

## Decision Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Storage | SQLite | Built-in, ACID, queryable, single file |
| Persistence | Immediate write | No data loss on crash |
| Startup load | Token budget (8k) | Prevents context stuffing |
| Message types (MVP) | User/assistant only | Simplicity; tool calls in Phase 1.5 |
| System prompts | Never store | App state changes between versions; inject live |
| Stale detection | 4 hour threshold | Balance between continuity and fresh starts |
| UI separator | Yes (MVP) | Simple, good UX |
| System message | Phase 1.5 | Adds complexity |
| ANSI stripping | Yes (MVP) | Prevent garbage in LLM context |
| Tool call fidelity | Phase 1.5 | Important but adds schema complexity |
| Episodic memory | Phase 2 | Cool but rabbit hole for MVP |
| Vector namespace | Phase 2 | Prevents pollution of codebase RAG |
| Hybrid search | Phase 2 | Best of both worlds |

---

## Implementation Checklist

### Phase 1 (MVP)
- [ ] Create `ConversationStore` class with SQLite backend
- [ ] Implement token-budgeted `get_recent()`
- [ ] Implement ANSI stripping utility
- [ ] Implement stale session detection
- [ ] Inject `ConversationStore` into `SessionContext`
- [ ] Wire `add_message()` into interactive loop
- [ ] Add stale separator to CLI startup
- [ ] Remove `/session save|load|toggle` commands
- [ ] Update `/session` to show SQLite stats
- [ ] Add `/history [n]` command
- [ ] Write tests for `ConversationStore`
- [ ] Manual testing of full flow

### Phase 1.5 (Tool Fidelity)
- [ ] Add `tool_calls`, `tool_call_id` columns
- [ ] Update `add_message()` for complex message types
- [ ] Update `get_recent()` to reconstruct tool call structure
- [ ] Add system message injection for stale sessions
- [ ] Test with actual tool-using conversations

### Phase 2 (Episodic Memory)
- [ ] Create `episodic_memory` namespace in vector DB
- [ ] Build `MemoryConsolidator` service
- [ ] Add `indexed_at` column to messages
- [ ] Create `RecallConversationTool`
- [ ] Optionally add FTS5 for exact search
- [ ] Test hybrid search quality
