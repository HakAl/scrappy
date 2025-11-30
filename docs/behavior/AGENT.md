# Agent

The Code Agent is an autonomous system that can analyze codebases, make changes, and execute tasks using available tools.

## Architecture

```
src/agent/
  core.py                 # Main CodeAgent class
  agent_loop.py           # Think-plan-execute loop
  protocols.py            # Agent protocols
  action_executor.py      # Executes agent actions
  response_parser.py      # Parses LLM responses into actions
  tool_runner.py          # Runs tools on behalf of agent
  provider_strategy.py    # Provider selection for agent tasks
  safety_checker.py       # Safety validation
  checkpoint.py           # Git checkpoint creation/rollback
  audit.py                # Audit logging
  duplicate_detector.py   # Detects repeated/stuck actions
  denial_handler.py       # Handles user denial of actions
  ui.py                   # User interaction components
  types.py                # Type definitions
```

### Execution Flow

```
Main Thread                           Worker Thread (Callback)
===========                           ========================
/agent command
    |
    v
agent_manager.run_agent()
    |
    v
CodeAgent.__init__()
    |
    +---> Orchestrator created
    |         |
    |         v
    |     context.start_background_initialization()
    |         |
    |         v
    |     SemanticSearchInitializer.start()
    |         |
    |         v
    |     wait_with_callback() ---------> Creates Thread
    |                                         |
    v                                         v
CodeAgent.run()                         _on_semantic_search_ready()
    |                                         |
    v                                         v
enable_auto_save()                      _index_for_semantic_search()
    |                                         |
    v                                         v
_register_crash_handlers()              [If any audit logging triggered]
    |                                         |
    v                                         v
signal.signal()                          signal.signal()
```

### Core Components

| Component | Responsibility |
|-----------|----------------|
| `CodeAgent` | Main agent loop - thinks, plans, executes |
| `ActionExecutor` | Executes parsed actions via tools |
| `ResponseParser` | Converts LLM output to structured actions |
| `ToolRunner` | Runs registered tools with context |
| `SafetyChecker` | Validates actions before execution |
| `Checkpoint` | Creates/restores git checkpoints |

## Agent Loop

```
1. Receive task from user
2. Think about approach (planning phase)
3. Select action to take
4. Execute action via tools
5. Observe result
6. Repeat until task complete or max iterations
```

### Think-Plan-Execute Cycle

```python
while not done and iterations < max_iterations:
    # Think: Analyze current state
    thought = agent._think(context)

    # Plan: Decide next action
    action = agent._plan_action(thought)

    # Execute: Run the action
    result = agent._execute_action(action)

    # Observe: Update context with result
    context.add_observation(result)
```

## System Prompt

The agent uses context-aware prompts built from:

1. **Platform detection** - Windows cmd.exe vs Unix shells
2. **Project type** - Python, Java, Node.js specific guidance
3. **Tool capabilities** - What tools can actually do
4. **Safety rules** - Platform-specific gotchas

Prompt building is handled by `src/prompts/` - see [PROMPTS.md](PROMPTS.md) for details.

## Response Parsing

The agent communicates via structured output that gets parsed:

### UnifiedResponseParser

Handles multiple response formats:
- JSON action blocks
- Native tool calls (provider-specific)
- Freeform text with action markers

### NativeToolCallParser

For providers supporting native tool calling:
- Groq
- Cohere

## Safety Features

### Pre-execution Checks

1. **Command validation** - Blocks dangerous commands (rm -rf, format, etc.)
2. **Path validation** - Prevents access outside project directory
3. **Interactive command detection** - Warns about commands requiring user input

### Git Checkpoints

Before making changes, the agent can:
1. Create a git checkpoint (commit or stash)
2. Execute changes
3. Rollback if needed

```python
checkpoint = Checkpoint(project_path)
checkpoint.create("Before agent changes")

# ... agent makes changes ...

if something_went_wrong:
    checkpoint.rollback()
```

### Audit Logging

All agent actions are logged for review:
- Tool invocations
- File modifications
- Command executions

## Configuration

### Max Iterations

Limits how many think-plan-execute cycles:

```bash
scrappy agent "fix the bug" --max-iterations 10
```

### Dry Run Mode

Preview what the agent would do without executing:

```bash
scrappy agent "refactor this file" --dry-run
```

### Auto-confirm

Skip confirmation prompts for file changes:

```bash
scrappy agent "update imports" --auto-confirm
```

## Integration Points

### Provider Integration

```python
# Providers supporting tool calling
src/providers/cohere_provider.py  -> chat_with_tools()
src/providers/groq_provider.py    -> chat_with_tools()
```

### Orchestrator Integration

```python
# Orchestrator delegates to agent
src/orchestrator_adapter.py -> delegate_with_tools()
```

### Tool Registry Integration

```python
# Agent uses registered tools
agent = CodeAgent(
    orchestrator=orchestrator,
    tool_registry=registry,
    checkpoint=checkpoint,
)
```

## Testing

The agent is designed for dependency injection:

```python
def test_agent_thinks():
    mock_orchestrator = MockOrchestrator()
    mock_registry = MockToolRegistry()

    agent = CodeAgent(
        orchestrator=mock_orchestrator,
        tool_registry=mock_registry,
    )

    thought = agent._think("analyze this code")
    assert thought.reasoning != ""
```

See `tests/test_agent_*.py` for examples.
