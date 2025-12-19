"""
Tests for HUD Phase 3 (Outcome Trail) and Phase 4 (HUD Injection).

Tests the outcome recording and HUD message generation functionality:
- OutcomeRecord dataclass
- smart_truncate function
- ConversationState.recent_outcomes
- AgentContextFactory.build_hud_message
"""
import pytest
from pathlib import Path

from scrappy.agent.types import (
    OutcomeRecord,
    smart_truncate,
    ConversationState,
)
from scrappy.agent.context_factory import AgentContextFactory
from scrappy.agent_config import AgentConfig
from scrappy.agent_tools.tools import ToolRegistry
from scrappy.agent_tools.tools.base import ToolContext, WorkingSet
from scrappy.protocols.tasks import InMemoryTaskStorage, Task, TaskStatus


class TestSmartTruncate:
    """Tests for smart_truncate function."""

    @pytest.mark.unit
    def test_success_returns_short_message(self):
        """Successful operations should return '(Success)'."""
        output = "Successfully wrote 500 characters to file.py"
        result = smart_truncate(output, success=True)
        assert result == "(Success)"

    @pytest.mark.unit
    def test_failure_short_returns_full_output(self):
        """Short failure outputs should be returned in full."""
        output = "Error: file not found"
        result = smart_truncate(output, success=False)
        assert result == output

    @pytest.mark.unit
    def test_failure_long_returns_tail(self):
        """Long failure outputs should return the tail (stack traces)."""
        # Create a long error with important info at the end
        prefix = "Traceback (most recent call last):\n" + ("  " * 50)
        suffix = "ValueError: invalid input"
        long_output = prefix + suffix

        result = smart_truncate(long_output, success=False, max_length=50)

        assert result.startswith("...")
        assert result.endswith(suffix)
        assert len(result) == 50

    @pytest.mark.unit
    def test_failure_exactly_max_length(self):
        """Output exactly at max_length should not be truncated."""
        output = "x" * 150
        result = smart_truncate(output, success=False, max_length=150)
        assert result == output

    @pytest.mark.unit
    def test_failure_one_over_max_length(self):
        """Output one over max_length should be truncated."""
        output = "x" * 151
        result = smart_truncate(output, success=False, max_length=150)
        assert len(result) == 150
        assert result.startswith("...")


class TestOutcomeRecord:
    """Tests for OutcomeRecord dataclass."""

    @pytest.mark.unit
    def test_outcome_record_creation(self):
        """OutcomeRecord should store all fields correctly."""
        outcome = OutcomeRecord(
            turn=5,
            tool="write_file",
            success=True,
            summary="(Success)",
        )

        assert outcome.turn == 5
        assert outcome.tool == "write_file"
        assert outcome.success is True
        assert outcome.summary == "(Success)"

    @pytest.mark.unit
    def test_outcome_record_failure(self):
        """OutcomeRecord should store failure info."""
        outcome = OutcomeRecord(
            turn=3,
            tool="run_command",
            success=False,
            summary="...AssertionError: expected 200 but got 401",
        )

        assert outcome.success is False
        assert "AssertionError" in outcome.summary


class TestConversationStateOutcomes:
    """Tests for ConversationState.recent_outcomes."""

    @pytest.mark.unit
    def test_recent_outcomes_default_empty(self):
        """recent_outcomes should default to empty list."""
        state = ConversationState()
        assert state.recent_outcomes == []

    @pytest.mark.unit
    def test_can_append_outcomes(self):
        """Should be able to append outcomes to the list."""
        state = ConversationState()

        outcome = OutcomeRecord(turn=1, tool="read_file", success=True, summary="(Success)")
        state.recent_outcomes.append(outcome)

        assert len(state.recent_outcomes) == 1
        assert state.recent_outcomes[0].tool == "read_file"

    @pytest.mark.unit
    def test_outcome_limit_not_automatic(self):
        """ConversationState doesn't auto-limit - that's agent_loop's job."""
        state = ConversationState()

        for i in range(10):
            outcome = OutcomeRecord(turn=i, tool=f"tool{i}", success=True, summary="(Success)")
            state.recent_outcomes.append(outcome)

        # No auto-limit, agent_loop handles trimming
        assert len(state.recent_outcomes) == 10


class TestBuildHudMessage:
    """Tests for AgentContextFactory.build_hud_message."""

    def _create_factory(
        self,
        task_storage=None,
        working_set=None,
    ):
        """Helper to create context factory with tool_context."""
        tool_context = ToolContext(
            project_root=Path("."),
            task_storage=task_storage,
            working_set=working_set,
            turn=5,
        )
        return AgentContextFactory(
            semantic_manager=None,
            config=AgentConfig(),
            tool_registry=ToolRegistry(),
            tool_context=tool_context,
        )

    @pytest.mark.unit
    def test_hud_with_no_state_returns_none(self):
        """Empty HUD (no tasks, no files, no outcomes) returns None."""
        factory = self._create_factory()
        state = ConversationState()

        result = factory.build_hud_message(state)
        assert result is None

    @pytest.mark.unit
    def test_hud_without_tool_context_returns_none(self):
        """HUD without tool_context returns None."""
        factory = AgentContextFactory(
            semantic_manager=None,
            config=AgentConfig(),
            tool_registry=ToolRegistry(),
            tool_context=None,
        )
        state = ConversationState()

        result = factory.build_hud_message(state)
        assert result is None

    @pytest.mark.unit
    def test_hud_with_tasks(self):
        """HUD should include tasks section."""
        storage = InMemoryTaskStorage()
        storage.write_tasks([
            Task(description="Fix the bug", status=TaskStatus.IN_PROGRESS),
            Task(description="Add tests", status=TaskStatus.PENDING),
            Task(description="Update docs", status=TaskStatus.DONE),
        ])

        factory = self._create_factory(task_storage=storage)
        state = ConversationState()

        result = factory.build_hud_message(state)

        assert result is not None
        assert result["role"] == "user"
        content = result["content"]
        assert "=== CURRENT STATE ===" in content
        assert "[TASKS]" in content
        assert "[>] Fix the bug" in content
        assert "[ ] Add tests" in content
        assert "[x] Update docs" in content

    @pytest.mark.unit
    def test_hud_with_working_set(self):
        """HUD should include working set section."""
        ws = WorkingSet()
        ws.record_read("src/main.py", turn=2)
        ws.record_write("src/main.py", turn=3)
        ws.record_read("tests/test_main.py", turn=4, line_start=10, line_end=50)

        factory = self._create_factory(working_set=ws)
        state = ConversationState()

        result = factory.build_hud_message(state)

        assert result is not None
        content = result["content"]
        assert "[WORKING SET]" in content
        assert "src/main.py" in content
        assert "Modified @ Turn 3" in content
        assert "tests/test_main.py" in content
        assert "Read L10-50 @ Turn 4" in content

    @pytest.mark.unit
    def test_hud_with_outcomes(self):
        """HUD should include recent outcomes section."""
        factory = self._create_factory()
        state = ConversationState()
        state.recent_outcomes = [
            OutcomeRecord(turn=1, tool="read_file", success=True, summary="(Success)"),
            OutcomeRecord(turn=2, tool="run_command", success=False, summary="...exit code 1"),
            OutcomeRecord(turn=3, tool="write_file", success=True, summary="(Success)"),
        ]

        result = factory.build_hud_message(state)

        assert result is not None
        content = result["content"]
        assert "[RECENT OUTCOMES]" in content
        assert "Turn 1: read_file - Success" in content
        assert "Turn 2: run_command - Failed: ...exit code 1" in content
        assert "Turn 3: write_file - Success" in content

    @pytest.mark.unit
    def test_hud_outcomes_most_recent_first(self):
        """Outcomes should be displayed most recent first."""
        factory = self._create_factory()
        state = ConversationState()
        state.recent_outcomes = [
            OutcomeRecord(turn=1, tool="first", success=True, summary="(Success)"),
            OutcomeRecord(turn=2, tool="second", success=True, summary="(Success)"),
            OutcomeRecord(turn=3, tool="third", success=True, summary="(Success)"),
        ]

        result = factory.build_hud_message(state)
        content = result["content"]

        # Find positions in the content
        first_pos = content.find("Turn 1: first")
        second_pos = content.find("Turn 2: second")
        third_pos = content.find("Turn 3: third")

        # Most recent (third) should appear first in the output
        assert third_pos < second_pos < first_pos

    @pytest.mark.unit
    def test_hud_full_example(self):
        """Full HUD with all sections."""
        storage = InMemoryTaskStorage(initial_task="Fix login bug")
        ws = WorkingSet()
        ws.record_read("src/auth.py", turn=1)
        ws.record_write("src/auth.py", turn=2)

        factory = self._create_factory(task_storage=storage, working_set=ws)
        state = ConversationState()
        state.recent_outcomes = [
            OutcomeRecord(turn=1, tool="read_file", success=True, summary="(Success)"),
            OutcomeRecord(turn=2, tool="write_file", success=True, summary="(Success)"),
        ]

        result = factory.build_hud_message(state)

        assert result is not None
        content = result["content"]

        # All sections present
        assert "=== CURRENT STATE ===" in content
        assert "[TASKS]" in content
        assert "[>] Fix login bug" in content
        assert "[WORKING SET]" in content
        assert "src/auth.py" in content
        assert "[RECENT OUTCOMES]" in content
        assert "read_file - Success" in content

    @pytest.mark.unit
    def test_hud_working_set_read_only(self):
        """Working set entry with only read should show read info."""
        ws = WorkingSet()
        ws.record_read("file.py", turn=5)

        factory = self._create_factory(working_set=ws)
        state = ConversationState()

        result = factory.build_hud_message(state)
        content = result["content"]

        assert "file.py (Read full @ Turn 5)" in content

    @pytest.mark.unit
    def test_hud_working_set_write_only(self):
        """Working set entry with only write should show modified info."""
        ws = WorkingSet()
        ws.record_write("new_file.py", turn=3)

        factory = self._create_factory(working_set=ws)
        state = ConversationState()

        result = factory.build_hud_message(state)
        content = result["content"]

        assert "new_file.py (Modified @ Turn 3)" in content


class TestHudIntegration:
    """Integration tests for HUD in conversation flow."""

    @pytest.mark.unit
    def test_outcomes_trimmed_to_three(self):
        """Outcomes should be trimmed to 3 (simulating agent_loop behavior)."""
        state = ConversationState()

        # Simulate agent_loop adding outcomes and trimming
        for i in range(5):
            outcome = OutcomeRecord(turn=i+1, tool=f"tool{i}", success=True, summary="(Success)")
            state.recent_outcomes.append(outcome)
            # Simulate agent_loop trimming
            if len(state.recent_outcomes) > 3:
                state.recent_outcomes = state.recent_outcomes[-3:]

        assert len(state.recent_outcomes) == 3
        # Should have most recent 3 (turns 3, 4, 5)
        assert state.recent_outcomes[0].turn == 3
        assert state.recent_outcomes[1].turn == 4
        assert state.recent_outcomes[2].turn == 5
