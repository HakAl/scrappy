# Multi-Provider Architecture

## Overview

This system creates a **swappable orchestrator** for multi-provider LLM coordination with **automatic codebase context awareness**. The orchestrator brain can be any provider (Cerebras, Groq, Gemini), making the system usable without Claude Code or any specific subscription.

```
User / CLI Interface
    │
    ▼
AgentOrchestrator
    │
    ├─── CodeAgent (Tool-based Code Writing)
    │     ├─ Planner: Gemini (smart reasoning)
    │     ├─ Executor: Cerebras (fast operations)
    │     ├─ Tools: read_file, write_file, run_command, etc.
    │     ├─ Human-in-the-loop approval
    │     └─ Safety: sandboxing, audit logging, git checkpoints
    │
    ├─── CodebaseContext (Auto-Explore & Cache)
    │     └─ Project analysis, file index, summary generation
    │
    ├─── Brain (Swappable: Cerebras/Groq/Gemini)
    │     └─ Planning, reasoning, synthesis
    │
    ├─── Cerebras (Primary - 14,400 RPD)
    │     └─ llama3.1-8b, llama-3.3-70b, qwen-3-32b
    │
    ├─── Groq (Secondary - 7,000 RPD)
    │     └─ llama-3.1-8b-instant, llama-3.3-70b-versatile, mixtral, gemma
    │
    ├─── Gemini (Overflow - 1,650 RPD, auto-fallback)
    │     └─ gemini-2.5-flash-lite, gemini-2.0-flash, etc.
    │
    └─── Cohere (Embeddings - 1,000/month)
          └─ command-r-08-2024, embed-english-v3.0
```

## Key Innovations

### 1. Code Agent with Human-in-the-Loop

The system includes an AI code agent that can read, write, and modify code with explicit human approval for every action:

```python
from src.agent import CodeAgent

# Create agent with hybrid model approach
agent = CodeAgent(orch)
# Uses Gemini for planning (smart), Cerebras for execution (fast)

# Run task with human approval at each step
result = agent.run("Add input validation to API endpoints")

# Every file operation requires explicit approval:
# Agent wants to: read_file
# Parameters: {"path": "src/api.py"}
# Allow? [y/N]: y
```

**Key Safety Features:**
- Human-in-the-loop approval for every action
- Git checkpoint before changes (easy rollback)
- Path sandboxing (can't escape project directory)
- Dangerous command blocking (rm -rf, del /f, etc.)
- Complete audit trail with timestamps
- Dry-run mode for previewing

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

### 1. Provider Abstraction (`src/providers/base.py`)

All providers implement a common interface:
- `chat()` - Send messages, get responses
- `get_limits()` - Check rate limits
- `is_available()` - Verify configuration
- `get_model_for_task()` - Recommend model based on task type

### 2. Provider Implementations

**CerebrasProvider** (`src/providers/cerebras_provider.py`)
- Best for: Primary workhorse, ultra-fast inference
- Models: llama3.1-8b, llama-3.3-70b, qwen-3-32b
- Limits: 14,400 RPD, 60,000 TPM
- Default orchestrator brain

**GroqProvider** (`src/providers/groq_provider.py`)
- Best for: Secondary provider, model variety
- Models: llama-3.1-8b-instant, llama-3.3-70b-versatile, mixtral-8x7b, gemma2-9b
- Limits: 30 RPM, 7,000 RPD, 20K TPM

**GeminiProvider** (`src/providers/gemini_provider.py`)
- Best for: Overflow capacity, auto-fallback
- Models: gemini-2.5-flash-lite (1000 RPD), gemini-2.0-flash (200 RPD), etc.
- Special feature: Auto-fallback between models on rate limits

**CohereProvider** (`src/providers/cohere_provider.py`)
- Best for: Embeddings only (trial is severely limited)
- Models: command-r-08-2024, embed-english-v3.0
- Limits: **1,000 calls/month total** (CRITICAL - use sparingly)

### 3. Codebase Context (`src/context/`)

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

### 4. Code Agent (`src/agent/`)

AI-powered code writing with safety, modularized into a package:

**Core Components:**
- `core.py` - Main CodeAgent class
- `agent_loop.py` - Agent reasoning/execution loop
- `action_executor.py` - Action execution coordination
- `tool_runner.py` - Tool execution
- `response_parser.py` - LLM response parsing
- `provider_strategy.py` - Provider selection strategy

**Safety Components:**
- `safety_checker.py` - Safety validation
- `checkpoint.py` - Git checkpoint operations
- `audit.py` - Audit logging
- `duplicate_detector.py` - Duplicate action detection
- `denial_handler.py` - Denial handling

**Features:**
- **Hybrid model approach**: Gemini for planning/reasoning, Cerebras for fast operations
- **Tool-based execution**: read_file, write_file, list_files, run_command, search_code, git_log, git_diff, git_blame, git_show
- **Git history awareness**: Agent can check commits, diffs, and blame to understand code evolution
- **Human-in-the-loop**: Every action requires explicit approval
- **Safety features**:
  - Path sandboxing (restricted to project directory)
  - Dangerous command blocking
  - Git checkpoint creation/rollback
  - Complete audit logging
  - Dry-run mode for previewing
- **Context-aware**: Uses project exploration for informed decisions

Note: `src/agent.py` exists as a backward-compatibility wrapper.

### 5. Orchestrator (`src/orchestrator/`)

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

### 6. CLI Interface (`src/cli/`)

Full-featured command-line interface:
- Interactive chat mode with slash commands
- One-shot commands (query, plan, reason, explore, **agent**)
- **Code agent** with human approval workflow
- Provider management (switch brain, list models)
- Context management (explore, refresh, clear, toggle)
- Usage monitoring and status display
- Built with Click for excellent UX

### 7. Platform Abstraction (`src/platform/`)

Cross-platform support layer:
- `detection.py` - Detects OS, shell type, capabilities
- `translation.py` - Translates commands between platforms (e.g., `ls` vs `dir`)
- `validation.py` - Validates commands for current platform
- `executors.py` - Platform-specific command execution strategies
- `factory.py` - Factory for platform-aware components

**Why it exists:** Scrappy runs on Windows, macOS, and Linux. Commands like `ls`, `cat`, and path separators differ. This layer abstracts those differences so the agent and CLI work consistently across platforms.

### 8. Infrastructure Layer (`src/infrastructure/`)

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

### 9. Prompt System (`src/prompts/`)

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

### Pattern 2: Simple Delegation

```python
# Direct provider call
result = orch.delegate('cerebras', 'Summarize this text: ...')
print(result.content)
```

### Pattern 3: Smart Delegation

```python
# Auto-selects best provider for task type
result = orch.delegate_smart(
    'What are the benefits of microservices?',
    task_type='fast'  # Uses Cerebras (14,400 RPD)
)
```

### Pattern 4: Complex Reasoning

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

### Pattern 5: Multi-Agent Synthesis

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

### Pattern 6: Code Agent with Human Approval

```python
from src.agent import CodeAgent, create_git_checkpoint

# Setup
orch = AgentOrchestrator(auto_explore=True)
agent = CodeAgent(orch)

# Create safety checkpoint
checkpoint = create_git_checkpoint(".")

# Run agent (human approves each action)
result = agent.run(
    task="Add error handling to all API endpoints",
    max_iterations=10,
    auto_confirm=False  # Human must approve each action
)

if result['success']:
    print(f"Completed in {result['iterations']} iterations")
    # Review audit log
    for entry in result['audit_log']:
        print(f"  {entry['action']} - {entry['approved']}")
else:
    # Rollback if needed
    rollback_to_checkpoint(checkpoint)
```

**CLI Usage:**
```bash
# One-shot
python scrappy.py agent "Add feature X"

# Interactive
You: /agent Add input validation
```

## Adding New Providers

### Step 1: Create Provider Class

```python
# src/providers/newprovider_provider.py
from .base import LLMProvider, LLMResponse, ProviderLimits

class NewProvider(LLMProvider):
    @property
    def name(self) -> str:
        return 'newprovider'

    @property
    def available_models(self) -> list[str]:
        return ['model-a', 'model-b']

    @property
    def default_model(self) -> str:
        return 'model-a'

    def chat(self, messages, model=None, max_tokens=1000, **kwargs):
        # Implementation
        pass

    def get_limits(self):
        return ProviderLimits(requests_per_day=1000)

    def get_model_for_task(self, task_type):
        if task_type == 'quality':
            return 'model-b'
        return 'model-a'
```

### Step 2: Register in `__init__.py`

```python
from .newprovider_provider import NewProvider
__all__ = [..., 'NewProvider']
```

### Step 3: Auto-register in Orchestrator

```python
# In orchestrator.py _auto_register_providers()
try:
    self.registry.register(NewProvider())
    print("[OK] NewProvider registered")
except Exception as e:
    print(f"[X] NewProvider unavailable: {e}")
```

### Step 4: Add to Brain Priority (optional)

```python
# In _setup_brain()
priority = ['cerebras', 'groq', 'gemini', 'newprovider']
```

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
# Test provider connectivity
python test_orchestrator.py

# Test basic usage patterns
python examples/basic_usage.py
```

## Project Structure

```
src/
├── __init__.py
├── orchestrator.py           # Backward-compat wrapper -> orchestrator/
├── agent.py                  # Backward-compat wrapper -> agent/
├── agent_config.py           # Agent configuration (extends BaseConfig)
├── orchestrator_adapter.py   # Orchestrator adapter for agents
├── orchestrator/             # Modularized orchestrator package
│   ├── core.py               # Main AgentOrchestrator class
│   ├── factory.py            # Factory methods
│   ├── delegation.py         # Delegation logic
│   ├── provider_selector.py  # Smart provider selection
│   ├── rate_limiter.py       # Rate limiting facade
│   ├── rate_limiting/        # Rate limit subsystem
│   ├── cache.py              # Response caching
│   ├── session.py            # Session persistence
│   ├── memory.py             # Working memory
│   └── ...                   # 25+ files total
├── agent/                    # Modularized agent package
│   ├── core.py               # Main CodeAgent class
│   ├── agent_loop.py         # Agent reasoning loop
│   ├── action_executor.py    # Action execution
│   ├── safety_checker.py     # Safety validation
│   ├── checkpoint.py         # Git checkpoints
│   ├── audit.py              # Audit logging
│   └── ...                   # 13+ files total
├── agent_tools/              # Agent tool implementations
│   ├── tools/                # Individual tools
│   │   ├── file_tools.py     # read_file, write_file, list_files
│   │   ├── git_tools.py      # git_log, git_diff, git_blame, git_show
│   │   ├── command_tool.py   # run_command
│   │   ├── search_tools.py   # search_code
│   │   └── ...
│   └── components/           # Tool components
├── context/                  # Context management
│   ├── codebase_context.py   # Main context manager
│   ├── protocols.py          # Context protocols
│   ├── semantic_manager.py   # Semantic search coordination
│   ├── semantic/             # Semantic search subsystem
│   │   ├── provider.py       # LanceDB vector search
│   │   ├── embeddings.py     # FastEmbed integration
│   │   ├── ranker.py         # Result ranking
│   │   └── chunkers/         # Code chunking strategies
│   ├── file_scanner.py       # File system scanning
│   ├── project_detector.py   # Project type detection
│   ├── git_history.py        # Git operations
│   └── cache.py              # Context caching
├── providers/                # LLM providers
│   ├── base.py               # Abstract base class & protocols
│   ├── cerebras_provider.py  # Cerebras (primary)
│   ├── groq_provider.py      # Groq (secondary)
│   ├── gemini_provider.py    # Gemini (auto-fallback)
│   ├── cohere_provider.py    # Cohere (embeddings)
│   └── github_models_provider.py  # GitHub Models
├── task_router/              # Task routing system
│   ├── classifier.py         # Task classification
│   ├── router.py             # Task routing
│   ├── strategies/           # Execution strategies
│   └── classification_strategies/
├── cli/                      # CLI implementation
│   ├── commands.py           # Click commands
│   ├── command_router.py     # Slash command routing
│   ├── core.py               # Main CLI class
│   └── ...
├── infrastructure/           # Infrastructure layer
│   ├── config/               # Configuration framework
│   ├── persistence/          # Persistence abstractions
│   ├── logging/              # Logging system
│   └── file_system.py        # File system abstraction
├── platform/                 # Platform abstraction
│   ├── detection.py          # Platform detection
│   ├── translation.py        # Command translation
│   └── executors.py          # Platform-specific execution
└── prompts/                  # Prompt system
    ├── factory.py            # Prompt factory
    ├── builders/             # Prompt builders
    └── templates/            # Prompt templates

docs/
├── CLI.md                    # CLI reference guide
├── ARCHITECTURE.md           # This file
└── RATE_LIMITS.md           # Detailed rate limits

examples/
├── basic_usage.py           # Basic orchestrator usage
├── orchestrator_demo.py     # Full orchestrator features
├── agent_demo.py            # Code agent safety features
└── context_aware_demo.py    # Context-aware development

scrappy.py                   # CLI entry point
.scrappy/
.scrappy/.context.json        # Cached codebase context (auto-generated)
.scrappy/.audit.json             # Agent action audit log (auto-generated)
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
