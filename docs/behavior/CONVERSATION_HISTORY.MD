### Architecture

SQLite DB stored in .scrappy/

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