# Task Router - Task-Type Aware Execution

A refined execution system that routes tasks to optimal execution strategies based on their type and complexity.

## Overview

The Task Router eliminates the overhead of running every task through a full agent loop. Instead, it:

1. **Classifies** user input by task type
2. **Routes** to the appropriate execution strategy
3. **Executes** with optimized settings for that task type

## Task Types

| Type | Example | Execution Path | Provider |
|------|---------|----------------|----------|
| **DIRECT_COMMAND** | `pip install requests` | Shell execution, no LLM | None |
| **CODE_GENERATION** | `write a fibonacci function` | Full agent loop with planning | Quality (70B) |
| **RESEARCH** | `explain the caching system` | Fast LLM, no file changes | Fast (Cerebras) |
| **CONVERSATION** | `hello`, `thanks` | Pre-defined responses | None |

## Quick Start

```python
from task_router import TaskRouter
from orchestrator import AgentOrchestrator

# Initialize
orchestrator = AgentOrchestrator()
router = TaskRouter(orchestrator=orchestrator)

# Route automatically
result = router.route("pip install requests")  # → DirectExecutor
result = router.route("explain auth module")   # → ResearchExecutor
result = router.route("write login function")  # → AgentExecutor
```

## Benefits

1. **No Agent Loop Overhead** - Simple commands execute immediately
2. **Optimal Provider Selection** - Fast provider for research, quality for code
3. **Reduced Token Usage** - Only use LLM when necessary
4. **Safety Checks** - Dangerous commands blocked automatically
5. **Metrics Tracking** - Monitor execution patterns

## Architecture

```
User Input
    ↓
TaskClassifier
    ├─ Pattern matching
    ├─ Complexity scoring
    └─ Provider suggestion
    ↓
TaskRouter
    ├─ Strategy selection
    ├─ Pre/post hooks
    └─ Metrics tracking
    ↓
ExecutionStrategy
    ├─ DirectExecutor (shell)
    ├─ ResearchExecutor (fast LLM)
    ├─ AgentExecutor (full loop)
    └─ ConversationExecutor (simple)
    ↓
ExecutionResult
```

## Components

### TaskClassifier

Classifies user input using pattern matching:

```python
classifier = TaskClassifier()
result = classifier.classify("git status")

print(result.task_type)       # TaskType.DIRECT_COMMAND
print(result.confidence)      # 1.0
print(result.complexity_score) # 1
print(result.extracted_command) # "git status"
```

### ExecutionStrategies

**DirectExecutor** - No AI, shell execution
- Timeout protection
- Safety validation
- Working directory awareness

**ResearchExecutor** - Fast provider, read-only
- Context augmentation
- Optimized prompts
- Quick responses

**AgentExecutor** - Full CodeAgent integration
- Planning phase
- Human approval
- Tool access (file, git, search)

**ConversationExecutor** - Simple responses
- Pre-defined patterns
- No external calls
- Instant responses

### TaskRouter

Central dispatcher:

```python
router = TaskRouter(
    orchestrator=orchestrator,
    auto_confirm_direct=True,  # Skip confirmation for shell commands
    verbose=True               # Show routing decisions
)

# Extensible with hooks
router.add_pre_hook(lambda task: log_task(task))
router.add_post_hook(lambda result: track_metrics(result))

# Get metrics
metrics = router.get_metrics()
print(f"Success rate: {metrics.success_rate:.1%}")
```

## CLI Integration

```python
from cli.task_router_handler import CLITaskRouterHandler

handler = CLITaskRouterHandler(orchestrator)
handler.handle_auto_route("pip install requests")
handler.handle_classify_only("explain the code")
handler.handle_route_status()
```

## Safety Features

- Dangerous command blocking (rm -rf, sudo rm, etc.)
- Pattern-based validation
- Human-in-the-loop for code changes
- Audit logging support

## Examples

See `/examples/task_router_demo.py` for comprehensive demonstrations.

## Future Enhancements

- [ ] Learning from user patterns
- [ ] Provider performance tracking
- [ ] Automatic strategy tuning
- [ ] Batch task optimization
- [ ] Streaming execution support
