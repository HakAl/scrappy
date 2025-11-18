 ## Provider Configuration 
 **- src/providers/base.py**

```  
class ModelType(Enum):
    """Classification of model training/tuning."""
    BASE = "base"           # Raw pretrained, no instruction tuning
    CHAT = "chat"           # Chat-tuned (conversational)
    INSTRUCT = "instruct"   # Instruction-tuned (follows structured commands)
    CODE = "code"           # Code-specialized
    REASONING = "reasoning" # Chain-of-thought / reasoning specialized
    UNKNOWN = "unknown"


  @dataclass
  class ModelInfo:
      """Metadata about a specific model."""
      id: str
      model_type: ModelType
      context_length: int
      rpd: Optional[int] = None  # Requests per day
      tpm: Optional[int] = None  # Tokens per minute
      quality: str = "good"      # good, very_good, excellent
      speed: str = "fast"        # fast, very_fast, moderate

      @property
      def is_instruction_tuned(self) -> bool:
          """Check if model is instruction-tuned (best for JSON compliance)."""
          return self.model_type == ModelType.INSTRUCT
```

```
class LLMProvider(ABC):
    # ... existing methods ...

    @abstractmethod
    def get_model_info(self, model_id: str) -> ModelInfo:
        """Get detailed information about a specific model."""
        pass

    def get_instruction_tuned_models(self) -> list[str]:
        """Get all instruction-tuned models from this provider."""
        return [
            model_id for model_id in self.available_models
            if self.get_model_info(model_id).is_instruction_tuned
        ]
```

Then in providers:

```
# In groq_provider.py
  MODELS = {
      'gemma2-9b-it': {
          'type': ModelType.INSTRUCT,  # NEW
          'rpm': 30, 'rpd': 14400, ...
      },
      'llama-3.3-70b-versatile': {
          'type': ModelType.CHAT,  # NEW
          'rpm': 30, 'rpd': 1000, ...
      },
  }
```

And orchestrator use:

```
def select_model_for_task(self, task_type: str) -> tuple[str, str]:
    """Select best provider/model for task type."""
    if task_type == "planning":
        # Prefer instruction-tuned for JSON compliance
        for provider in self.providers:
            instruct_models = provider.get_instruction_tuned_models()
            if instruct_models:
                # Pick highest RPD instruction-tuned model
                best = max(instruct_models, key=lambda m: provider.get_model_info(m).rpd or 0)
                return provider.name, best
```

Benefits:
  1. Automatic selection of instruction-tuned models for agent planning
  2. Self-documenting model capabilities
  3. Smarter fallback logic
  4. Easy to extend with new model types

---

### Native tool calling implementation -- tests/test_native_tool_calling.py

providers have supports_tool_calling() to check support

- Tool Schema Support in Base Provider

```
# src/providers/base.py
  from dataclasses import dataclass
  from typing import List, Dict, Any

  @dataclass
  class ToolCall:
      """Structured tool call from LLM."""
      id: str
      name: str
      arguments: Dict[str, Any]

  @dataclass
  class LLMResponse:
      # ... existing fields ...
      tool_calls: List[ToolCall] = None  # NEW

  class LLMProvider(ABC):
      def chat_with_tools(
          self,
          messages: list[dict],
          tools: list[dict],  # OpenAI-compatible tool schemas
          tool_choice: str = "auto",
          **kwargs
      ) -> LLMResponse:
          """Chat with native tool calling support."""
          pass
```

**- Provider implementations**

```
# src/providers/groq_provider.py
  def chat_with_tools(self, messages, tools, tool_choice="auto", **kwargs):
      response = self._client.chat.completions.create(
          messages=messages,
          tools=tools,
          tool_choice=tool_choice,
          **kwargs
      )

      tool_calls = []
      if response.choices[0].message.tool_calls:
          for tc in response.choices[0].message.tool_calls:
              tool_calls.append(ToolCall(
                  id=tc.id,
                  name=tc.function.name,
                  arguments=json.loads(tc.function.arguments)
              ))

      return LLMResponse(
          content=response.choices[0].message.content or "",
          tool_calls=tool_calls,
          # ...
      )
```

** Agent Core**

```
 # src/agent/core.py - SIMPLIFIED
  def _think(self, state):
      # Convert tool registry to OpenAI schema
      tools = self.tool_registry.to_openai_schema()

      response = self.provider.chat_with_tools(
          messages=state.messages,
          tools=tools,
          tool_choice="auto"
      )

      # No JSON parsing needed!
      if response.tool_calls:
          tool_call = response.tool_calls[0]
          return AgentAction(
              thought=response.content,
              action=tool_call.name,
              parameters=tool_call.arguments,
              is_complete=False
          )
      else:
          # Model decided not to call a tool
          return AgentAction(
              thought=response.content,
              action="complete",
              result=response.content,
              is_complete=True
          )
```


  1. Implement chat_with_tools() in specific providers (e.g., groq_provider.py)
  2. Update CodeAgent._think() to optionally use native tool calling
  3. Add provider capability detection for graceful fallback