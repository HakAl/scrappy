# Providers

Providers are adapters for different LLM APIs. Each provider implements a common interface, allowing the orchestrator to swap between them transparently.

## Architecture

```
src/providers/
  base.py                   # BaseProvider, LLMResponse
  cerebras_provider.py      # Cerebras API
  groq_provider.py          # Groq API
  gemini_provider.py        # Google Gemini API
  github_models_provider.py # GitHub Models API
  cohere_provider.py        # Cohere API
```

## Provider Protocol

All providers implement the base interface:

```python
class BaseProvider:
    name: str
    models: List[str]

    def chat(
        self,
        messages: List[Dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> LLMResponse: ...

    def is_available(self) -> bool: ...
```

## LLMResponse

Standard response format from all providers:

```python
@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str
    tokens_used: int
    finish_reason: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
```

## Available Providers

| Provider | API | Tool Calling | Streaming |
|----------|-----|--------------|-----------|
| Cerebras | Cerebras Cloud | No | Yes |
| Groq | Groq Cloud | Yes | Yes |
| Gemini | Google AI | No | Yes |
| GitHub Models | Azure OpenAI | No | Yes |
| Cohere | Cohere API | Yes | Yes |

## Tool Calling

Providers supporting native tool calling implement additional methods:

```python
class ToolCapableProvider(BaseProvider):
    def chat_with_tools(
        self,
        messages: List[Dict],
        tools: List[ToolDefinition],
        model: Optional[str] = None,
    ) -> LLMResponse: ...
```

Currently supported:
- `groq_provider.py`
- `cohere_provider.py`

## Provider Registration

Providers are registered with the `ProviderRegistry`:

```python
from src.providers import ProviderRegistry

registry = ProviderRegistry()
registry.register("cerebras", CerebrasProvider(api_key=key))
registry.register("groq", GroqProvider(api_key=key))

# Get provider by name
provider = registry.get("cerebras")

# List all providers
providers = registry.list_providers()
```

## Configuration

Providers are configured via environment variables or config files:

```bash
# Environment variables
CEREBRAS_API_KEY=...
GROQ_API_KEY=...
GEMINI_API_KEY=...
GITHUB_TOKEN=...
COHERE_API_KEY=...
```

```json
// .scrappy/config.json
{
  "providers": {
    "cerebras": {"enabled": true},
    "groq": {"enabled": true, "default_model": "llama-3.1-70b-versatile"}
  }
}
```

## Rate Limiting

Each provider tracks its own rate limits:

```python
provider = registry.get("groq")

# Check if rate limited
if provider.is_rate_limited():
    # Use fallback provider
    provider = registry.get("cerebras")
```

The orchestrator handles rate limit rotation automatically.

## Adding a New Provider

1. Create a new file in `src/providers/`
2. Inherit from `BaseProvider`
3. Implement required methods
4. Register with the `ProviderRegistry`

```python
class MyProvider(BaseProvider):
    name = "my_provider"
    models = ["model-a", "model-b"]

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = MyAPIClient(api_key)

    def chat(self, messages, model=None, **kwargs) -> LLMResponse:
        response = self.client.generate(messages, model or self.models[0])
        return LLMResponse(
            content=response.text,
            model=model,
            provider=self.name,
            tokens_used=response.usage.total_tokens,
        )

    def is_available(self) -> bool:
        return bool(self.api_key)
```

## Testing Providers

Use mock providers for testing:

```python
class MockProvider(BaseProvider):
    name = "mock"
    models = ["mock-model"]

    def __init__(self, responses: List[str]):
        self.responses = responses
        self.call_count = 0

    def chat(self, messages, **kwargs) -> LLMResponse:
        response = self.responses[self.call_count % len(self.responses)]
        self.call_count += 1
        return LLMResponse(
            content=response,
            model="mock-model",
            provider="mock",
            tokens_used=10,
        )
```

See `tests/helpers.py` for test utilities.
