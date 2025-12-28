"""
Pydantic models for the agent loop.

Contains policy models for verification and approval, as well as
structured data models for planning and execution.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class StepStatus(str, Enum):
    """Status of a plan step."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class Step(BaseModel):
    """
    A single step in an execution plan.

    Represents an atomic unit of work the agent will perform.
    Steps are executed sequentially and may involve tool calls.
    """

    id: str = Field(description="Unique identifier for the step")
    description: str = Field(description="Human-readable description of what this step does")
    tool: Optional[str] = Field(default=None, description="Tool to use for this step, if any")
    parameters: dict = Field(default_factory=dict, description="Parameters for the tool")
    status: StepStatus = Field(default=StepStatus.PENDING, description="Current status of the step")
    depends_on: list[str] = Field(
        default_factory=list, description="IDs of steps that must complete first"
    )
    verification_required: bool = Field(
        default=True, description="Whether this step requires verification"
    )
    is_read_only: bool = Field(
        default=False, description="Whether this step only reads (no verification needed)"
    )
    execution_result: Optional[str] = Field(
        default=None, description="Result after execution"
    )
    verification_result: Optional["VerificationResult"] = Field(
        default=None, description="Verification result after execution"
    )
    retry_count: int = Field(default=0, description="Number of retry attempts for this step")
    started_at: Optional[datetime] = Field(default=None, description="When execution started")
    completed_at: Optional[datetime] = Field(default=None, description="When execution completed")
    error_message: Optional[str] = Field(default=None, description="Error message if step failed")

    def mark_started(self) -> None:
        """Mark the step as started, setting status and timestamp."""
        self.started_at = datetime.now(timezone.utc)
        self.status = StepStatus.IN_PROGRESS

    def mark_completed(self, result: str) -> None:
        """
        Mark the step as completed successfully.

        Args:
            result: The execution result to store
        """
        self.completed_at = datetime.now(timezone.utc)
        self.execution_result = result
        self.status = StepStatus.COMPLETED

    def mark_failed(self, error: str) -> None:
        """
        Mark the step as failed.

        Args:
            error: The error message describing the failure
        """
        self.completed_at = datetime.now(timezone.utc)
        self.status = StepStatus.FAILED
        self.error_message = error

    def can_retry(self, policy: VerificationPolicy) -> bool:
        """
        Check if the step can be retried based on policy.

        Args:
            policy: The verification policy with max retry settings

        Returns:
            True if retry count is below the maximum allowed
        """
        return self.retry_count < policy.max_fix_attempts


class Plan(BaseModel):
    """
    An execution plan for a user request.

    Contains a sequence of steps to accomplish the user's goal.
    Plans are created by the planner and executed step-by-step.
    """

    id: str = Field(description="Unique identifier for the plan")
    goal: str = Field(description="The user's goal this plan addresses")
    steps: list[Step] = Field(default_factory=list, description="Ordered list of steps")
    context: Optional[str] = Field(default=None, description="Additional context for the plan")
    revision_count: int = Field(default=0, description="Number of times this plan has been revised")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the plan was created",
    )
    approved_at: Optional[datetime] = Field(
        default=None, description="When user approved the plan"
    )
    approval_mode: Optional[str] = Field(
        default=None, description="Approval mode: 'all', 'step_by_step', or None"
    )

    def current_step(self) -> Optional[Step]:
        """
        Get the first pending or in-progress step.

        Returns:
            The current step to work on, or None if all done
        """
        for step in self.steps:
            if step.status in (StepStatus.PENDING, StepStatus.IN_PROGRESS):
                return step
        return None

    def next_step(self) -> Optional[Step]:
        """
        Get the next pending step after any in-progress step.

        Returns:
            The next pending step, or None if no more pending steps
        """
        found_current = False
        for step in self.steps:
            if step.status == StepStatus.IN_PROGRESS:
                found_current = True
            elif step.status == StepStatus.PENDING:
                if found_current:
                    return step
                # If no in-progress step, return first pending
                return step
        return None

    def all_completed(self) -> bool:
        """
        Check if all steps are completed (or skipped).

        Returns:
            True if no pending or in-progress steps remain
        """
        for step in self.steps:
            if step.status in (StepStatus.PENDING, StepStatus.IN_PROGRESS):
                return False
        return True

    def completed_steps(self) -> list[Step]:
        """
        Get all completed steps.

        Returns:
            List of steps with COMPLETED status
        """
        return [step for step in self.steps if step.status == StepStatus.COMPLETED]

    def failed_steps(self) -> list[Step]:
        """
        Get all failed steps.

        Returns:
            List of steps with FAILED status
        """
        return [step for step in self.steps if step.status == StepStatus.FAILED]

    def progress_summary(self) -> str:
        """
        Get a human-readable progress summary.

        Returns:
            String like "[Step 2/5] description" or "Complete" if done
        """
        if not self.steps:
            return "No steps"

        completed_count = len(self.completed_steps())
        failed_count = len(self.failed_steps())
        total = len(self.steps)

        current = self.current_step()
        if current is None:
            # No pending/in-progress steps - check if any failed
            if failed_count > 0:
                return f"Stopped ({completed_count}/{total} completed, {failed_count} failed)"
            return f"Complete ({total}/{total} steps)"

        # Find current step index (1-based for display)
        current_index = self.steps.index(current) + 1
        return f"[Step {current_index}/{total}] {current.description}"

    def can_revise(self, policy: "VerificationPolicy") -> bool:
        """
        Check if the plan can be revised based on policy.

        Args:
            policy: The verification policy with revision limits

        Returns:
            True if revision count is below the hard cap
        """
        return self.revision_count < policy.hard_revision_cap


class VerificationResult(BaseModel):
    """
    Result of a verification operation.

    Contains the outcome of running tests, linting, or type checking
    on modified files.
    """

    success: bool = Field(description="Whether verification passed")
    message: str = Field(default="", description="Summary of verification outcome")
    errors: list[str] = Field(default_factory=list, description="List of error messages")
    warnings: list[str] = Field(default_factory=list, description="List of warning messages")
    files_checked: list[str] = Field(default_factory=list, description="Files that were verified")


class UnitTestResult(BaseModel):
    """
    Result of running tests.

    Contains detailed information about test execution.

    Note: Named UnitTestResult (not TestResult) to avoid pytest collection warnings.
    Pytest collects any class starting with "Test" as a test class.
    """

    success: bool = Field(description="Whether all tests passed")
    passed: int = Field(default=0, description="Number of tests that passed")
    failed: int = Field(default=0, description="Number of tests that failed")
    skipped: int = Field(default=0, description="Number of tests that were skipped")
    errors: list[str] = Field(default_factory=list, description="Error messages from failed tests")
    output: str = Field(default="", description="Raw test output")


class LintResult(BaseModel):
    """
    Result of running linting.

    Contains information about lint violations found.
    """

    success: bool = Field(description="Whether linting passed (no errors)")
    error_count: int = Field(default=0, description="Number of lint errors")
    warning_count: int = Field(default=0, description="Number of lint warnings")
    errors: list[str] = Field(default_factory=list, description="Error messages")
    warnings: list[str] = Field(default_factory=list, description="Warning messages")
    files_checked: list[str] = Field(default_factory=list, description="Files that were linted")


class TypecheckResult(BaseModel):
    """
    Result of running type checking.

    Contains information about type errors found.
    """

    success: bool = Field(description="Whether type checking passed")
    error_count: int = Field(default=0, description="Number of type errors")
    warning_count: int = Field(default=0, description="Number of type warnings")
    errors: list[str] = Field(default_factory=list, description="Error messages")
    warnings: list[str] = Field(default_factory=list, description="Warning messages")
    files_checked: list[str] = Field(default_factory=list, description="Files that were checked")


class VerificationPolicy(BaseModel):
    """
    Configurable policy for what fails verification.

    Controls how strict the verification process is and how many
    fix attempts are allowed before giving up.
    """

    fail_on_lint_errors: bool = Field(
        default=True, description="Whether lint errors cause verification to fail"
    )
    fail_on_lint_warnings: bool = Field(
        default=False, description="Whether lint warnings cause verification to fail"
    )
    fail_on_type_errors: bool = Field(
        default=True, description="Whether type errors cause verification to fail"
    )
    fail_on_type_warnings: bool = Field(
        default=False, description="Whether type warnings cause verification to fail"
    )
    fail_on_test_failure: bool = Field(
        default=True, description="Whether test failures cause verification to fail"
    )
    fail_on_test_skip: bool = Field(
        default=False, description="Whether skipped tests cause verification to fail"
    )
    max_fix_attempts: int = Field(
        default=3,
        ge=1,
        description="Maximum fix attempts per step before giving up",
    )
    max_plan_revisions: int = Field(
        default=2,
        ge=0,
        description="Soft limit on plan revisions (ask user after this)",
    )
    hard_revision_cap: int = Field(
        default=5,
        ge=1,
        description="Hard limit on plan revisions (fail after this)",
    )
    min_revision_interval_seconds: float = Field(
        default=5.0,
        ge=0.0,
        description="Minimum seconds between plan revisions (rate limiting)",
    )

    def should_fail(
        self,
        lint_result: Optional[LintResult] = None,
        typecheck_result: Optional[TypecheckResult] = None,
        test_result: Optional[UnitTestResult] = None,
    ) -> tuple[bool, str]:
        """
        Determine if verification should fail based on results.

        Args:
            lint_result: Result from linting, if performed
            typecheck_result: Result from type checking, if performed
            test_result: Result from tests, if performed

        Returns:
            Tuple of (should_fail, reason)
        """
        reasons = []

        if lint_result:
            if self.fail_on_lint_errors and lint_result.error_count > 0:
                reasons.append(f"{lint_result.error_count} lint error(s)")
            if self.fail_on_lint_warnings and lint_result.warning_count > 0:
                reasons.append(f"{lint_result.warning_count} lint warning(s)")

        if typecheck_result:
            if self.fail_on_type_errors and typecheck_result.error_count > 0:
                reasons.append(f"{typecheck_result.error_count} type error(s)")
            if self.fail_on_type_warnings and typecheck_result.warning_count > 0:
                reasons.append(f"{typecheck_result.warning_count} type warning(s)")

        if test_result:
            if self.fail_on_test_failure and test_result.failed > 0:
                reasons.append(f"{test_result.failed} test failure(s)")
            if self.fail_on_test_skip and test_result.skipped > 0:
                reasons.append(f"{test_result.skipped} test(s) skipped")

        if reasons:
            return True, "; ".join(reasons)
        return False, ""


class ApprovalPolicy(BaseModel):
    """
    Policy for plan and step approval.

    Controls what requires user approval before execution and
    identifies dangerous commands that should always require approval.
    """

    require_plan_approval: bool = Field(
        default=True,
        description="Whether plans require user approval (always True per Reba's ruling)",
    )
    auto_approve_read_only: bool = Field(
        default=True,
        description="Whether read-only operations (read_file, search_code) are auto-approved",
    )
    dangerous_commands: list[str] = Field(
        default_factory=lambda: ["rm", "git push", "DROP", "DELETE"],
        description="Commands that always require explicit approval",
    )

    # Patterns that indicate command chaining/substitution (security risk)
    _DANGEROUS_PATTERNS: list[str] = [
        r'[;&|]',          # Command chaining: ; && || |
        r'`',              # Backtick command substitution
        r'\$\(',           # Dollar command substitution $(...)
        r'\\x[0-9a-fA-F]{2}',  # Hex escapes \x00
        r'\\u[0-9a-fA-F]{4}',  # Unicode escapes \u0000
    ]

    def is_dangerous(self, command: str) -> bool:
        """
        Check if a command contains dangerous patterns.

        Uses word boundary detection for single-word patterns to avoid
        false positives (e.g., "firmware" should not match "rm").

        Also detects command chaining, substitution, and encoding bypass attempts.

        Args:
            command: The command string to check

        Returns:
            True if the command contains any dangerous pattern
        """
        # First check for command chaining/substitution patterns
        # These can be used to bypass simple command detection
        for pattern in self._DANGEROUS_PATTERNS:
            if re.search(pattern, command):
                return True

        command_lower = command.lower()

        # Check for configured dangerous commands
        for danger in self.dangerous_commands:
            danger_lower = danger.lower()
            # Use word boundaries for single-word patterns
            if " " in danger_lower:
                # Multi-word pattern (e.g., "git push") - substring match is OK
                if danger_lower in command_lower:
                    return True
            else:
                # Single-word pattern - require word boundary
                pattern = rf"\b{re.escape(danger_lower)}\b"
                if re.search(pattern, command_lower):
                    return True
        return False

    def requires_approval(self, tool_name: str, is_read_only: bool = False) -> bool:
        """
        Check if an operation requires user approval.

        Args:
            tool_name: Name of the tool being invoked
            is_read_only: Whether the operation is read-only

        Returns:
            True if approval is required
        """
        if is_read_only and self.auto_approve_read_only:
            return False
        return True


class PlanExecutionState(BaseModel):
    """
    Tracks the full execution state of a plan.

    Maintains checkpoints for rollback capability and tracks
    progress through the plan's steps.
    """

    plan: Plan = Field(description="The plan being executed")
    current_step_index: int = Field(
        default=0, description="Index of the current step being executed"
    )
    checkpoint_hash: Optional[str] = Field(
        default=None, description="Git checkpoint hash before execution started"
    )
    step_checkpoints: dict[str, str] = Field(
        default_factory=dict, description="Map of step_id to git hash at completion"
    )
    started_at: Optional[datetime] = Field(
        default=None, description="When execution started"
    )
    completed_at: Optional[datetime] = Field(
        default=None, description="When execution completed"
    )

    def advance(self) -> Optional[Step]:
        """
        Advance to the next step and return it.

        Returns:
            The next step to execute, or None if no more steps
        """
        if self.current_step_index >= len(self.plan.steps):
            return None

        # Find the next pending step starting from current index
        while self.current_step_index < len(self.plan.steps):
            step = self.plan.steps[self.current_step_index]
            if step.status == StepStatus.PENDING:
                return step
            self.current_step_index += 1

        return None

    def rollback_available(self) -> bool:
        """
        Check if rollback is possible.

        Returns:
            True if there's a checkpoint to roll back to
        """
        return self.checkpoint_hash is not None


# Allow Step to reference VerificationResult now that it's defined
Step.model_rebuild()
