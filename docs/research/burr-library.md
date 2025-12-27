# Burr Library Research

**Bead**: scrappy-x5e
**Status**: Complete
**Date**: 2025-12-25

## Overview

Burr is a Python framework for building stateful AI applications. It provides:
- State machine abstraction for agent flows
- Built-in persistence and checkpointing
- Real-time telemetry UI
- Visualization of state transitions

## Key Concepts

### Actions and Transitions

```python
from burr.core import action, State, ApplicationBuilder, when, expr, default

@action(reads=["chat_history"], writes=["response", "chat_history"])
def ai_response(state: State) -> State:
    response = query_llm(state["chat_history"])
    return state.update(response=response).append(chat_history={"role": "assistant", "content": response})

@action(reads=[], writes=["prompt", "chat_history"])
def human_input(state: State, prompt: str) -> State:
    return state.update(prompt=prompt).append(chat_history={"role": "user", "content": prompt})

# Build application with transitions
app = (
    ApplicationBuilder()
    .with_actions(human_input, ai_response)
    .with_transitions(
        ("human_input", "ai_response"),
        ("ai_response", "human_input")
    )
    .with_state(chat_history=[])
    .with_entrypoint("human_input")
    .build()
)
```

### Conditional Transitions

```python
from burr.core import when, expr, default

# Transitions with conditions
app = (
    ApplicationBuilder()
    .with_actions(classify, research, code_gen, conversation)
    .with_transitions(
        ("classify", "code_gen", when(task_type="CODE_GENERATION")),
        ("classify", "research", when(task_type="RESEARCH")),
        ("classify", "conversation", default),
        ("research", "complete", expr("confidence > 0.8")),
        ("research", "escalate", expr("confidence <= 0.8")),
    )
    .build()
)
```

### Persistence and Checkpointing

```python
from burr.core import ApplicationBuilder
from burr.core.persistence import SQLLitePersister
from burr.tracking import LocalTrackingClient

# SQLite persistence
persister = SQLLitePersister(db_path=".burr.db", table_name="burr_state")
persister.initialize()

# Build with persistence
app = (
    ApplicationBuilder()
    .with_actions(...)
    .with_transitions(...)
    .with_state_persister(persister)
    .with_tracker(project="scrappy-agent")
    .build()
)

# Resume from checkpoint
reloaded_app = (
    ApplicationBuilder()
    .with_actions(...)
    .initialize_from(
        persister,
        resume_at_next_action=True,
        default_state={},
        default_entrypoint="human_input"
    )
    .with_state_persister(persister)
    .with_identifiers(app_id=app_id)
    .build()
)
```

## Scrappy Code That Could Benefit

### 1. Agent Loop (1018 lines) - `agent/agent_loop.py`

**Current Implementation**:
```python
class AgentLoop:
    def run_loop(self, ...):
        while True:
            thought = self.think(state, context)      # 1. Think
            actions = self.plan(thought)               # 2. Plan
            result = self.execute(action, state)       # 3. Execute
            evaluation = self.evaluate(...)            # 4. Evaluate
            if evaluation.is_complete:
                break
```

**Burr Equivalent**:
```python
from burr.core import action, State, ApplicationBuilder

@action(reads=["task", "context"], writes=["thought", "raw_response"])
def think(state: State) -> State:
    response = orchestrator.delegate(state["task"], context=state["context"])
    return state.update(thought=response.content, raw_response=response)

@action(reads=["raw_response"], writes=["actions"])
def plan(state: State) -> State:
    parsed = parser.parse(state["raw_response"])
    return state.update(actions=parsed)

@action(reads=["actions"], writes=["result"])
def execute(state: State) -> State:
    result = executor.execute(state["actions"])
    return state.update(result=result)

@action(reads=["result"], writes=["is_complete"])
def evaluate(state: State) -> State:
    is_complete = state["result"].metadata.get("stop_loop", False)
    return state.update(is_complete=is_complete)

agent_app = (
    ApplicationBuilder()
    .with_actions(think, plan, execute, evaluate)
    .with_transitions(
        ("think", "plan"),
        ("plan", "execute"),
        ("execute", "evaluate"),
        ("evaluate", "think", ~when(is_complete=True)),  # Loop back
        ("evaluate", "complete", when(is_complete=True)),
    )
    .with_state(task="", context={}, is_complete=False)
    .with_entrypoint("think")
    .with_tracker(project="scrappy-agent")
    .build()
)
```

**Benefits**:
- Automatic state tracking and visualization
- Built-in checkpointing (can resume mid-task)
- Clear separation of stages
- Telemetry UI for debugging

### 2. Task Router Escalation (841 lines) - `task_router/router.py`

**Current Flow**:
```
classify -> low confidence? -> LLM reclassify -> still low? -> clarify -> escalate -> execute
```

**Burr State Machine**:
```python
@action(reads=["user_input"], writes=["task_type", "confidence", "reasoning"])
def rule_classify(state: State) -> State:
    result = classifier.classify(state["user_input"])
    return state.update(
        task_type=result.task_type,
        confidence=result.confidence,
        reasoning=result.reasoning
    )

@action(reads=["user_input", "task_type", "confidence"], writes=["task_type", "confidence"])
def llm_classify(state: State) -> State:
    # LLM-based semantic classification
    result = classify_with_llm(state["user_input"])
    return state.update(task_type=result.task_type, confidence=result.confidence)

@action(reads=["task_type"], writes=["task_type"])
def escalate(state: State) -> State:
    # Escalate RESEARCH -> CODE_GENERATION
    return state.update(task_type="CODE_GENERATION")

router_app = (
    ApplicationBuilder()
    .with_actions(rule_classify, llm_classify, escalate, execute_research, execute_agent)
    .with_transitions(
        # High confidence -> direct execution
        ("rule_classify", "execute_research", when(task_type="RESEARCH") & expr("confidence >= 0.7")),
        ("rule_classify", "execute_agent", when(task_type="CODE_GENERATION") & expr("confidence >= 0.7")),

        # Low confidence -> LLM classification
        ("rule_classify", "llm_classify", expr("confidence < 0.7")),

        # After LLM, still low -> escalate
        ("llm_classify", "escalate", expr("confidence < 0.7")),
        ("llm_classify", "execute_research", when(task_type="RESEARCH")),
        ("llm_classify", "execute_agent", when(task_type="CODE_GENERATION")),

        # Escalation always goes to agent
        ("escalate", "execute_agent"),
    )
    .with_state(user_input="", task_type=None, confidence=0.0)
    .with_entrypoint("rule_classify")
    .build()
)
```

### 3. Session Manager (176 lines) - `orchestrator/session.py`

**Current Implementation**: Custom JSON file persistence

**Burr Replacement**:
```python
from burr.core.persistence import SQLLitePersister

# Replace SessionManager with Burr's built-in persistence
persister = SQLLitePersister(db_path=".scrappy/session.db")

app = (
    ApplicationBuilder()
    .with_state_persister(persister)
    .initialize_from(
        persister,
        resume_at_next_action=True,
        default_state={"working_memory": {}, "task_history": []}
    )
    .build()
)

# State is automatically persisted after each action
# Recovery is automatic on restart
```

**Benefits**:
- Automatic checkpointing after each state transition
- Resume from any point in the flow
- Built-in app_id management
- No custom serialization code

## Potential State Machine Design for Scrappy

```
                          ┌─────────────────────┐
                          │    user_input       │
                          └──────────┬──────────┘
                                     │
                          ┌──────────▼──────────┐
                          │   rule_classify     │
                          └──────────┬──────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              │                      │                      │
              ▼                      ▼                      ▼
     confidence >= 0.7      confidence < 0.7       DIRECT_COMMAND
              │                      │                      │
              │           ┌──────────▼──────────┐          │
              │           │    llm_classify     │          │
              │           └──────────┬──────────┘          │
              │                      │                      │
              ▼                      ▼                      ▼
    ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
    │  task_router    │   │    escalate     │   │  direct_exec    │
    └────────┬────────┘   └────────┬────────┘   └────────┬────────┘
             │                     │                     │
             ▼                     ▼                     │
    ┌─────────────────┐   ┌─────────────────┐           │
    │  research_exec  │   │   agent_exec    │           │
    └────────┬────────┘   └────────┬────────┘           │
             │                     │                     │
             │            ┌────────┴────────┐           │
             │            │                 │           │
             │            ▼                 ▼           │
             │    ┌─────────────┐   ┌─────────────┐    │
             │    │    think    │   │   complete  │    │
             │    └──────┬──────┘   └──────┬──────┘    │
             │           │                 │           │
             │           ▼                 │           │
             │    ┌─────────────┐          │           │
             │    │    plan     │          │           │
             │    └──────┬──────┘          │           │
             │           │                 │           │
             │           ▼                 │           │
             │    ┌─────────────┐          │           │
             │    │   execute   │          │           │
             │    └──────┬──────┘          │           │
             │           │                 │           │
             │           ▼                 │           │
             │    ┌─────────────┐          │           │
             │    │  evaluate   │──────────┤           │
             │    └──────┬──────┘          │           │
             │           │                 │           │
             │           └─────────────────┤           │
             │                             │           │
             └─────────────────────────────┴───────────┘
                                           │
                                           ▼
                                    ┌─────────────┐
                                    │   terminal  │
                                    └─────────────┘
```

## Comparison Summary

| Aspect | Current Scrappy | With Burr |
|--------|-----------------|-----------|
| Agent Loop | 1018 lines custom | ~100 lines + decorators |
| Task Router | 841 lines custom | ~150 lines + transitions |
| Session | 176 lines JSON | Built-in SQLite |
| Checkpointing | Manual | Automatic |
| Visualization | None | Built-in telemetry UI |
| Recovery | Load from file | Resume mid-action |
| Debugging | Console logs | Web UI + traces |

## Risks and Considerations

1. **Learning Curve**: Burr's action/transition model requires mindset shift
2. **Migration Complexity**: Large refactor of agent loop and router
3. **Dependency**: Adds substantial dependency (dagworks-inc/burr)
4. **Flexibility**: State machine may be too rigid for some edge cases
5. **Performance**: Unknown overhead for simple operations

## Recommendation

**Partial Adoption for New Features**:

1. **Good Fit**: New multi-step workflows (e.g., new agent types)
2. **Good Fit**: Session recovery and checkpointing
3. **Good Fit**: Debugging/observability via telemetry UI
4. **Poor Fit**: Simple request-response patterns
5. **Poor Fit**: High-frequency operations (rate limiting, caching)

**Suggested Approach**:
- Keep existing agent loop (works well, heavily tested)
- Use Burr for new complex workflows requiring checkpointing
- Consider Burr for session persistence (replaces custom JSON)
- Use Burr telemetry UI for debugging complex flows

## Integration with Other Libraries

| Library | Integration Point |
|---------|-------------------|
| Instructor | Actions can use Instructor for structured outputs |
| LiteLLM | Burr is LLM-agnostic, works with any provider |
| DSPy | Actions could wrap DSPy modules |
| Pydantic-AI | State can use Pydantic models |

## Conclusion

Burr provides valuable state machine primitives but requires significant refactoring to adopt fully. Best suited for:
- New multi-step agent workflows
- Session recovery/checkpointing
- Debugging complex flows via telemetry

Not recommended as complete replacement due to migration cost vs. benefit ratio for existing stable code.
