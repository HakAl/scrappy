# Agent Loop Epic - Architecture Audit

## Current Execution Flow

```
User Input (CLI)
    |
    v
interactive.py::_process_input()
    |
    +-- Commands (/foo) --> command_router.route()
    |
    +-- Chat --> task_router.handle_auto_route_streaming_sync()
                    |
                    v
                TaskRouter.route_streaming()
                    |
                    v
                _prepare_for_execution()
                    |
                    +-- 1. classifier.classify() [rule-based]
                    +-- 2. Apply provider override
                    +-- 3. Apply confidence escalation
                    +-- 4. LLM fallback (if low confidence) [BROKEN - scrappy-cij]
                    +-- 5. Clarify intent (if still ambiguous)
                    +-- 6. Resolve provider
                    +-- 7. Apply pre-execution hooks
                    |
                    v
                Select Strategy by TaskType
                    |
                    +-- DIRECT_COMMAND --> DirectExecutor
                    +-- CODE_GENERATION --> AgentExecutor
                    +-- RESEARCH --> ResearchExecutor
                    +-- CONVERSATION --> ConversationExecutor
                    |
                    v
                strategy.execute_streaming() or strategy.execute()
                    |
                    v
                Apply post-execution hooks
                    |
                    v
                ExecutionResult
```

## Task Types and Strategies

| TaskType | Strategy | Lines | Purpose |
|----------|----------|-------|---------|
| DIRECT_COMMAND | DirectExecutor | 124 | Shell commands, no LLM |
| CODE_GENERATION | AgentExecutor | 296 | Full planning, tool use |
| RESEARCH | ResearchExecutor | 538 | Info gathering, fast provider |
| CONVERSATION | ConversationExecutor | 157 | Simple Q&A |

## Dead Code Identified

### src/scrappy/llm/

| File | Status | Reason |
|------|--------|--------|
| models.py | KEEP | Used by router.py, delegation.py |
| adapters.py | DELETE | Standalone adapters, replaced by LiteLLMService |
| protocols.py | DELETE | Only used by adapters.py |
| testing.py | DELETE | MockStructuredProvider for dead adapters |

### tests/llm/

| File | Status |
|------|--------|
| test_models.py | KEEP |
| test_adapters.py | DELETE |
| test_testing.py | DELETE |

### task_router/pure_functions.py

| Function | Status |
|----------|--------|
| parse_llm_classification_response() | ALREADY DELETED (this session) |

## Blocking Issues

1. **scrappy-cij**: Instructor mode bug blocks LLM classification fallback
2. **No verification step**: Code gets written but not tested
3. **No plan persistence**: Plans are not structured or tracked

## What's Missing for Agent Loop

### 1. Planner Component
- Structured plan output (requires Instructor)
- Step dependencies
- Acceptance criteria per step
- User approval flow

### 2. Executor Component
- Step-by-step execution with observation
- Progress tracking (integrate with TodoWrite?)
- Rollback capability on failure

### 3. Verifier Component
- Test runner integration (pytest)
- Lint check (ruff)
- Type check (mypy)
- Endpoint verification (httpx/Playwright)
- Security scan for sensitive tasks (bandit)

### 4. Feedback Loop
- Detect verification failures
- Generate fix attempts
- Retry with modified approach
- Escalate to user if stuck

## Architecture Proposal

```
User Input
    |
    v
+------------------+
|   AgentLoop      |  <-- NEW: Unified orchestration
+------------------+
    |
    +-- understand() --> Classify + gather context
    |
    +-- plan() --> Structured Plan with steps
    |       |
    |       v
    |   [User Approval]
    |
    +-- execute() --> For each step:
    |       |
    |       +-- AgentExecutor (current, for code)
    |       +-- ResearchExecutor (current, for research)
    |       +-- DirectExecutor (current, for commands)
    |
    +-- verify() --> For each step:
    |       |
    |       +-- Run tests
    |       +-- Lint/type check
    |       +-- Custom verification
    |
    +-- [Iterate if failed]
    |
    v
Success/Report
```

## Proposed Models

```python
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

class StepType(str, Enum):
    RESEARCH = "research"      # Gather information
    CODE = "code"              # Write/modify code
    COMMAND = "command"        # Run shell command
    VERIFY = "verify"          # Run tests/checks
    APPROVE = "approve"        # User approval checkpoint

class StepStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

class Step(BaseModel):
    """Single step in an execution plan."""
    id: str
    type: StepType
    description: str
    depends_on: list[str] = Field(default_factory=list)
    acceptance_criteria: str = ""
    status: StepStatus = StepStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None

class Plan(BaseModel):
    """Structured execution plan."""
    goal: str = Field(description="What the user wants to achieve")
    context: str = Field(description="Relevant codebase context")
    steps: list[Step] = Field(default_factory=list)
    current_step: int = 0
    status: str = "pending"  # pending, approved, executing, completed, failed

class VerificationResult(BaseModel):
    """Result of verification step."""
    passed: bool
    tests_run: int = 0
    tests_passed: int = 0
    lint_errors: int = 0
    type_errors: int = 0
    issues: list[str] = Field(default_factory=list)
```

## AgentLoop Interface

```python
class AgentLoop:
    """Unified plan-execute-verify loop."""

    def __init__(
        self,
        orchestrator: OrchestratorLike,
        planner: Planner,
        verifier: Verifier,
    ):
        self.orchestrator = orchestrator
        self.planner = planner
        self.verifier = verifier
        self.strategies = {
            StepType.RESEARCH: ResearchExecutor(...),
            StepType.CODE: AgentExecutor(...),
            StepType.COMMAND: DirectExecutor(...),
        }

    async def solve(self, user_input: str) -> ExecutionResult:
        # 1. Create plan
        plan = await self.planner.create(user_input)

        # 2. Get approval
        plan = await self.approve(plan)
        if plan.status == "rejected":
            return ExecutionResult(success=False, output="Plan rejected")

        # 3. Execute steps
        for step in plan.steps:
            if step.status == StepStatus.SKIPPED:
                continue

            # Check dependencies
            if not self._deps_satisfied(step, plan):
                continue

            # Execute
            step.status = StepStatus.IN_PROGRESS
            result = await self._execute_step(step)

            # Verify
            if step.type in (StepType.CODE, StepType.COMMAND):
                verification = await self.verifier.verify(step, result)
                if not verification.passed:
                    # Retry logic
                    result = await self._fix_and_retry(step, verification)

            step.result = result
            step.status = StepStatus.COMPLETED

        return ExecutionResult(success=True, output=self._summarize(plan))
```

## Implementation Phases (FINALIZED)

Status updated: 2025-12-27

### Phase 0: Fix Blockers - COMPLETED
- [x] scrappy-cij: Fix Instructor mode bug - CLOSED
- [x] scrappy-2pg: Delete dead code - CLOSED

### Phase 0.5: Protocol Definitions (scrappy-022) - READY
- [ ] PlannerProtocol, VerifierProtocol
- [ ] VerificationPolicy, ApprovalPolicy
- [ ] Error hierarchy (AgentLoopError, etc.)

### Phase 1: Models (scrappy-y8p)
- [ ] StepType, StepStatus, PlanStatus enums
- [ ] Step model with fix_attempts, is_modifying
- [ ] Plan model with progress tracking
- [ ] VerificationResult model

### Phase 2: Planner (scrappy-ixw)
- [ ] Planner implementing PlannerProtocol
- [ ] Structured plan via Instructor
- [ ] Dangerous command detection
- [ ] Revision logic (soft 2, hard 5)

### Phase 3: Verifier (scrappy-8h6)
- [ ] Verifier implementing VerifierProtocol
- [ ] pytest, ruff, mypy integration
- [ ] Test discovery heuristics
- [ ] Policy-based pass/fail

### Phase 4: Integration (scrappy-qhq)
- [ ] solve() method on AgentLoop
- [ ] Git checkpoint before modifying steps
- [ ] Escape hatch: [E]dit/[S]kip/[R]ollback/[A]bort
- [ ] Progress visibility: "Step 2/5: ..."
- [ ] Partial success handling

## Locked Decisions

| Decision | Resolution | Authority |
|----------|------------|-----------|
| Which paths? | CODE_GENERATION only | Neo |
| Enhance or replace? | ENHANCE existing AgentLoop | Neo |
| When verify? | After modifying steps + plan end | Neo |
| What fails? | Errors fatal, warnings not (configurable) | Neo |
| Playwright? | P2, deferred | Neo |
| Plan approval | ALWAYS required | Reba (override) |
| Retry limits | 3/step, soft 2, hard 5 revisions | Peter + Reba |
| Git checkpoints | Before each modifying step | Reba |
| Execution model | Linear only (no parallelism v1) | Peter |
| Escape hatch | [E]dit/[S]kip/[R]ollback/[A]bort | Reba |
| Partial success | Keep completed, offer rollback | Reba |

## Out of Scope (P2)
- Playwright/web endpoint verification
- Plan persistence across sessions
- Plan diffing on revision
- DAG step dependencies
- Concurrent step execution
- Token budgets per step/plan
