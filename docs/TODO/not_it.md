Your diagnosis and proposed solution look solid. The loop affinity issue is a classic pitfall with async HTTP clients, and the factory pattern is the right fix for this architecture. A few thoughts:

## The Diagnosis is Correct

When `@work(thread=True)` runs `process_command`, it creates a new thread with its own event loop (via `asyncio.run()` internally if any async code is called). If `orchestrator.delegate()` or `task_router.handle_auto_route()` uses a shared `AsyncClient` that was bound to the main thread's loop at startup, you get exactly the deadlock you described.

## Consider: Do You Even Need Async in Thread Workers?

Since you're already in a thread (via `@work(thread=True)`), you could simplify by using **sync `httpx.Client`** instead of async. This avoids the loop affinity problem entirely:

```python
class NetworkFactory:
    # For thread workers, just use sync clients
    def new_client(self) -> httpx.Client:
        return httpx.Client(...)

# In your tool
def search(self, query):  # Note: not async
    with self.factory.new_client() as client:
        resp = client.get(f"https://api.xyz?q={query}")
        return resp.json()
```

The async machinery adds complexity when you're already doing concurrency via threads. Unless your orchestrator is doing concurrent async operations *within* a single request (like `asyncio.gather` for parallel API calls), sync might be cleaner.

## If You Stick with Async Factory

The solution as written is correct. Two things to verify:

1. **Trace all HTTP paths** — Make sure `orchestrator.delegate()`, `task_router.handle_auto_route()`, and `smart.smart_query()` all use the factory. The bug will persist if even one path uses a shared client.

2. **Check how async is being invoked** — `_process_input` isn't async, so something inside must be calling `asyncio.run()`. That's where the new loop gets created and where the factory pattern needs to be applied.

## One Potential Issue in Your Current Code

In `_process_input`, you're calling `io.secho()` and `io.echo()` directly from the thread worker. This works *only if* your `io` object routes through `TextualOutputAdapter`'s queue. If there's any code path where `io` writes directly to a widget, that would be a separate thread-safety bug. Worth double-checking.

## The Performance Note is Accurate

The 50-200ms client overhead is noise compared to LLM latency. Don't worry about it.

---

**Quick question:** Can you share where the `AsyncClient` is currently being instantiated? It's not visible in the provided code, and confirming that location will help ensure the factory gets injected in the right place.



This is helpful context. Looking at `CerebrasProvider`, I see a mix of patterns:

## What's Already Correct

The `chat_async` method is actually fine — it creates a fresh `AsyncClient` per request:

```python
async with httpx.AsyncClient() as client:  # ✓ Created in current loop
```

This won't cause loop affinity issues.

## What Could Be Problematic

The sync `OpenAI` client is created once at init and stored:

```python
self._client = client or self._create_default_client()  # Created at startup
```

The `openai` SDK uses `httpx` internally. While the *sync* `OpenAI` client should generally be thread-safe, there can be subtle issues depending on how it's configured and what version you're using.

## Key Questions

1. **How is async being invoked?** Your `_process_input` is sync, but if `orchestrator.delegate()` or `task_router.handle_auto_route()` calls `asyncio.run()` internally to run async provider methods, that's where the new loop is created. Is that happening?

2. **Are other providers/tools sharing an `AsyncClient`?** This Cerebras example looks okay, but do you have something like this elsewhere?

   ```python
   # Problematic pattern in another file
   class SomeService:
       def __init__(self):
           self._async_client = httpx.AsyncClient()  # Bound at init
       
       async def fetch(self, url):
           return await self._async_client.get(url)  # Dies in wrong loop
   ```

3. **What does `orchestrator.delegate()` actually call?** Does it use sync `chat()` or async `chat_async()`? If async, how does it bridge from the sync `_process_input`?

## If You Apply the Factory Pattern Here

```python
class CerebrasProvider(LLMProvider):
    def __init__(self, api_key=None, client_factory=None, ...):
        self._api_key = api_key or os.environ.get('CEREBRAS_API_KEY')
        self._client_factory = client_factory or self._default_client_factory
    
    def _default_client_factory(self):
        return OpenAI(api_key=self._api_key, base_url=self.BASE_URL)
    
    def chat(self, messages, ...):
        # Create client per-call (or use context manager if OpenAI supports it)
        client = self._client_factory()
        response = client.chat.completions.create(...)
```

But honestly, **I'd first trace the actual call path** before refactoring. Can you add some debug logging to confirm:

1. Which thread `CerebrasProvider.__init__` runs on
2. Which thread `chat()` or `chat_async()` runs on
3. Whether `asyncio.run()` is being called anywhere in the delegate path

The deadlock might not be in the provider layer at all — it could be in a tool or middleware layer.

---

This is good — the orchestrator itself is cleanly separated into sync (`delegate`) and async (`delegate_async`) paths. The sync path should work fine from a thread worker *if it stays sync all the way down*.

## The Critical Question

Looking at `_process_input`, I see three code paths:

```python
# Path 1: Auto-route mode
result = self.task_router.handle_auto_route(user_input)

# Path 2: Smart mode  
response = self.smart.smart_query(user_input)

# Path 3: Direct delegation (sync)
response = self.orchestrator.delegate(...)
```

**Path 3 looks safe** — `delegate()` → `delegation_manager.delegate()` → provider's sync `chat()` → sync `OpenAI` client. No loop affinity issues.

**But what about Paths 1 and 2?** 

The bug description says "many sync async calls (tools, http, routing)" — this suggests something is bridging sync→async somewhere. Common patterns that cause your exact deadlock:

```python
# Somewhere in task_router or tools
def handle_auto_route(self, query):
    # This creates a NEW event loop in the thread
    return asyncio.run(self._async_implementation(query))

async def _async_implementation(self, query):
    # This tries to use a client bound to the MAIN loop
    result = await self.shared_async_client.get(...)  # 💥 DEADLOCK
```

## What I Need to See

1. **`task_router.handle_auto_route()`** — Does it call `asyncio.run()` internally? Does it use tools that have async HTTP?

2. **`delegation_manager.delegate()`** — Is this purely sync, or does it bridge to async anywhere?

3. **Any tools** — You mentioned tools in the original doc. If tools use `httpx.AsyncClient` and are invoked via `asyncio.run()` from the thread, that's your culprit.

## Quick Diagnostic

Add this at the start of your provider's `chat()` and `chat_async()` methods:

```python
import threading
import asyncio

def chat(self, ...):
    logger.debug(f"[chat SYNC] thread={threading.current_thread().name}")
    ...

async def chat_async(self, ...):
    try:
        loop = asyncio.get_running_loop()
        logger.debug(f"[chat ASYNC] thread={threading.current_thread().name}, loop={id(loop)}")
    except RuntimeError:
        logger.debug(f"[chat ASYNC] thread={threading.current_thread().name}, NO RUNNING LOOP")
    ...
```

And at app startup:
```python
logger.debug(f"[MAIN] thread={threading.current_thread().name}, loop={id(asyncio.get_event_loop())}")
```

This will tell you immediately if async methods are being called from a different thread/loop than where clients were created.


---

That narrows it down significantly. The problem is in the **tools/router layer**, not the providers.

## The Bug Is In `router.route()`

```python
def handle_auto_route(self, user_input: str):
    result = self.router.route(user_input)  # ← Problem is in here
```

Somewhere inside `router.route()`, there's likely a tool or service with this pattern:

```python
class SomeTool:
    def __init__(self):
        self._client = httpx.AsyncClient()  # Bound to main loop at startup
    
    async def execute(self, query):
        # Called via asyncio.run() from thread worker → DEADLOCK
        return await self._client.get(...)
```

## Next Step

Can you share:

1. **`router.route()` implementation** — how does it invoke tools?

2. **Tool classes** — especially any that do HTTP calls (web search, API calls, etc.)

Look for any class that stores `httpx.AsyncClient` or `aiohttp.ClientSession` as an instance variable. That's almost certainly your culprit.

Alternatively, grep your codebase:

```bash
grep -r "AsyncClient()" src/ --include="*.py" | grep -v "async with"
```

This will find any `AsyncClient()` instantiation that's **not** inside an `async with` context manager — those are your suspects.


---

Good, we're getting closer. The router itself is clean — it just delegates to strategies:

```python
strategy = self._get_strategy(classified)
result = strategy.execute(classified)
```

## The Bug Is In a Strategy

One of your strategy classes (the one that handles research/tool-based tasks) likely has the problematic pattern.

**Can you share:**

1. **`_get_strategy()` method** — to see which strategies exist

2. **The strategies that do HTTP calls** — especially anything named like:
   - `ResearchStrategy`
   - `WebSearchStrategy`
   - `ToolStrategy`
   - `AgentStrategy`

Or run this to find the likely culprits:

```bash
# Find strategy classes
grep -r "class.*Strategy" src/ --include="*.py" -l

# Find AsyncClient usage in those files
grep -r "AsyncClient" src/ --include="*.py" -B2 -A2
```

The deadlock is almost certainly in a strategy that:
1. Has `self._client = httpx.AsyncClient()` in `__init__`
2. Uses it in an async method called via `asyncio.run()` during `execute()`

---
