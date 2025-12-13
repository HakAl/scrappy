# Conversation History

Automatic, transparent conversation persistence using SQLite.

## Overview

Scrappy remembers conversations across sessions. Messages are persisted immediately to prevent data loss on crashes. On startup, recent history is loaded (token-budgeted) to provide continuity.

## Key Behaviors

| Behavior | Description |
|----------|-------------|
| **Immediate writes** | Every message saved to SQLite on send (no batch, no delay) |
| **Token-budgeted recall** | Loads ~8k tokens of recent history on startup |
| **Staleness detection** | Sessions >4 hours old show visual separator |
| **Atomic turn boundaries** | Tool call sequences never split mid-sequence |
| **ANSI stripping** | Terminal escape codes removed before storage |
| **Graceful degradation** | DB errors log warnings, don't crash |

## Architecture

```
User sends message
       |
       v
SessionContext.add_message()
       |
       +---> In-memory list (for current session)
       +---> ConversationStore.add_message() (immediate SQLite write)

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

## Components

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `ConversationStore` | `cli/conversation_store.py` | SQLite persistence, token-budgeted recall |
| `ConversationStoreProtocol` | `cli/conversation_store.py` | Interface for testing/mocking |
| `SessionContext` | `cli/session_context.py` | Orchestrates in-memory + persistent storage |
| `get_or_create_project_id()` | `cli/conversation_store.py` | UUID-based project identity |

## Database

**Location:** `{project_root}/.scrappy/conversations.db`

**Schema:**
```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,     -- UUID from .scrappy/config.json
    role TEXT NOT NULL,           -- 'user', 'assistant', 'tool'
    content TEXT,                 -- Message text (nullable for tool-call-only)
    tool_calls TEXT,              -- JSON array of tool calls (assistant)
    tool_call_id TEXT,            -- Reference ID (tool results)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    indexed_at TIMESTAMP          -- Phase 2: when embedded to vector DB
);

CREATE INDEX idx_messages_project_time
    ON messages(project_id, created_at DESC);
```

**Journal mode:** WAL (Write-Ahead Logging) for crash safety.

## Project Identity

Projects are identified by UUID, not path. This survives:
- Directory renames
- Moving projects to different locations
- Symlink variations

**Storage:** `{project_root}/.scrappy/config.json`
```json
{
    "project_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

## Token Budget & Recall

On startup, `get_recent(token_budget=8000)` loads messages:

1. Works backwards from newest message
2. Estimates tokens as `len(content) // 3` (conservative for code)
3. Stops when budget exhausted
4. Always includes at least the most recent message

**Atomic turn boundaries:** Tool call sequences are never split:
```
[assistant w/tool_calls] -> [tool result(s)...] -> [assistant response]
```
If budget would split this sequence, the entire sequence is excluded.

## Staleness Detection

**Threshold:** 4 hours since last message

**Behavior when stale:**
1. Visual separator shown in CLI: `--- Previous session (Dec 10, 2:30 PM) ---`
2. System message injected into context (helps LLM understand discontinuity)

```python
{
    "role": "system",
    "content": "Note: The following conversation happened in a previous session. The user may be starting a new workflow."
}
```

## Message Types

| Role | Stored | Notes |
|------|--------|-------|
| `user` | Yes | User input |
| `assistant` | Yes | LLM responses, may include `tool_calls` |
| `tool` | Yes | Tool execution results with `tool_call_id` |
| `system` | No | App state, not conversation state; injected live |

## ANSI Stripping

Terminal escape codes are removed before storage to prevent garbage in LLM context:
- SGR sequences (colors, styles)
- Cursor movement
- OSC sequences

```python
# Pattern handles comprehensive escape sequences
ANSI_PATTERN = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]|\x1b\].*?\x07|\x1b[PX^_].*?\x1b\\')
```

## Error Handling

**Graceful degradation** - DB errors don't crash the app:

| Error | Behavior |
|-------|----------|
| Corrupted database | Log warning, create fresh DB, continue |
| Disk full on write | Log error, skip persistence, continue in-memory |
| Permission denied | Log error at startup, disable persistence for session |
| Lock timeout | Raise `IndexingError` with helpful message |

## Commands

| Command | Description |
|---------|-------------|
| `/session` | Show conversation stats (message count, tokens, timestamps) |
| `/session clear` | Clear all history for current project |
| `/history [n]` | Show last n messages (default: 10) |

## Configuration

Currently no user-configurable options. Future candidates:
- Token budget size
- Staleness threshold
- Auto-clear after N days

## Future: Episodic Memory (Phase 2)

For long conversations (500+ messages), recent history isn't enough. Phase 2 adds:
- Vector-indexed conversation history (LanceDB)
- Semantic search via `RecallConversationTool`
- Temporal filtering ("what did we discuss yesterday?")

See: `docs/TODO/_WIP.md` for Phase 2 design.
