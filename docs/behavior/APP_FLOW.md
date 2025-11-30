# Startup Flow

## Code Paths

### One-off Command Execution
```
scrappy.py -> commands.py -> [command handler]
```

### Interactive Mode (Textual App)
```
scrappy.py
  -> src/cli/commands.py: cli()
  -> cli_instance.interactive_mode()
  -> src/cli/core.py: interactive_mode()
  -> TextualInteractiveMode()
  -> src/cli/textual_interactive.py: __init__()
  -> src/cli/interactive.py: __init__() (runs chat loop)
  -> ScrappyApp created
  -> textual_interactive.py: run()
```

## Flow Diagram

```
graph TD
    %% Define styles
    classDef file fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    classDef func fill:#fff9c4,stroke:#fbc02d,stroke-width:2px
    classDef classObj fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px

    %% Entry Point
    Start("Start") --> A["scrappy.py"]:::file

    %% CLI Phase
    subgraph CLI_Setup ["CLI Bootstrap"]
        A -->|Calls| B["commands.py"]:::file
        B -->|executes| C("cli function"):::func
        C -->|invokes| D("cli_instance.interactive_mode"):::func
    end

    %% Core Logic Phase
    subgraph Core_Logic ["Core Logic"]
        D -->|Calls| E["core.py"]:::file
        E -->|executes| F("interactive_mode"):::func
        F -->|Instantiates| G["TextualInteractiveMode"]:::classObj
    end

    %% TUI Initialization Phase
    subgraph TUI_Init ["TUI Initialization"]
        G -->|"__init__"| H["textual_interactive.py"]:::file
        H -->|"super().__init__"| I["interactive.py"]:::file
        I -->|Setup| J("Initialize Chat Loop/State"):::func
    end

    %% Execution Phase
    subgraph App_Runtime ["App Runtime"]
        H -->|Creates| K["ScrappyApp Instance"]:::classObj
        K -->|Calls| L("textual_interactive.py: run"):::func
        L --> M(("Event/Chat Loop")):::func
    end
```

## Sequence Diagram

```
sequenceDiagram
    participant S as scrappy.py
    participant CMD as commands.py
    participant CORE as core.py
    participant TEXT as textual_interactive.py
    participant BASE as interactive.py
    participant APP as ScrappyApp

    S->>CMD: Calls cli()
    CMD->>CORE: cli_instance.interactive_mode()
    CORE->>TEXT: Instantiate TextualInteractiveMode()
    activate TEXT
    TEXT->>BASE: super().__init__()
    note right of BASE: Sets up Chat Loop State
    TEXT->>APP: Create ScrappyApp
    TEXT->>APP: run()
    activate APP
    note right of APP: TUI / Interactive Mode Active
    deactivate APP
    deactivate TEXT
```

## Initialization Details

### scrappy.py

1. Sets environment variables (gRPC, ONNX, UTF-8)
2. Configures debug logging to `.scrappy/debug.log`
3. Imports and calls `main()` from `src.cli`

### commands.py

1. Parses CLI arguments with Click
2. Loads configuration from `.scrappy/` directory
3. Creates orchestrator with selected providers
4. Routes to appropriate command handler

### core.py (interactive_mode)

1. Creates display manager
2. Initializes session manager
3. Creates command router
4. Instantiates TextualInteractiveMode

### textual_interactive.py

1. Creates ScrappyApp (Textual application)
2. Sets up input/output bindings
3. Starts the event loop

## Key Classes

| Class | File | Responsibility |
|-------|------|----------------|
| `CLI` | `core.py` | Main CLI orchestration |
| `TextualInteractiveMode` | `textual_interactive.py` | TUI mode handler |
| `ScrappyApp` | `textual_app.py` | Textual application |
| `CommandRouter` | `command_router.py` | Slash command dispatch |
| `CLIDisplay` | `display.py` | Output formatting |
| `CLISessionManager` | `session.py` | Session persistence |
