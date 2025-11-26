# Caching

The caching system stores LLM responses to avoid redundant API calls, reducing latency and costs.

## Architecture

```
src/orchestrator/
  cache.py      # ResponseCache implementation
  protocols.py  # CacheProtocol definition
```

## Cache Protocol

```python
class CacheProtocol(Protocol):
    def get(self, key: str) -> Optional[LLMResponse]: ...
    def put(self, key: str, response: LLMResponse) -> None: ...
    def clear(self) -> None: ...
    def size(self) -> int: ...
```

## Response Cache

The default implementation uses an in-memory LRU cache:

```python
from src.orchestrator.cache import ResponseCache

cache = ResponseCache(max_size=1000)

# Store a response
cache.put(cache_key, response)

# Retrieve a response
cached = cache.get(cache_key)
if cached:
    return cached  # Skip API call
```

## Cache Key Generation

Keys are generated from request parameters:

```python
def generate_cache_key(
    messages: List[Dict],
    model: str,
    temperature: float,
) -> str:
    # Hash of messages + model + temperature
    content = json.dumps(messages) + model + str(temperature)
    return hashlib.sha256(content.encode()).hexdigest()
```

## Integration with Orchestrator

The orchestrator checks cache before making API calls:

```python
class AgentOrchestrator:
    def __init__(self, cache: CacheProtocol, ...):
        self.cache = cache

    def delegate(self, prompt: str, **kwargs) -> LLMResponse:
        cache_key = generate_cache_key(...)

        # Check cache first
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        # Make API call
        response = self._call_provider(prompt, **kwargs)

        # Store in cache
        self.cache.put(cache_key, response)

        return response
```

## Cache Statistics

View cache performance via CLI:

```bash
scrappy usage
# Shows: Cache hits, misses, hit rate, size
```

Or in interactive mode:

```
/cache
```

## Configuration

```json
// .scrappy/config.json
{
  "cache": {
    "enabled": true,
    "max_size": 1000,
    "ttl_seconds": 3600
  }
}
```

## Cache Invalidation

Clear the cache when needed:

```python
# Clear entire cache
cache.clear()

# Clear specific entry
cache.invalidate(cache_key)
```

Via CLI:

```bash
scrappy context --clear
```

## Testing

Use a mock cache for testing:

```python
class MockCache:
    def __init__(self):
        self._store = {}

    def get(self, key: str) -> Optional[LLMResponse]:
        return self._store.get(key)

    def put(self, key: str, response: LLMResponse) -> None:
        self._store[key] = response

# Test with mock
def test_orchestrator_uses_cache():
    cache = MockCache()
    orchestrator = AgentOrchestrator(cache=cache, ...)

    # First call - cache miss
    response1 = orchestrator.delegate("hello")

    # Second call - cache hit
    response2 = orchestrator.delegate("hello")

    assert response1.content == response2.content
```

## Cache Behavior

| Scenario | Behavior |
|----------|----------|
| Identical prompts | Cache hit |
| Same prompt, different temperature | Cache miss |
| Same prompt, different model | Cache miss |
| Context changes | Cache miss |
| After `--clear` | Cache miss |

## When Caching is Skipped

- Streaming responses (cannot cache partial responses)
- Tool calling requests
- When `--no-cache` flag is used
- Temperature > 0.9 (high randomness)
