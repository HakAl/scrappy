## Release Bare Minimum (beta v.1)

missing doc: theme

---
NO API KEYS SET SCENARIO
Consider a /tour or /features command - Show what's available
---


---
  4. Complexity vs. discoverability
  The system does a LOT. New users might not discover features like:
  - /classify for debugging routing decisions
  - /limits for quota management

Make quick commands in welcome better:
/help
/plan
/agent
/providers
/explore

HOW TO DOCS?
eg: change chat model, change agent models
plan a task, complete a task
---

Add version/changelog - Beta users need to know what's new


### Graceful Degradation
What happens when the API is down? 
EG: rate-limited, or returns garbage? Users will blame your tool.
- Retry with exponential backoff
- Clear error messages: "XXX returned 429. Waiting 30s..." vs "Error: Unknown"

### Version Compatibility Check
- Check if user's config file schema matches current version
- Migrate old configs gracefully
- Warn if using deprecated settings

---

### TODO Tool: docs/TODO/TODO_TOOL.md

### Rate Limit Enforcement: docs/TODO/RATE_LIMITING.md

### P5_IMPLEMENTATION_PLAN.md

---

