## ARCHITECTURE GOAL

LiteLLM acts as our bridge to providers. We still decide taskrouting, but delegate to LiteLLM for:
requests
retries
rate limit
fallbacks
Enables easier streaming integration 
Potentially some classification  

## CODE RESEARCH

### INTEGRATION DESIGN

New client: LiteLLMClient(litellm, logging, config)
Integration: ProviderService(LiteLLMClient)
Orch/Task Router/Agent/etc: Orch(ProviderService)

### PROVIDER INTEGRATION POINTS
Orchestrator 
Task Router
Agent?

docs/PROVIDERS.md

LiteLLM RESEARCH
Response format
```
{
    "id": "chatcmpl-fe575c37-5004-4926-ae5e-bfbc31f356ca",
    "created": 1751494808,
    "model": "claude-sonnet-4-20250514",
    "object": "chat.completion.chunk",
    "system_fingerprint": null,
    "choices": [
        {
            "finish_reason": null,
            "index": 0,
            "delta": {
                "provider_specific_fields": null,
                "content": "Hello",
                "role": "assistant",
                "function_call": null,
                "tool_calls": null,
                "audio": null
            },
            "logprobs": null
        }
    ],
    "provider_specific_fields": null,
    "stream_options": null,
    "citations": null
}
```

**LiteLLM Integration**

**`LiteLLM` is the Muscle, but your Task Router is the Brain.**

If you deleted your router today and switched to `LiteLLM`'s default router, your app would actually get *dumber*.

Here is why your custom logic is still the "secret sauce" and exactly how to combine the two.

### 1. The "Brain vs. Muscle" Distinction

*   **What `LiteLLM` does (The Muscle):**
    *   "I need to send this string to Gemini." → *It handles the HTTP request, the API key, the retry if it fails, and the fallback to Claude if Gemini is down.*
    *   It is an **Infrastructure Layer**. It ensures the message gets delivered. It generally defaults to random load balancing or latency-based routing, not "intelligence-based" routing.

*   **What YOUR Router does (The Brain):**
    *   "This is a large `git diff` (500 lines), so I shouldn't send it to Llama-3-8b because it will hallucinate. I must send it to Gemini-Pro-1.5."
    *   "The user is asking for a 'Security Review', so I need a model trained on reasoning, not a fast chat model."
    *   This is **Business Logic**. `LiteLLM` cannot do this out of the box. It doesn't know your file structure or what a "complex task" means in your specific app context.

### 2. Why Your Code is Better for *Coding Agents*
`LiteLLM`'s router is primarily designed for **Reliability** (e.g., "Model A is rate-limited, send to Model B"). It is *not* natively designed for **Cognitive Routing** (e.g., "This task is hard, send to Smart Model").

You mentioned your router uses "dynamic ad-hoc scanning" of the project to inform the decision. **`LiteLLM` can't do that.** It doesn't know you have a `tests/` folder. Your logic that checks the context *before* choosing a model is your competitive advantage.

### 3. The "Power Move": Combine Them
Don't throw away your code. **Wrap it.**

Use your Router to make the *Strategic Decision*, and use `LiteLLM` to execute the *Action*.

**Before (What you probably have):**
```python
# Your custom logic mixed with API calls
def route_task(task):
    if analyze_complexity(task) > 5:
        # You likely wrote custom code to call Gemini here
        return requests.post("https://generativelanguage.googleapis.com...", ...)
    else:
        # And custom code to call Groq here
        return requests.post("https://api.groq.com...", ...)
```

**After (The "Supercharged" Architecture):**
```python
from litellm import completion

# Your custom logic STAYS as the "Manager"
def route_task(task):
    # 1. Your Brain makes the decision
    complexity = analyze_complexity(task)
    
    target_model = ""
    if complexity > 5:
        target_model = "gemini/gemini-1.5-pro-latest"
    else:
        target_model = "groq/llama3-8b-8192"

    # 2. LiteLLM handles the "dirty work" (Connections, Retries, Errors)
    response = completion(
        model=target_model, 
        messages=[{"role": "user", "content": task}],
        fallbacks=["openai/gpt-4o-mini"] # <--- You now get this for free!
    )
    return response
```

### Summary
You built the **Strategy Layer**. `LiteLLM` is just the **Connectivity Layer**.

*   **Keep your Router:** It contains your app's intelligence.
*   **Refactor the *calls* inside it:** Swap your raw `requests` or SDK calls for `LiteLLM` calls.

This gives you the best of both worlds: **Your smart decision-making + Their battle-tested error handling.** You are exactly where you need to be.
