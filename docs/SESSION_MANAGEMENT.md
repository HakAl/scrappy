# Session Management

Scrappy supports session persistence, allowing you to save your working state and resume later. This includes conversation history, file reads, searches, and discoveries - everything the LLM needs to maintain context across sessions.

## Quick Start

```bash
# Start a session
scrappy
> /smart what is the main entry point?
> /agent fix the auth bug
> /quit
# Session auto-saved!

# Resume later
scrappy --resume
# Conversation and context restored!
```

## Features

### Auto-Save on Exit (Default)

Sessions are automatically saved when you exit with `/quit`. This includes:

- **Conversation history** - All user/assistant messages
- **File reads** - Recently accessed files (LRU cache, last 20 files)
- **Search results** - Recent code searches (last 10)
- **Git operations** - Recent git commands (last 10)
- **Discoveries** - Key findings and learnings
- **Task history** - Usage statistics and metrics

### Resume Previous Session

```bash
scrappy --resume
# or
scrappy -r
```

On resume, you'll see:
```
Resumed session from 2025-11-15T10:30:00
  Files restored: 5
  Searches restored: 3
  Git ops restored: 2
  Discoveries restored: 4
  Task history: 12 entries
  Conversation: 8 messages restored

Last conversation:
  You: Where is the auth module?
  Assistant: The auth module is located in src/auth/...
```

### Disable Auto-Save

If you don't want to save the session:

```bash
scrappy --no-save
```

Or toggle during session:
```
> /session toggle
Auto-save on exit: OFF
```

## Session Commands

### `/session` - View Status

Shows current session state and saved session info:

```
Session Management:
--------------------------------------------------
Session File: /path/to/project/.scrappy/session.json
Session Exists: Yes
Last Saved: 2025-11-15T10:30:00
Files Cached: 5
Searches: 3
Git Ops: 2
Discoveries: 4
Conversation: 8 messages

Current Session Memory:
  Files in memory: 3
  Searches: 2
  Git ops: 1
  Discoveries: 2
  Conversation: 4 messages
  Auto-save: ON
```

### `/session save` - Manual Save

Save the current session without quitting:

```
> /session save
Session saved to: .llm_team_session.json
  Conversation: 6 messages
```

### `/session load` - Load Saved Session

Load a previously saved session into the current session:

```
> /session load
Session loaded from 2025-11-15T10:30:00
  Files: 5
  Searches: 3
  Git ops: 2
  Discoveries: 4
  Conversation: 8 messages
```

### `/session clear` - Delete Saved Session

Remove the saved session file:

```
> /session clear
Saved session cleared.
```

### `/session toggle` - Toggle Auto-Save

Turn auto-save on or off:

```
> /session toggle
Auto-save on exit: OFF
Session will NOT be saved on /quit (use '/session save' manually)

> /session toggle
Auto-save on exit: ON
Session will be saved automatically on /quit
```

## Working Memory

The session system includes "working memory" - context that's automatically tracked during your session and passed to the LLM for better responses.

### What's Tracked

1. **File Reads** - When the agent reads a file, it's cached
2. **Code Searches** - Search queries and results are remembered
3. **Git Operations** - Git log, diff, blame outputs are stored
4. **Discoveries** - Key findings can be manually added

### How It's Used

When you make an LLM query, the working memory is automatically included in the prompt:

```
[Session Working Memory]
Recently accessed files:
  - src/auth/login.py (150 lines)
  - src/models/user.py (89 lines)

Recent searches:
  - 'authenticate (*.py)' (12 results)
  - 'JWT token (*.py)' (5 results)

Recent git operations:
  - git log -10
  - git diff HEAD~1 src/auth/

Key discoveries:
  - Auth uses JWT tokens at src/auth/jwt.py
  - User model defines permissions at src/models/user.py:45

[Codebase Context]
...

[User Request]
Your query here
```

### Managing Working Memory

Clear working memory without affecting saved session:

```
> /context clearmem
Session working memory cleared.
```

View working memory status:

```
> /context
...
Session Working Memory:
--------------------------------------------------
Files Cached: 3
  - src/auth/login.py
  - src/models/user.py
  - src/config.py
Recent Searches: 2
Git Operations: 1
Discoveries: 3
```

## Storage

### Session File

Sessions are stored in `.scrappy/session.json` in your project root.

**Add to .gitignore:**
```
.scrappy/
```

This file contains:
- File contents (can be large)
- Conversation history (may contain sensitive info)
- Search results and git outputs

### File Structure

```json
{
  "file_reads": {
    "src/auth.py": {
      "content": "...",
      "timestamp": "2025-11-15T10:30:00",
      "lines": 150
    }
  },
  "search_results": [...],
  "git_operations": [...],
  "discoveries": [...],
  "conversation_history": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ],
  "task_history": [...],
  "saved_at": "2025-11-15T10:35:00",
  "session_start": "2025-11-15T10:00:00"
}
```

## Use Cases

### Multi-Day Feature Development

```bash
# Day 1
scrappy
> /smart how does the payment system work?
> /agent add stripe integration
> /quit

# Day 2
scrappy --resume
# LLM remembers previous context
> continue with the stripe integration
```

### Long Debugging Sessions

```bash
scrappy
> /smart where is the memory leak?
> /agent analyze heap dumps
# Take a break
> /quit

# Resume later
scrappy --resume
# All debugging context preserved
```

### Code Review Workflow

```bash
scrappy
> /smart review recent changes
> what security issues do you see?
> /quit

# Later
scrappy --resume
> let's fix the SQL injection you found
```

## Best Practices

1. **Use `/quit` to save** - Ctrl+C doesn't trigger auto-save
2. **Clear sensitive sessions** - Use `/session clear` after working with credentials
3. **Add to .gitignore** - Session files contain code and may be large
4. **Toggle auto-save for experiments** - Use `--no-save` or `/session toggle` when experimenting
5. **Check status regularly** - Use `/session` to see what's being tracked

## Limitations

- **No multi-session support** - Only one session file per project
- **Session size** - Large file caches can make the session file big
- **No encryption** - Session data is stored in plaintext JSON
- **Ephemeral on interrupt** - Ctrl+C doesn't save (must use `/quit`)
- **LRU eviction** - Only last 20 files, 10 searches, 10 git ops are kept
