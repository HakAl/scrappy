# Multi-Provider Architecture

## Overview

This system creates a **swappable orchestrator** for multi-provider LLM coordination with **automatic codebase context awareness**. The orchestrator brain can be any provider (Cerebras, Groq, Gemini), making the system usable without Claude Code or any specific subscription.

```
User / CLI Interface
    │
    ▼
Orchestrator (LiteLLM Router)
    │
    ├─── Graph Agent (LangGraph-based)
    │     ├─ Think Node: LLM reasoning
    │     ├─ Execute Node: Tool execution
    │     ├─ Verify Node: Linting/testing
    │     ├─ Confirm Node: Human-in-the-loop
    │     └─ Error Node: Recovery handling
    │
    ├─── CodebaseContext (Auto-Explore & Cache)
    │     └─ Project analysis, file index, summary generation
    │
    ├─── LiteLLM Router (Provider Selection)
    │     └─ Fast tier, Quality tier, fallback chains
    │
    ├─── Cerebras (Primary - 14,400 RPD)
    │     └─ llama3.1-8b, llama-3.3-70b, qwen-3-235b-instruct, gpt-oss-120b
    │
    ├─── Groq (Secondary - 7,000 RPD)
    │     └─ kimi-k2-instruct, llama-3.1-8b-instant, llama-3.3-70b-versatile
    │
    ├─── Gemini (Overflow - 1,650 RPD, auto-fallback)
    │     └─ gemini-2.5-flash-lite, gemini-2.0-flash, etc.
    
```

## Key Innovations

### 1. Graph-Based Agent with Human-in-the-Loop

The system uses a LangGraph-based agent that can read, write, and modify code with explicit human approval for dangerous operations:

```python
from scrappy.graph import build_graph, run_agent, AgentRunContext

# Build the graph
graph = build_graph()

# Run agent on a task
result = await run_agent(
    graph=graph,
    task="Add input validation to API endpoints",
    run_context=AgentRunContext(...),
)

# Dangerous file operations trigger confirm node with user approval
```

**Key Safety Features:**
- Human-in-the-loop approval for file writes and commands
- Undo points before changes (rollback with `/undo`)
- Path sandboxing (can't escape project directory)
- Dangerous command blocking (rm -rf, del /f, etc.)
- Docker sandbox for command execution (when available)

### 2. Swappable Orchestrator Brain

Unlike traditional setups that require a specific "master" LLM (like Claude Code), this system allows any registered provider to act as the orchestrator brain:

```python
# Default: Cerebras (best free tier)
orch = AgentOrchestrator()

# Explicit selection
orch = AgentOrchestrator(orchestrator_provider='groq')
orch = AgentOrchestrator(orchestrator_provider='gemini')

# Brain performs complex reasoning
steps = orch.plan("Add authentication to API")
answer = orch.reason("Which database for this use case?")
summary = orch.synthesize([result1, result2])
```

### 3. Automatic Context Awareness

The orchestrator can automatically learn about your codebase and inject relevant context into prompts:

```python
# Auto-explore codebase on startup
orch = AgentOrchestrator(auto_explore=True, context_aware=True)

# Context is automatically injected into prompts
result = orch.delegate('cerebras', 'Fix the auth bug', use_context=True)

# The LLM now knows:
# - Project type (CLI tool, library, web app)
# - Technologies used (Python, frameworks)
# - File structure and organization
# - Key dependencies
```

**Context Flow:**
```
User Prompt → CodebaseContext.augment_prompt() → Enhanced Prompt → LLM
                        ↓
              [Codebase Context]
              Project: Multi-provider LLM orchestrator...
              Structure: python=15, docs=8, config=3

              [User Request]
              Fix the auth bug
```

## Core Components

### 1. Provider Management (LiteLLM Router)

Providers are managed through LiteLLM Router, configured in `src/scrappy/orchestrator/litellm_config.py`. There are no individual provider classes - LiteLLM handles all provider interactions.

**Configuration:** API keys are set via environment variables:
- `CEREBRAS_API_KEY`
- `GROQ_API_KEY`
- `GEMINI_API_KEY`
- `SAMBANOVA_API_KEY`

**Model Groups:** The router organizes models into groups for different use cases:

| Group | Purpose | Models |
|-------|---------|--------|
| `fast` | Speed priority, simple tasks | llama-3.1-8b (Groq, Cerebras, SambaNova) |
| `chat` | Conversation, tool-capable | gemini-2.5-flash, kimi-k2-instruct |
| `instruct` | Agent tasks, tool use | qwen-3-235b-instruct, gpt-oss-120b, kimi-k2, gemini |

**Provider Details:**

| Provider | Daily Quota | Best For | Notes |
|----------|-------------|----------|-------|
| Cerebras | 14,400 RPD | Fast tier, high volume | Ultra-fast inference (2000+ tok/s) |
| Groq | 7,000 RPD | Tool-capable models | Hosts Kimi K2 for agent tasks |
| Gemini | 1,650 RPD | Large context, fallback | 1M token context window |
| SambaNova | ~40 RPD | Backup only | Very limited free tier |

**Fallback Behavior:** LiteLLM Router automatically fails over to the next provider when rate limits are hit.

### 2. Codebase Context (`src/context/`)

Automatic project understanding with **built-in semantic search**:
- Scans project files and structure
- Analyzes dependencies and configuration
- **Indexes code for semantic search** (automatic, built-in)
- Generates LLM summaries of the codebase
- Caches results to `.scrappy/context.json`
- Augments prompts with relevant context

#### Semantic Search Architecture

**Components:**
- **`CodeChunkerProtocol`** (`src/context/protocols.py`) - Abstracts chunking strategies
  - Implementation: `SemanticCodeChunker` - Overlapping line-based chunks
- **`SemanticSearchProtocol`** (`src/context/protocols.py`) - Abstracts search backends
  - Implementation: `LanceDBSearchProvider` - Vector + full-text hybrid search
- **`CodebaseContext`** (`src/context/codebase_context.py`) - Seamless integration
  - Automatically indexes during `explore()`
  - Falls back to keyword matching if LanceDB unavailable

**Data Flow:**
```
User runs scrappy
    ↓
CodebaseContext.explore()
    ├─ Scan files
    ├─ Analyze structure
    ├─ Read key files
    └─ Index for semantic search (if available)
        ├─ Chunk files (SemanticCodeChunker)
        └─ Build vector index (LanceDBSearchProvider)

User asks question
    ↓
CodebaseContext.get_relevant_context(query)
    ├─ Try semantic search first
    │   ├─ Vector similarity (embeddings)
    │   └─ Hybrid ranking (vector + keyword)
    └─ Fall back to keyword matching (if semantic unavailable)
        └─ Return context
```

**Key Features:**
- **Incremental updates**: Only re-indexes changed files
- **Fully automatic**: Built-in, no configuration needed
- **Security**: Path traversal prevention, project root enforcement
- **File locking**: Prevents concurrent indexing race conditions
- **Local storage**: Index stored in `.lancedb/` (never leaves machine)
- **Graceful degradation**: Falls back to keyword search if indexing fails

**Search Strategy:**
1. **Hybrid search**: Combines vector similarity (semantic meaning) with full-text search (keywords)
2. **Token budgets**: Respects max_tokens parameter to avoid overwhelming LLM context
3. **Deduplication**: Prevents duplicate chunks in results
4. **Fallback**: If hybrid search fails, falls back to vector-only search

### 3. Graph Agent (`src/scrappy/graph/`)

LangGraph-based agent for autonomous code tasks:

**Node Components:**
- `nodes/think.py` - LLM reasoning step (decide what to do next)
- `nodes/execute.py` - Tool execution (run tools from LLM response)
- `nodes/verify.py` - Linting/testing verification (ruff, mypy)
- `nodes/confirm.py` - Human-in-the-loop confirmation (dangerous operations)
- `nodes/error.py` - Error handling and recovery

**Supporting Classes:**
- `nodes/token_estimator.py` - Token counting for context management
- `nodes/context_manager.py` - Context window management and trimming
- `nodes/tool_call_processor.py` - Tool call format conversion

**Graph Structure:**
- `agent.py` - Graph construction and configuration
- `state.py` - AgentState (Pydantic) for graph state
- `edges.py` - Conditional edge logic (routing between nodes)
- `protocols.py` - Protocol definitions for dependency injection

**Features:**
- **LangGraph architecture**: Nodes connected by conditional edges
- **Streaming support**: Real-time token streaming via callbacks
- **Tool calling**: Native LLM tool calling with schema validation
- **Human-in-the-loop**: Dangerous operations require confirmation
- **Error recovery**: Automatic retry with tier escalation
- **Context management**: Token-aware context trimming and observation masking

### 4. Orchestrator (`src/scrappy/orchestrator/`)

Central coordinator, modularized into a package:

**Core Components:**
- `core.py` - Main AgentOrchestrator class
- `factory.py` - Factory methods for creation
- `delegation.py` - Delegation logic
- `provider_selector.py` - Smart provider selection
- `context_coordinator.py` - Context coordination
- `prompt_augmenter.py` - Prompt augmentation with context

**Resource Management:**
- `rate_limiter.py` - Rate limiting facade
- `rate_limiting/` - Rate limiting subsystem (storage, policy, calculator)
- `cache.py` - Response caching
- `batch_scheduler.py` - Batch operations
- `retry_orchestrator.py` - Retry strategies

**State Management:**
- `session.py` - Session persistence
- `memory.py` - Working memory
- `usage_reporter.py` - Usage tracking

**Features:**
- Registers available providers automatically
- Sets up swappable brain (default: Cerebras)
- **Manages codebase context** (auto-explore, caching)
- Provides planning, reasoning, and synthesis via brain
- Routes tasks to appropriate providers
- **Augments prompts with context** when enabled
- Tracks usage across all providers (including context usage)

Note: `src/orchestrator.py` exists as a backward-compatibility wrapper.

### 5. CLI Interface (`src/scrappy/cli/`)

Full-featured command-line interface:
- Interactive chat mode with slash commands
- One-shot commands (query, plan, reason, explore, **agent**)
- **Code agent** with human approval workflow
- Provider management (switch brain, list models)
- Context management (explore, refresh, clear, toggle)
- Usage monitoring and status display
- Built with Click for excellent UX

### 6. Platform Abstraction (`src/scrappy/platform/`)

Cross-platform support layer:
- `detection.py` - Detects OS, shell type, capabilities
- `translation.py` - Translates commands between platforms (e.g., `ls` vs `dir`)
- `validation.py` - Validates commands for current platform
- `executors.py` - Platform-specific command execution strategies
- `factory.py` - Factory for platform-aware components

**Why it exists:** Scrappy runs on Windows, macOS, and Linux. Commands like `ls`, `cat`, and path separators differ. This layer abstracts those differences so the agent and CLI work consistently across platforms.

### 7. Infrastructure Layer (`src/scrappy/infrastructure/`)

Cross-cutting concerns and abstractions:

**Configuration (`config/`):**
- Protocol-based configuration framework
- Environment-specific config (dev/test/prod)
- Validation with clear error messages
- See [CONFIGURATION.md](CONFIGURATION.md)

**Persistence (`persistence/`):**
- `protocols.py` - Storage abstraction protocol
- `json_persistence.py` - JSON file-based persistence
- Enables swapping storage backends (file, database, etc.)

**Logging (`logging/`):**
- `protocols.py` - Logging abstraction
- `logger.py` - Logger implementation
- `formatters.py` - Output formatters
- `registry.py` - Logger registry for component-specific loggers

**File System (`file_system.py`):**
- Abstraction over file operations
- Enables testing without touching real filesystem
- Path normalization and security checks

### 8. Prompt System (`src/scrappy/prompts/`)

Structured prompt generation:
- `factory.py` - Creates prompts for different contexts
- `builders/` - Prompt builders for specific use cases
- `templates/` - Reusable prompt templates

**Why it exists:** Different tasks require different prompt structures. The prompt system ensures consistent, well-structured prompts for planning, reasoning, tool use, and code generation.

## Usage Patterns

### Pattern 1: Context-Aware Development

```python
from src.orchestrator import AgentOrchestrator

# Auto-explore codebase on startup
orch = AgentOrchestrator(auto_explore=True, context_aware=True)

# All queries now include project context
result = orch.delegate(
    'cerebras',
    'How should I implement caching here?',
    use_context=True  # Includes project knowledge
)

# The response will be informed by:
# - Project architecture
# - Existing patterns
# - Dependencies available
```

### Pattern 2: Autonomous Operation

```python
from src.orchestrator import AgentOrchestrator

# Cerebras as brain
orch = AgentOrchestrator()

# Brain plans the task
steps = orch.plan("Build REST API with authentication")

# Execute each step
for step in steps:
    if step['provider_type'] == 'fast':
        result = orch.delegate_smart(step['description'], task_type='fast')
    else:
        result = orch.delegate_smart(step['description'], task_type='quality')
```

### Pattern 3: Simple Delegation

```python
# Direct provider call
result = orch.delegate('cerebras', 'Summarize this text: ...')
print(result.content)
```

### Pattern 4: Smart Delegation

```python
# Auto-selects best provider for task type
result = orch.delegate_smart(
    'What are the benefits of microservices?',
    task_type='fast'  # Uses Cerebras (14,400 RPD)
)
```

### Pattern 5: Complex Reasoning

```python
# Brain analyzes with evidence
answer = orch.reason(
    "Should we use JWT or sessions?",
    context="Building mobile app backend",
    evidence=[
        "Need offline support",
        "Multiple devices per user",
        "Token refresh complexity"
    ]
)
```

### Pattern 6: Multi-Agent Synthesis

```python
# Get perspectives from multiple models
result1 = orch.delegate('cerebras', question, model='llama3.1-8b')
result2 = orch.delegate('groq', question, model='llama-3.3-70b-versatile')
result3 = orch.delegate('gemini', question)

# Brain synthesizes
summary = orch.synthesize(
    [result1, result2, result3],
    "Identify common themes and key differences:"
)
```

### Pattern 7: Graph Agent with Human Approval

The CLI handles agent execution. Programmatic usage:

```python
from scrappy.graph import build_graph, run_agent, AgentRunContext
from scrappy.undo import create_undo_point, undo, UndoError

# Create safety undo point
try:
    undo_state = create_undo_point()
except UndoError as e:
    print(f"Warning: Could not create undo point: {e}")

# Build and run agent
graph = build_graph()
result = await run_agent(
    graph=graph,
    task="Add error handling to all API endpoints",
    run_context=AgentRunContext(...),
)

# Rollback if needed
if not result.success:
    undo(n=1)
```

**CLI Usage:**
```bash
# Interactive mode
scrappy
You: /agent Add input validation

# The CLI will:
# 1. Create an undo point
# 2. Run the agent with human approval for each action
# 3. Allow rollback via /undo if needed
```

## Adding New Providers

Providers are added by configuring them in the LiteLLM Router. No custom provider classes needed.

### Step 1: Add API Key Environment Variable

```python
# In src/scrappy/orchestrator/litellm_config.py, add to build_model_list():
newprovider_key = api_key_service.get_key("NEWPROVIDER_API_KEY")
```

### Step 2: Add Models to Appropriate Groups

```python
# Add to the appropriate model group (fast, chat, or instruct)
if newprovider_key:
    model_list.append({
        "model_name": "fast",  # or "chat" or "instruct"
        "litellm_params": {
            "model": "newprovider/model-name",  # LiteLLM format
            "api_key": newprovider_key,
        },
        "tpm": 60000,  # tokens per minute
        "rpm": 30,     # requests per minute
    })
```

### Step 3: Add Metadata for Status Display (Optional)

```python
# In MODEL_METADATA dict for /status and /limits commands
"newprovider/model-name": ModelMetadata(
    model_id="newprovider/model-name",
    provider="newprovider",
    group="fast",
    context_length=8192,
    speed=SpeedRank.FAST,
    quality=QualityRank.GOOD,
    rpd=1000,
    tpm=60000,
),
```

LiteLLM supports 100+ providers out of the box. Check [LiteLLM docs](https://docs.litellm.ai/docs/providers) for the model format.

## Rate Limit Strategy

### Combined Capacity

- **Cerebras**: 14,400 RPD
- **Groq**: 7,000 RPD
- **Gemini**: 1,650 RPD
- **Total**: ~23,000 requests/day

### Routing Priority

1. **Cerebras** (primary) - highest quota, fast inference
2. **Groq** (secondary) - good variety, proven reliability
3. **Gemini** (overflow) - auto-fallback handles limits
4. **Cohere** (embeddings only) - preserve monthly quota

### Best Practices

1. **Use Cerebras for orchestrator brain** - 14,400 RPD is plenty
2. **Route simple tasks to Cerebras** - maximize throughput
3. **Reserve Groq for variety** - different models for different needs
4. **Let Gemini handle overflow** - auto-fallback is smart
5. **Avoid Cohere for chat** - 1K/month is too limited

## Error Handling

The system handles:
- Missing API keys (provider won't register, skipped gracefully)
- Rate limit errors (Gemini auto-fallback)
- Model unavailability (checked at runtime)
- JSON parsing failures (fallback to raw response)


## Testing

```bash
# Run all tests
pytest tests/

# Run specific test modules
pytest tests/graph/           # Agent graph tests
pytest tests/orchestrator/    # Orchestrator tests
pytest tests/cli/             # CLI tests
```

## Project Structure

```
src/scrappy/
├── __init__.py
├── agent_config.py           # Agent configuration
├── orchestrator_adapter.py   # Orchestrator adapter for graph agent
├── graph/                    # LangGraph-based agent
│   ├── agent.py              # Graph construction
│   ├── state.py              # AgentState definition
│   ├── edges.py              # Conditional edge logic
│   ├── protocols.py          # Protocol definitions
│   ├── tools.py              # Tool adapter
│   ├── tracing.py            # Langfuse observability
│   ├── run_context.py        # Agent run context
│   ├── nodes/                # Graph nodes
│   │   ├── think.py          # LLM reasoning
│   │   ├── execute.py        # Tool execution
│   │   ├── verify.py         # Linting/testing
│   │   ├── confirm.py        # Human confirmation
│   │   ├── error.py          # Error recovery
│   │   └── ...
│   └── ...
├── orchestrator/             # LiteLLM-based orchestration
│   ├── core.py               # Main orchestrator class
│   ├── factory.py            # Factory methods
│   ├── litellm_service.py    # LiteLLM integration
│   ├── litellm_config.py     # Router configuration
│   ├── delegation.py         # Delegation logic
│   ├── rate_limiting/        # Rate limit subsystem
│   ├── cache.py              # Response caching
│   └── ...
├── agent_tools/              # Tool implementations
│   ├── tools/                # Individual tools
│   │   ├── file_tools.py     # read_file, write_file, list_files
│   │   ├── git_tools.py      # git operations
│   │   ├── command_tool.py   # run_command
│   │   ├── search_tools.py   # search_code
│   │   └── ...
│   └── components/           # Tool components
├── context/                  # Context management
│   ├── codebase_context.py   # Main context manager
│   ├── semantic_manager.py   # Semantic search coordination
│   ├── semantic/             # Semantic search subsystem
│   └── ...
├── cli/                      # CLI implementation
│   ├── core.py               # Main CLI class
│   ├── session_context.py    # Session management
│   └── ...
├── infrastructure/           # Infrastructure layer
│   ├── exceptions.py         # Exception hierarchy
│   ├── persistence/          # Persistence abstractions
│   ├── logging/              # Logging system
│   └── ...
├── platform/                 # Platform abstraction
│   ├── detection.py          # Platform detection
│   └── ...
└── prompts/                  # Prompt system
    ├── factory.py            # Prompt factory
    └── ...

docs/
├── ARCHITECTURE.md           # This file
├── CLI.md                    # CLI reference guide
└── behavior/                 # Internal behavior specs
```

## Context Caching

The system maintains a cache file (`.scrappy/context.json`) that stores:

```json
{
  "explored_at": "2025-01-15T10:30:00",
  "summary": "Multi-provider LLM orchestrator with...",
  "structure": {
    "total_files": 25,
    "by_type": {"python": 15, "docs": 8, "config": 2},
    "has_readme": true,
    "directories": ["src", "docs", "examples"]
  },
  "file_index": {
    "python": ["src/orchestrator.py", "src/cli.py", ...],
    "docs": ["README.md", "docs/CLI.md", ...]
  }
}
```

This cache:
- Survives session restarts
- Auto-loads on orchestrator initialization
- Can be refreshed with `orch.explore_project(force=True)`
- Cleared with `orch.context.clear_cache()`
