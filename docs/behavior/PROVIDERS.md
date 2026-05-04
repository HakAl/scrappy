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

## Self-Healing Fallback

Scrappy uses deterministic orchestrator-level fallback for normal model
completion entry points. The orchestrator selects a concrete model from the
requested tier, runs the request, classifies provider failures, marks unhealthy
models or providers in process-local health state, and selects the next eligible
model.

Fallback currently covers:

- `AgentOrchestrator.delegate`
- `AgentOrchestrator.delegate_structured`
- `AgentOrchestrator.stream_completion_with_fallback`
- `AgentOrchestrator.delegate_async`
- `AgentOrchestrator.stream_delegate` when a model selector is configured

Fallback is attempted only for retryable provider failures such as rate limits,
auth/config failures, payment/quota failures, network failures, timeouts,
server errors, and deprecated or unavailable models. Content refusal and
unknown provider failures surface immediately without marking health.

Streaming fallback is allowed only before user-visible output or tool-call
fragments have been yielded. If a provider fails after content or tool-call
fragments reach the user, Scrappy re-raises the original error and includes
partial output metadata in the exception context.

Successful fallback is visible in two places:

- The TUI metrics/status line shows the fallback trace, for example
  `cerebras(rate_limit)->groq: llama-3.1-8b-instant`.
- The structured logger emits a `provider_fallback` event with the failed and
  successful model/provider, failure kind, retry-after value, scope, attempt
  count, request id, and elapsed time.

Selection exhaustion raises `SelectionExhaustedError`. Its `failure_summary`
maps concrete model ids to failure records containing the failure kind, provider,
retry-after value, and message. The user-facing suggestion lists affected
models and only mentions waiting for rate-limit failures or setup/billing work
for auth and payment failures.

Process-local counters are maintained for:

- `provider_fallbacks_total{from_provider,to_provider,kind}`
- `provider_failure_unknown_total{provider,error_type}`
- `provider_selection_exhausted_total{selection_type}`

Counters are exposed through `get_provider_fallback_metrics_snapshot()` so
operators can wire them into their preferred dashboard or monitoring system.

The health state and counters are process-local and reset when the process
restarts.

## Explicit Out Of Scope Paths

The following paths intentionally bypass orchestrator-level self-healing
fallback:

- `batch_delegate`
- `batch_delegate_async`
- `multi_provider_query_async`
- `stream_delegate` when no model selector is configured and it falls back to
  legacy provider-hint routing

Batch and multi-provider calls preserve caller-supplied routing because each
provider or batch item is treated as an independent target. Legacy no-selector
streaming cannot mark concrete model health because no concrete model was
selected by the orchestrator.

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
