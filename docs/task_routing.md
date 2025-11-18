# Task Routing System

Complete documentation for the task-type aware execution system with dynamic provider selection.

## Overview

The Task Router is an intelligent dispatch system that:

1. **Classifies** user input by task type and complexity
2. **Selects** the optimal provider based on task requirements
3. **Routes** to the appropriate execution strategy
4. **Executes** with strategy-specific optimizations

This eliminates the overhead of running every task through a full agent loop while ensuring complex tasks still receive appropriate handling.

## Architecture

```
User Input
    │
    ▼
TaskClassifier (src/task_router/classifier.py)
    ├─ Pattern matching (regex-based)
    ├─ Complexity scoring (1-10 scale)
    ├─ Provider suggestion ("fast" or "quality")
    └─ Safety validation
    │
    ▼
TaskRouter (src/task_router/router.py)
    ├─ Provider resolution (hint → actual provider)
    ├─ Strategy selection
    ├─ Pre/post execution hooks
    └─ Metrics tracking
    │
    ▼
ExecutionStrategy (src/task_router/strategies.py)
    ├─ DirectExecutor (shell commands, no LLM)
    ├─ ResearchExecutor (fast LLM, read-only)
    ├─ ConversationExecutor (simple responses)
    └─ AgentExecutor (full planning loop)
    │
    ▼
ExecutionResult
    ├─ Output and success status
    ├─ Provider and tokens used
    ├─ Classification metadata
    └─ Execution time
```

## Task Types

| Type | Description | Provider | Approval | Example |
|------|-------------|----------|----------|---------|
| **DIRECT_COMMAND** | Shell commands | None | Optional | `pip install requests` |
| **RESEARCH** | Information gathering | Fast (Cerebras) | No | `explain the auth module` |
| **CODE_GENERATION** | Writing/modifying code | Fast or Quality | Yes | `implement login function` |
| **CONVERSATION** | Simple interactions | None | No | `hello`, `thanks` |

## Provider Selection

### Automatic Selection Based on Complexity

The classifier suggests a provider hint based on task complexity:

```python
def _suggest_provider(task_type, complexity):
    if task_type == TaskType.DIRECT_COMMAND:
        return None  # No LLM needed

    if task_type == TaskType.CONVERSATION:
        return "fast"

    if task_type == TaskType.RESEARCH:
        return "fast"

    if task_type == TaskType.CODE_GENERATION:
        if complexity >= 7:
            return "quality"  # 70B model for complex tasks
        else:
            return "fast"     # 8B model for simpler code
```

### Provider Resolution

The router resolves hints to actual providers:

| Hint | Priority Order | Model |
|------|----------------|-------|
| `"fast"` | Cerebras > Groq > Gemini | 8B models |
| `"quality"` | Cerebras > Groq > Gemini | 70B models |
| `"high_volume"` | Cerebras (14,400 RPD) | Default |

```python
def _resolve_provider(hint):
    if hint == "fast":
        return ("cerebras", None)  # Uses default 8B model

    if hint == "quality":
        return ("cerebras", "llama-3.3-70b")  # Uses 70B model

    return (None, None)
```

### Override Support

Manual provider override takes precedence:

```python
# In code
result = router.route("implement auth", provider="quality")

# Via ClassifiedTask
task.override_provider = "quality"

# Via pre-hook
def force_quality(task):
    if task.complexity_score >= 8:
        task.override_provider = "quality"
    return task

router.add_pre_hook(force_quality)
```

## Execution Strategies

### DirectExecutor

**Purpose**: Execute shell commands without LLM involvement

**Features**:
- No LLM overhead
- Timeout protection (configurable, default 60s)
- Safety validation (blocks dangerous commands)
- Working directory awareness
- Optional user confirmation

**Usage**:
```python
executor = DirectExecutor(
    working_dir=Path.cwd(),
    timeout=60,
    require_confirmation=True
)

result = executor.execute(ClassifiedTask(
    original_input="git status",
    task_type=TaskType.DIRECT_COMMAND,
    extracted_command="git status",
    ...
))
```

**Blocked Commands**:
- `rm -rf /`
- `sudo rm`
- `format`
- `dd if=`
- Fork bombs

### ResearchExecutor

**Purpose**: Fast information gathering with context awareness

**Features**:
- Uses fastest available provider (Cerebras by default)
- No file modifications
- Context-aware responses (includes project summary)
- Dynamic provider selection per task
- No human approval needed

**Usage**:
```python
executor = ResearchExecutor(orchestrator)
executor.set_provider("cerebras", None)  # Set by router

result = executor.execute(ClassifiedTask(
    original_input="explain the caching system",
    task_type=TaskType.RESEARCH,
    ...
))
```

**Provider Priority**:
1. Resolved provider from TaskRouter
2. Preferred provider (default "cerebras")
3. Orchestrator brain (fallback)

### AgentExecutor

**Purpose**: Full agent loop with planning and tool access

**Features**:
- Complete planning phase
- Human-in-the-loop approval
- Tool access (file, git, search, command)
- Iterative execution (max iterations configurable)
- Dynamic provider selection for complex tasks

**Usage**:
```python
executor = AgentExecutor(
    orchestrator,
    project_root=Path.cwd(),
    max_iterations=10,
    require_approval=True
)
executor.set_provider("gemini", "gemini-pro")  # For complex tasks

result = executor.execute(ClassifiedTask(
    original_input="implement user authentication",
    task_type=TaskType.CODE_GENERATION,
    complexity_score=8,  # High complexity
    ...
))
```

**Provider Flow**:
1. Router sets preferred provider via `set_provider()`
2. AgentExecutor passes to AgentOrchestratorAdapter
3. CodeAgent uses adapter's preferred provider
4. Overrides default planner/executor preferences

### ConversationExecutor

**Purpose**: Handle simple interactions without external calls

**Features**:
- Pre-defined response patterns
- No LLM calls
- Instant responses
- Pattern matching for common interactions

**Patterns**:
- `greeting` → "Hello! I'm ready to help..."
- `thanks` → "You're welcome!"
- `help_request` → Lists capabilities
- `farewell` → "Goodbye!"

## Task Classification

### Pattern Matching

The classifier uses regex patterns to identify task types:

**DIRECT_COMMAND patterns**:
```python
r'^(pip|npm|git|docker|make|pytest|cargo)\s+',
r'^(cd|ls|dir|mkdir|rm|cp|mv|cat|grep)\s+',
r'^(python|node|ruby|go)\s+\S+\.(py|js|rb|go)'
```

**CODE_GENERATION patterns**:
```python
r'\b(write|create|implement|add|build)\b.*\b(function|class|module|endpoint)\b',
r'\b(refactor|fix|debug|optimize|update)\b.*\b(code|function|class)\b',
r'\b(generate|scaffold|setup)\b'
```

**RESEARCH patterns**:
```python
r'\b(explain|describe|what is|how does|why)\b',
r'\b(analyze|review|summarize)\b',
r'\b(find|locate|search for)\b.*\b(function|class|file)\b'
```

**CONVERSATION patterns**:
```python
r'^(hi|hello|hey|greetings)',
r'^(thanks|thank you)',
r'^(bye|goodbye|exit)'
```

### Complexity Scoring

Scores from 1-10 based on:

1. **Base complexity by type**:
   - DIRECT_COMMAND: 1
   - CONVERSATION: 1
   - RESEARCH: 3
   - CODE_GENERATION: 5

2. **Modifiers**:
   - Multiple files mentioned: +2
   - Architecture keywords: +2
   - Integration keywords: +2
   - Testing mentioned: +1
   - Security mentioned: +2
   - Performance mentioned: +1
   - Action word count (max +3)

**Example**:
```python
"implement user authentication with JWT and session management"
# Base: 5 (CODE_GENERATION)
# + 2 (security: authentication)
# + 1 (action: implement)
# = 8/10 → "quality" provider
```

## CLI Integration

### Auto-Execute Mode

Enabled by default, automatically executes plan tasks:

```python
# In src/cli/core.py
self.auto_execute_tasks = True

def _execute_current_task(self):
    result = self.task_router.router.route(task)
    # Shows strategy, provider, and result
```

Toggle with `/autoexec`:
```
You: /autoexec
Auto-execute tasks: ENABLED
  Tasks in plans will be automatically executed using intelligent routing
```

### Auto-Route Mode

Automatically classify and route all inputs:

```
You: /auto
Task routing mode: ENABLED

You: pip install flask
📋 Task Classification:
  Type: direct_command
  Confidence: 1.00
  Complexity: 1/10
  Provider: none (hint: None)
  Executing with: DirectExecutor
✓ Command executed successfully
```

### Classify Only (Preview)

Preview classification without execution:

```python
handler.handle_classify_only("implement auth")
# Shows classification details without executing
```

### Routing Metrics

Track execution patterns:

```python
metrics = router.get_metrics()
print(f"Total tasks: {metrics.total_tasks}")
print(f"By type: {metrics.tasks_by_type}")
print(f"Success rate: {metrics.success_rate:.1%}")
print(f"Avg execution time: {metrics.avg_execution_time:.2f}s")
print(f"Total tokens: {metrics.total_tokens_used}")
```

## Safety Features

### Command Validation

DirectExecutor blocks dangerous patterns:
- Root directory deletion
- Privilege escalation
- Disk formatting
- Fork bombs

### Human Approval

AgentExecutor maintains human-in-the-loop:
- Every file operation requires approval
- Git checkpoints before changes
- Audit logging of all actions
- Content preview before writes

### Provider Fallback

Automatic fallback if preferred provider unavailable:
```python
# ResearchExecutor fallback
if provider_to_use not in available:
    provider_to_use = self.orchestrator.brain
```

## Configuration

### AgentConfig Preferences

```python
# In src/agent_config.py
planner_preferences: List[str] = ['gemini', 'groq']
executor_preferences: List[str] = ['cerebras']

# For interactive commands (now comprehensive)
interactive_commands: List[str] = [
    'npm init', 'npm create', 'npx ', 'yarn create',
    'vite@', 'next@', 'git commit', 'ssh ', ...
]
```

### Router Configuration

```python
router = TaskRouter(
    orchestrator=orchestrator,
    project_root=Path.cwd(),
    auto_confirm_direct=False,  # Require confirmation for commands
    verbose=True                 # Show routing decisions
)
```

## Extensibility

### Pre/Post Hooks

Add custom processing:

```python
# Pre-execution hook
def log_task(task):
    logger.info(f"Executing: {task.task_type}")
    return task

router.add_pre_hook(log_task)

# Post-execution hook
def track_metrics(result):
    metrics_db.save(result)
    return result

router.add_post_hook(track_metrics)
```

### Custom Strategies

Replace or add strategies:

```python
class CustomResearchExecutor(ExecutionStrategy):
    def execute(self, task):
        # Custom implementation
        pass

router.set_strategy(TaskType.RESEARCH, CustomResearchExecutor())
```

## Examples

### Simple Command Execution

```python
result = router.route("git status")
# → DirectExecutor
# → Immediate execution
# → No LLM overhead
```

### Research Query

```python
result = router.route("explain how the auth module works")
# → ResearchExecutor
# → Uses Cerebras (fast)
# → Context-aware response
# → No approval needed
```

### Complex Code Generation

```python
result = router.route("implement OAuth2 authentication with refresh tokens")
# → AgentExecutor
# → Complexity: 9/10
# → Uses Gemini 70B (quality)
# → Requires human approval
```

### Provider Override

```python
# Force quality provider for important task
result = router.route(
    "fix critical security bug",
    provider="quality"
)
# → Uses 70B model regardless of complexity
```

## Metadata and Debugging

ExecutionResult includes full routing information:

```python
result = router.route("implement auth")

print(result.metadata["classification"])
# {
#   "type": "code_generation",
#   "confidence": 0.95,
#   "complexity": 8,
#   "reasoning": "Code generation task with high complexity",
#   "suggested_provider": "quality",
#   "override_provider": None,
#   "resolved_provider": "gemini",
#   "resolved_model": "gemini-pro"
# }
```

## Best Practices

1. **Let the router decide** - Trust automatic classification for most tasks
2. **Override for critical tasks** - Use `route(provider=...)` for important work
3. **Monitor metrics** - Track success rates and adjust strategies
4. **Use pre-hooks** - Add logging, validation, or modification logic
5. **Keep patterns updated** - Add new patterns as usage patterns emerge

## Future Enhancements

- [ ] Learning from user patterns
- [ ] Provider performance tracking
- [ ] Automatic strategy tuning based on success rates
- [ ] Batch task optimization
- [ ] Streaming execution support
- [ ] Cost-aware provider selection
- [ ] Rate limit awareness in routing decisions
