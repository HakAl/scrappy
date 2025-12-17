## Issues
  Quality tier priority:
  1. cerebras/qwen-3-235b-a22b-instruct-2507 - 235B instruction-tuned 
  2. groq/meta-llama/llama-4-scout-17b-16e-instruct - 0.4s latency
  3. groq/moonshotai/kimi-k2-instruct - fast, 128k context 
  4. gemini/gemini-2.5-flash - deprioritized (JSON issues)
---
NEXT UP
---
✶ Adding verbose config… (esc to interrupt · ctrl+t to hide todos · 8m 5s · ↑ 18.1k tokens · thinking)
     ☒ Add --dry-run flag parsing to command_router.py
     ☒ Implement CancellationToken
     ☒ Wire cancellation through AgentLoop
     ☒ Add Escape binding to main_screen
     ☒ Enhance audit logging with thinking field
     ☒ Implement compact output mode
     ☒ Fix codebase_search not in SAFE_ACTIONS
     ☒ Fix timer cleanup on unmount
     ☒ Fix app exit blocking issue
     ☒ Update litellm_config with optimal models
     ☒ Remove hard step limit, add soft c

---
Search: indexing -- if new (empty) repo, indexing message persists
---


---
proper config scopes
eg: command history should likely be per project, rate limit per user

Current State: command_history in user scope, rate_limits in project

Proposed State:

    USER        |   PROJECT
----------------------------------
rate_limits.json
config 
 -api keys
 -disclaimer
                    command_history
                    lancedb/
                    conversations.db
                    audit.json
                    config.json -> project id
                    conversations.db
                    debug.log
                    fingerprints.json
                    response_cache.json
                    session.json


---

---
python -m pytest tests/ --cov=src --cov-report=term-missing
C:\Python313\Lib\site-packages\pytest_asyncio\plugin.py:207: PytestDeprecationWarning: The configuration option "asyncio_default_fixture_loop_scope" is unset.
The event loop scope for asynchronous fixtures will default to the fixture caching scope. Future versions of pytest-asyncio will default the loop scope for asynchronous fixtures to function scope. Set the default fixture loop scope explicitly in order to avoid unexpected behavior in the future. Valid fixture loop scopes are: "function", "class", "module", "package", "session"

  warnings.warn(PytestDeprecationWarning(_DEFAULT_FIXTURE_LOOP_SCOPE_UNSET))
---

---
multiline paste input -- NO TOGGLE
---


---
# 2. Dependency Check on Startup

```python
# Add to startup after migration
def check_dependencies() -> List[str]:
    """Check for required external tools."""
    missing = []
    if not shutil.which("git"):
        missing.append("git")
    if not shutil.which("rg"):
        logger.info("ripgrep (rg) not found - using slower grep")
    return missing
```

---

 ### 3. **Scalability Improvements**
 - Refactor the core agent to support distributed execution
 - Implement proper resource management for concurrent operations
 - Add configuration options for resource limits and throttling

 ### 4. **Extensibility**
 - Create a formal plugin interface for custom action executors
 - Standardize the context factory pattern across components
 - Add clear extension points in the agent loop

 ### 5. **Observability**
 - Enhance the audit module with structured logging
 - Add metrics collection for key operations and performance indicators
 - Implement distributed tracing support

 ### 6. **Configuration and Usability**
 - Create a centralized configuration system
 - Add validation for configuration parameters
 - Implement better defaults and documentation

 ### 7. **Testing and Reliability**
 - Increase test coverage, especially for edge cases
 - Add integration tests for the complete agent workflow
 - Implement property-based testing for core algorithms

---

---
why python tools? what's the purpose?? generalize to dependencies tool? is that useful?
---

---
src/agent/core.py -- _format_codebase_structure -- does this belong here?
---


===

Unconfirmed / Mixed Behavior
----