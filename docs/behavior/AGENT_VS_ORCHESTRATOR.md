### Agent's responsibility:
Decide what to do (reason, plan, execute tools). The agent properly delegates provider selection to the orchestrator, respecting rate limits and enabling smart provider rotation.

### Orchestrator's responsibility:
Decide which provider to use (rate limits, availability, capabilities)

**Orchestrator uses LLMResponse from providers/base.py**

### Specific Behavior:

1.  Agent should not hardcode provider selection. The current `self.planner = 'gemini'` approach defeats the orchestrator's purpose.
2.  Agent should request delegation by task type, not provider name:
    ```python
    # Instead of:
    response = self.orch.delegate('gemini', prompt, ...)

    # Should be:
    response = self.orch.delegate_for_task(
        task_type='planning',  # or 'execution', 'quick_response'
        prompt=prompt,
        ...
    )
    ```
3.  Orchestrator decides provider based on:
    *   Task type requirements (planning needs reasoning → gemini/groq; execution needs speed → cerebras)
    *   Current rate limit status (don't pick gemini if exhausted)
    *   Provider availability
    *   Provider health/error rates
4.  Fallback logic lives in orchestrator, not agent. If preferred provider is rate-limited, orchestrator picks next best.

### Benefits:

*   Rate limiting actually works
*   Provider rotation when limits approached
*   Agent code stays clean and focused
*   Easy to add new providers without touching agent