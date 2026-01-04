"""Unit tests for edge routing logic."""

from scrappy.graph.edges import (
    MAX_ITERATIONS,
    MAX_RETRIES,
    Route,
    route_after_think,
    should_continue,
)
from scrappy.graph.state import AgentState


class TestRouteAfterThink:
    """Tests for the route_after_think conditional edge function."""

    def test_normal_flow_routes_to_execute(self) -> None:
        """Normal state (no error, not done) should route to execute."""
        state = AgentState(
            input="test",
            original_task="test",
        )
        assert route_after_think(state) == Route.EXECUTE

    def test_last_error_routes_to_error(self) -> None:
        """When last_error is set, should route to error (bypass execute)."""
        state = AgentState(
            input="test",
            original_task="test",
            last_error="LLM API failed",
        )
        assert route_after_think(state) == Route.ERROR

    def test_done_routes_to_end(self) -> None:
        """When done=True, should route to end (bypass execute)."""
        state = AgentState(
            input="test",
            original_task="test",
            done=True,
        )
        assert route_after_think(state) == Route.END

    def test_done_takes_priority_over_error(self) -> None:
        """When both error and done are set, done takes priority (stops immediately)."""
        state = AgentState(
            input="test",
            original_task="test",
            last_error="Some error",
            done=True,
        )
        # done check happens first - fatal errors (NotConfiguredError) set both
        # and should stop immediately, not go to error recovery
        assert route_after_think(state) == Route.END

    def test_empty_error_still_routes_to_error(self) -> None:
        """Empty string error still routes to error (is not None check)."""
        state = AgentState(
            input="test",
            original_task="test",
            last_error="",
        )
        assert route_after_think(state) == Route.ERROR

    def test_none_error_routes_to_execute(self) -> None:
        """None error should route to execute."""
        state = AgentState(
            input="test",
            original_task="test",
            last_error=None,
        )
        assert route_after_think(state) == Route.EXECUTE

    def test_fresh_state_routes_to_execute(self) -> None:
        """A freshly created state should route to execute."""
        state = AgentState.create_initial("test task", "/tmp")
        assert route_after_think(state) == Route.EXECUTE


class TestShouldContinueTerminalConditions:
    """Tests for terminal routing conditions."""

    def test_done_routes_to_end(self) -> None:
        """When done=True, should route to end."""
        state = AgentState(
            input="test",
            original_task="test",
            done=True,
        )
        assert should_continue(state) == Route.END

    def test_done_takes_priority_over_other_conditions(self) -> None:
        """done=True should short-circuit all other checks."""
        state = AgentState(
            input="test",
            original_task="test",
            done=True,
            pending_confirmation={"type": "command"},
            last_error="Some error",
            files_changed=["file.py"],
            files_verified=False,
        )
        assert should_continue(state) == Route.END


class TestShouldContinueSafetyLimits:
    """Tests for iteration and retry limits."""

    def test_max_iterations_boundary_continues(self) -> None:
        """At MAX_ITERATIONS - 1, should continue (not end)."""
        state = AgentState(
            input="test",
            original_task="test",
            iteration=MAX_ITERATIONS - 1,
        )
        assert should_continue(state) == Route.THINK

    def test_max_iterations_exact_ends(self) -> None:
        """At exactly MAX_ITERATIONS, should end."""
        state = AgentState(
            input="test",
            original_task="test",
            iteration=MAX_ITERATIONS,
        )
        assert should_continue(state) == Route.END

    def test_max_iterations_exceeded_ends(self) -> None:
        """Above MAX_ITERATIONS, should end."""
        state = AgentState(
            input="test",
            original_task="test",
            iteration=MAX_ITERATIONS + 1,
        )
        assert should_continue(state) == Route.END

    def test_max_retries_boundary_continues(self) -> None:
        """At MAX_RETRIES - 1, should continue."""
        state = AgentState(
            input="test",
            original_task="test",
            error_count=MAX_RETRIES - 1,
        )
        assert should_continue(state) == Route.THINK

    def test_max_retries_exact_ends(self) -> None:
        """At exactly MAX_RETRIES, should end."""
        state = AgentState(
            input="test",
            original_task="test",
            error_count=MAX_RETRIES,
        )
        assert should_continue(state) == Route.END

    def test_max_retries_exceeded_ends(self) -> None:
        """Above MAX_RETRIES, should end."""
        state = AgentState(
            input="test",
            original_task="test",
            error_count=MAX_RETRIES + 1,
        )
        assert should_continue(state) == Route.END


class TestShouldContinueHumanInTheLoop:
    """Tests for human confirmation routing."""

    def test_pending_confirmation_routes_to_confirm(self) -> None:
        """When pending_confirmation is set, should route to confirm."""
        state = AgentState(
            input="test",
            original_task="test",
            pending_confirmation={"type": "command", "command": "rm -rf /"},
        )
        assert should_continue(state) == Route.CONFIRM

    def test_no_pending_confirmation_does_not_route_to_confirm(self) -> None:
        """When pending_confirmation is None, should not route to confirm."""
        state = AgentState(
            input="test",
            original_task="test",
            pending_confirmation=None,
        )
        assert should_continue(state) != Route.CONFIRM


class TestShouldContinueErrorRecovery:
    """Tests for error recovery routing."""

    def test_last_error_routes_to_error(self) -> None:
        """When last_error is set, should route to error node."""
        state = AgentState(
            input="test",
            original_task="test",
            last_error="Something went wrong",
        )
        assert should_continue(state) == Route.ERROR

    def test_no_last_error_does_not_route_to_error(self) -> None:
        """When last_error is None, should not route to error."""
        state = AgentState(
            input="test",
            original_task="test",
            last_error=None,
        )
        assert should_continue(state) != Route.ERROR


class TestShouldContinueVerification:
    """Tests for file verification routing."""

    def test_unverified_files_routes_to_verify(self) -> None:
        """When files changed but not verified, should route to verify."""
        state = AgentState(
            input="test",
            original_task="test",
            files_changed=["file.py"],
            files_verified=False,
        )
        assert should_continue(state) == Route.VERIFY

    def test_verified_files_does_not_route_to_verify(self) -> None:
        """When files changed but already verified, should not route to verify."""
        state = AgentState(
            input="test",
            original_task="test",
            files_changed=["file.py"],
            files_verified=True,
        )
        assert should_continue(state) == Route.THINK

    def test_no_files_changed_does_not_route_to_verify(self) -> None:
        """When no files changed, should not route to verify."""
        state = AgentState(
            input="test",
            original_task="test",
            files_changed=[],
            files_verified=False,
        )
        assert should_continue(state) == Route.THINK


class TestShouldContinueDefaultCase:
    """Tests for default routing behavior."""

    def test_default_routes_to_think(self) -> None:
        """When no special conditions, should route to think."""
        state = AgentState(
            input="test",
            original_task="test",
        )
        assert should_continue(state) == Route.THINK

    def test_fresh_state_routes_to_think(self) -> None:
        """A freshly created state should route to think."""
        state = AgentState.create_initial("test task", "/tmp")
        assert should_continue(state) == Route.THINK


class TestShouldContinuePriorityOrder:
    """Tests that routing checks happen in the correct priority order."""

    def test_done_beats_iteration_limit(self) -> None:
        """done=True takes priority over iteration limit."""
        state = AgentState(
            input="test",
            original_task="test",
            done=True,
            iteration=MAX_ITERATIONS + 100,
        )
        assert should_continue(state) == Route.END

    def test_iteration_limit_beats_pending_confirmation(self) -> None:
        """Iteration limit takes priority over pending confirmation."""
        state = AgentState(
            input="test",
            original_task="test",
            iteration=MAX_ITERATIONS,
            pending_confirmation={"type": "command"},
        )
        assert should_continue(state) == Route.END

    def test_error_limit_beats_pending_confirmation(self) -> None:
        """Error limit takes priority over pending confirmation."""
        state = AgentState(
            input="test",
            original_task="test",
            error_count=MAX_RETRIES,
            pending_confirmation={"type": "command"},
        )
        assert should_continue(state) == Route.END

    def test_pending_confirmation_beats_last_error(self) -> None:
        """Pending confirmation takes priority over error recovery."""
        state = AgentState(
            input="test",
            original_task="test",
            pending_confirmation={"type": "command"},
            last_error="Some error",
        )
        assert should_continue(state) == Route.CONFIRM

    def test_last_error_beats_verification(self) -> None:
        """Error recovery takes priority over verification."""
        state = AgentState(
            input="test",
            original_task="test",
            last_error="Some error",
            files_changed=["file.py"],
            files_verified=False,
        )
        assert should_continue(state) == Route.ERROR


class TestModuleLevelConstants:
    """Tests that module-level constants are accessible and sensible."""

    def test_max_iterations_is_positive(self) -> None:
        """MAX_ITERATIONS should be a positive integer."""
        assert MAX_ITERATIONS > 0
        assert isinstance(MAX_ITERATIONS, int)

    def test_max_retries_is_positive(self) -> None:
        """MAX_RETRIES should be a positive integer."""
        assert MAX_RETRIES > 0
        assert isinstance(MAX_RETRIES, int)

    def test_max_iterations_is_reasonable(self) -> None:
        """MAX_ITERATIONS should be in a reasonable range."""
        assert 10 <= MAX_ITERATIONS <= 1000

    def test_max_retries_is_reasonable(self) -> None:
        """MAX_RETRIES should be in a reasonable range."""
        assert 1 <= MAX_RETRIES <= 10


class TestEdgeCasesNegativeValues:
    """Tests for edge cases with negative or unusual values."""

    def test_negative_iteration_continues_to_think(self) -> None:
        """Negative iteration values should continue (not hit limit)."""
        state = AgentState(
            input="test",
            original_task="test",
            iteration=-1,
        )
        assert should_continue(state) == Route.THINK

    def test_negative_error_count_continues_to_think(self) -> None:
        """Negative error_count values should continue (not hit limit)."""
        state = AgentState(
            input="test",
            original_task="test",
            error_count=-1,
        )
        assert should_continue(state) == Route.THINK

    def test_zero_iteration_continues(self) -> None:
        """Zero iteration should continue to think."""
        state = AgentState(
            input="test",
            original_task="test",
            iteration=0,
        )
        assert should_continue(state) == Route.THINK

    def test_zero_error_count_continues(self) -> None:
        """Zero error_count should continue to think."""
        state = AgentState(
            input="test",
            original_task="test",
            error_count=0,
        )
        assert should_continue(state) == Route.THINK

    def test_empty_string_last_error_routes_to_error(self) -> None:
        """Empty string last_error routes to error (is not None check)."""
        state = AgentState(
            input="test",
            original_task="test",
            last_error="",
        )
        # The check is `is not None`, so empty string DOES route to error
        # This documents current behavior - may want to change to truthiness check
        assert should_continue(state) == Route.ERROR

    def test_whitespace_only_last_error_routes_to_error(self) -> None:
        """Whitespace-only last_error routes to error."""
        state = AgentState(
            input="test",
            original_task="test",
            last_error="   ",
        )
        assert should_continue(state) == Route.ERROR

    def test_none_last_error_does_not_route_to_error(self) -> None:
        """None last_error does not route to error."""
        state = AgentState(
            input="test",
            original_task="test",
            last_error=None,
        )
        assert should_continue(state) == Route.THINK

    def test_empty_files_changed_list_does_not_verify(self) -> None:
        """Empty files_changed list should not route to verify."""
        state = AgentState(
            input="test",
            original_task="test",
            files_changed=[],
            files_verified=False,
        )
        assert should_continue(state) == Route.THINK

    def test_none_pending_confirmation_does_not_route_to_confirm(self) -> None:
        """None pending_confirmation does not route to confirm."""
        state = AgentState(
            input="test",
            original_task="test",
            pending_confirmation=None,
        )
        assert should_continue(state) == Route.THINK
