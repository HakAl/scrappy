
All four providers are using the **safe pattern** — `AsyncClient` is created inside `async with` blocks, not stored as instance attributes. This is correct.

## So the Problem Isn't in the Providers

The loop affinity issue with `AsyncClient` isn't your bug. Time to look elsewhere.

## What's Different Between Chat and Auto-Route?

Since direct chat works but `handle_auto_route` doesn't, the difference is in what the **strategy** does during `execute()`.

**Can you share:**

1. **The strategy classes** — especially `ResearchStrategy`, `CodeGenerationStrategy`, or whatever handles the tasks that freeze

2. **Any tool classes** — separate from providers, do you have tool implementations (web search, file operations, etc.) that might have their own HTTP clients?

3. **The `RetryOrchestrator.execute_with_retry()` method** — this is called by `delegate_async` and might have something relevant

## Quick Debug to Pinpoint the Hang

Add logging to narrow down exactly where it freezes:

```python
def route(self, user_input: str, ...) -> ExecutionResult:
    logger.debug("[route] Starting classification")
    classified = self.classifier.classify(user_input)
    
    logger.debug(f"[route] Getting strategy for {classified.task_type}")
    strategy = self._get_strategy(classified)
    
    logger.debug(f"[route] Executing strategy: {strategy.__class__.__name__}")
    result = strategy.execute(classified)  # ← Does it hang here?
    
    logger.debug("[route] Strategy complete")
    return result
```

And inside the strategy's `execute()`:

```python
def execute(self, task: ClassifiedTask) -> ExecutionResult:
    logger.debug("[strategy] Starting execute")
    # ... each step ...
    logger.debug("[strategy] Calling orchestrator.delegate")
    response = self.orchestrator.delegate(...)
    logger.debug("[strategy] Delegate returned")
```

This will tell you exactly which call never returns. My guess is it's either:
- A tool that has a shared client
- Something in the classifier using HTTP
- A hook in `_pre_hooks` or `_post_hooks`

---

Here are targeted searches to find the culprit:

```bash
# 1. AsyncClient stored as instance attribute (the classic bug)
grep -rn "self\.\w*client\s*=.*AsyncClient" src/
grep -rn "self\.\w*client\s*=.*httpx\.AsyncClient" src/

# 2. AsyncClient created at module/class level (not in a method)
grep -rn "AsyncClient()" src/ --include="*.py" | grep -v "async with" | grep -v "def "

# 3. aiohttp sessions (same problem as AsyncClient)
grep -rn "aiohttp.ClientSession" src/
grep -rn "self\.\w*session" src/ --include="*.py"

# 4. asyncio.run() calls (shows where sync→async bridging happens)
grep -rn "asyncio\.run(" src/

# 5. Specifically check web_tools
grep -rn "AsyncClient\|ClientSession\|httpx\|aiohttp" src/**/web*.py
grep -rn "def __init__" src/**/web*.py -A 20 | grep -E "(AsyncClient|ClientSession|httpx|aiohttp)"

# 6. Check semantic search initialization
grep -rn "class.*Semantic" src/ -l
grep -rn "AsyncClient\|httpx\|aiohttp" src/**/semantic*.py

# 7. Any HTTP client stored as self._anything or self.anything
grep -rn "self\._\?client\s*=" src/ --include="*.py"

# 8. Check for event loop manipulation
grep -rn "get_event_loop\|new_event_loop\|set_event_loop" src/
```

## Most Likely Candidates

Based on what you said, check these specifically:

```bash
# Web tools - likely culprit
find src -name "*web*tool*" -o -name "*search*tool*" | xargs grep -l "httpx\|aiohttp"

# Semantic search - often has embedding API clients
find src -name "*semantic*" -o -name "*embed*" | xargs grep -l "httpx\|aiohttp\|openai"
```

## What to Look For

Any file where you see both of these:
1. `def __init__(self` containing `Client()` or `AsyncClient()` or `ClientSession()`
2. An `async def` method that uses `self._client` or `self._session`

Share what these greps find and I can pinpoint the exact fix.

# Search Results

## 1. AsyncClient stored as instance attribute
```
No matches found for: self\.\w*client\s*=.*AsyncClient
No matches found for: self\.\w*client\s*=.*httpx
```

## 2. aiohttp sessions
```
No matches found for: aiohttp.ClientSession
```

## 3. asyncio.run() calls - CRITICAL FINDING
```
src/orchestrator/delegation.py:158:        return asyncio.run(
src/orchestrator/delegation.py:325:        return asyncio.run(
```

These are in:
- `DelegationManager.delegate()` - calls `asyncio.run(self.delegate_async(...))`
- `DelegationManager.delegate_batch()` - calls `asyncio.run(self.batch_delegate_async(...))`

## 4. Event loop manipulation - CRITICAL FINDING
```
src/providers/base.py:251:        loop = asyncio.get_event_loop()
```

This is in `LLMProvider.chat_async()` default implementation:
```python
async def chat_async(self, messages, model, max_tokens, temperature, **kwargs) -> LLMResponse:
    # Default: run sync version in thread pool
    loop = asyncio.get_event_loop()  # <-- PROBLEM
    return await loop.run_in_executor(
        None,
        lambda: self.chat(messages, model, max_tokens, temperature, **kwargs)
    )
```

## 5. HTTP clients stored as self._client
```
src/providers/cerebras_provider.py:85:  self._client = client or self._create_default_client()
src/providers/cohere_provider.py:88:    self._client = cohere.ClientV2(api_key=self._api_key)
src/providers/groq_provider.py:89:      self._client = client or self._create_default_client()
src/providers/github_models_provider.py:104: self._client = client or self._create_default_client()
```

These are all **sync** clients (OpenAI SDK client), not AsyncClient - this is SAFE.

## 6. Web tools
`src/agent_tools/tools/web_tools.py` uses `httpx.Client` (sync, not async) with context manager:
```python
with httpx.Client(...) as client:
    response = client.get(url, headers=headers)
```
This is SAFE - sync client with proper context manager.

---

# ROOT CAUSE ANALYSIS

## The Bug: Nested asyncio.run() from Textual worker thread

### Architecture Flow (PROBLEMATIC):

```
Textual App (has its own event loop)
    |
    v
@work(thread=True)  <-- Creates worker thread
process_command(user_input)
    |
    v
interactive_mode._process_input(user_input)
    |
    v
task_router.handle_auto_route(user_input)
    |
    v
router.route(user_input)
    |
    v
strategy.execute(classified)  [ResearchExecutor, etc.]
    |
    v
orchestrator.delegate(...)
    |
    v
delegation_manager.delegate(...)
    |
    v
asyncio.run(self.delegate_async(...))  <-- PROBLEM!
```

### Why This Fails:

1. **Textual runs its own asyncio event loop** on the main thread
2. The `@work(thread=True)` decorator runs `process_command` in a **worker thread**
3. The worker thread calls `orchestrator.delegate()`
4. `delegate()` calls `asyncio.run(self.delegate_async(...))`
5. **`asyncio.run()` tries to create a NEW event loop in the worker thread**

This fails because:
- `asyncio.run()` is designed to be called from the main thread
- When called from a worker thread, it can interfere with the main event loop
- The Textual app's event loop may conflict with the nested event loop

### The Specific Failure Mode:

When `asyncio.run()` is called from a thread that wasn't expecting it:
- It may block waiting for the event loop
- Or it may deadlock if something tries to post back to the main loop
- The output queue messages never reach the UI

### Secondary Issue: `asyncio.get_event_loop()` deprecation

In `src/providers/base.py:251`:
```python
loop = asyncio.get_event_loop()
```

This is deprecated in Python 3.10+ and can return the wrong loop or raise
`DeprecationWarning`. It should use `asyncio.get_running_loop()` inside async
context, or avoid event loop manipulation entirely.

---

# SOLUTION

## Option 1: Use synchronous providers in Textual worker threads (RECOMMENDED)

The Textual worker thread is already non-blocking (it's a thread!), so there's
no need to use async internally. The providers already have sync `chat()` methods.

**Fix in `DelegationManager`:**

Change `delegate()` to NOT use `asyncio.run()` when called from a non-main thread:

```python
import threading

def delegate(self, provider_name, prompt, ...):
    # If we're in the main thread, use asyncio.run (original behavior)
    # If we're in a worker thread, use sync methods directly
    if threading.current_thread() is threading.main_thread():
        return asyncio.run(self.delegate_async(...))
    else:
        # Use sync path - call provider.chat() directly
        return self._delegate_sync(...)
```

Or simpler: **always use sync methods in `delegate()`** and only use
`delegate_async()` when explicitly called by async code.

## Option 2: Use `asyncio.Runner` or nest_asyncio (HACKY)

```python
import nest_asyncio
nest_asyncio.apply()  # Allows nested event loops
```

This is a hack and not recommended for production.

## Option 3: Restructure to use Textual's async workers

Instead of `@work(thread=True)`, use `@work(exclusive=True)` (async) and make
the entire call chain async-aware. This requires more changes but is cleaner.

---

# QUICK FIX TO TEST

Add this to the top of `src/orchestrator/delegation.py`:

```python
import threading

def delegate(self, ...):
    # Temporary fix: detect if we're in a worker thread
    if threading.current_thread() is not threading.main_thread():
        # We're in a worker thread - DON'T use asyncio.run()
        # Instead, call the sync provider methods directly
        return self._delegate_sync_fallback(...)

    # Original async path for main thread
    return asyncio.run(self.delegate_async(...))
```

This should immediately unblock the Textual UI.