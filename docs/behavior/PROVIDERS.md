# Providers

LLM providers are accessed through LiteLLM Router, which provides unified access to multiple providers with automatic failover.

## Architecture

```
src/scrappy/orchestrator/
  litellm_service.py      # LiteLLMService - main interface
  litellm_config.py       # Model definitions, groups
  litellm_router.py       # Router initialization

src/scrappy/providers/
  base.py                 # LLMResponse, ToolCall, enums
```

## LiteLLM Router

All LLM calls go through LiteLLM Router which handles:
- Provider abstraction
- Automatic failover between providers
- Rate limit handling
- Unified response format

```python
from scrappy.orchestrator.litellm_service import LiteLLMService

service = LiteLLMService()
response = service.chat(
    messages=[{"role": "user", "content": "Hello"}],
    model_group="fast",  # or "quality"
)
```

## Model Groups

Models are organized into two tiers:

### FAST (speed priority)
- 8B class models
- High throughput, low latency
- Best for quick tasks and high volume
- Providers: Cerebras, Groq, SambaNova

### QUALITY (reasoning priority)
- 70B+ class models
- Complex reasoning, larger context
- Best for planning and analysis
- Providers: Cerebras, Groq, Gemini

## Available Providers

| Provider | API | Models |
|----------|-----|--------|
| Cerebras | Cerebras Cloud | llama3.1-8b, llama-3.3-70b |
| Groq | Groq Cloud | llama-3.1-8b-instant, llama-3.3-70b-versatile |
| Gemini | Google AI | gemini-2.5-flash, gemini-2.0-flash |
| SambaNova | SambaNova Cloud | Meta-Llama-3.1-8B-Instruct |

## LLMResponse

Standard response format:

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

## Configuration

Providers are configured via environment variables:

```bash
# Required (at least one)
CEREBRAS_API_KEY=...
GROQ_API_KEY=...

# Optional
GEMINI_API_KEY=...
SAMBANOVA_API_KEY=...
```

## Automatic Fallback

LiteLLM Router handles failover automatically:

1. Primary model in group fails -> try next model in group
2. Context window exceeded -> escalate to quality tier
3. Rate limit hit -> try alternate provider

```python
# Example: fast tier with automatic escalation
response = service.chat(
    messages=messages,
    model_group="fast",
    # If context too large, automatically uses quality tier
)
```

## Adding Models

Models are defined in `litellm_config.py`:

```python
MODEL_DEFINITIONS = [
    ModelDefinition(
        model_id="cerebras/llama3.1-8b",
        provider="cerebras",
        group="fast",
        context_length=8192,
        rpd=14400,
    ),
    # ... more models
]
```

## Testing

Use mock service for testing:

```python
from tests.helpers import create_mock_litellm_service

mock_service = create_mock_litellm_service(responses=["test response"])
orchestrator = AgentOrchestrator(litellm_service=mock_service)
```
