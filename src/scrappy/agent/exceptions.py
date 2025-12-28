"""
Agent loop exception hierarchy.

Provides context-rich exceptions for agent loop operations including
planning, verification, step execution, and retry management.
"""

from typing import Any, Optional


class AgentLoopError(Exception):
    """
    Base exception for all agent loop errors.

    All agent loop exceptions inherit from this, allowing callers
    to catch all agent errors with a single except clause.

    Attributes:
        message: Human-readable error message
        context: Additional context data about the error
    """

    def __init__(self, message: str, context: Optional[dict[str, Any]] = None):
        """
        Initialize the error.

        Args:
            message: Error description
            context: Additional context data
        """
        super().__init__(message)
        self.message = message
        self.context = context or {}

    def __str__(self) -> str:
        """Return string representation with context."""
        if self.context:
            context_str = ", ".join(f"{k}={v!r}" for k, v in self.context.items())
            return f"{self.message} ({context_str})"
        return self.message

    def __repr__(self) -> str:
        """Return detailed representation."""
        return f"{self.__class__.__name__}(message={self.message!r}, context={self.context!r})"


class PlanCreationError(AgentLoopError):
    """
    Raised when plan creation fails.

    This can happen when the LLM fails to generate a valid plan
    or when the plan structure is malformed.

    Attributes:
        user_input: The original user request
        llm_response: The raw LLM response, if available
    """

    def __init__(
        self,
        message: str,
        user_input: str,
        llm_response: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ):
        """
        Initialize plan creation error.

        Args:
            message: Error description
            user_input: The user's original request
            llm_response: Raw LLM response that failed to parse
            context: Additional context
        """
        ctx = context or {}
        ctx["user_input"] = user_input
        if llm_response:
            ctx["llm_response"] = llm_response[:500]  # Truncate for readability
        super().__init__(message, ctx)
        self.user_input = user_input
        self.llm_response = llm_response


class PlanRejectedError(AgentLoopError):
    """
    Raised when the user rejects a plan.

    This is a non-error termination - the user chose not to proceed.

    Attributes:
        plan_id: ID of the rejected plan
        reason: Optional reason provided by the user
    """

    def __init__(
        self,
        plan_id: str,
        reason: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ):
        """
        Initialize plan rejected error.

        Args:
            plan_id: ID of the rejected plan
            reason: Reason for rejection, if provided
            context: Additional context
        """
        ctx = context or {}
        ctx["plan_id"] = plan_id
        if reason:
            ctx["rejection_reason"] = reason
        message = f"Plan '{plan_id}' was rejected by user"
        if reason:
            message = f"{message}: {reason}"
        super().__init__(message, ctx)
        self.plan_id = plan_id
        self.reason = reason


class VerificationError(AgentLoopError):
    """
    Raised when verification fails.

    This includes lint errors, type errors, and test failures
    that exceed the configured policy thresholds.

    Attributes:
        step_id: ID of the step that failed verification
        verification_type: Type of verification that failed (lint, type, test)
        errors: List of specific error messages
    """

    def __init__(
        self,
        message: str,
        step_id: Optional[str] = None,
        verification_type: Optional[str] = None,
        errors: Optional[list[str]] = None,
        context: Optional[dict[str, Any]] = None,
    ):
        """
        Initialize verification error.

        Args:
            message: Error description
            step_id: ID of the step that failed
            verification_type: Type of verification (lint, type, test)
            errors: List of error messages
            context: Additional context
        """
        ctx = context or {}
        if step_id:
            ctx["step_id"] = step_id
        if verification_type:
            ctx["verification_type"] = verification_type
        if errors:
            ctx["error_count"] = len(errors)
        super().__init__(message, ctx)
        self.step_id = step_id
        self.verification_type = verification_type
        self.errors = errors or []


class MaxRetriesExceededError(AgentLoopError):
    """
    Raised when maximum retry attempts are exhausted.

    This applies to both step-level fix attempts and plan-level revisions.

    Attributes:
        retry_type: What was being retried (step_fix, plan_revision)
        attempts: Number of attempts made
        max_attempts: Maximum attempts allowed
        last_error: The final error that triggered this
    """

    def __init__(
        self,
        retry_type: str,
        attempts: int,
        max_attempts: int,
        last_error: Optional[Exception] = None,
        context: Optional[dict[str, Any]] = None,
    ):
        """
        Initialize max retries error.

        Args:
            retry_type: What was being retried
            attempts: Number of attempts made
            max_attempts: Maximum allowed
            last_error: Final error encountered
            context: Additional context
        """
        ctx = context or {}
        ctx["retry_type"] = retry_type
        ctx["attempts"] = attempts
        ctx["max_attempts"] = max_attempts
        message = f"Maximum {retry_type} attempts exceeded ({attempts}/{max_attempts})"
        if last_error:
            ctx["last_error"] = str(last_error)
            message = f"{message}: {last_error}"
        super().__init__(message, ctx)
        self.retry_type = retry_type
        self.attempts = attempts
        self.max_attempts = max_attempts
        self.last_error = last_error


class PlanRevisionLimitError(AgentLoopError):
    """
    Raised when plan revision hits the soft limit.

    This is raised to give the user a chance to intervene before
    hitting the hard cap. The user can choose to continue or stop.

    Attributes:
        plan_id: ID of the plan that hit the limit
        revision_count: Current number of revisions
        soft_limit: The soft limit that was reached
        feedback: The feedback that triggered the revision attempt
    """

    def __init__(
        self,
        plan_id: str,
        revision_count: int,
        soft_limit: int,
        feedback: str,
        context: Optional[dict[str, Any]] = None,
    ):
        """
        Initialize plan revision limit error.

        Args:
            plan_id: ID of the plan
            revision_count: Current revision count
            soft_limit: The soft limit value
            feedback: Feedback that would trigger revision
            context: Additional context
        """
        ctx = context or {}
        ctx["plan_id"] = plan_id
        ctx["revision_count"] = revision_count
        ctx["soft_limit"] = soft_limit
        message = (
            f"Plan '{plan_id}' has been revised {revision_count} times "
            f"(soft limit: {soft_limit}). User intervention required."
        )
        super().__init__(message, ctx)
        self.plan_id = plan_id
        self.revision_count = revision_count
        self.soft_limit = soft_limit
        self.feedback = feedback


class StepExecutionError(AgentLoopError):
    """
    Raised when a step fails to execute.

    This includes tool execution failures and unexpected errors
    during step processing.

    Attributes:
        step_id: ID of the step that failed
        tool_name: Name of the tool that was being executed
        original_error: The underlying exception, if any
    """

    def __init__(
        self,
        message: str,
        step_id: str,
        tool_name: Optional[str] = None,
        original_error: Optional[Exception] = None,
        context: Optional[dict[str, Any]] = None,
    ):
        """
        Initialize step execution error.

        Args:
            message: Error description
            step_id: ID of the step that failed
            tool_name: Tool that was being executed
            original_error: Original exception
            context: Additional context
        """
        ctx = context or {}
        ctx["step_id"] = step_id
        if tool_name:
            ctx["tool_name"] = tool_name
        if original_error:
            ctx["original_error_type"] = type(original_error).__name__
        super().__init__(message, ctx)
        self.step_id = step_id
        self.tool_name = tool_name
        self.original_error = original_error

    def __str__(self) -> str:
        """Include original error in string representation."""
        base = super().__str__()
        if self.original_error:
            return f"{base}\nCaused by: {type(self.original_error).__name__}: {self.original_error}"
        return base
