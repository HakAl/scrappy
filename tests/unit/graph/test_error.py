"""
Unit tests for the Error node.

Tests error handling and recovery including:
- Error context formatting
- last_error clearing after processing
- Tier escalation on repeated errors
- Messages update with error context
- Edge cases (no error set, etc.)
"""

from typing import Literal, Optional

from scrappy.graph.state import AgentState, Message
from scrappy.graph.nodes.error import (
    error_node,
    format_error_context,
    should_escalate_tier,
    ERROR_ESCALATION_THRESHOLD,
)


# =============================================================================
# Test Helpers
# =============================================================================


def create_test_state(
    input_text: str = "Test task",
    working_dir: str = "/tmp/test",
    messages: Optional[list[Message]] = None,
    error_count: int = 0,
    last_error: Optional[str] = None,
    error_suggestion: Optional[str] = None,
    current_tier: Literal["fast", "chat", "instruct"] = "fast",
) -> AgentState:
    """Create a test AgentState."""
    return AgentState(
        input=input_text,
        original_task=input_text,
        working_dir=working_dir,
        messages=messages or [],
        error_count=error_count,
        last_error=last_error,
        error_suggestion=error_suggestion,
        current_tier=current_tier,
    )


# =============================================================================
# Format Error Context Tests
# =============================================================================


class TestFormatErrorContext:
    """Tests for error context formatting."""

    def test_includes_error_message(self):
        """Should include the error message in context."""
        error = "File not found: /tmp/missing.py"
        result = format_error_context(error, error_count=1)

        assert error in result
        assert "[Error Recovery]" in result

    def test_includes_recovery_guidance(self):
        """Should include guidance for recovery."""
        result = format_error_context("some error", error_count=1)

        assert "different approach" in result
        assert "prerequisite step" in result

    def test_repeated_errors_add_warning(self):
        """Should add warning for repeated errors."""
        result = format_error_context("error", error_count=3)

        assert "error #3" in result
        assert "different strategy" in result

    def test_first_error_no_repeated_warning(self):
        """First error should not have repeated error warning."""
        result = format_error_context("error", error_count=1)

        assert "error #" not in result

    def test_includes_error_suggestion(self):
        """Should include actionable suggestion when provided."""
        result = format_error_context(
            "No healthy models remain",
            error_count=1,
            error_suggestion="Run /setup or update API keys.",
        )

        assert "Provider Guidance" in result
        assert "Run /setup or update API keys." in result


# =============================================================================
# Should Escalate Tier Tests
# =============================================================================


class TestShouldEscalateTier:
    """Tests for tier escalation logic."""

    def test_escalate_after_threshold(self):
        """Should escalate after reaching error threshold."""
        result = should_escalate_tier(
            error_count=ERROR_ESCALATION_THRESHOLD,
            current_tier="fast",
        )
        assert result is True

    def test_no_escalate_below_threshold(self):
        """Should not escalate below threshold."""
        result = should_escalate_tier(
            error_count=ERROR_ESCALATION_THRESHOLD - 1,
            current_tier="fast",
        )
        assert result is False

    def test_no_escalate_if_already_instruct(self):
        """Should not escalate if already on instruct tier (top tier)."""
        result = should_escalate_tier(
            error_count=ERROR_ESCALATION_THRESHOLD + 5,
            current_tier="instruct",
        )
        assert result is False

    def test_escalate_chat_to_instruct(self):
        """Should escalate from chat to instruct after threshold."""
        result = should_escalate_tier(
            error_count=ERROR_ESCALATION_THRESHOLD,
            current_tier="chat",
        )
        assert result is True

    def test_escalate_above_threshold(self):
        """Should escalate above threshold."""
        result = should_escalate_tier(
            error_count=ERROR_ESCALATION_THRESHOLD + 1,
            current_tier="fast",
        )
        assert result is True


# =============================================================================
# Error Node Tests
# =============================================================================


class TestErrorNode:
    """Tests for the main error_node function."""

    def test_clears_last_error(self):
        """Should clear last_error after processing."""
        state = create_test_state(
            last_error="File not found",
            error_suggestion="Check the path.",
            error_count=1,
        )

        result = error_node(state)

        assert result.last_error is None
        assert result.error_suggestion is None

    def test_appends_error_context_to_messages(self):
        """Should append error context as system message."""
        state = create_test_state(
            last_error="Tool execution failed",
            error_suggestion="Use a different tool.",
            error_count=1,
            messages=[{"role": "user", "content": "hello"}],
        )

        result = error_node(state)

        assert len(result.messages) == 2
        assert result.messages[1]["role"] == "system"
        assert "Tool execution failed" in result.messages[1]["content"]
        assert "Use a different tool." in result.messages[1]["content"]
        assert "[Error Recovery]" in result.messages[1]["content"]

    def test_preserves_error_count(self):
        """Should not modify error_count."""
        state = create_test_state(
            last_error="some error",
            error_count=3,
        )

        result = error_node(state)

        assert result.error_count == 3

    def test_escalates_tier_on_repeated_errors(self):
        """Should escalate to chat tier after threshold (fast -> chat)."""
        state = create_test_state(
            last_error="error",
            error_count=ERROR_ESCALATION_THRESHOLD,
            current_tier="fast",
        )

        result = error_node(state)

        assert result.current_tier == "chat"

    def test_no_escalation_below_threshold(self):
        """Should not escalate below threshold."""
        state = create_test_state(
            last_error="error",
            error_count=1,
            current_tier="fast",
        )

        result = error_node(state)

        assert result.current_tier == "fast"

    def test_no_escalation_if_already_instruct(self):
        """Should not change tier if already on instruct (top tier)."""
        state = create_test_state(
            last_error="error",
            error_count=ERROR_ESCALATION_THRESHOLD,
            current_tier="instruct",
        )

        result = error_node(state)

        assert result.current_tier == "instruct"

    def test_handles_no_error_gracefully(self):
        """Should handle being called with no error set."""
        state = create_test_state(
            last_error=None,
            error_count=0,
        )

        result = error_node(state)

        # Should return state unchanged
        assert result.last_error is None
        assert result.messages == []

    def test_handles_empty_messages_list(self):
        """Should work with empty messages list."""
        state = create_test_state(
            last_error="error",
            error_count=1,
            messages=[],
        )

        result = error_node(state)

        assert len(result.messages) == 1
        assert result.messages[0]["role"] == "system"

    def test_preserves_existing_messages(self):
        """Should preserve existing messages."""
        existing_messages: list[Message] = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "second"},
        ]
        state = create_test_state(
            last_error="error",
            error_count=1,
            messages=existing_messages,
        )

        result = error_node(state)

        assert len(result.messages) == 3
        assert result.messages[0]["content"] == "first"
        assert result.messages[1]["content"] == "second"

    def test_long_error_is_included(self):
        """Should include long error messages fully."""
        long_error = "Error: " + "x" * 500
        state = create_test_state(
            last_error=long_error,
            error_count=1,
        )

        result = error_node(state)

        assert long_error in result.messages[0]["content"]

    def test_preserves_other_state_fields(self):
        """Should not modify unrelated state fields."""
        state = create_test_state(
            input_text="my task",
            working_dir="/my/dir",
            last_error="error",
            error_count=1,
        )

        result = error_node(state)

        assert result.input == "my task"
        assert result.original_task == "my task"
        assert result.working_dir == "/my/dir"
        assert result.done is False
        assert result.iteration == 0


# =============================================================================
# Integration with Routing Tests
# =============================================================================


class TestErrorNodeRouting:
    """Tests for error node integration with routing."""

    def test_clears_error_for_think_routing(self):
        """After error_node, should route to think (last_error=None)."""
        state = create_test_state(
            last_error="some error",
            error_count=1,
        )

        result = error_node(state)

        # When last_error is None, edges.py routes to think
        assert result.last_error is None

    def test_repeated_errors_info_in_context(self):
        """Repeated errors should provide that info to LLM."""
        state = create_test_state(
            last_error="same error again",
            error_count=3,
        )

        result = error_node(state)

        # LLM should see that this is a repeated failure
        assert "error #3" in result.messages[0]["content"]
