# Behavior Documentation

This directory contains internal behavior specifications for contributors and developers who want to understand how Scrappy works.

For user-facing documentation, see the parent `docs/` directory.

## Document Index

### Core Components

| Document | Description |
|----------|-------------|
| [ORCHESTRATOR.md](ORCHESTRATOR.md) | Multi-provider orchestration, delegation, and coordination |
| [AGENT.md](AGENT.md) | Code agent loop, thinking, planning, and execution |
| [AGENT_VS_ORCHESTRATOR.md](AGENT_VS_ORCHESTRATOR.md) | Separation of concerns between agent and orchestrator |
| [PROVIDERS.md](PROVIDERS.md) | LLM provider adapters and integration |

### User Interface

| Document | Description |
|----------|-------------|
| [CLI.md](CLI.md) | Command-line interface, commands, and slash commands |
| [APP_FLOW.md](APP_FLOW.md) | Application startup flow and initialization |

### Agent Capabilities

| Document | Description |
|----------|-------------|
| [TOOLS.md](TOOLS.md) | Available tools (file, git, web, search, command) |
| [TASK_ROUTER.md](TASK_ROUTER.md) | Task classification and routing strategies |
| [SEMANTIC_FILE_SEARCH.md](SEMANTIC_FILE_SEARCH.md) | Semantic code search architecture |

### System Features

| Document | Description |
|----------|-------------|
| [CONTEXT.md](CONTEXT.md) | Codebase context detection (platform, project type) |
| [CACHING.md](CACHING.md) | Response caching behavior |
| [SESSION.md](SESSION.md) | Session persistence and management |

### Miscellaneous

| Document | Description |
|----------|-------------|
| [EMOJIS.md](EMOJIS.md) | Unicode emoji detection (project avoids emojis) |

## Architecture Overview

```
User Input
    |
    v
+---CLI---+
|  Command Router  |
+------------------+
    |
    v
+---Orchestrator---+
|  Provider Selection  |
|  Rate Limiting       |
|  Caching             |
+----------------------+
    |
    v
+---Agent---+
|  Think    |
|  Plan     |
|  Execute  |
+-----------+
    |
    v
+---Tools---+
|  File Ops |
|  Git      |
|  Commands |
|  Web      |
+-----------+
```

## Key Architectural Principles

From `CLAUDE.md`:

1. **Protocol-First Design** - Define interfaces before implementations
2. **Dependency Injection** - All dependencies injected via constructors
3. **SOLID Principles** - Single responsibility, open/closed, etc.
4. **Testability** - Everything designed for testing with mocks

## Quick Links

- [Main README](../../README.md)
- [Architecture Overview](../ARCHITECTURE.md)
- [Configuration Guide](../CONFIGURATION.md)
- [Quick Start](../QUICKSTART.md)
