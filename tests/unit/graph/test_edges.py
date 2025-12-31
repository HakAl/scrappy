"""Unit tests for edge routing logic."""

from scrappy.graph.edges import (
    MAX_ITERATIONS,
    MAX_RETRIES,
    should_continue,
)
from scrappy.graph.state import AgentState


class TestShouldContinueTerminalConditions:
    """Tests for terminal routing conditions."""

    def test_done_routes_to_end(self) -> None:
        """When done=True, should route to end."""
        state = AgentState(
            input="test",
            original_task="test",
            done=True,
        )
        assert should_continue(state) == "end"

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
        assert should_continue(state) == "end"


class TestShouldContinueSafetyLimits:
    """Tests for iteration and retry limits."""

    def test_max_iterations_boundary_continues(self) -> None:
        """At MAX_ITERATIONS - 1, should continue (not end)."""
        state = AgentState(
            input="test",
            original_task="test",
            iteration=MAX_ITERATIONS - 1,
        )
        assert should_continue(state) == "think"

    def test_max_iterations_exact_ends(self) -> None:
        """At exactly MAX_ITERATIONS, should end."""
        state = AgentState(
            input="test",
            original_task="test",
            iteration=MAX_ITERATIONS,
        )
        assert should_continue(state) == "end"

    def test_max_iterations_exceeded_ends(self) -> None:
        """Above MAX_ITERATIONS, should end."""
        state = AgentState(
            input="test",
            original_task="test",
            iteration=MAX_ITERATIONS + 1,
        )
        assert should_continue(state) == "end"

    def test_max_retries_boundary_continues(self) -> None:
        """At MAX_RETRIES - 1, should continue."""
        state = AgentState(
            input="test",
            original_task="test",
            error_count=MAX_RETRIES - 1,
        )
        assert should_continue(state) == "think"

    def test_max_retries_exact_ends(self) -> None:
        """At exactly MAX_RETRIES, should end."""
        state = AgentState(
            input="test",
            original_task="test",
            error_count=MAX_RETRIES,
        )
        assert should_continue(state) == "end"

    def test_max_retries_exceeded_ends(self) -> None:
        """Above MAX_RETRIES, should end."""
        state = AgentState(
            input="test",
            original_task="test",
            error_count=MAX_RETRIES + 1,
        )
        assert should_continue(state) == "end"


class TestShouldContinueHumanInTheLoop:
    """Tests for human confirmation routing."""

    def test_pending_confirmation_routes_to_confirm(self) -> None:
        """When pending_confirmation is set, should route to confirm."""
        state = AgentState(
            input="test",
            original_task="test",
            pending_confirmation={"type": "command", "command": "rm -rf /"},
        )
        assert should_continue(state) == "confirm"

    def test_no_pending_confirmation_does_not_route_to_confirm(self) -> None:
        """When pending_confirmation is None, should not route to confirm."""
        state = AgentState(
            input="test",
            original_task="test",
            pending_confirmation=None,
        )
        assert should_continue(state) != "confirm"


class TestShouldContinueErrorRecovery:
    """Tests for error recovery routing."""

    def test_last_error_routes_to_error(self) -> None:
        """When last_error is set, should route to error node."""
        state = AgentState(
            input="test",
            original_task="test",
            last_error="Something went wrong",
        )
        assert should_continue(state) == "error"

    def test_no_last_error_does_not_route_to_error(self) -> None:
        """When last_error is None, should not route to error."""
        state = AgentState(
            input="test",
            original_task="test",
            last_error=None,
        )
        assert should_continue(state) != "error"


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
        assert should_continue(state) == "verify"

    def test_verified_files_does_not_route_to_verify(self) -> None:
        """When files changed but already verified, should not route to verify."""
        state = AgentState(
            input="test",
            original_task="test",
            files_changed=["file.py"],
            files_verified=True,
        )
        assert should_continue(state) == "think"

    def test_no_files_changed_does_not_route_to_verify(self) -> None:
        """When no files changed, should not route to verify."""
        state = AgentState(
            input="test",
            original_task="test",
            files_changed=[],
            files_verified=False,
        )
        assert should_continue(state) == "think"


class TestShouldContinueDefaultCase:
    """Tests for default routing behavior."""

    def test_default_routes_to_think(self) -> None:
        """When no special conditions, should route to think."""
        state = AgentState(
            input="test",
            original_task="test",
        )
        assert should_continue(state) == "think"

    def test_fresh_state_routes_to_think(self) -> None:
        """A freshly created state should route to think."""
        state = AgentState.create_initial("test task", "/tmp")
        assert should_continue(state) == "think"


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
        assert should_continue(state) == "end"

    def test_iteration_limit_beats_pending_confirmation(self) -> None:
        """Iteration limit takes priority over pending confirmation."""
        state = AgentState(
            input="test",
            original_task="test",
            iteration=MAX_ITERATIONS,
            pending_confirmation={"type": "command"},
        )
        assert should_continue(state) == "end"

    def test_error_limit_beats_pending_confirmation(self) -> None:
        """Error limit takes priority over pending confirmation."""
        state = AgentState(
            input="test",
            original_task="test",
            error_count=MAX_RETRIES,
            pending_confirmation={"type": "command"},
        )
        assert should_continue(state) == "end"

    def test_pending_confirmation_beats_last_error(self) -> None:
        """Pending confirmation takes priority over error recovery."""
        state = AgentState(
            input="test",
            original_task="test",
            pending_confirmation={"type": "command"},
            last_error="Some error",
        )
        assert should_continue(state) == "confirm"

    def test_last_error_beats_verification(self) -> None:
        """Error recovery takes priority over verification."""
        state = AgentState(
            input="test",
            original_task="test",
            last_error="Some error",
            files_changed=["file.py"],
            files_verified=False,
        )
        assert should_continue(state) == "error"


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
