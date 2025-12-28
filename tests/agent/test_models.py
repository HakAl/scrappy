"""
Tests for agent loop models and exceptions.

Tests behavior of policy models and exception hierarchy.
"""

from datetime import datetime, timezone

from scrappy.agent.models import (
    Step,
    StepStatus,
    Plan,
    PlanExecutionState,
    VerificationResult,
    UnitTestResult,
    LintResult,
    TypecheckResult,
    VerificationPolicy,
    ApprovalPolicy,
)
from scrappy.agent.exceptions import (
    AgentLoopError,
    PlanCreationError,
    PlanRejectedError,
    VerificationError,
    MaxRetriesExceededError,
    StepExecutionError,
)


# =============================================================================
# Step Model Tests
# =============================================================================


class TestStep:
    """Tests for Step model."""

    def test_step_defaults(self):
        """Step should have sensible defaults."""
        step = Step(id="step-1", description="Do something")

        assert step.id == "step-1"
        assert step.description == "Do something"
        assert step.tool is None
        assert step.parameters == {}
        assert step.status == StepStatus.PENDING
        assert step.depends_on == []
        assert step.verification_required is True

    def test_step_with_tool(self):
        """Step can specify a tool and parameters."""
        step = Step(
            id="step-2",
            description="Read a file",
            tool="read_file",
            parameters={"path": "test.py"},
        )

        assert step.tool == "read_file"
        assert step.parameters == {"path": "test.py"}

    def test_step_with_dependencies(self):
        """Step can depend on other steps."""
        step = Step(
            id="step-3",
            description="Final step",
            depends_on=["step-1", "step-2"],
        )

        assert step.depends_on == ["step-1", "step-2"]

    def test_step_new_fields_defaults(self):
        """Step should have new field defaults."""
        step = Step(id="step-1", description="Test")

        assert step.is_read_only is False
        assert step.execution_result is None
        assert step.verification_result is None
        assert step.retry_count == 0
        assert step.started_at is None
        assert step.completed_at is None
        assert step.error_message is None

    def test_mark_started_sets_status_and_timestamp(self):
        """mark_started should set IN_PROGRESS status and timestamp."""
        step = Step(id="step-1", description="Test")

        step.mark_started()

        assert step.status == StepStatus.IN_PROGRESS
        assert step.started_at is not None
        assert step.started_at.tzinfo == timezone.utc

    def test_mark_completed_sets_status_result_and_timestamp(self):
        """mark_completed should set COMPLETED status, result, and timestamp."""
        step = Step(id="step-1", description="Test")
        step.mark_started()

        step.mark_completed("Success: file written")

        assert step.status == StepStatus.COMPLETED
        assert step.execution_result == "Success: file written"
        assert step.completed_at is not None
        assert step.completed_at >= step.started_at

    def test_mark_failed_sets_status_and_error(self):
        """mark_failed should set FAILED status and error message."""
        step = Step(id="step-1", description="Test")
        step.mark_started()

        step.mark_failed("File not found: config.yaml")

        assert step.status == StepStatus.FAILED
        assert step.error_message == "File not found: config.yaml"
        assert step.completed_at is not None

    def test_can_retry_returns_true_when_below_max(self):
        """can_retry should return True when retry_count < max_fix_attempts."""
        step = Step(id="step-1", description="Test", retry_count=1)
        policy = VerificationPolicy(max_fix_attempts=3)

        assert step.can_retry(policy) is True

    def test_can_retry_returns_false_at_max(self):
        """can_retry should return False when retry_count >= max_fix_attempts."""
        step = Step(id="step-1", description="Test", retry_count=3)
        policy = VerificationPolicy(max_fix_attempts=3)

        assert step.can_retry(policy) is False

    def test_step_with_read_only_flag(self):
        """Step can be marked as read-only."""
        step = Step(
            id="step-1",
            description="Read config",
            is_read_only=True,
        )

        assert step.is_read_only is True

    def test_step_stores_verification_result(self):
        """Step can store a verification result."""
        step = Step(id="step-1", description="Test")
        verification = VerificationResult(
            success=True,
            message="All checks passed",
        )

        step.verification_result = verification

        assert step.verification_result is not None
        assert step.verification_result.success is True


# =============================================================================
# Plan Model Tests
# =============================================================================


class TestPlan:
    """Tests for Plan model."""

    def test_plan_defaults(self):
        """Plan should have sensible defaults."""
        plan = Plan(id="plan-1", goal="Fix the bug")

        assert plan.id == "plan-1"
        assert plan.goal == "Fix the bug"
        assert plan.steps == []
        assert plan.context is None
        assert plan.revision_count == 0

    def test_plan_with_steps(self):
        """Plan can contain multiple steps."""
        steps = [
            Step(id="s1", description="Find the bug"),
            Step(id="s2", description="Fix the bug", depends_on=["s1"]),
            Step(id="s3", description="Test the fix", depends_on=["s2"]),
        ]
        plan = Plan(id="plan-2", goal="Fix bug #123", steps=steps)

        assert len(plan.steps) == 3
        assert plan.steps[0].id == "s1"
        assert plan.steps[2].depends_on == ["s2"]

    def test_plan_new_fields_defaults(self):
        """Plan should have new field defaults."""
        plan = Plan(id="plan-1", goal="Test")

        assert plan.created_at is not None
        assert plan.created_at.tzinfo == timezone.utc
        assert plan.approved_at is None
        assert plan.approval_mode is None

    def test_current_step_returns_first_pending(self):
        """current_step should return the first pending step."""
        steps = [
            Step(id="s1", description="Step 1"),
            Step(id="s2", description="Step 2"),
        ]
        plan = Plan(id="plan-1", goal="Test", steps=steps)

        current = plan.current_step()

        assert current is not None
        assert current.id == "s1"

    def test_current_step_returns_in_progress(self):
        """current_step should return an in-progress step."""
        steps = [
            Step(id="s1", description="Step 1", status=StepStatus.COMPLETED),
            Step(id="s2", description="Step 2", status=StepStatus.IN_PROGRESS),
            Step(id="s3", description="Step 3"),
        ]
        plan = Plan(id="plan-1", goal="Test", steps=steps)

        current = plan.current_step()

        assert current is not None
        assert current.id == "s2"

    def test_current_step_returns_none_when_all_complete(self):
        """current_step should return None when all steps are done."""
        steps = [
            Step(id="s1", description="Step 1", status=StepStatus.COMPLETED),
            Step(id="s2", description="Step 2", status=StepStatus.COMPLETED),
        ]
        plan = Plan(id="plan-1", goal="Test", steps=steps)

        current = plan.current_step()

        assert current is None

    def test_next_step_returns_first_pending_when_no_in_progress(self):
        """next_step should return first pending if none in progress."""
        steps = [
            Step(id="s1", description="Step 1"),
            Step(id="s2", description="Step 2"),
        ]
        plan = Plan(id="plan-1", goal="Test", steps=steps)

        next_s = plan.next_step()

        assert next_s is not None
        assert next_s.id == "s1"

    def test_next_step_returns_pending_after_in_progress(self):
        """next_step should return pending step after in-progress one."""
        steps = [
            Step(id="s1", description="Step 1", status=StepStatus.IN_PROGRESS),
            Step(id="s2", description="Step 2"),
            Step(id="s3", description="Step 3"),
        ]
        plan = Plan(id="plan-1", goal="Test", steps=steps)

        next_s = plan.next_step()

        assert next_s is not None
        assert next_s.id == "s2"

    def test_next_step_returns_none_when_none_pending(self):
        """next_step should return None when no pending steps."""
        steps = [
            Step(id="s1", description="Step 1", status=StepStatus.COMPLETED),
            Step(id="s2", description="Step 2", status=StepStatus.IN_PROGRESS),
        ]
        plan = Plan(id="plan-1", goal="Test", steps=steps)

        next_s = plan.next_step()

        assert next_s is None

    def test_all_completed_returns_true_when_all_done(self):
        """all_completed should return True when all steps are completed/skipped."""
        steps = [
            Step(id="s1", description="Step 1", status=StepStatus.COMPLETED),
            Step(id="s2", description="Step 2", status=StepStatus.SKIPPED),
            Step(id="s3", description="Step 3", status=StepStatus.COMPLETED),
        ]
        plan = Plan(id="plan-1", goal="Test", steps=steps)

        assert plan.all_completed() is True

    def test_all_completed_returns_false_when_pending(self):
        """all_completed should return False when steps are pending."""
        steps = [
            Step(id="s1", description="Step 1", status=StepStatus.COMPLETED),
            Step(id="s2", description="Step 2"),  # PENDING
        ]
        plan = Plan(id="plan-1", goal="Test", steps=steps)

        assert plan.all_completed() is False

    def test_all_completed_returns_true_for_empty_plan(self):
        """all_completed should return True for plan with no steps."""
        plan = Plan(id="plan-1", goal="Test", steps=[])

        assert plan.all_completed() is True

    def test_completed_steps_returns_only_completed(self):
        """completed_steps should return only steps with COMPLETED status."""
        steps = [
            Step(id="s1", description="Step 1", status=StepStatus.COMPLETED),
            Step(id="s2", description="Step 2", status=StepStatus.FAILED),
            Step(id="s3", description="Step 3", status=StepStatus.COMPLETED),
        ]
        plan = Plan(id="plan-1", goal="Test", steps=steps)

        completed = plan.completed_steps()

        assert len(completed) == 2
        assert completed[0].id == "s1"
        assert completed[1].id == "s3"

    def test_failed_steps_returns_only_failed(self):
        """failed_steps should return only steps with FAILED status."""
        steps = [
            Step(id="s1", description="Step 1", status=StepStatus.COMPLETED),
            Step(id="s2", description="Step 2", status=StepStatus.FAILED),
            Step(id="s3", description="Step 3", status=StepStatus.FAILED),
        ]
        plan = Plan(id="plan-1", goal="Test", steps=steps)

        failed = plan.failed_steps()

        assert len(failed) == 2
        assert failed[0].id == "s2"
        assert failed[1].id == "s3"

    def test_progress_summary_shows_current_step(self):
        """progress_summary should show current step number and description."""
        steps = [
            Step(id="s1", description="Find the bug", status=StepStatus.COMPLETED),
            Step(id="s2", description="Fix the bug"),
            Step(id="s3", description="Test the fix"),
        ]
        plan = Plan(id="plan-1", goal="Test", steps=steps)

        summary = plan.progress_summary()

        assert summary == "[Step 2/3] Fix the bug"

    def test_progress_summary_shows_complete(self):
        """progress_summary should show Complete when all done."""
        steps = [
            Step(id="s1", description="Step 1", status=StepStatus.COMPLETED),
            Step(id="s2", description="Step 2", status=StepStatus.COMPLETED),
        ]
        plan = Plan(id="plan-1", goal="Test", steps=steps)

        summary = plan.progress_summary()

        assert summary == "Complete (2/2 steps)"

    def test_progress_summary_shows_stopped_on_failure(self):
        """progress_summary should show Stopped when there are failed steps."""
        steps = [
            Step(id="s1", description="Step 1", status=StepStatus.COMPLETED),
            Step(id="s2", description="Step 2", status=StepStatus.FAILED),
            Step(id="s3", description="Step 3", status=StepStatus.SKIPPED),
        ]
        plan = Plan(id="plan-1", goal="Test", steps=steps)

        summary = plan.progress_summary()

        assert "Stopped" in summary
        assert "1/3 completed" in summary
        assert "1 failed" in summary

    def test_progress_summary_empty_plan(self):
        """progress_summary should handle empty plan."""
        plan = Plan(id="plan-1", goal="Test", steps=[])

        summary = plan.progress_summary()

        assert summary == "No steps"

    def test_can_revise_returns_true_below_cap(self):
        """can_revise should return True when revision_count < hard_revision_cap."""
        plan = Plan(id="plan-1", goal="Test", revision_count=3)
        policy = VerificationPolicy(hard_revision_cap=5)

        assert plan.can_revise(policy) is True

    def test_can_revise_returns_false_at_cap(self):
        """can_revise should return False when revision_count >= hard_revision_cap."""
        plan = Plan(id="plan-1", goal="Test", revision_count=5)
        policy = VerificationPolicy(hard_revision_cap=5)

        assert plan.can_revise(policy) is False

    def test_plan_approval_fields(self):
        """Plan can store approval info."""
        now = datetime.now(timezone.utc)
        plan = Plan(
            id="plan-1",
            goal="Test",
            approved_at=now,
            approval_mode="all",
        )

        assert plan.approved_at == now
        assert plan.approval_mode == "all"


# =============================================================================
# PlanExecutionState Tests
# =============================================================================


class TestPlanExecutionState:
    """Tests for PlanExecutionState model."""

    def test_execution_state_defaults(self):
        """PlanExecutionState should have sensible defaults."""
        plan = Plan(id="plan-1", goal="Test")
        state = PlanExecutionState(plan=plan)

        assert state.plan is plan
        assert state.current_step_index == 0
        assert state.checkpoint_hash is None
        assert state.step_checkpoints == {}
        assert state.started_at is None
        assert state.completed_at is None

    def test_advance_returns_first_pending_step(self):
        """advance should return the first pending step."""
        steps = [
            Step(id="s1", description="Step 1"),
            Step(id="s2", description="Step 2"),
        ]
        plan = Plan(id="plan-1", goal="Test", steps=steps)
        state = PlanExecutionState(plan=plan)

        step = state.advance()

        assert step is not None
        assert step.id == "s1"

    def test_advance_skips_completed_steps(self):
        """advance should skip completed steps."""
        steps = [
            Step(id="s1", description="Step 1", status=StepStatus.COMPLETED),
            Step(id="s2", description="Step 2"),
        ]
        plan = Plan(id="plan-1", goal="Test", steps=steps)
        state = PlanExecutionState(plan=plan)

        step = state.advance()

        assert step is not None
        assert step.id == "s2"
        assert state.current_step_index == 1

    def test_advance_returns_none_when_all_done(self):
        """advance should return None when no pending steps."""
        steps = [
            Step(id="s1", description="Step 1", status=StepStatus.COMPLETED),
            Step(id="s2", description="Step 2", status=StepStatus.COMPLETED),
        ]
        plan = Plan(id="plan-1", goal="Test", steps=steps)
        state = PlanExecutionState(plan=plan)

        step = state.advance()

        assert step is None

    def test_advance_returns_none_for_empty_plan(self):
        """advance should return None for empty plan."""
        plan = Plan(id="plan-1", goal="Test", steps=[])
        state = PlanExecutionState(plan=plan)

        step = state.advance()

        assert step is None

    def test_rollback_available_true_with_checkpoint(self):
        """rollback_available should return True when checkpoint exists."""
        plan = Plan(id="plan-1", goal="Test")
        state = PlanExecutionState(plan=plan, checkpoint_hash="abc123")

        assert state.rollback_available() is True

    def test_rollback_available_false_without_checkpoint(self):
        """rollback_available should return False when no checkpoint."""
        plan = Plan(id="plan-1", goal="Test")
        state = PlanExecutionState(plan=plan)

        assert state.rollback_available() is False

    def test_step_checkpoints_tracking(self):
        """step_checkpoints should track git hashes per step."""
        plan = Plan(id="plan-1", goal="Test")
        state = PlanExecutionState(plan=plan)

        state.step_checkpoints["s1"] = "hash1"
        state.step_checkpoints["s2"] = "hash2"

        assert state.step_checkpoints["s1"] == "hash1"
        assert state.step_checkpoints["s2"] == "hash2"
        assert len(state.step_checkpoints) == 2


# =============================================================================
# VerificationPolicy Tests
# =============================================================================


class TestVerificationPolicy:
    """Tests for VerificationPolicy behavior."""

    def test_default_policy(self):
        """Default policy fails on errors but not warnings."""
        policy = VerificationPolicy()

        assert policy.fail_on_lint_errors is True
        assert policy.fail_on_lint_warnings is False
        assert policy.fail_on_type_errors is True
        assert policy.fail_on_type_warnings is False
        assert policy.fail_on_test_failure is True
        assert policy.fail_on_test_skip is False
        assert policy.max_fix_attempts == 3
        assert policy.max_plan_revisions == 2
        assert policy.hard_revision_cap == 5

    def test_should_fail_on_lint_errors(self):
        """Policy should fail when lint errors exceed threshold."""
        policy = VerificationPolicy(fail_on_lint_errors=True)
        lint_result = LintResult(success=False, error_count=2, warning_count=1)

        should_fail, reason = policy.should_fail(lint_result=lint_result)

        assert should_fail is True
        assert "2 lint error" in reason

    def test_should_not_fail_on_lint_warnings_by_default(self):
        """Policy should not fail on warnings with default settings."""
        policy = VerificationPolicy()
        lint_result = LintResult(success=True, error_count=0, warning_count=5)

        should_fail, reason = policy.should_fail(lint_result=lint_result)

        assert should_fail is False
        assert reason == ""

    def test_should_fail_on_lint_warnings_when_configured(self):
        """Policy should fail on warnings when configured."""
        policy = VerificationPolicy(fail_on_lint_warnings=True)
        lint_result = LintResult(success=True, error_count=0, warning_count=3)

        should_fail, reason = policy.should_fail(lint_result=lint_result)

        assert should_fail is True
        assert "3 lint warning" in reason

    def test_should_fail_on_type_errors(self):
        """Policy should fail on type errors by default."""
        policy = VerificationPolicy()
        typecheck_result = TypecheckResult(success=False, error_count=1)

        should_fail, reason = policy.should_fail(typecheck_result=typecheck_result)

        assert should_fail is True
        assert "1 type error" in reason

    def test_should_fail_on_test_failures(self):
        """Policy should fail on test failures by default."""
        policy = VerificationPolicy()
        test_result = UnitTestResult(success=False, passed=5, failed=2, skipped=1)

        should_fail, reason = policy.should_fail(test_result=test_result)

        assert should_fail is True
        assert "2 test failure" in reason

    def test_should_not_fail_on_skipped_tests_by_default(self):
        """Policy should not fail on skipped tests with default settings."""
        policy = VerificationPolicy()
        test_result = UnitTestResult(success=True, passed=5, failed=0, skipped=2)

        should_fail, reason = policy.should_fail(test_result=test_result)

        assert should_fail is False

    def test_should_fail_on_skipped_tests_when_configured(self):
        """Policy should fail on skipped tests when configured."""
        policy = VerificationPolicy(fail_on_test_skip=True)
        test_result = UnitTestResult(success=True, passed=5, failed=0, skipped=2)

        should_fail, reason = policy.should_fail(test_result=test_result)

        assert should_fail is True
        assert "2 test(s) skipped" in reason

    def test_combines_multiple_failures(self):
        """Policy should combine multiple failure reasons."""
        policy = VerificationPolicy()
        lint_result = LintResult(success=False, error_count=1)
        typecheck_result = TypecheckResult(success=False, error_count=2)
        test_result = UnitTestResult(success=False, failed=3)

        should_fail, reason = policy.should_fail(
            lint_result=lint_result,
            typecheck_result=typecheck_result,
            test_result=test_result,
        )

        assert should_fail is True
        assert "1 lint error" in reason
        assert "2 type error" in reason
        assert "3 test failure" in reason

    def test_passes_when_all_succeed(self):
        """Policy should pass when all verifications succeed."""
        policy = VerificationPolicy()
        lint_result = LintResult(success=True, error_count=0, warning_count=0)
        typecheck_result = TypecheckResult(success=True, error_count=0)
        test_result = UnitTestResult(success=True, passed=10, failed=0, skipped=0)

        should_fail, reason = policy.should_fail(
            lint_result=lint_result,
            typecheck_result=typecheck_result,
            test_result=test_result,
        )

        assert should_fail is False
        assert reason == ""

    def test_should_fail_no_results(self):
        """Policy should pass when no results provided."""
        policy = VerificationPolicy()
        should_fail, reason = policy.should_fail()
        assert should_fail is False
        assert reason == ""


# =============================================================================
# ApprovalPolicy Tests
# =============================================================================


class TestApprovalPolicy:
    """Tests for ApprovalPolicy behavior."""

    def test_default_policy(self):
        """Default policy requires plan approval and auto-approves read-only."""
        policy = ApprovalPolicy()

        assert policy.require_plan_approval is True
        assert policy.auto_approve_read_only is True
        assert "rm" in policy.dangerous_commands
        assert "git push" in policy.dangerous_commands
        assert "DROP" in policy.dangerous_commands
        assert "DELETE" in policy.dangerous_commands

    def test_is_dangerous_detects_rm(self):
        """Policy should detect rm as dangerous."""
        policy = ApprovalPolicy()

        assert policy.is_dangerous("rm -rf /tmp/test") is True
        assert policy.is_dangerous("RM -RF /tmp/test") is True  # Case insensitive

    def test_is_dangerous_detects_git_push(self):
        """Policy should detect git push as dangerous."""
        policy = ApprovalPolicy()

        assert policy.is_dangerous("git push origin main") is True
        assert policy.is_dangerous("git push --force") is True

    def test_is_dangerous_detects_sql_drop(self):
        """Policy should detect SQL DROP as dangerous."""
        policy = ApprovalPolicy()

        assert policy.is_dangerous("DROP TABLE users") is True
        assert policy.is_dangerous("drop database test") is True

    def test_is_dangerous_detects_sql_delete(self):
        """Policy should detect SQL DELETE as dangerous."""
        policy = ApprovalPolicy()

        assert policy.is_dangerous("DELETE FROM users WHERE id=1") is True

    def test_is_dangerous_allows_safe_commands(self):
        """Policy should allow safe commands."""
        policy = ApprovalPolicy()

        assert policy.is_dangerous("ls -la") is False
        assert policy.is_dangerous("git status") is False
        assert policy.is_dangerous("python test.py") is False

    def test_custom_dangerous_commands(self):
        """Policy should respect custom dangerous commands."""
        policy = ApprovalPolicy(dangerous_commands=["shutdown", "reboot"])

        assert policy.is_dangerous("shutdown now") is True
        assert policy.is_dangerous("reboot") is True
        assert policy.is_dangerous("rm -rf /") is False  # Not in custom list

    def test_requires_approval_for_write_operations(self):
        """Policy should require approval for non-read-only operations."""
        policy = ApprovalPolicy()

        assert policy.requires_approval("write_file", is_read_only=False) is True
        assert policy.requires_approval("run_command", is_read_only=False) is True

    def test_auto_approves_read_only_when_configured(self):
        """Policy should auto-approve read-only when configured."""
        policy = ApprovalPolicy(auto_approve_read_only=True)

        assert policy.requires_approval("read_file", is_read_only=True) is False
        assert policy.requires_approval("search_code", is_read_only=True) is False

    def test_requires_approval_for_read_only_when_disabled(self):
        """Policy should require approval for read-only when auto-approve disabled."""
        policy = ApprovalPolicy(auto_approve_read_only=False)

        assert policy.requires_approval("read_file", is_read_only=True) is True

    def test_is_dangerous_empty_command(self):
        """Policy should handle empty commands."""
        policy = ApprovalPolicy()
        assert policy.is_dangerous("") is False

    def test_is_dangerous_whitespace_only(self):
        """Policy should handle whitespace-only commands."""
        policy = ApprovalPolicy()
        assert policy.is_dangerous("   ") is False

    def test_is_dangerous_false_positives(self):
        """Ensure common words aren't flagged."""
        policy = ApprovalPolicy()
        assert policy.is_dangerous("firmware update") is False
        assert policy.is_dangerous("dropdown menu") is False
        assert policy.is_dangerous("determine value") is False

    # Security tests for command injection/bypass prevention
    def test_is_dangerous_command_chaining_semicolon(self):
        """Command chaining with semicolon should be dangerous."""
        policy = ApprovalPolicy()
        assert policy.is_dangerous("echo foo; rm -rf /") is True
        assert policy.is_dangerous("ls; cat /etc/passwd") is True

    def test_is_dangerous_command_chaining_ampersand(self):
        """Command chaining with && should be dangerous."""
        policy = ApprovalPolicy()
        assert policy.is_dangerous("echo foo && rm -rf /") is True
        assert policy.is_dangerous("ls && cat /etc/passwd") is True

    def test_is_dangerous_command_chaining_pipe(self):
        """Command chaining with pipe should be dangerous."""
        policy = ApprovalPolicy()
        assert policy.is_dangerous("cat file | sh") is True
        assert policy.is_dangerous("echo 'rm -rf /' | bash") is True

    def test_is_dangerous_command_chaining_or(self):
        """Command chaining with || should be dangerous."""
        policy = ApprovalPolicy()
        assert policy.is_dangerous("false || rm -rf /") is True

    def test_is_dangerous_backtick_substitution(self):
        """Backtick command substitution should be dangerous."""
        policy = ApprovalPolicy()
        assert policy.is_dangerous("echo `whoami`") is True
        assert policy.is_dangerous("cat `ls`") is True

    def test_is_dangerous_dollar_substitution(self):
        """Dollar command substitution should be dangerous."""
        policy = ApprovalPolicy()
        assert policy.is_dangerous("echo $(whoami)") is True
        assert policy.is_dangerous("cat $(ls)") is True

    def test_is_dangerous_hex_escapes(self):
        """Hex escape sequences should be dangerous (bypass attempts)."""
        policy = ApprovalPolicy()
        # Trying to encode 'rm' as hex
        assert policy.is_dangerous(r"echo \x72\x6d") is True

    def test_is_dangerous_unicode_escapes(self):
        """Unicode escape sequences should be dangerous (bypass attempts)."""
        policy = ApprovalPolicy()
        assert policy.is_dangerous(r"echo \u0072\u006d") is True


# =============================================================================
# Exception Hierarchy Tests
# =============================================================================


class TestAgentLoopError:
    """Tests for base AgentLoopError."""

    def test_basic_error(self):
        """Error should store message and context."""
        error = AgentLoopError("Something went wrong", context={"key": "value"})

        assert error.message == "Something went wrong"
        assert error.context == {"key": "value"}
        assert str(error) == "Something went wrong (key='value')"

    def test_error_without_context(self):
        """Error should work without context."""
        error = AgentLoopError("Simple error")

        assert error.message == "Simple error"
        assert error.context == {}
        assert str(error) == "Simple error"

    def test_all_agent_errors_inherit(self):
        """All agent errors should inherit from AgentLoopError."""
        errors = [
            PlanCreationError("fail", user_input="test"),
            PlanRejectedError("plan-1"),
            VerificationError("fail"),
            MaxRetriesExceededError("step", 3, 3),
            StepExecutionError("fail", step_id="s1"),
        ]

        for error in errors:
            assert isinstance(error, AgentLoopError)


class TestPlanCreationError:
    """Tests for PlanCreationError."""

    def test_stores_user_input(self):
        """Error should store user input."""
        error = PlanCreationError(
            "Failed to parse plan",
            user_input="fix the bug",
            llm_response='{"invalid": "json"}',
        )

        assert error.user_input == "fix the bug"
        assert error.llm_response == '{"invalid": "json"}'
        assert "user_input" in error.context
        assert "llm_response" in error.context

    def test_truncates_long_llm_response(self):
        """Error should truncate long LLM responses."""
        long_response = "x" * 1000
        error = PlanCreationError(
            "Failed to parse",
            user_input="test",
            llm_response=long_response,
        )

        assert len(error.context["llm_response"]) == 500


class TestPlanRejectedError:
    """Tests for PlanRejectedError."""

    def test_stores_plan_id(self):
        """Error should store plan ID."""
        error = PlanRejectedError("plan-123")

        assert error.plan_id == "plan-123"
        assert error.reason is None
        assert "plan-123" in str(error)

    def test_stores_rejection_reason(self):
        """Error should store rejection reason."""
        error = PlanRejectedError("plan-123", reason="Too complex")

        assert error.reason == "Too complex"
        assert "Too complex" in str(error)


class TestVerificationError:
    """Tests for VerificationError."""

    def test_stores_step_info(self):
        """Error should store step and verification info."""
        error = VerificationError(
            "Lint failed",
            step_id="step-2",
            verification_type="lint",
            errors=["E501: line too long", "F401: unused import"],
        )

        assert error.step_id == "step-2"
        assert error.verification_type == "lint"
        assert len(error.errors) == 2
        assert error.context["error_count"] == 2

    def test_works_without_step_info(self):
        """Error should work for plan-level verification."""
        error = VerificationError("Tests failed", errors=["test_foo failed"])

        assert error.step_id is None
        assert error.verification_type is None


class TestMaxRetriesExceededError:
    """Tests for MaxRetriesExceededError."""

    def test_stores_retry_info(self):
        """Error should store retry counts."""
        error = MaxRetriesExceededError(
            retry_type="step_fix",
            attempts=3,
            max_attempts=3,
        )

        assert error.retry_type == "step_fix"
        assert error.attempts == 3
        assert error.max_attempts == 3
        assert error.last_error is None
        assert "step_fix" in str(error)
        assert "3/3" in str(error)

    def test_stores_last_error(self):
        """Error should store the final error."""
        last = ValueError("Final failure")
        error = MaxRetriesExceededError(
            retry_type="plan_revision",
            attempts=5,
            max_attempts=5,
            last_error=last,
        )

        assert error.last_error is last
        assert "Final failure" in str(error)


class TestStepExecutionError:
    """Tests for StepExecutionError."""

    def test_stores_step_info(self):
        """Error should store step and tool info."""
        error = StepExecutionError(
            "Tool failed",
            step_id="step-3",
            tool_name="write_file",
        )

        assert error.step_id == "step-3"
        assert error.tool_name == "write_file"
        assert error.original_error is None

    def test_stores_original_error(self):
        """Error should store and display original error."""
        original = OSError("Permission denied")
        error = StepExecutionError(
            "Write failed",
            step_id="step-4",
            tool_name="write_file",
            original_error=original,
        )

        assert error.original_error is original
        assert "OSError" in str(error)
        assert "Permission denied" in str(error)


# =============================================================================
# Result Model Tests
# =============================================================================


class TestVerificationResult:
    """Tests for VerificationResult model."""

    def test_success_result(self):
        """Successful verification should have success=True."""
        result = VerificationResult(
            success=True,
            message="All checks passed",
            files_checked=["foo.py", "bar.py"],
        )

        assert result.success is True
        assert result.errors == []
        assert result.warnings == []
        assert len(result.files_checked) == 2

    def test_failure_result(self):
        """Failed verification should contain errors."""
        result = VerificationResult(
            success=False,
            message="Verification failed",
            errors=["Error 1", "Error 2"],
            warnings=["Warning 1"],
        )

        assert result.success is False
        assert len(result.errors) == 2
        assert len(result.warnings) == 1


class TestUnitTestResultModel:
    """Tests for UnitTestResult model."""

    def test_all_passed(self):
        """Result should reflect all tests passing."""
        result = UnitTestResult(success=True, passed=10, failed=0, skipped=0)

        assert result.success is True
        assert result.passed == 10
        assert result.failed == 0

    def test_some_failed(self):
        """Result should reflect test failures."""
        result = UnitTestResult(
            success=False,
            passed=8,
            failed=2,
            skipped=1,
            errors=["test_foo: AssertionError", "test_bar: ValueError"],
        )

        assert result.success is False
        assert result.failed == 2
        assert len(result.errors) == 2


class TestLintResult:
    """Tests for LintResult model."""

    def test_clean_lint(self):
        """Result should reflect clean lint."""
        result = LintResult(
            success=True,
            error_count=0,
            warning_count=0,
            files_checked=["foo.py"],
        )

        assert result.success is True
        assert result.error_count == 0

    def test_lint_with_issues(self):
        """Result should contain lint issues."""
        result = LintResult(
            success=False,
            error_count=2,
            warning_count=3,
            errors=["E501", "F401"],
            warnings=["W503", "W504", "W505"],
        )

        assert result.success is False
        assert result.error_count == 2
        assert len(result.errors) == 2


class TestTypecheckResult:
    """Tests for TypecheckResult model."""

    def test_clean_typecheck(self):
        """Result should reflect clean type check."""
        result = TypecheckResult(
            success=True,
            error_count=0,
            files_checked=["foo.py"],
        )

        assert result.success is True

    def test_typecheck_with_errors(self):
        """Result should contain type errors."""
        result = TypecheckResult(
            success=False,
            error_count=1,
            errors=['foo.py:10: error: Incompatible return type'],
        )

        assert result.success is False
        assert result.error_count == 1
