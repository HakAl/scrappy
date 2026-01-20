# CLI

The command-line interface provides interactive mode with a Textual TUI and one-shot commands for undo operations.

## Entry Points

```
scrappy -> src/scrappy/cli/commands.py -> cli() -> interactive_mode()
```

The CLI uses Click for command parsing, Rich for output formatting, and Textual for the TUI.

## One-Shot Commands

Run a single command and exit:

| Command | Purpose | Key Options |
|---------|---------|-------------|
| `version` | Show scrappy version | None |
| `undo` | Undo agent runs | `[n]` count, `--force` |
| `undo-list` | List available undo points | None |
| `undo-gc` | Clean up old undo points | `--keep N` |

## Global Options

```
--resume, -r          Resume from last saved session
--no-save             Disable auto-save on exit
--help                Show help
--version             Show version
```

## Interactive Mode

Start with `scrappy` (no arguments).

### Slash Commands

**Session Management**
- `/quit`, `/exit`, `/q` - Exit the application
- `/session` - Manage session state (show/save/load/clear)
- `/context` - View/manage codebase context
- `/cache` - View cache statistics
- `/limits` - View rate limit status

**Display Commands**
- `/help` - Show available commands
- `/status` - Show system status
- `/usage` - Show usage statistics
- `/models` - List available models
- `/model` - Show/switch mode (fast/chat/instruct)

**Task Commands**
- `/plan` - Create a task plan
- `/tasks` - View current plan progress
- `/reason` - Reason with evidence
- `/agent` - Run the code agent
- `/autoexec` - Toggle auto-execute for plan tasks

**Query Commands**
- `/smart` - Research-first query (uses tools to gather context)
- `/explore` - Explore a codebase

**State Commands**
- `/clear` - Clear conversation history
- `/history [n]` - Show last n messages (default: 10)
- `/verbose`, `/v` - Toggle verbose output mode
- `/ml` - Toggle multiline input mode

**Setup Commands**
- `/setup` - Configure API keys via interactive wizard

## Architecture

```
src/scrappy/cli/
  core.py                    # Main CLI class
  commands.py                # Click command definitions
  command_router.py          # Routes slash commands to handlers
  interactive.py             # Interactive mode main loop
  textual_interactive.py     # Textual TUI wrapper
  input_handler.py           # Input parsing and multiline handling
  display.py                 # Display protocol and handlers
  display_rich.py            # Rich-formatted display (tables, panels)
  session_context.py         # Shared session state
  state_manager.py           # Plan and task state management
  command_history.py         # Command history tracking
  unified_io.py              # Abstracted IO interface
  config_factory.py          # Configuration management
  cli_config.py              # CLI configuration dataclass
  textual/
    app.py                   # Main Textual app (ScrappyApp)
    bridge.py                # Thread-safe async bridge
    langgraph_bridge.py      # LangGraph integration for unified chat
    messages.py              # Textual message types
    status_components.py     # Status bar components (MetricsStatus, etc.)
  screens/
    main_screen.py           # Main chat screen (MainAppScreen)
    chat_layout.py           # Chat UI layout component
    wizard_screen.py         # Setup wizard screen
  widgets/
    task_progress.py         # Task progress display
    selectable_log.py        # Scrollable log with text selection
  validators/                # Input validators
  error_recovery/            # Error handling and recovery
  protocols.py               # Protocol definitions
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

### Textual TUI Architecture

The interactive mode uses Textual for a modern terminal UI:

- **ScrappyApp** (`textual/app.py`): Main application, manages screens and global state
- **MainAppScreen** (`screens/main_screen.py`): Primary chat interface
- **ChatLayout** (`screens/chat_layout.py`): Reusable layout with output, input, and status bar
- **LangGraphBridge** (`textual/langgraph_bridge.py`): Unified chat routing through LangGraph
- **StatusBar** (`textual/status_components.py`): Dynamic status display (metrics, progress, activity)

### Input Flow

1. User types in TextArea widget
2. InputHandler parses input (command vs. chat)
3. Commands go to CommandRouter
4. Chat messages go through LangGraphBridge to agent
5. Agent decides tool usage via LangGraph
6. Output routed back through thread-safe bridges

### Model Tiers

The CLI uses a tiered model selection system:

| Tier | Description | Use Case |
|------|-------------|----------|
| `fast` | 8B models | High throughput, quick responses |
| `chat` | 70B models | Conversational quality |
| `instruct` | Instruction-tuned | Agent/tool use, code generation |

Switch with `/model fast`, `/model chat`, or `/model instruct`.
