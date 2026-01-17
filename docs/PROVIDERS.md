# LLM Providers

Scrappy uses LiteLLM Router to access multiple LLM providers through a unified interface.

## Architecture

```
LiteLLMService
    |
    +-- LiteLLM Router
    |       +-- Model Groups (fast/quality)
    |       +-- Automatic Failover
    |       +-- Rate Limit Handling
    |
    +-- Model Definitions (litellm_config.py)
```

## Model Groups

Models are organized into two tiers with automatic selection based on task complexity:

### FAST (speed priority)
- 8B class models
- High throughput, low latency
- Best for quick tasks and high volume

### QUALITY (reasoning priority)
- 70B+ class models
- Complex reasoning, larger context
- Best for planning and analysis

## Available Providers

| Provider | Environment Variable | Models |
|----------|---------------------|--------|
| **Cerebras** | `CEREBRAS_API_KEY` | llama3.1-8b, llama-3.3-70b |
| **Groq** | `GROQ_API_KEY` | llama-3.1-8b-instant, llama-3.3-70b-versatile |
| **Gemini** | `GEMINI_API_KEY` | gemini-2.5-flash, gemini-2.0-flash |
| **SambaNova** | `SAMBANOVA_API_KEY` | Meta-Llama-3.1-8B-Instruct |

## Configuration

Set API keys as environment variables:

```bash
# Required (at least one)
export CEREBRAS_API_KEY=your_key
export GROQ_API_KEY=your_key

# Optional
export GEMINI_API_KEY=your_key
export SAMBANOVA_API_KEY=your_key
```

Or use a `.env` file:

```bash
CEREBRAS_API_KEY=your_key
GROQ_API_KEY=your_key
GEMINI_API_KEY=your_key
SAMBANOVA_API_KEY=your_key
```

## LLMResponse Format

All providers return a standard response:

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

## Tool Calling

Tool calling is supported through LiteLLM's native tool calling:

```python
response = service.chat_with_tools(
    messages=messages,
    tools=tool_definitions,
    model_group="quality",
)

if response.tool_calls:
    for tool_call in response.tool_calls:
        print(f"Tool: {tool_call.name}")
        print(f"Args: {tool_call.arguments}")
```

## Automatic Fallback

LiteLLM Router handles failover automatically:

1. **Within group**: If primary model fails, tries next model in same group
2. **Escalation**: If context window exceeded in fast tier, escalates to quality
3. **Rate limits**: Automatically rotates to available providers

## Rate Limits

| Provider | Daily Quota | Best For |
|----------|------------|----------|
| Cerebras | 14,400 RPD | Fast tier, highest quota |
| Groq | 7,000 RPD | Fast and quality tiers |
| Gemini | varies | Quality tier, large context |
| SambaNova | varies | Fast tier alternative |

## Adding a New Provider

1. Add model definition in `src/scrappy/orchestrator/litellm_config.py`:

```python
ModelDefinition(
    model_id="newprovider/model-name",
    provider="newprovider",
    group="fast",  # or "quality"
    context_length=8192,
    rpd=10000,
),
```

2. Ensure LiteLLM supports the provider (check [LiteLLM docs](https://docs.litellm.ai/docs/providers))

3. Set the API key environment variable

## Testing

Use mock service for testing without API calls:

```python
from tests.helpers import create_mock_litellm_service

mock_service = create_mock_litellm_service(
    responses=["mocked response"]
)
orchestrator = AgentOrchestrator(litellm_service=mock_service)
```
