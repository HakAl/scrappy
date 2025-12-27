# Agent Library Integration Plan

**Bead**: scrappy-5ap
**Status**: Complete
**Date**: 2025-12-25

## Executive Summary

After evaluating 6 agent libraries, we recommend adopting **Instructor** (immediate), with **DSPy** (medium-term) and **Burr** (selective) for specific use cases.

### Recommended Adoption

| Library | Priority | Code Reduction | Stability Impact | UX Impact |
|---------|----------|----------------|------------------|-----------|
| **Instructor** | P1 (Now) | ~790 lines | High | High |
| **DSPy** | P2 (Medium) | ~560 lines | Medium | High |
| **Burr** | P3 (Selective) | ~100 lines | High | Medium |

**Total potential reduction**: ~1,450 lines of custom code

---

## Part 1: Instructor Integration

### What It Solves

Instructor eliminates brittle JSON parsing code by letting the LLM return validated Pydantic models directly.

**Before** (259 lines in json_extractor.py):
```python
def extract_json(response: str) -> dict:
    # Try markdown code blocks
    # Try Python bool conversion
    # Try brace matching
    # Try truncated JSON recovery
    # Try regex extraction
    # Handle 6 different failure modes...
```

**After** (~10 lines):
```python
import instructor
from pydantic import BaseModel

client = instructor.from_provider("groq/llama3-8b-8192")

class TaskClassification(BaseModel):
    task_type: TaskType
    confidence: float
    reasoning: str

result = client.chat.completions.create(
    response_model=TaskClassification,
    messages=[...],
    max_retries=2,
)
# result is already validated TaskClassification
```

### Files to Replace

| File | Lines | Instructor Replacement |
|------|-------|----------------------|
| `task_router/json_extractor.py` | 259 | Delete entirely |
| `agent/response_parser.py` | 555 | Reduce to ~50 lines |
| `task_router/router.py` (LLM section) | ~50 | Simplify to ~15 lines |

### Integration with Near-Term Features

#### 1. Seamless Escalation (P1 - High Impact)

Instructor's structured outputs make escalation decisions reliable:

```python
from pydantic import BaseModel, Field
from enum import Enum

class ComplexityLevel(str, Enum):
    SIMPLE = "simple"      # Fast model: "what does X do?"
    MODERATE = "moderate"  # Fast model with more context
    COMPLEX = "complex"    # Quality model: "refactor auth system"

class EscalationDecision(BaseModel):
    """Structured escalation decision with reasoning."""
    complexity: ComplexityLevel
    requires_code_changes: bool
    estimated_files: int = Field(ge=0, le=100)
    reasoning: str
    suggested_provider: str = Field(description="'fast' or 'quality'")

@lru_cache
def get_escalation_client():
    return instructor.from_provider("groq/llama3-8b-8192")

def decide_escalation(user_input: str, context: str) -> EscalationDecision:
    """Fast, reliable escalation decision."""
    client = get_escalation_client()
    return client.chat.completions.create(
        response_model=EscalationDecision,
        messages=[
            {"role": "system", "content": ESCALATION_PROMPT},
            {"role": "user", "content": f"Task: {user_input}\nContext: {context}"}
        ],
        max_retries=1,  # Fast - don't retry much
    )

# Usage in router
decision = decide_escalation(user_input, codebase_context)
if decision.complexity == ComplexityLevel.COMPLEX:
    provider = "quality"  # Claude, GPT-4
else:
    provider = "fast"     # Groq, Cerebras
```

**UX Win**: Users never think about model selection. System automatically uses fast model for questions, quality model for refactoring.

#### 2. Context Priming - Test Config Hints (P3 - Quick Win)

Instructor makes test config detection structured and reliable:

```python
class TestFramework(str, Enum):
    PYTEST = "pytest"
    UNITTEST = "unittest"
    JEST = "jest"
    VITEST = "vitest"
    UNKNOWN = "unknown"

class TestConfigHints(BaseModel):
    """Detected test configuration for context priming."""
    framework: TestFramework
    config_files: list[str] = Field(description="e.g., pytest.ini, conftest.py")
    test_command: str = Field(description="Recommended test command")
    coverage_enabled: bool
    special_flags: list[str] = Field(default_factory=list)

def detect_test_config(file_index: dict) -> TestConfigHints:
    """Detect test configuration from codebase structure."""
    # Rule-based detection (no LLM needed)
    if "pytest.ini" in file_index.get("config", []):
        return TestConfigHints(
            framework=TestFramework.PYTEST,
            config_files=["pytest.ini"],
            test_command="pytest",
            coverage_enabled="pytest-cov" in detect_dependencies(),
            special_flags=detect_pytest_flags(),
        )
    # ... other frameworks

# Inject into agent context
def build_test_context(hints: TestConfigHints) -> str:
    return f"""
## Test Configuration (Auto-detected)
- Framework: {hints.framework.value}
- Command: `{hints.test_command}`
- Config files: {', '.join(hints.config_files)}
{f'- Coverage: enabled' if hints.coverage_enabled else ''}
"""
```

**UX Win**: `pytest` runs correctly on first try because agent knows about conftest.py and pytest.ini.

#### 3. Judge/Magistrate Pattern (Quality)

Instructor enables reliable self-validation:

```python
class ValidationResult(BaseModel):
    """Self-validation before showing results."""
    is_valid: bool
    issues: list[str] = Field(default_factory=list)
    severity: str = Field(description="'blocker', 'warning', 'info'")
    suggested_fix: Optional[str] = None

class JudgeVerdict(BaseModel):
    """Judge evaluation of agent output."""
    passes_review: bool
    confidence: float = Field(ge=0.0, le=1.0)
    issues_found: list[ValidationResult]
    should_retry: bool
    retry_guidance: Optional[str] = None

def judge_agent_output(
    task: str,
    agent_output: str,
    code_changes: list[str],
) -> JudgeVerdict:
    """Self-validate before showing to user."""
    client = instructor.from_provider("groq/llama3-8b-8192")
    return client.chat.completions.create(
        response_model=JudgeVerdict,
        messages=[
            {"role": "system", "content": JUDGE_PROMPT},
            {"role": "user", "content": f"""
Task: {task}
Agent Output: {agent_output}
Code Changes: {code_changes}

Evaluate if this output is correct and complete.
"""}
        ],
    )

# Usage in agent loop
verdict = judge_agent_output(task, output, changes)
if not verdict.passes_review and verdict.should_retry:
    # Retry with guidance
    state.messages.append({
        "role": "user",
        "content": f"Review found issues: {verdict.retry_guidance}"
    })
    continue  # Another iteration
```

**UX Win**: Errors caught before user sees them. Builds trust through consistent quality.

---

## Part 2: DSPy Integration

### What It Solves

DSPy replaces manual prompt engineering with declarative signatures that can be optimized with training data.

**Before** (prompts/factory.py - 200 lines):
```python
def build_agent_prompt(platform, tools, project_type):
    prompt = BASE_PROMPT
    prompt += PLATFORM_SECTION.format(platform=platform)
    prompt += TOOLS_SECTION.format(tools=format_tools(tools))
    # ... manual string building
```

**After** (~50 lines):
```python
import dspy

class AgentResponse(dspy.Signature):
    """Generate next action for coding task."""
    task: str = dspy.InputField()
    context: str = dspy.InputField()
    tools: str = dspy.InputField()

    thought: str = dspy.OutputField(desc="Reasoning about next step")
    action: str = dspy.OutputField(desc="Tool to use")
    parameters: dict = dspy.OutputField(desc="Tool parameters")

agent_module = dspy.ChainOfThought(AgentResponse)
```

### Integration with Near-Term Features

#### 1. Seamless Escalation with DSPy Optimization

DSPy can learn optimal escalation patterns from usage data:

```python
class EscalateTask(dspy.Signature):
    """Decide if task needs escalation to quality model."""
    user_input: str = dspy.InputField()
    codebase_summary: str = dspy.InputField()

    needs_escalation: bool = dspy.OutputField()
    reasoning: str = dspy.OutputField()

# Collect training data from actual usage
training_examples = [
    dspy.Example(
        user_input="what does this function do?",
        codebase_summary="...",
        needs_escalation=False,
        reasoning="Simple question, fast model sufficient"
    ),
    dspy.Example(
        user_input="refactor the authentication system to use OAuth",
        codebase_summary="...",
        needs_escalation=True,
        reasoning="Complex refactoring across multiple files"
    ),
]

# Optimize the escalation decision
optimizer = dspy.BootstrapFewShot(metric=escalation_accuracy)
optimized_escalator = optimizer.compile(
    dspy.ChainOfThought(EscalateTask),
    trainset=training_examples
)
optimized_escalator.save("escalation_optimized.json")
```

**Benefit**: Escalation improves automatically as you collect usage data.

#### 2. Context Priming with DSPy

DSPy can generate context-aware hints:

```python
class ContextPrimer(dspy.Signature):
    """Generate helpful context hints for task."""
    task: str = dspy.InputField()
    detected_configs: str = dspy.InputField(desc="pytest.ini, package.json, etc.")
    file_structure: str = dspy.InputField()

    hints: str = dspy.OutputField(desc="Actionable hints for the agent")
    relevant_files: list[str] = dspy.OutputField()

primer = dspy.ChainOfThought(ContextPrimer)

# For test tasks, primer generates:
# hints: "Use pytest with -v flag. conftest.py has fixtures. Tests in tests/ dir."
# relevant_files: ["conftest.py", "pytest.ini", "tests/test_auth.py"]
```

#### 3. Judge/Magistrate with DSPy

DSPy enables optimizable judge patterns:

```python
class JudgeOutput(dspy.Signature):
    """Evaluate if agent output is correct."""
    task: str = dspy.InputField()
    agent_output: str = dspy.InputField()
    code_changes: str = dspy.InputField()

    is_correct: bool = dspy.OutputField()
    issues: list[str] = dspy.OutputField()
    should_retry: bool = dspy.OutputField()

# Train judge on historical corrections
judge_examples = [
    dspy.Example(
        task="add error handling",
        agent_output="Added try/except",
        code_changes="...",
        is_correct=False,
        issues=["Missing specific exception types"],
        should_retry=True
    ),
]

optimized_judge = optimizer.compile(
    dspy.ChainOfThought(JudgeOutput),
    trainset=judge_examples
)
```

**Benefit**: Judge gets better at catching errors over time.

---

## Part 3: Burr Integration (Selective)

### What It Solves

Burr provides state machine patterns for complex multi-step workflows with checkpointing.

### Integration with Near-Term Features

#### 1. Seamless Escalation State Machine

```python
from burr.core import action, State, ApplicationBuilder, when, expr

@action(reads=["task"], writes=["complexity", "provider"])
def assess_complexity(state: State) -> State:
    decision = decide_escalation(state["task"])
    return state.update(
        complexity=decision.complexity,
        provider=decision.suggested_provider
    )

@action(reads=["task", "provider"], writes=["result"])
def execute_with_provider(state: State) -> State:
    result = run_with_provider(state["task"], state["provider"])
    return state.update(result=result)

@action(reads=["result"], writes=["validated_result", "needs_retry"])
def judge_result(state: State) -> State:
    verdict = judge_agent_output(state["task"], state["result"])
    return state.update(
        validated_result=state["result"] if verdict.passes_review else None,
        needs_retry=verdict.should_retry
    )

escalation_app = (
    ApplicationBuilder()
    .with_actions(assess_complexity, execute_with_provider, judge_result)
    .with_transitions(
        ("assess_complexity", "execute_with_provider"),
        ("execute_with_provider", "judge_result"),
        ("judge_result", "execute_with_provider", when(needs_retry=True)),  # Retry
        ("judge_result", "complete", when(needs_retry=False)),
    )
    .with_state_persister(SQLLitePersister(db_path=".scrappy/state.db"))
    .with_tracker(project="scrappy-agent")
    .build()
)
```

**Benefit**:
- Automatic checkpointing at each step
- Can resume if interrupted
- Visual debugging via Burr telemetry UI

#### 2. Judge/Magistrate as State Machine

```python
@action(reads=["agent_output"], writes=["judge_verdict"])
def first_review(state: State) -> State:
    verdict = judge_agent_output(state["agent_output"])
    return state.update(judge_verdict=verdict)

@action(reads=["agent_output", "judge_verdict"], writes=["final_verdict"])
def appeal_review(state: State) -> State:
    # Second judge reviews first judge's decision
    appeal = appeal_verdict(state["agent_output"], state["judge_verdict"])
    return state.update(final_verdict=appeal)

judge_app = (
    ApplicationBuilder()
    .with_actions(first_review, appeal_review, deliver_result)
    .with_transitions(
        ("first_review", "deliver_result", when(passes_review=True)),
        ("first_review", "appeal_review", when(passes_review=False)),
        ("appeal_review", "deliver_result"),
    )
    .build()
)
```

---

## Implementation Roadmap

### Phase 1: Instructor (Week 1-2) - Immediate Impact

**Goal**: Eliminate JSON parsing failures, improve classification reliability

1. Add dependency: `pip install "instructor[litellm]"`
2. Create `src/scrappy/llm/structured.py`:
   - `TaskClassification` model
   - `AgentAction` model
   - `EscalationDecision` model
   - Client factory with provider support
3. Replace `json_extractor.py` (delete 259 lines)
4. Simplify `response_parser.py` (reduce 555 to ~50 lines)
5. Refactor router LLM classification

**Deliverable**: ~790 lines removed, more reliable parsing

### Phase 2: Seamless Escalation (Week 2-3) - UX Win

**Goal**: Users never think about model selection

1. Implement `EscalationDecision` with Instructor
2. Add escalation logic to task router
3. Configure provider tiers:
   - Fast: Groq, Cerebras (questions, simple tasks)
   - Quality: Claude, GPT-4 (refactoring, complex tasks)
4. Add confidence-based fallback

**Deliverable**: Automatic speed/quality tradeoff

### Phase 3: Context Priming (Week 3) - Quick Win

**Goal**: Agent runs tests correctly on first try

1. Implement `TestConfigHints` detection
2. Add framework detection (pytest, jest, etc.)
3. Inject hints into agent context
4. Test with common project structures

**Deliverable**: Better first-try success rate for test commands

### Phase 4: Judge Pattern (Week 4) - Quality

**Goal**: Catch errors before user sees them

1. Implement `JudgeVerdict` with Instructor
2. Add judge step to agent loop (after execution, before display)
3. Implement retry logic with judge guidance
4. Add confidence threshold (only retry if fixable)

**Deliverable**: Self-correcting agent, higher quality outputs

### Phase 5: DSPy Optimization (Week 5-6) - Long-term

**Goal**: Improve over time with usage data

1. Add DSPy dependency
2. Convert key prompts to DSPy signatures
3. Set up training data collection
4. Implement optimization pipeline
5. A/B test optimized vs baseline

**Deliverable**: Prompts that improve automatically

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Input                               │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Task Router + Escalation                      │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Instructor: EscalationDecision                          │    │
│  │  - complexity: simple|moderate|complex                   │    │
│  │  - suggested_provider: fast|quality                      │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
            ┌───────────────┐       ┌───────────────┐
            │  Fast Model   │       │ Quality Model │
            │  (Groq/Cere)  │       │ (Claude/GPT)  │
            └───────────────┘       └───────────────┘
                    │                       │
                    └───────────┬───────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Context Priming                             │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  TestConfigHints + Framework Detection                   │    │
│  │  - Injects pytest.ini, conftest.py awareness             │    │
│  │  - Adds recommended commands to context                  │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Agent Loop                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Instructor: AgentAction                                 │    │
│  │  - thought, action, parameters                           │    │
│  │  - Replaces JSONResponseParser                           │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Judge/Magistrate                             │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Instructor: JudgeVerdict                                │    │
│  │  - Validates output before display                       │    │
│  │  - Triggers retry if issues found                        │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      User Output                                 │
│                   (Validated, High Quality)                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## Success Metrics

| Metric | Current | Target | How to Measure |
|--------|---------|--------|----------------|
| JSON parse failures | ~5% | <0.5% | Error logs |
| First-try test success | ~60% | >90% | User feedback |
| Escalation accuracy | N/A | >85% | Manual review sample |
| Self-caught errors | 0% | >20% | Judge intervention rate |
| Code lines | ~2,500 | ~1,050 | Line count |

---

## Conclusion

The combination of **Instructor** (structured outputs), **DSPy** (prompt optimization), and selective **Burr** (state management) provides:

1. **Immediate wins**: ~790 lines removed, more reliable parsing
2. **UX improvements**: Seamless escalation, better first-try success
3. **Quality gains**: Self-validating outputs via Judge pattern
4. **Long-term benefits**: Prompts that improve with usage

**Start with Instructor** - it has the highest impact-to-effort ratio and unlocks all three near-term features.
