## Release Bare Minimum (beta v.1)

## BUGS - docs/TODO/MODEL_SELECTION_REFACTOR.md, docs/TODO/PROMPT_REFINEMENT.md, docs/TODO/NO_OUTPUT.md

### Update Docs
Update all top level docs/ to have current information
- Add coming soon section for planned features: docs/TODO

### TODO Tool: docs/TODO/TODO_TOOL.md

### Rate Limit Enforcement: docs/TODO/RATE_LIMITING.md

### P5_IMPLEMENTATION_PLAN.md

---

### Graceful Degradation
What happens when the API is down? 
EG: rate-limited, or returns garbage? Users will blame your tool, not OpenAI.
- Retry with exponential backoff
- Clear error messages: "OpenAI returned 429. Waiting 30s..." vs "Error: Unknown"
- Offline mode for semantic search (local embeddings only)

### Session Persistence -- works, but one shot commands help screen doesn't match feature set
Users will close the terminal mid-task. Can they resume? 
Ensure resume feature works well -- what context is restored?
- Auto-save conversation state to `.scrappy/session.json`
- `scrappy --resume` command
- Clear "session expired" vs "session resumed" messaging

### Audit Log
For trust and debugging:
- Log every file modification with before/after hashes
- Log every shell command with exit code
- `scrappy history` to view recent actions
- This also helps users report bugs with context

### Cost Tracking 
-- UNCLEAR - scrappy is free. relies on free apis
Users will want to know:
- Token usage per session
- Estimated cost (even rough) -- it's free ?
- "This session used ~15k tokens (~$0.02)" at exit

### Interrupt Handling
What happens when users hit Ctrl+C mid-operation?
- Clean shutdown, not stack trace
- Save partial state if possible
- "Operation cancelled. Your work has been saved."

### Version Compatibility Check
- Check if user's config file schema matches current version
- Migrate old configs gracefully
- Warn if using deprecated settings

### Dry Run Mode
Dry run exists. Test to ensure it works
- `--dry-run` flag that shows what would happen without doing it
- Especially valuable for shell commands and file modifications
- Builds trust with new users

### Priority Order (If Time-Limited)

1. **Safety rails** (Y/N gate, .git protection) - Required
- agent prompts for: dry run? git checkpoint?
2. **Config command** - Required
3. **Interrupt handling** - Required (users WILL hit Ctrl+C)
4. **Audit log** - High value for trust/debugging
5. **Session persistence** - Nice to have
6. **Cost tracking** - Nice to have
7. **Dry run** - Nice to have

