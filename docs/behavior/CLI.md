# CLI

The command-line interface provides two modes of operation: one-shot commands and interactive mode.

## Entry Points

```
scrappy.py -> src/cli/commands.py -> cli() -> interactive_mode()
```

The CLI uses Click for command parsing and Rich for output formatting.

## One-Shot Commands

Run a single command and exit:

| Command | Purpose | Key Options |
|---------|---------|-------------|
| `query` | Send a query to the orchestrator | `--provider`, `--model`, `--temperature`, `--max-tokens`, `--with-context`, `--brain` |
| `plan` | Create a task plan | `--max-steps` (default: 5) |
| `reason` | Reason about a question with evidence | `--context`, `--evidence` (multiple) |
| `smart` | Research-first query using tools | None |
| `status` | Show system status | None |
| `providers` | List available providers | None |
| `provider_info` | Show detailed provider selection info | `--verbose` |
| `models` | List available models | provider (optional) |
| `usage` | Show usage statistics | None |
| `interactive` | Start interactive chat mode | `--resume` |
| `context` | Show and manage codebase context | `--clear`, `--refresh` |
| `explore` | Explore and learn about a codebase | path, `--save` |
| `agent` | Run code agent to complete a task | `--dry-run`, `--no-checkpoint`, `--auto-confirm`, `--max-iterations` |

## Global Options

```
--brain, -b           Orchestrator brain provider (cerebras, groq, gemini)
--auto-explore, -a    Automatically explore codebase on startup
--no-context          Disable context-aware prompts
--resume, -r          Resume from last saved session
--no-save             Disable auto-save on exit
--show-providers, -p  Show detailed provider status on startup
--verbose-selection   Show verbose provider selection logic
```

## Interactive Mode

Start with `scrappy` (no arguments) or `scrappy interactive`.

### Slash Commands

**Session Management**
- `/quit`, `/exit`, `/q` - Exit the application
- `/session` - Manage session state
- `/context` - View/manage codebase context
- `/cache` - View cache statistics
- `/limits` - View rate limit status

**Display Commands**
- `/help` - Show available commands
- `/status` - Show system status
- `/providers` - List providers
- `/brain` - Show current brain provider
- `/usage` - Show usage statistics
- `/models` - List available models

**Task Commands**
- `/plan` - Create a task plan
- `/reason` - Reason with evidence
- `/agent` - Run the code agent
- `/task` - Execute a task
- `/batch` - Batch operations

**Query Commands**
- `/smart` - Research-first query
- `/research` - Deep research query
- `/stream` - Streaming response
- `/chat` - Chat mode

## Architecture

```
src/cli/
  core.py              # Main CLI class
  commands.py          # Click command handlers
  command_router.py    # Routes slash commands to handlers
  display.py           # Output formatting
  session.py           # Session persistence
  tasks.py             # Task execution (planning, reasoning)
  multiprovider.py     # Multi-provider coordination
  smart_query.py       # Smart query with research
  agent_manager.py     # Code agent management
  textual_app.py       # Textual UI (Rich-based TUI)
  protocols.py         # Protocol definitions
```

### Command Router

The `CommandRouter` class in `command_router.py` dispatches slash commands to appropriate handlers:

```python
router = CommandRouter(
    orchestrator=orchestrator,
    display=display,
    session_manager=session_manager,
    # ... other handlers
)

result = router.route("/plan create a REST API")
```

### Display Protocol

All output goes through the `DisplayProtocol`, enabling:
- Rich console output in production
- Captured output in tests
- Null output for silent operation

```python
class DisplayProtocol(Protocol):
    def print(self, message: str) -> None: ...
    def print_error(self, message: str) -> None: ...
    def print_success(self, message: str) -> None: ...
```
