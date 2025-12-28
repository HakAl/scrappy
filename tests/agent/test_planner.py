"""
Tests for the Planner component.

Tests plan generation, revision, and policy enforcement with mocked LLM.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from scrappy.agent.planner import (
    Planner,
    PlanResponse,
    StepResponse,
    READ_ONLY_TOOLS,
)
from scrappy.agent.models import (
    Plan,
    Step,
    StepStatus,
    ApprovalPolicy,
    VerificationPolicy,
)
from scrappy.agent.exceptions import (
    PlanCreationError,
    PlanRevisionLimitError,
    MaxRetriesExceededError,
    RevisionThrottleError,
)


# =============================================================================
# Test Fixtures
# =============================================================================


class MockLLMClient:
    """Mock LLM client for testing."""

    def __init__(self, response: Any = None, error: Exception | None = None):
        """
        Initialize mock client.

        Args:
            response: Response to return from completion_structured
            error: Exception to raise instead of returning response
        """
        self._response = response
        self._error = error
        self.calls: list[dict] = []

    async def completion_structured(
        self,
        model: str,
        messages: list[dict[str, str]],
        response_model: type,
        **kwargs: Any,
    ) -> Any:
        """Record call and return configured response."""
        self.calls.append({
            "model": model,
            "messages": messages,
            "response_model": response_model,
            "kwargs": kwargs,
        })
        if self._error:
            raise self._error
        return self._response


@pytest.fixture
def simple_plan_response() -> PlanResponse:
    """Create a simple plan response."""
    return PlanResponse(
        goal="Fix the bug in authentication",
        steps=[
            StepResponse(
                description="Read the auth module",
                tool_name="read_file",
                tool_args={"path": "src/auth.py"},
            ),
            StepResponse(
                description="Fix the validation logic",
                tool_name="edit_file",
                tool_args={
                    "path": "src/auth.py",
                    "old_content": "if user.valid",
                    "new_content": "if user.is_valid()",
                },
            ),
            StepResponse(
                description="Run the tests",
                tool_name="run_tests",
                tool_args={"paths": ["tests/test_auth.py"]},
            ),
        ],
        reasoning="First read the file to understand, then fix, then verify.",
    )


@pytest.fixture
def dangerous_command_response() -> PlanResponse:
    """Create a plan with dangerous commands."""
    return PlanResponse(
        goal="Clean up old files",
        steps=[
            StepResponse(
                description="List old files",
                tool_name="run_command",
                tool_args={"command": "find . -name '*.bak' -mtime +30"},
            ),
            StepResponse(
                description="Remove old backup files",
                tool_name="run_command",
                tool_args={"command": "rm -rf *.bak"},
            ),
            StepResponse(
                description="Push changes",
                tool_name="run_command",
                tool_args={"command": "git push origin main"},
            ),
        ],
        reasoning="Find and remove old files, then sync.",
    )


@pytest.fixture
def read_only_response() -> PlanResponse:
    """Create a plan with only read-only steps."""
    return PlanResponse(
        goal="Understand the codebase",
        steps=[
            StepResponse(
                description="Search for usages",
                tool_name="search_code",
                tool_args={"pattern": "def authenticate"},
            ),
            StepResponse(
                description="Read the main module",
                tool_name="read_file",
                tool_args={"path": "src/main.py"},
            ),
            StepResponse(
                description="Think about the approach",
                tool_name="think",
                tool_args={"thought": "The authentication uses JWT tokens."},
            ),
        ],
        reasoning="Explore the code first.",
    )


# =============================================================================
# Plan Creation Tests
# =============================================================================


class TestPlannerCreatePlan:
    """Tests for Planner.create_plan method."""

    @pytest.mark.asyncio
    async def test_creates_plan_from_user_input(self, simple_plan_response: PlanResponse):
        """Planner should create a Plan from user input."""
        client = MockLLMClient(response=simple_plan_response)
        planner = Planner(client=client)

        plan = await planner.create_plan("Fix the authentication bug")

        assert plan is not None
        assert isinstance(plan, Plan)
        assert plan.goal == "Fix the bug in authentication"
        assert len(plan.steps) == 3
        assert plan.revision_count == 0

    @pytest.mark.asyncio
    async def test_steps_have_correct_structure(self, simple_plan_response: PlanResponse):
        """Plan steps should have correct structure."""
        client = MockLLMClient(response=simple_plan_response)
        planner = Planner(client=client)

        plan = await planner.create_plan("Fix the bug")

        step = plan.steps[0]
        assert step.id == "step-1"
        assert step.description == "Read the auth module"
        assert step.tool == "read_file"
        assert step.parameters == {"path": "src/auth.py"}
        assert step.status == StepStatus.PENDING

    @pytest.mark.asyncio
    async def test_includes_context_in_prompt(self, simple_plan_response: PlanResponse):
        """Planner should include context in the user prompt."""
        client = MockLLMClient(response=simple_plan_response)
        planner = Planner(client=client)

        await planner.create_plan(
            "Fix the bug",
            context="Error log: AuthenticationError at line 42"
        )

        # Check that context was included in the message
        assert len(client.calls) == 1
        user_message = client.calls[0]["messages"][1]["content"]
        assert "Error log: AuthenticationError at line 42" in user_message
        # Context is now wrapped in <context> tags for security
        assert "<context>" in user_message

    @pytest.mark.asyncio
    async def test_uses_configured_model(self, simple_plan_response: PlanResponse):
        """Planner should use the configured model."""
        client = MockLLMClient(response=simple_plan_response)
        planner = Planner(client=client, model="quality")

        await planner.create_plan("Fix the bug")

        assert client.calls[0]["model"] == "quality"

    @pytest.mark.asyncio
    async def test_raises_plan_creation_error_on_failure(self):
        """Planner should raise PlanCreationError on LLM failure."""
        client = MockLLMClient(error=ValueError("LLM error"))
        planner = Planner(client=client)

        with pytest.raises(PlanCreationError) as exc_info:
            await planner.create_plan("Fix the bug")

        assert "Failed to create plan" in str(exc_info.value)
        assert exc_info.value.user_input == "Fix the bug"

    @pytest.mark.asyncio
    async def test_plan_has_unique_id(self, simple_plan_response: PlanResponse):
        """Each plan should have a unique ID."""
        client = MockLLMClient(response=simple_plan_response)
        planner = Planner(client=client)

        plan1 = await planner.create_plan("Task 1")
        plan2 = await planner.create_plan("Task 2")

        assert plan1.id != plan2.id
        assert plan1.id.startswith("plan-")
        assert plan2.id.startswith("plan-")


# =============================================================================
# Post-Processing Tests
# =============================================================================


class TestPlannerPostProcessing:
    """Tests for plan post-processing logic."""

    @pytest.mark.asyncio
    async def test_marks_read_only_steps(self, read_only_response: PlanResponse):
        """Planner should mark read-only steps correctly."""
        client = MockLLMClient(response=read_only_response)
        planner = Planner(client=client)

        plan = await planner.create_plan("Understand the code")

        # All steps in read_only_response use read-only tools
        for step in plan.steps:
            assert step.is_read_only is True
            assert step.verification_required is False

    @pytest.mark.asyncio
    async def test_detects_dangerous_commands(self, dangerous_command_response: PlanResponse):
        """Planner should detect dangerous commands."""
        client = MockLLMClient(response=dangerous_command_response)
        planner = Planner(client=client)

        plan = await planner.create_plan("Clean up files")

        # Step with rm -rf should be marked as requiring verification
        rm_step = plan.steps[1]
        assert rm_step.is_read_only is False
        assert rm_step.verification_required is True

        # Step with git push should also be marked
        push_step = plan.steps[2]
        assert push_step.is_read_only is False
        assert push_step.verification_required is True

    @pytest.mark.asyncio
    async def test_uses_custom_approval_policy(self):
        """Planner should use custom approval policy."""
        response = PlanResponse(
            goal="Deploy",
            steps=[
                StepResponse(
                    description="Deploy to production",
                    tool_name="run_command",
                    tool_args={"command": "deploy --production"},
                ),
            ],
            reasoning="Deploy.",
        )
        # Custom policy with "deploy" as dangerous
        custom_policy = ApprovalPolicy(dangerous_commands=["deploy"])
        client = MockLLMClient(response=response)
        planner = Planner(client=client, policy=custom_policy)

        plan = await planner.create_plan("Deploy")

        step = plan.steps[0]
        assert step.verification_required is True

    @pytest.mark.asyncio
    async def test_read_only_tools_constant(self):
        """READ_ONLY_TOOLS should contain expected tools."""
        assert "read_file" in READ_ONLY_TOOLS
        assert "search_code" in READ_ONLY_TOOLS
        assert "think" in READ_ONLY_TOOLS
        assert "write_file" not in READ_ONLY_TOOLS
        assert "run_command" not in READ_ONLY_TOOLS


# =============================================================================
# Plan Revision Tests
# =============================================================================


class TestPlannerRevisePlan:
    """Tests for Planner.revise_plan method."""

    @pytest.mark.asyncio
    async def test_revises_plan_with_feedback(self, simple_plan_response: PlanResponse):
        """Planner should revise plan based on feedback."""
        # First create a plan
        client = MockLLMClient(response=simple_plan_response)
        planner = Planner(client=client)
        original_plan = await planner.create_plan("Fix the bug")

        # Now revise it
        revised_response = PlanResponse(
            goal="Fix the bug (revised)",
            steps=[
                StepResponse(
                    description="Read the auth module with more context",
                    tool_name="read_file",
                    tool_args={"path": "src/auth.py"},
                ),
            ],
            reasoning="Revised approach.",
        )
        client._response = revised_response

        revised_plan = await planner.revise_plan(
            original_plan,
            feedback="The edit step failed because the old_content was not found."
        )

        assert revised_plan.revision_count == 1
        assert revised_plan.id == original_plan.id  # Same plan ID
        assert len(revised_plan.steps) == 1

    @pytest.mark.asyncio
    async def test_revision_includes_original_plan_in_prompt(
        self, simple_plan_response: PlanResponse
    ):
        """Revision prompt should include original plan details."""
        client = MockLLMClient(response=simple_plan_response)
        planner = Planner(client=client)

        # Create a plan with some completed steps
        original_plan = Plan(
            id="plan-test",
            goal="Fix the bug",
            steps=[
                Step(
                    id="step-1",
                    description="Read file",
                    tool="read_file",
                    status=StepStatus.COMPLETED,
                ),
                Step(
                    id="step-2",
                    description="Edit file",
                    tool="edit_file",
                    status=StepStatus.FAILED,
                    error_message="Content not found",
                ),
            ],
            revision_count=0,
        )

        await planner.revise_plan(original_plan, feedback="Step 2 failed")

        # Check that the prompt includes plan info
        user_message = client.calls[0]["messages"][1]["content"]
        assert "Step 2 failed" in user_message
        assert "Fix the bug" in user_message

    @pytest.mark.asyncio
    async def test_raises_revision_limit_error_at_soft_limit(self):
        """Planner should raise PlanRevisionLimitError at soft limit."""
        policy = VerificationPolicy(max_plan_revisions=2, hard_revision_cap=5)
        client = MockLLMClient(response=None)
        planner = Planner(client=client, verification_policy=policy)

        plan = Plan(
            id="plan-test",
            goal="Fix bug",
            steps=[],
            revision_count=2,  # At soft limit
        )

        with pytest.raises(PlanRevisionLimitError) as exc_info:
            await planner.revise_plan(plan, feedback="Try again")

        error = exc_info.value
        assert error.plan_id == "plan-test"
        assert error.revision_count == 2
        assert error.soft_limit == 2
        assert error.feedback == "Try again"

    @pytest.mark.asyncio
    async def test_raises_max_retries_error_at_hard_cap(self):
        """Planner should raise MaxRetriesExceededError at hard cap."""
        policy = VerificationPolicy(max_plan_revisions=2, hard_revision_cap=5)
        client = MockLLMClient(response=None)
        planner = Planner(client=client, verification_policy=policy)

        plan = Plan(
            id="plan-test",
            goal="Fix bug",
            steps=[],
            revision_count=5,  # At hard cap
        )

        with pytest.raises(MaxRetriesExceededError) as exc_info:
            await planner.revise_plan(plan, feedback="Try again")

        error = exc_info.value
        assert error.retry_type == "plan_revision"
        assert error.attempts == 5
        assert error.max_attempts == 5

    @pytest.mark.asyncio
    async def test_revision_increments_count(self, simple_plan_response: PlanResponse):
        """Each revision should increment revision_count."""
        client = MockLLMClient(response=simple_plan_response)
        planner = Planner(client=client)

        plan = Plan(
            id="plan-test",
            goal="Fix bug",
            steps=[],
            revision_count=1,
        )

        revised = await planner.revise_plan(plan, feedback="Needs work")

        assert revised.revision_count == 2

    @pytest.mark.asyncio
    async def test_revision_preserves_context(self, simple_plan_response: PlanResponse):
        """Revision should preserve original context."""
        client = MockLLMClient(response=simple_plan_response)
        planner = Planner(client=client)

        plan = Plan(
            id="plan-test",
            goal="Fix bug",
            steps=[],
            context="Original error context",
            revision_count=0,
        )

        revised = await planner.revise_plan(plan, feedback="Retry")

        assert revised.context == "Original error context"


# =============================================================================
# Revision Flow Tests
# =============================================================================


class TestRevisionFlow:
    """Tests for the complete revision flow."""

    @pytest.mark.asyncio
    async def test_revision_flow_auto_revisions(self, simple_plan_response: PlanResponse):
        """Plan should allow auto-revisions up to soft limit."""
        # Disable throttle to test revision count limits
        policy = VerificationPolicy(
            max_plan_revisions=2,
            hard_revision_cap=5,
            min_revision_interval_seconds=0.0,
        )
        client = MockLLMClient(response=simple_plan_response)
        planner = Planner(client=client, verification_policy=policy)

        # Start with revision_count 0
        plan = Plan(id="plan-test", goal="Fix", steps=[], revision_count=0)

        # First revision (0 -> 1) should succeed
        plan = await planner.revise_plan(plan, "Failure 1")
        assert plan.revision_count == 1

        # Second revision (1 -> 2) should succeed
        plan = await planner.revise_plan(plan, "Failure 2")
        assert plan.revision_count == 2

        # Third revision should hit soft limit
        with pytest.raises(PlanRevisionLimitError):
            await planner.revise_plan(plan, "Failure 3")

    @pytest.mark.asyncio
    async def test_revision_flow_hard_cap(self, simple_plan_response: PlanResponse):
        """Hard cap should block revisions completely."""
        policy = VerificationPolicy(max_plan_revisions=2, hard_revision_cap=5)
        client = MockLLMClient(response=simple_plan_response)
        planner = Planner(client=client, verification_policy=policy)

        # Simulate plan that has already hit hard cap
        plan = Plan(id="plan-test", goal="Fix", steps=[], revision_count=5)

        # Revision should be blocked by hard cap (checked before soft limit)
        with pytest.raises(MaxRetriesExceededError) as exc_info:
            await planner.revise_plan(plan, "Final failure")

        assert exc_info.value.retry_type == "plan_revision"
        assert exc_info.value.attempts == 5
        assert exc_info.value.max_attempts == 5

    @pytest.mark.asyncio
    async def test_soft_limit_triggers_before_hard_cap(
        self, simple_plan_response: PlanResponse
    ):
        """Soft limit should trigger for counts between soft and hard limits."""
        policy = VerificationPolicy(max_plan_revisions=2, hard_revision_cap=5)
        client = MockLLMClient(response=simple_plan_response)
        planner = Planner(client=client, verification_policy=policy)

        # revision_count = 3 is past soft limit (2) but before hard cap (5)
        plan = Plan(id="plan-test", goal="Fix", steps=[], revision_count=3)

        # Should raise PlanRevisionLimitError (soft limit), not MaxRetriesExceededError
        with pytest.raises(PlanRevisionLimitError):
            await planner.revise_plan(plan, "Failure")


# =============================================================================
# Policy Access Tests
# =============================================================================


class TestPlannerProperties:
    """Tests for Planner properties."""

    def test_policy_property(self):
        """Planner should expose policy property."""
        custom_policy = ApprovalPolicy(dangerous_commands=["custom"])
        client = MockLLMClient()
        planner = Planner(client=client, policy=custom_policy)

        assert planner.policy is custom_policy
        assert "custom" in planner.policy.dangerous_commands

    def test_verification_policy_property(self):
        """Planner should expose verification_policy property."""
        custom_policy = VerificationPolicy(max_plan_revisions=10)
        client = MockLLMClient()
        planner = Planner(client=client, verification_policy=custom_policy)

        assert planner.verification_policy is custom_policy
        assert planner.verification_policy.max_plan_revisions == 10

    def test_default_policies(self):
        """Planner should use default policies when not specified."""
        client = MockLLMClient()
        planner = Planner(client=client)

        assert planner.policy is not None
        assert planner.verification_policy is not None
        assert planner.policy.require_plan_approval is True
        assert planner.verification_policy.max_plan_revisions == 2


# =============================================================================
# Exception Tests
# =============================================================================


class TestPlanRevisionLimitError:
    """Tests for PlanRevisionLimitError."""

    def test_error_attributes(self):
        """Error should store all attributes."""
        error = PlanRevisionLimitError(
            plan_id="plan-123",
            revision_count=3,
            soft_limit=2,
            feedback="Step failed",
        )

        assert error.plan_id == "plan-123"
        assert error.revision_count == 3
        assert error.soft_limit == 2
        assert error.feedback == "Step failed"

    def test_error_message(self):
        """Error should have informative message with cost warning."""
        error = PlanRevisionLimitError(
            plan_id="plan-123",
            revision_count=3,
            soft_limit=2,
            feedback="Step failed",
        )

        message = str(error)
        assert "plan-123" in message
        assert "3" in message
        assert "2" in message
        # Message should warn about costs
        assert "cost" in message.lower()
        assert "credit" in message.lower()

    def test_error_context(self):
        """Error should include context dict."""
        error = PlanRevisionLimitError(
            plan_id="plan-123",
            revision_count=3,
            soft_limit=2,
            feedback="Step failed",
        )

        assert error.context["plan_id"] == "plan-123"
        assert error.context["revision_count"] == 3
        assert error.context["soft_limit"] == 2


# =============================================================================
# Edge Cases
# =============================================================================


class TestPlannerEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_empty_steps_response(self):
        """Planner should handle response with no steps."""
        response = PlanResponse(
            goal="Nothing to do",
            steps=[],
            reasoning="No action needed.",
        )
        client = MockLLMClient(response=response)
        planner = Planner(client=client)

        plan = await planner.create_plan("Check if anything is needed")

        assert len(plan.steps) == 0
        assert plan.goal == "Nothing to do"

    @pytest.mark.asyncio
    async def test_step_without_tool_args(self):
        """Planner should handle steps with empty tool_args."""
        response = PlanResponse(
            goal="Think about it",
            steps=[
                StepResponse(
                    description="Just think",
                    tool_name="think",
                    tool_args={},
                ),
            ],
            reasoning="Thinking step.",
        )
        client = MockLLMClient(response=response)
        planner = Planner(client=client)

        plan = await planner.create_plan("Think")

        step = plan.steps[0]
        assert step.parameters == {}
        assert step.is_read_only is True

    @pytest.mark.asyncio
    async def test_non_string_command_in_run_command(self):
        """Planner should handle non-string command gracefully."""
        response = PlanResponse(
            goal="Run something",
            steps=[
                StepResponse(
                    description="Run a command",
                    tool_name="run_command",
                    tool_args={"command": None},  # Invalid, but shouldn't crash
                ),
            ],
            reasoning="Run it.",
        )
        client = MockLLMClient(response=response)
        planner = Planner(client=client)

        plan = await planner.create_plan("Run")

        # Should not crash, step should be created
        assert len(plan.steps) == 1

    @pytest.mark.asyncio
    async def test_preserves_plan_creation_error(self):
        """PlanCreationError should be re-raised without wrapping."""
        original_error = PlanCreationError(
            message="Original error",
            user_input="test",
        )
        client = MockLLMClient(error=original_error)
        planner = Planner(client=client)

        with pytest.raises(PlanCreationError) as exc_info:
            await planner.create_plan("test")

        # Should be the same error, not wrapped
        assert exc_info.value is original_error


# =============================================================================
# Time-Based Throttling Tests
# =============================================================================


class TestRevisionThrottling:
    """Tests for time-based revision rate limiting."""

    @pytest.mark.asyncio
    async def test_first_revision_not_throttled(self, simple_plan_response: PlanResponse):
        """First revision should not be throttled (no previous revision time)."""
        policy = VerificationPolicy(min_revision_interval_seconds=5.0)
        client = MockLLMClient(response=simple_plan_response)
        planner = Planner(client=client, verification_policy=policy)

        plan = Plan(id="plan-test", goal="Fix bug", steps=[], revision_count=0)

        # Should succeed - no previous revision time set
        revised = await planner.revise_plan(plan, feedback="Try again")
        assert revised.revision_count == 1

    @pytest.mark.asyncio
    async def test_rapid_revision_is_throttled(self, simple_plan_response: PlanResponse):
        """Rapid successive revisions should be throttled."""
        policy = VerificationPolicy(min_revision_interval_seconds=5.0)
        client = MockLLMClient(response=simple_plan_response)
        planner = Planner(client=client, verification_policy=policy)

        plan = Plan(id="plan-test", goal="Fix bug", steps=[], revision_count=0)

        # First revision succeeds
        revised = await planner.revise_plan(plan, feedback="First attempt")

        # Immediate second revision should be throttled
        with pytest.raises(RevisionThrottleError) as exc_info:
            await planner.revise_plan(revised, feedback="Second attempt")

        error = exc_info.value
        assert error.plan_id == "plan-test"
        assert error.min_interval == 5.0
        assert error.seconds_remaining > 0

    @pytest.mark.asyncio
    async def test_throttle_respects_zero_interval(self, simple_plan_response: PlanResponse):
        """Zero interval should disable throttling."""
        policy = VerificationPolicy(min_revision_interval_seconds=0.0)
        client = MockLLMClient(response=simple_plan_response)
        planner = Planner(client=client, verification_policy=policy)

        plan = Plan(id="plan-test", goal="Fix bug", steps=[], revision_count=0)

        # Both revisions should succeed immediately
        revised = await planner.revise_plan(plan, feedback="First")
        revised2 = await planner.revise_plan(revised, feedback="Second")
        assert revised2.revision_count == 2

    @pytest.mark.asyncio
    async def test_throttle_allows_after_interval(self, simple_plan_response: PlanResponse):
        """Revision should be allowed after interval passes."""
        policy = VerificationPolicy(min_revision_interval_seconds=0.1)  # Short interval for test
        client = MockLLMClient(response=simple_plan_response)
        planner = Planner(client=client, verification_policy=policy)

        plan = Plan(id="plan-test", goal="Fix bug", steps=[], revision_count=0)

        # First revision
        revised = await planner.revise_plan(plan, feedback="First")

        # Simulate time passing by manipulating _last_revision_time
        planner._last_revision_time = datetime.now(timezone.utc) - timedelta(seconds=1)

        # Second revision should now succeed
        revised2 = await planner.revise_plan(revised, feedback="Second")
        assert revised2.revision_count == 2

    @pytest.mark.asyncio
    async def test_throttle_error_attributes(self, simple_plan_response: PlanResponse):
        """RevisionThrottleError should have correct attributes."""
        policy = VerificationPolicy(min_revision_interval_seconds=10.0)
        client = MockLLMClient(response=simple_plan_response)
        planner = Planner(client=client, verification_policy=policy)

        plan = Plan(id="plan-test", goal="Fix bug", steps=[], revision_count=0)

        await planner.revise_plan(plan, feedback="First")

        with pytest.raises(RevisionThrottleError) as exc_info:
            await planner.revise_plan(plan, feedback="Second")

        error = exc_info.value
        assert error.plan_id == "plan-test"
        assert error.min_interval == 10.0
        assert 0 < error.seconds_remaining <= 10.0
        assert "throttled" in str(error).lower()
        assert error.context["plan_id"] == "plan-test"

    @pytest.mark.asyncio
    async def test_throttle_checked_before_limits(self, simple_plan_response: PlanResponse):
        """Throttle should be checked before soft/hard limits."""
        # If throttle is checked first, we get throttle error even at limit
        policy = VerificationPolicy(
            min_revision_interval_seconds=5.0,
            max_plan_revisions=1,  # At limit after first revision
        )
        client = MockLLMClient(response=simple_plan_response)
        planner = Planner(client=client, verification_policy=policy)

        plan = Plan(id="plan-test", goal="Fix bug", steps=[], revision_count=0)

        # First revision succeeds (reaches soft limit)
        revised = await planner.revise_plan(plan, feedback="First")
        assert revised.revision_count == 1

        # Immediate second revision hits throttle (checked first)
        with pytest.raises(RevisionThrottleError):
            await planner.revise_plan(revised, feedback="Second")


class TestRevisionThrottleError:
    """Tests for RevisionThrottleError exception."""

    def test_error_message_format(self):
        """Error message should include key information."""
        error = RevisionThrottleError(
            plan_id="plan-abc",
            seconds_remaining=3.5,
            min_interval=5.0,
        )

        message = str(error)
        assert "plan-abc" in message
        assert "3.5" in message
        assert "5" in message
        assert "wait" in message.lower()

    def test_error_context(self):
        """Error should include context dict."""
        error = RevisionThrottleError(
            plan_id="plan-xyz",
            seconds_remaining=2.0,
            min_interval=10.0,
        )

        assert error.context["plan_id"] == "plan-xyz"
        assert error.context["seconds_remaining"] == 2.0
        assert error.context["min_interval"] == 10.0


# =============================================================================
# Updated Soft Limit Message Tests
# =============================================================================


class TestCostWarningMessage:
    """Tests for cost warning in soft limit message."""

    def test_soft_limit_message_warns_about_costs(self):
        """PlanRevisionLimitError message should warn about API costs."""
        error = PlanRevisionLimitError(
            plan_id="plan-123",
            revision_count=2,
            soft_limit=2,
            feedback="Step failed",
        )

        message = str(error)
        assert "cost" in message.lower()
        assert "credit" in message.lower()
