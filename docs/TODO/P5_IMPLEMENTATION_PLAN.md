# P5 Issues Implementation Plan

## Overview

These issues have been investigated and require attention.

P5 issues are confirmed bugs that impact efficiency and edge-case behavior but are not blocking.

---

## Issues Summary

| Issue | Status | Impact | Effort |
|-------|--------|--------|--------|
| 5.4 Premature Task Completion | PARTIALLY CONFIRMED | Medium | Medium |



## Issue 5.4: Premature Task Completion

### Problem Statement

The agent may declare task completion prematurely, especially in dry-run mode where the meaningful actions guard is bypassed. 
Complex tasks may overwhelm the agent, causing it to give up early.

### Current Behavior

```python
# agent_loop.py:338-346
if not meaningful_actions and not self._dry_run:  # Bypassed in dry-run!
    return EvaluationResult(is_complete=False, ...)
```

### Desired Behavior

1. Apply meaningful actions check consistently (including dry-run)
2. Add task decomposition for complex tasks
3. Improve detection and handling of premature completion

### Design

**Approach: Multi-layered Completion Validation**

1. Define a `CompletionValidatorProtocol` for extensible completion checks
2. Apply meaningful actions check in all modes (remove dry-run bypass)
3. Add complexity estimation and task decomposition
4. Track progress indicators beyond just tool execution

**Protocol Definition:**

```python
@runtime_checkable
class CompletionValidatorProtocol(Protocol):
    """Protocol for validating task completion."""

    def validate_completion(
        self,
        action: AgentAction,
        state: ConversationState,
        config: AgentConfig
    ) -> CompletionValidation:
        """
        Validate if completion should be allowed.

        Returns:
            CompletionValidation with allow flag and reason
        """
        ...


@dataclass
class CompletionValidation:
    """Result of completion validation."""
    allow_completion: bool
    reason: str
    suggestions: List[str] = field(default_factory=list)
```

### Implementation Steps

#### Step 1: Create CompletionValidator class

**File:** `src/agent/completion_validator.py` (new)

```python
"""Validation for agent task completion."""

from typing import List, Set, Optional
from dataclasses import dataclass, field


@dataclass
class CompletionValidation:
    """Result of completion validation."""
    allow_completion: bool
    reason: str
    suggestions: List[str] = field(default_factory=list)


class CompletionValidator:
    """
    Validates that task completion is legitimate.

    Checks:
    1. Meaningful actions performed (file writes, commands)
    2. Task requirements addressed
    3. No obvious incomplete state
    """

    def __init__(self, meaningful_actions: Set[str]):
        """
        Initialize validator.

        Args:
            meaningful_actions: Set of action names considered meaningful
        """
        self._meaningful_actions = meaningful_actions

    def validate(
        self,
        tools_executed: List[str],
        task_description: str,
        result_text: Optional[str] = None
    ) -> CompletionValidation:
        """
        Validate completion request.

        Args:
            tools_executed: List of tools that were executed
            task_description: Original task description
            result_text: Agent's completion message

        Returns:
            CompletionValidation with result
        """
        # Check for meaningful work
        meaningful_work = [
            t for t in tools_executed
            if t in self._meaningful_actions
        ]

        if not meaningful_work:
            return CompletionValidation(
                allow_completion=False,
                reason="No meaningful actions performed",
                suggestions=[
                    "Use write_file to create or modify files",
                    "Use run_command to execute necessary commands",
                    "If the task requires no changes, explain why"
                ]
            )

        # Check for obvious incomplete indicators
        incomplete_indicators = self._check_incomplete_indicators(
            task_description, result_text
        )
        if incomplete_indicators:
            return CompletionValidation(
                allow_completion=False,
                reason=f"Task appears incomplete: {incomplete_indicators}",
                suggestions=["Address the incomplete items before completing"]
            )

        return CompletionValidation(
            allow_completion=True,
            reason="Completion validated"
        )

    def _check_incomplete_indicators(
        self,
        task: str,
        result: Optional[str]
    ) -> Optional[str]:
        """Check for signs of incomplete work."""
        if not result:
            return "No result message provided"

        # Check for "TODO" or "will implement" in result
        result_lower = result.lower()
        incomplete_phrases = [
            "will implement",
            "will add",
            "need to add",
            "still need",
            "remaining work",
            "not yet implemented",
            "todo:",
            "fixme:",
        ]

        for phrase in incomplete_phrases:
            if phrase in result_lower:
                return f"Result contains incomplete indicator: '{phrase}'"

        return None
```

#### Step 2: Fix dry-run bypass

**File:** `src/agent/agent_loop.py:338-346`

Change from:
```python
if not meaningful_actions and not self._dry_run:
    # Bypass in dry-run mode
```

To:
```python
# Apply validation in ALL modes (including dry-run)
validation = self._completion_validator.validate(
    tools_executed=state.tools_executed,
    task_description=state.task,
    result_text=action.result_text
)

if not validation.allow_completion:
    self._ui.show_warning(
        f"Completion blocked: {validation.reason}"
    )
    if validation.suggestions:
        self._ui.show_progress(
            f"Suggestions: {', '.join(validation.suggestions)}"
        )
    return EvaluationResult(
        is_complete=False,
        should_continue=True,
        reason=validation.reason,
    )
```

#### Step 3: Add task complexity estimation

**File:** `src/agent/complexity.py` (new)

```python
"""Task complexity estimation."""

from dataclasses import dataclass
from typing import List, Tuple
import re


@dataclass
class ComplexityEstimate:
    """Estimated task complexity."""
    score: int  # 1-10
    indicators: List[str]
    suggested_max_iterations: int


class TaskComplexityEstimator:
    """
    Estimates task complexity to set appropriate iteration limits.

    Complexity indicators:
    - Multiple files mentioned
    - Multiple operations requested
    - Keywords like "refactor", "implement", "fix all"
    - Code generation vs simple edits
    """

    def estimate(self, task: str) -> ComplexityEstimate:
        """Estimate complexity of a task description."""
        indicators = []
        score = 1

        # Check for multiple targets
        if self._count_file_references(task) > 1:
            score += 2
            indicators.append("Multiple files referenced")

        # Check for multi-step keywords
        multi_step_keywords = [
            "and then", "after that", "also",
            "multiple", "all", "every", "each"
        ]
        for kw in multi_step_keywords:
            if kw in task.lower():
                score += 1
                indicators.append(f"Multi-step keyword: '{kw}'")
                break

        # Check for complex operation keywords
        complex_keywords = [
            ("refactor", 3),
            ("implement", 2),
            ("fix all", 3),
            ("test coverage", 2),
            ("migrate", 3),
        ]
        for kw, weight in complex_keywords:
            if kw in task.lower():
                score += weight
                indicators.append(f"Complex operation: '{kw}'")

        # Cap score
        score = min(score, 10)

        # Map score to iterations
        iteration_map = {
            1: 10, 2: 15, 3: 20, 4: 25, 5: 30,
            6: 35, 7: 40, 8: 45, 9: 50, 10: 50
        }

        return ComplexityEstimate(
            score=score,
            indicators=indicators,
            suggested_max_iterations=iteration_map.get(score, 20)
        )

    def _count_file_references(self, task: str) -> int:
        """Count apparent file references in task."""
        # Match patterns like file.py, path/to/file.js, etc.
        file_pattern = r'\b[\w/\\]+\.\w{1,4}\b'
        matches = re.findall(file_pattern, task)
        return len(set(matches))
```

#### Step 4: Add tests

**File:** `tests/agent/test_completion_validator.py` (new)

```python
"""Tests for completion validation."""

import pytest
from src.agent.completion_validator import (
    CompletionValidator,
    CompletionValidation
)


class TestCompletionValidator:
    """Tests for CompletionValidator."""

    @pytest.fixture
    def validator(self):
        """Create validator with default meaningful actions."""
        return CompletionValidator(
            meaningful_actions={'write_file', 'run_command', 'apply_diff'}
        )

    def test_blocks_completion_without_meaningful_work(self, validator):
        """Completion blocked when no meaningful actions performed."""
        result = validator.validate(
            tools_executed=['read_file', 'list_files'],
            task_description="Create a test file",
            result_text="Done!"
        )

        assert not result.allow_completion
        assert "No meaningful actions" in result.reason

    def test_allows_completion_with_meaningful_work(self, validator):
        """Completion allowed when meaningful actions performed."""
        result = validator.validate(
            tools_executed=['read_file', 'write_file'],
            task_description="Create a test file",
            result_text="Created test_example.py with unit tests."
        )

        assert result.allow_completion

    def test_blocks_incomplete_indicators(self, validator):
        """Completion blocked when result indicates incomplete work."""
        result = validator.validate(
            tools_executed=['write_file'],
            task_description="Implement feature X",
            result_text="Started implementation. Will add error handling later."
        )

        assert not result.allow_completion
        assert "incomplete indicator" in result.reason.lower()

    def test_provides_suggestions_on_block(self, validator):
        """Suggestions provided when completion is blocked."""
        result = validator.validate(
            tools_executed=[],
            task_description="Fix the bug",
            result_text="I analyzed the code."
        )

        assert not result.allow_completion
        assert len(result.suggestions) > 0
```

### Files to Modify

1. `src/agent/completion_validator.py` - NEW: CompletionValidator class
2. `src/agent/complexity.py` - NEW: TaskComplexityEstimator
3. `src/agent/protocols.py` - Add CompletionValidatorProtocol
4. `src/agent/agent_loop.py:338-346` - Remove dry-run bypass, use validator
5. `src/agent/agent_loop.py:536-564` - Improve premature completion handling
6. `tests/agent/test_completion_validator.py` - NEW: Tests

### Risk Assessment

- **Medium risk**: Changes affect core agent loop behavior
- **Breaking change consideration**: Removing dry-run bypass may affect existing workflows
- **Mitigation**: Make validation configurable via AgentConfig

---

## Implementation Order

Recommended order based on dependencies and risk:

### Phase 1: Low-risk, isolated changes

1. **Issue 5.2** - Lazy summary generation
   - Self-contained change
   - No dependencies on other issues
   - Immediate token cost savings

### Phase 2: Medium-risk infrastructure

2. **Issue 5.3** - Staleness detection
   - Requires new infrastructure (StalenessChecker)
   - Benefits from testing in isolation first
   - Enables better semantic search accuracy

### Phase 3: Core behavior changes

3. **Issue 5.4** - Completion validation
   - Affects core agent loop
   - Should be tested thoroughly

---

## Testing Strategy

### Unit Tests

Each new class should have comprehensive unit tests:
- `test_lazy_summary.py` - LazySummaryGenerator
- `test_staleness.py` - StalenessChecker
- `test_completion_validator.py` - CompletionValidator

### Integration Tests

Test the integrated behavior:
- `test_codebase_integration.py` - Lazy summary in explore flow
- `test_context_coordinator_integration.py` - Staleness with auto-explore
- `test_agent_loop_integration.py` - Completion validation in full loop

### Regression Tests

Ensure existing behavior is not broken:
- Run full test suite after each phase
- Manual testing of CLI workflows
- Verify dry-run mode still works correctly

---

## Rollback Plan

Each change should be:
- Reversible via git revert
- Isolated enough to not affect other components

Example feature flag:
```python
class AgentConfig:
    enable_completion_validation: bool = True
    enable_staleness_detection: bool = True
    enable_lazy_summary: bool = True
```

---

## Success Criteria

### Issue 5.2
- [ ] No LLM API call during explore unless user confirms save
- [ ] Summary generation works correctly when requested
- [ ] Tests pass for lazy summary behavior

### Issue 5.3
- [ ] Stale context detected when files added/modified
- [ ] Semantic search returns results from new files
- [ ] Fingerprinting performance < 100ms for 1000 files
- [ ] Tests pass for staleness detection

### Issue 5.4
- [ ] Premature completion blocked in dry-run mode
- [ ] Meaningful actions check applied consistently
- [ ] Agent provides helpful suggestions when blocked
- [ ] Tests pass for completion validation

---

## Appendix: File Change Summary

### New Files
- `src/context/lazy_summary.py`
- `src/context/staleness.py`
- `src/agent/completion_validator.py`
- `src/agent/complexity.py` (optional)
- `tests/cli/test_codebase_lazy_summary.py`
- `tests/context/test_staleness.py`
- `tests/agent/test_completion_validator.py`

### Modified Files
- `src/cli/codebase.py`
- `src/orchestrator/context_coordinator.py`
- `src/context/protocols.py`
- `src/agent/protocols.py`
- `src/agent/agent_loop.py`
- `src/context/context.py`
