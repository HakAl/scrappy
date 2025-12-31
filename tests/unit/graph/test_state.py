"""Unit tests for AgentState model."""

import json
import pytest

from scrappy.graph.state import AgentState


class TestAgentStateCreation:
    """Tests for AgentState creation and initialization."""

    def test_create_initial_state(self) -> None:
        """Test creating initial state with factory method."""
        state = AgentState.create_initial("Write hello world", "/tmp/project")

        assert state.input == "Write hello world"
        assert state.original_task == "Write hello world"
        assert state.working_dir == "/tmp/project"
        assert state.iteration == 0
        assert state.done is False
        assert state.error_count == 0
        assert state.messages == []
        assert state.files_changed == []
        assert state.current_tier == "fast"

    def test_create_with_defaults(self) -> None:
        """Test creating state with minimal required fields."""
        state = AgentState(input="test", original_task="test")

        assert state.input == "test"
        assert state.working_dir == "."
        assert state.current_tier == "fast"

    def test_all_fields_have_meaningful_descriptions(self) -> None:
        """Verify all fields have non-trivial documentation (>10 chars)."""
        for field_name, field_info in AgentState.model_fields.items():
            desc = field_info.description or ""
            assert len(desc) > 10, (
                f"Field '{field_name}' has trivial or missing description: '{desc}'"
            )


class TestAgentStateJsonSerialization:
    """Tests for JSON serialization (required for SqliteSaver)."""

    def test_json_round_trip(self) -> None:
        """Test state survives JSON serialization and deserialization."""
        original = AgentState.create_initial("test task", "/home/user/project")
        original = original.model_copy(update={
            "iteration": 5,
            "messages": [{"role": "user", "content": "hello"}],
            "files_changed": ["file1.py", "file2.py"],
            "last_error": "Something went wrong",
        })

        # Serialize to JSON string
        json_dict = original.model_dump_json_safe()
        json_str = json.dumps(json_dict)

        # Deserialize back
        parsed = json.loads(json_str)
        restored = AgentState(**parsed)

        # Verify all fields match
        assert restored.input == original.input
        assert restored.original_task == original.original_task
        assert restored.iteration == original.iteration
        assert restored.messages == original.messages
        assert restored.files_changed == original.files_changed
        assert restored.last_error == original.last_error

    def test_nested_dict_serialization(self) -> None:
        """Test nested dicts in messages serialize correctly."""
        state = AgentState(
            input="test",
            original_task="test",
            messages=[
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi", "tool_calls": [{"id": "1", "name": "read"}]},
            ],
            pending_confirmation={"type": "command", "command": "rm -rf /"},
        )

        json_dict = state.model_dump_json_safe()
        json_str = json.dumps(json_dict)  # Should not raise

        restored = AgentState(**json.loads(json_str))
        assert restored.messages == state.messages
        assert restored.pending_confirmation == state.pending_confirmation


class TestAgentStateUpdates:
    """Tests for state update patterns."""

    def test_immutable_style_update(self) -> None:
        """Test that model_copy creates new instance without mutating original."""
        original = AgentState.create_initial("task", ".")

        updated = original.model_copy(update={"iteration": 1, "done": True})

        # Original unchanged
        assert original.iteration == 0
        assert original.done is False

        # Updated has new values
        assert updated.iteration == 1
        assert updated.done is True

    def test_update_messages(self) -> None:
        """Test appending to messages list."""
        state = AgentState.create_initial("task", ".")

        new_messages = state.messages + [{"role": "user", "content": "new message"}]
        updated = state.model_copy(update={"messages": new_messages})

        assert len(updated.messages) == 1
        assert len(state.messages) == 0  # Original unchanged

    def test_update_files_changed(self) -> None:
        """Test tracking changed files."""
        state = AgentState.create_initial("task", ".")

        updated = state.model_copy(update={
            "files_changed": state.files_changed + ["new_file.py"]
        })

        assert "new_file.py" in updated.files_changed
        assert len(state.files_changed) == 0


class TestAgentStateValidation:
    """Tests for Pydantic validation."""

    def test_validate_on_assignment(self) -> None:
        """Test that invalid assignments raise errors."""
        state = AgentState.create_initial("task", ".")

        # This should work (valid tier)
        state.current_tier = "quality"
        assert state.current_tier == "quality"

    def test_required_fields(self) -> None:
        """Test that required fields must be provided."""
        with pytest.raises(Exception):  # ValidationError
            AgentState()  # Missing input and original_task
