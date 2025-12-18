"""Tests for unified agent stop condition."""

import pytest
from unittest.mock import Mock

from scrappy.agent.stop_condition import AgentStopCondition, StopReason


class TestStopConditionUserCancellation:
    """Test user cancellation via CancellationToken."""

    def test_should_stop_when_token_cancelled(self):
        """Stop condition returns USER_CANCELLED when token is cancelled."""
        token = Mock()
        token.is_cancelled.return_value = True

        condition = AgentStopCondition(cancellation_token=token)

        should_stop, reason = condition.should_stop()

        assert should_stop is True
        assert reason == StopReason.USER_CANCELLED

    def test_should_not_stop_when_token_not_cancelled(self):
        """Stop condition continues when token is not cancelled."""
        token = Mock()
        token.is_cancelled.return_value = False
        token.is_force_cancelled.return_value = False

        condition = AgentStopCondition(cancellation_token=token)

        should_stop, reason = condition.should_stop()

        assert should_stop is False
        assert reason == StopReason.NONE

    def test_works_without_cancellation_token(self):
        """Stop condition works when no token provided."""
        condition = AgentStopCondition(cancellation_token=None)

        should_stop, reason = condition.should_stop()

        assert should_stop is False
        assert reason == StopReason.NONE


class TestStopConditionMaxIterations:
    """Test max iterations stop condition."""

    def test_stops_at_max_iterations(self):
        """Stop when max iterations reached."""
        condition = AgentStopCondition(max_iterations=3)

        # Simulate 3 iterations
        for _ in range(3):
            condition.increment_iteration()

        should_stop, reason = condition.should_stop()

        assert should_stop is True
        assert reason == StopReason.MAX_ITERATIONS

    def test_continues_before_max_iterations(self):
        """Continue when under max iterations."""
        condition = AgentStopCondition(max_iterations=3)

        condition.increment_iteration()
        condition.increment_iteration()

        should_stop, reason = condition.should_stop()

        assert should_stop is False
        assert reason == StopReason.NONE

    def test_iteration_counter_tracks_correctly(self):
        """Iteration counter increments properly."""
        condition = AgentStopCondition(max_iterations=10)

        assert condition.current_iteration == 0

        condition.increment_iteration()
        assert condition.current_iteration == 1

        condition.increment_iteration()
        assert condition.current_iteration == 2


class TestStopConditionParseFailures:
    """Test consecutive parse failure stop condition."""

    def test_stops_after_max_parse_failures(self):
        """Stop after consecutive parse failures exceed threshold."""
        condition = AgentStopCondition(max_parse_failures=3)

        condition.record_parse_failure()
        condition.record_parse_failure()
        condition.record_parse_failure()

        should_stop, reason = condition.should_stop()

        assert should_stop is True
        assert reason == StopReason.PARSE_FAILURES

    def test_continues_before_max_parse_failures(self):
        """Continue when parse failures under threshold."""
        condition = AgentStopCondition(max_parse_failures=3)

        condition.record_parse_failure()
        condition.record_parse_failure()

        should_stop, reason = condition.should_stop()

        assert should_stop is False

    def test_clear_parse_failures_resets_counter(self):
        """Successful parse clears the failure counter."""
        condition = AgentStopCondition(max_parse_failures=3)

        condition.record_parse_failure()
        condition.record_parse_failure()
        condition.clear_parse_failures()
        condition.record_parse_failure()

        should_stop, reason = condition.should_stop()

        assert should_stop is False  # Only 1 failure after reset


class TestStopConditionDenials:
    """Test repeated user denial stop condition."""

    def test_stops_after_max_denials(self):
        """Stop after consecutive denials exceed threshold."""
        condition = AgentStopCondition(max_denials=3)

        condition.record_denial()
        condition.record_denial()
        condition.record_denial()

        should_stop, reason = condition.should_stop()

        assert should_stop is True
        assert reason == StopReason.REPEATED_DENIALS

    def test_continues_before_max_denials(self):
        """Continue when denials under threshold."""
        condition = AgentStopCondition(max_denials=3)

        condition.record_denial()
        condition.record_denial()

        should_stop, reason = condition.should_stop()

        assert should_stop is False

    def test_clear_denials_resets_counter(self):
        """Approved action clears the denial counter."""
        condition = AgentStopCondition(max_denials=3)

        condition.record_denial()
        condition.record_denial()
        condition.clear_denials()
        condition.record_denial()

        should_stop, reason = condition.should_stop()

        assert should_stop is False  # Only 1 denial after reset


class TestStopConditionNetworkErrors:
    """Test network error stop condition."""

    def test_stops_after_max_network_errors(self):
        """Stop after consecutive network errors exceed threshold."""
        condition = AgentStopCondition(max_network_errors=3)

        condition.record_network_error()
        condition.record_network_error()
        condition.record_network_error()

        should_stop, reason = condition.should_stop()

        assert should_stop is True
        assert reason == StopReason.NETWORK_ERROR

    def test_clear_network_errors_resets_counter(self):
        """Successful request clears the error counter."""
        condition = AgentStopCondition(max_network_errors=3)

        condition.record_network_error()
        condition.record_network_error()
        condition.clear_network_errors()
        condition.record_network_error()

        should_stop, reason = condition.should_stop()

        assert should_stop is False


class TestStopConditionRateLimited:
    """Test rate limit exhaustion stop condition."""

    def test_stops_when_rate_limited(self):
        """Stop when all models are rate limited."""
        condition = AgentStopCondition()

        condition.mark_rate_limited()

        should_stop, reason = condition.should_stop()

        assert should_stop is True
        assert reason == StopReason.RATE_LIMITED


class TestStopConditionCompletion:
    """Test task completion stop condition."""

    def test_stops_when_completed(self):
        """Stop when task is marked complete."""
        condition = AgentStopCondition()

        condition.mark_completed()

        should_stop, reason = condition.should_stop()

        assert should_stop is True
        assert reason == StopReason.COMPLETED


class TestStopConditionPriority:
    """Test that stop reasons are checked in priority order."""

    def test_user_cancellation_takes_priority(self):
        """User cancellation overrides other stop conditions."""
        token = Mock()
        token.is_cancelled.return_value = True

        condition = AgentStopCondition(
            cancellation_token=token,
            max_iterations=1
        )
        condition.increment_iteration()  # Would trigger MAX_ITERATIONS
        condition.mark_rate_limited()    # Would trigger RATE_LIMITED

        should_stop, reason = condition.should_stop()

        assert reason == StopReason.USER_CANCELLED

    def test_completion_checked_before_rate_limit(self):
        """Completion is checked before rate limit."""
        condition = AgentStopCondition()

        condition.mark_completed()
        condition.mark_rate_limited()

        should_stop, reason = condition.should_stop()

        assert reason == StopReason.COMPLETED


class TestStopConditionReset:
    """Test reset functionality for new tasks."""

    def test_reset_clears_all_counters(self):
        """Reset clears all state for new task."""
        condition = AgentStopCondition(
            max_iterations=10,
            max_parse_failures=3,
            max_denials=3,
        )

        # Accumulate state
        condition.increment_iteration()
        condition.increment_iteration()
        condition.record_parse_failure()
        condition.record_denial()
        condition.mark_rate_limited()

        # Reset
        condition.reset()

        # Verify all cleared
        assert condition.current_iteration == 0

        should_stop, reason = condition.should_stop()
        assert should_stop is False
        assert reason == StopReason.NONE


class TestStopConditionMessages:
    """Test human-readable stop messages."""

    def test_get_stop_message_user_cancelled(self):
        """User cancellation message is clear."""
        condition = AgentStopCondition()

        message = condition.get_stop_message(StopReason.USER_CANCELLED)

        assert "cancelled" in message.lower()

    def test_get_stop_message_rate_limited(self):
        """Rate limit message mentions trying later."""
        condition = AgentStopCondition()

        message = condition.get_stop_message(StopReason.RATE_LIMITED)

        assert "rate limit" in message.lower()

    def test_get_stop_message_max_iterations(self):
        """Max iterations message includes the limit."""
        condition = AgentStopCondition(max_iterations=50)

        message = condition.get_stop_message(StopReason.MAX_ITERATIONS)

        assert "50" in message

    def test_get_stop_message_parse_failures(self):
        """Parse failure message includes count."""
        condition = AgentStopCondition(max_parse_failures=3)

        message = condition.get_stop_message(StopReason.PARSE_FAILURES)

        assert "3" in message
