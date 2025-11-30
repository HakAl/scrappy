## Release Bare Minimum (beta v.1)


  4. Complexity vs. discoverability
  The system does a LOT. New users might not discover features like:
  - /classify for debugging routing decisions
  - /limits for quota management

  Recommendations
  2. Consider a /tour or /features command - Show what's available
  4. Clean up behavior/ docs - Remove or mark as "planned" anything not implemented
  5. Add version/changelog - Beta users need to know what's new


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

### Interrupt Handling
What happens when users hit Ctrl+C mid-operation?
- Clean shutdown, not stack trace
- Save partial state if possible
- "Operation cancelled. Your work has been saved."

### Version Compatibility Check
- Check if user's config file schema matches current version
- Migrate old configs gracefully
- Warn if using deprecated settings


