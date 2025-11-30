## Release Bare Minimum (beta v.1)

---
 That makes sense. So the fix is narrower: GitHub Models should be blocked specifically from agent/planner roles,
  not removed entirely.

  A few options:

  1. Block at agent level - CodeAgent refuses to use GitHub Models as planner, falls back to next available
  2. Block at CLI level - /agent command rejects --brain github with clear error message
  3. Add to provider metadata - Mark GitHub Models as supports_agent=False and have provider selector respect it

  Option 3 is cleanest architecturally - the provider self-describes its limitations, and the system respects them.
  Keeps the logic where it belongs.
---

  4. Complexity vs. discoverability
  The system does a LOT. New users might not discover features like:
  - /classify for debugging routing decisions
  - /limits for quota management

  Recommendations
  2. Consider a /tour or /features command - Show what's available
  5. Add version/changelog - Beta users need to know what's new



### Graceful Degradation
What happens when the API is down? 
EG: rate-limited, or returns garbage? Users will blame your tool, not OpenAI.
- Retry with exponential backoff
- Clear error messages: "OpenAI returned 429. Waiting 30s..." vs "Error: Unknown"
- Offline mode for semantic search (local embeddings only)

### Version Compatibility Check
- Check if user's config file schema matches current version
- Migrate old configs gracefully
- Warn if using deprecated settings

---

### TODO Tool: docs/TODO/TODO_TOOL.md

### Rate Limit Enforcement: docs/TODO/RATE_LIMITING.md

### P5_IMPLEMENTATION_PLAN.md

---

