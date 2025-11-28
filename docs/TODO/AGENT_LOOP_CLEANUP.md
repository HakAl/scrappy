# **Eliminate the Hacks:** Move `complete` and `run_command` out of `agent_loop.py` and into proper `ToolBase` classes.


### Formalize the "Hacked" Tools
Create proper classes for the tools you were hardcoding. This allows the registry to generate their schemas automatically.

**File:** `agent_tools/tools/control_tools.py` (New file)
```python
from .base import ToolBase, ToolParameter, ToolResult, ToolContext

class CompleteTool(ToolBase):
    @property
    def name(self) -> str:
        return "complete"

    @property
    def description(self) -> str:
        return "Mark the task as complete and provide final result."

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter("result", str, "Final result or summary of completed task")
        ]

    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        # distinct "completion" signal
        return ToolResult(True, kwargs["result"], metadata={"stop_loop": True})

# CommandTool in tools/command_tool.py
```

### Clean up `agent_loop.py`

Now we remove the hacks. The logic moves to where you **initialize** the agent/registry (usually `__init__` or a `setup()` method), ensuring the loop is clean.

**1. Update Registry Initialization (e.g. inside `AgentLoop.__init__`):**
```python
# Import the new classes
from .tools.control_tools import CompleteTool
from .tools.command_tool import CommandTool # Assuming this exists
from .tools.meta_tools import RunParallelTool

# ... inside your init ...
self._tool_registry = ToolRegistry() # or however you init it

# Register standard tools
self._tool_registry.register(ReadFileTool())
self._tool_registry.register(ListFilesTool())
# ... etc ...

# Register Control Tools (Replacing the hacks)
self._tool_registry.register(CommandTool()) 
self._tool_registry.register(CompleteTool())

# Register Meta Tool (Pass registry reference!)
self._tool_registry.register(RunParallelTool(self._tool_registry))
```

**2. Update the Delegate Method:**
Now `_delegate_with_tools` is pure and just passes the registry's output.

```python
    def _delegate_with_tools(
        self, provider: str, prompt: str, system_prompt: str
    ) -> Any:
        """Delegate to orchestrator with native tool calling."""
        
        # CLEAN: No manual appending. The registry acts as the source of truth.
        tools = self._tool_registry.to_openai_schema()

        return self._orchestrator.delegate_with_tools(
            provider_name=provider,
            prompt=prompt,
            tools=tools,
            system_prompt=system_prompt,
            max_tokens=self._config.default_max_tokens,
            temperature=self._config.default_temperature,
            tool_choice="auto",
        )
```