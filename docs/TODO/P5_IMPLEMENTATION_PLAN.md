# P5 Issues Implementation Plan

## Overview

These issues have been investigated and require attention.

P5 issues are confirmed bugs that impact efficiency and edge-case behavior but are not blocking.

---

## Issues Summary

| Issue | Status | Impact | Effort |
|-------|--------|--------|--------|
| 5.3 Auto-explore Stale Context | CONFIRMED BUG | Medium | Medium |
| 5.4 Premature Task Completion | PARTIALLY CONFIRMED | Medium | Medium |

---

#### Step 2: Modify explore_codebase() flow

**File:** `src/cli/codebase.py:86-142`

Change from:
```python
summary = self.orchestrator.context.generate_summary(llm_summary)
# ... later ...
if self.io.confirm("Save summary?"):
    summary_file.write_text(summary)
```

To:
```python
# Step 1: Explore and scan files only
result = self.orchestrator.context.explore(force=True)
progress.advance(1)

# Step 2: Set up lazy summary (no API call yet)
lazy_summary = LazySummaryGenerator()
lazy_summary.set_context(self._build_summary_prompt(result))
progress.advance(1)

# ... display exploration results ...

# Step 3: Only generate summary if user wants to save
if self.io.confirm("Generate and save summary?", default=False):
    summary = lazy_summary.generate(llm_summary)
    summary_file.write_text(summary)
    self.io.secho(f"Saved to: {summary_file}", fg="green")
else:
    self.io.echo("Summary generation skipped.")
```

#### Step 3: Add tests

**File:** `tests/cli/test_codebase_lazy_summary.py` (new)

```python
"""Tests for lazy summary generation."""

import pytest
from unittest.mock import Mock, call

from src.context.lazy_summary import LazySummaryGenerator


class TestLazySummaryGenerator:
    """Tests for LazySummaryGenerator."""

    def test_no_api_call_until_generate(self):
        """Summary is not generated until explicitly requested."""
        lazy = LazySummaryGenerator()
        llm_func = Mock(return_value="Summary")

        lazy.set_context("prompt")

        # No call yet
        llm_func.assert_not_called()
        assert not lazy.has_summary()

    def test_generates_on_demand(self):
        """Summary generated when requested."""
        lazy = LazySummaryGenerator()
        llm_func = Mock(return_value="Generated summary")

        lazy.set_context("prompt")
        result = lazy.generate(llm_func)

        assert result == "Generated summary"
        llm_func.assert_called_once_with("prompt")

    def test_caches_result(self):
        """Repeated generate() calls return cached result."""
        lazy = LazySummaryGenerator()
        llm_func = Mock(return_value="Summary")

        lazy.set_context("prompt")
        lazy.generate(llm_func)
        lazy.generate(llm_func)

        # Only one call despite two generate() calls
        assert llm_func.call_count == 1

    def test_invalidate_clears_cache(self):
        """invalidate() clears cached summary."""
        lazy = LazySummaryGenerator()
        llm_func = Mock(return_value="Summary")

        lazy.set_context("prompt")
        lazy.generate(llm_func)
        lazy.invalidate()

        assert not lazy.has_summary()
```

### Files to Modify

1. `src/context/lazy_summary.py` - NEW: LazySummaryGenerator class
2. `src/cli/codebase.py:86-142` - Refactor to use lazy generation
3. `tests/cli/test_codebase_lazy_summary.py` - NEW: Tests for lazy summary

### Risk Assessment

- **Low risk**: Changes are isolated to exploration flow
- **Testable**: Easy to mock LLM function for testing

---

## Issue 5.3: Auto-explore Stale Context

### Problem Statement

Auto-explore skips re-indexing if context is cached, even when files have been added/modified since the last exploration.
This causes semantic search to miss content in new/modified files.

### Current Behavior

```python
# context_coordinator.py:98
def auto_explore(self):
    if self._context.is_explored():
        return {'status': 'cached', ...}  # ALWAYS skips if explored
```

### Desired Behavior

Check if context is stale (files added/modified since last exploration) and trigger re-indexing when needed.

### Design

**Approach: Staleness Detection via File Fingerprinting**

1. Define a `StalenessCheckerProtocol` for detecting context staleness
2. Store fingerprint (file count + max mtime) after each exploration
3. On `auto_explore()`, compare current fingerprint with stored one
4. Trigger partial re-index if stale (only new/modified files)

**Protocol Definition:**

```python
@runtime_checkable
class StalenessCheckerProtocol(Protocol):
    """Protocol for detecting stale context."""

    def is_stale(self) -> bool:
        """Check if context needs refresh."""
        ...

    def get_changes(self) -> StalenessReport:
        """Get details about what changed."""
        ...

    def update_fingerprint(self) -> None:
        """Update stored fingerprint after refresh."""
        ...


@dataclass
class StalenessReport:
    """Report of what changed since last exploration."""
    is_stale: bool
    files_added: List[str]
    files_modified: List[str]
    files_deleted: List[str]
    last_check: datetime
```

### Implementation Steps

#### Step 1: Create StalenessChecker class

**File:** `src/context/staleness.py` (new)

```python
"""Staleness detection for codebase context."""

from typing import Set, Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class StalenessReport:
    """Report of what changed since last exploration."""
    is_stale: bool
    files_added: Set[str] = field(default_factory=set)
    files_modified: Set[str] = field(default_factory=set)
    files_deleted: Set[str] = field(default_factory=set)
    last_check: Optional[datetime] = None


@dataclass
class FileFingerprint:
    """Lightweight fingerprint of a file."""
    mtime: float
    size: int


class StalenessChecker:
    """
    Detects when codebase context is stale.

    Uses file modification times and sizes to detect changes
    without reading file contents.
    """

    def __init__(self, project_path: Path):
        self._project_path = project_path
        self._fingerprints: Dict[str, FileFingerprint] = {}
        self._last_check: Optional[datetime] = None

    def compute_fingerprints(self, files: Set[str]) -> Dict[str, FileFingerprint]:
        """Compute fingerprints for given files."""
        fingerprints = {}
        for file_path in files:
            full_path = self._project_path / file_path
            if full_path.exists():
                stat = full_path.stat()
                fingerprints[file_path] = FileFingerprint(
                    mtime=stat.st_mtime,
                    size=stat.st_size
                )
        return fingerprints

    def update_fingerprint(self, files: Set[str]) -> None:
        """Update stored fingerprints after exploration."""
        self._fingerprints = self.compute_fingerprints(files)
        self._last_check = datetime.now()

    def check_staleness(self, current_files: Set[str]) -> StalenessReport:
        """
        Check if context is stale compared to current file state.

        Args:
            current_files: Set of file paths that currently exist

        Returns:
            StalenessReport with details about changes
        """
        if not self._fingerprints:
            # No previous fingerprint - consider stale
            return StalenessReport(
                is_stale=True,
                files_added=current_files,
                last_check=self._last_check
            )

        previous_files = set(self._fingerprints.keys())
        current_fingerprints = self.compute_fingerprints(current_files)

        files_added = current_files - previous_files
        files_deleted = previous_files - current_files
        files_modified = set()

        # Check for modified files (different mtime or size)
        for file_path in current_files & previous_files:
            old_fp = self._fingerprints.get(file_path)
            new_fp = current_fingerprints.get(file_path)
            if old_fp and new_fp:
                if old_fp.mtime != new_fp.mtime or old_fp.size != new_fp.size:
                    files_modified.add(file_path)

        is_stale = bool(files_added or files_modified or files_deleted)

        return StalenessReport(
            is_stale=is_stale,
            files_added=files_added,
            files_modified=files_modified,
            files_deleted=files_deleted,
            last_check=self._last_check
        )

    def is_stale(self, current_files: Set[str]) -> bool:
        """Quick check if context is stale."""
        return self.check_staleness(current_files).is_stale
```

#### Step 2: Integrate with ContextCoordinator

**File:** `src/orchestrator/context_coordinator.py:80-106`

Change from:
```python
def auto_explore(self) -> Dict[str, Any]:
    if self._context.is_explored():
        return {'status': 'cached', ...}  # Always returns cached
```

To:
```python
def auto_explore(self) -> Dict[str, Any]:
    """Auto-explore with staleness detection."""
    if self._context.is_explored():
        # Check for staleness before returning cached
        if self._staleness_checker:
            current_files = self._get_current_files()
            report = self._staleness_checker.check_staleness(current_files)

            if report.is_stale:
                self.output.info(
                    f"[CONTEXT] Context stale: {len(report.files_added)} added, "
                    f"{len(report.files_modified)} modified, "
                    f"{len(report.files_deleted)} deleted"
                )
                return self._refresh_stale_context(report)

        # Not stale - use cached
        project_name = getattr(self._context.project_path, 'name', 'project')
        self.output.info(f"[CONTEXT] Loaded cached context for {project_name}")
        status = self._context.get_status()
        return {
            'status': 'cached',
            'cache_used': True,
            'total_files': status.get('total_files', 0),
        }

    # No cache - full exploration
    return self._full_explore()

def _refresh_stale_context(self, report: StalenessReport) -> Dict[str, Any]:
    """Refresh context for changed files only."""
    self.output.info("[CONTEXT] Refreshing stale context...")

    # For semantic search, only re-index changed files
    if self._semantic_manager and report.files_added | report.files_modified:
        changed_files = report.files_added | report.files_modified
        self.output.info(f"[CONTEXT] Re-indexing {len(changed_files)} files")
        # Partial re-index implementation

    # Update fingerprint
    if self._staleness_checker:
        self._staleness_checker.update_fingerprint(self._get_current_files())

    return {
        'status': 'refreshed',
        'files_added': len(report.files_added),
        'files_modified': len(report.files_modified),
        'files_deleted': len(report.files_deleted),
        'cache_used': True,
    }
```

#### Step 3: Update CodebaseContext to support partial refresh

**File:** `src/context/context.py`

Add method:
```python
def refresh_files(self, files: Set[str]) -> None:
    """
    Refresh context for specific files.

    Used for incremental updates when only some files changed.

    Args:
        files: Set of file paths to refresh
    """
    # Implementation for partial refresh
```

#### Step 4: Add tests

**File:** `tests/context/test_staleness.py` (new)

```python
"""Tests for staleness detection."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch
import tempfile
import time

from src.context.staleness import StalenessChecker, StalenessReport


class TestStalenessChecker:
    """Tests for StalenessChecker."""

    def test_fresh_context_not_stale(self, tmp_path):
        """Context is not stale when no files changed."""
        # Create test files
        (tmp_path / "file1.py").write_text("content1")
        (tmp_path / "file2.py").write_text("content2")

        checker = StalenessChecker(tmp_path)
        files = {"file1.py", "file2.py"}

        # Initial fingerprint
        checker.update_fingerprint(files)

        # Check staleness
        report = checker.check_staleness(files)

        assert not report.is_stale
        assert len(report.files_added) == 0
        assert len(report.files_modified) == 0

    def test_new_file_detected(self, tmp_path):
        """New files are detected as additions."""
        (tmp_path / "file1.py").write_text("content1")

        checker = StalenessChecker(tmp_path)
        checker.update_fingerprint({"file1.py"})

        # Add new file
        (tmp_path / "file2.py").write_text("content2")

        report = checker.check_staleness({"file1.py", "file2.py"})

        assert report.is_stale
        assert "file2.py" in report.files_added

    def test_modified_file_detected(self, tmp_path):
        """Modified files are detected."""
        test_file = tmp_path / "file1.py"
        test_file.write_text("original")

        checker = StalenessChecker(tmp_path)
        checker.update_fingerprint({"file1.py"})

        # Modify file (ensure mtime changes)
        time.sleep(0.1)
        test_file.write_text("modified content")

        report = checker.check_staleness({"file1.py"})

        assert report.is_stale
        assert "file1.py" in report.files_modified

    def test_deleted_file_detected(self, tmp_path):
        """Deleted files are detected."""
        (tmp_path / "file1.py").write_text("content1")
        (tmp_path / "file2.py").write_text("content2")

        checker = StalenessChecker(tmp_path)
        checker.update_fingerprint({"file1.py", "file2.py"})

        # "Delete" file2 by not including it
        report = checker.check_staleness({"file1.py"})

        assert report.is_stale
        assert "file2.py" in report.files_deleted
```

### Files to Modify

1. `src/context/staleness.py` - NEW: StalenessChecker class
2. `src/context/protocols.py` - Add StalenessCheckerProtocol
3. `src/orchestrator/context_coordinator.py:80-106` - Integrate staleness checking
4. `src/context/context.py` - Add refresh_files() method
5. `tests/context/test_staleness.py` - NEW: Tests for staleness detection

### Risk Assessment

- **Medium risk**: Changes affect auto-explore flow
- **Performance consideration**: Fingerprinting adds I/O, but is fast (stat only, no content read)

---

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
